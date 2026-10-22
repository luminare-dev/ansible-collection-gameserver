#!/usr/bin/env python3
"""Check the gameserver-observability files vendored into the gameserver_observability role.

The role installs files of the gameserver-observability pack (exporter modules, rules,
dashboard), copied into roles/gameserver_observability/files/pack/ from one pack version.
files/pack/manifest.json records that version, the pack commit they were copied from and the
sha256 of every vendored file. Python 3 standard library only.

Two checks:

1. Manifest (always, offline): every file listed in the manifest exists with the recorded
   sha256, and the folder holds no other file (besides manifest.json and README.md).
2. Release (when a pack release is configured): every vendored file is byte for byte the file of
   the same path in the pack's release archive <archive_name>-<version>.tar.gz, whose top folder
   is <archive_name>-<version>/ (a `git archive` of the release tag). The archive comes from
   --tarball, or, when the manifest's release_tag is set (or --tag is given), it is downloaded
   from the pack's GitHub release together with SHA256SUMS and checked against it, and against
   the manifest's release_sha256 when that is set. Without a tarball and a tag the release check
   is skipped, which the output says.

Usage:
    python3 scripts/check_vendored_pack.py                  manifest check, release check if configured
    python3 scripts/check_vendored_pack.py --tarball gameserver-observability-0.1.0.tar.gz
    python3 scripts/check_vendored_pack.py --tag v0.1.0     download that release and compare
    python3 scripts/check_vendored_pack.py --offline        manifest check only, never download
    python3 scripts/check_vendored_pack.py --update-from gameserver-observability-0.2.0.tar.gz
        copy the listed files from a release archive, set version and hashes in the manifest
        (then set commit, release_tag and release_sha256 by hand and run the check again)

Exit codes: 0 ok (or release check skipped), 1 a file differs or is missing, 2 bad manifest,
arguments, archive or download.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = ROOT / "roles" / "gameserver_observability" / "files" / "pack"
MANIFEST = "manifest.json"
NOT_VENDORED = {MANIFEST, "README.md"}
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DOWNLOAD_TIMEOUT = 60


class CheckError(Exception):
    """The manifest, the arguments, the archive or a download cannot be used (exit code 2)."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(pack_dir: Path) -> dict:
    try:
        manifest = json.loads((pack_dir / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CheckError(f"cannot read {pack_dir / MANIFEST}: {exc}") from exc
    errors = []
    if not REPO_RE.match(str(manifest.get("repository", ""))):
        errors.append("repository must be https://github.com/<owner>/<repo>")
    if not re.match(r"^[a-z0-9][a-z0-9._-]*$", str(manifest.get("archive_name", ""))):
        errors.append("archive_name must be the release archive's name (lower-case)")
    if not VERSION_RE.match(str(manifest.get("version", ""))):
        errors.append("version must be X.Y.Z")
    if not COMMIT_RE.match(str(manifest.get("commit", ""))):
        errors.append("commit must be a 40-character commit id")
    tag = manifest.get("release_tag", "")
    if tag not in ("", f"v{manifest.get('version')}"):
        errors.append(f"release_tag must be empty or v{manifest.get('version')}")
    if manifest.get("release_sha256", "") and not SHA256_RE.match(manifest["release_sha256"]):
        errors.append("release_sha256 must be empty or 64 lower-case hex digits")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        errors.append("files must map vendored paths to their sha256")
    else:
        for path, digest in files.items():
            if path.startswith("/") or ".." in Path(path).parts or path in NOT_VENDORED:
                errors.append(f"files: {path!r} is not a relative path inside the pack folder")
            if not SHA256_RE.match(str(digest)):
                errors.append(f"files: {path}: the sha256 must be 64 lower-case hex digits")
    if errors:
        raise CheckError("manifest.json: " + "; ".join(errors))
    return manifest


def check_manifest(pack_dir: Path, manifest: dict) -> list[str]:
    """Findings of the offline check: missing, changed and unlisted files."""
    findings = []
    for path, digest in sorted(manifest["files"].items()):
        target = pack_dir / path
        if not target.is_file():
            findings.append(f"{path}: listed in the manifest but missing")
        elif sha256_bytes(target.read_bytes()) != digest:
            findings.append(f"{path}: differs from the sha256 in the manifest")
    present = {p.relative_to(pack_dir).as_posix() for p in pack_dir.rglob("*") if p.is_file()}
    for path in sorted(present - set(manifest["files"]) - NOT_VENDORED):
        findings.append(f"{path}: in the pack folder but not listed in the manifest")
    return findings


def archive_members(data: bytes, top: str) -> tuple[dict[str, bytes], str]:
    """Regular files below top/ of a .tar.gz, by path relative to top, and git's commit id."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            commit = tar.pax_headers.get("comment", "")
            members = {}
            for info in tar.getmembers():
                if info.isfile() and info.name.startswith(top + "/"):
                    fh = tar.extractfile(info)
                    if fh is not None:
                        members[info.name[len(top) + 1:]] = fh.read()
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise CheckError(f"cannot read the release archive: {exc}") from exc
    if not members:
        raise CheckError(f"the release archive has no folder {top}/ (is it the archive of this version?)")
    return members, commit


def compare_with_archive(pack_dir: Path, manifest: dict, data: bytes) -> list[str]:
    top = f"{manifest['archive_name']}-{manifest['version']}"
    members, commit = archive_members(data, top)
    print(f"check_vendored_pack: release archive {top}.tar.gz, sha256 {sha256_bytes(data)}"
          + (f", commit {commit}" if commit else ""))
    findings = []
    for path in sorted(manifest["files"]):
        if path not in members:
            findings.append(f"{path}: not in the release archive")
        elif (pack_dir / path).is_file() and (pack_dir / path).read_bytes() != members[path]:
            findings.append(f"{path}: differs from the release archive")
    return findings


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "check_vendored_pack"})
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:  # noqa: S310 (https only)
            return response.read()
    except OSError as exc:
        raise CheckError(f"cannot download {url}: {exc}") from exc


def download_release(manifest: dict, tag: str, get: Callable[[str], bytes] = fetch) -> bytes:
    """The release archive of tag, checked against the release's SHA256SUMS and release_sha256."""
    name = f"{manifest['archive_name']}-{manifest['version']}.tar.gz"
    base = f"{manifest['repository']}/releases/download/{tag}"
    sums = get(f"{base}/SHA256SUMS").decode("utf-8", "replace")
    listed = {parts[1].lstrip("*"): parts[0] for parts in (line.split() for line in sums.splitlines())
              if len(parts) == 2}
    if not SHA256_RE.match(listed.get(name, "")):
        raise CheckError(f"SHA256SUMS of {tag} has no line for {name}")
    data = get(f"{base}/{name}")
    digest = sha256_bytes(data)
    if digest != listed[name]:
        raise CheckError(f"{name}: sha256 {digest} differs from the release's SHA256SUMS ({listed[name]})")
    if manifest.get("release_sha256") and digest != manifest["release_sha256"]:
        raise CheckError(f"{name}: sha256 {digest} differs from release_sha256 in the manifest")
    return data


def update_from(pack_dir: Path, manifest: dict, data: bytes, archive_name: str) -> dict:
    """Copy the listed files from a release archive and return the manifest with new hashes."""
    top = archive_name.removesuffix(".tar.gz")
    version = top.removeprefix(f"{manifest['archive_name']}-")
    if not VERSION_RE.match(version):
        raise CheckError(f"{archive_name}: expected {manifest['archive_name']}-X.Y.Z.tar.gz")
    members, _ = archive_members(data, top)
    missing = sorted(set(manifest["files"]) - set(members))
    if missing:
        raise CheckError(f"not in {archive_name}: {', '.join(missing)}")
    for path in manifest["files"]:
        (pack_dir / path).parent.mkdir(parents=True, exist_ok=True)
        (pack_dir / path).write_bytes(members[path])
    return {**manifest, "version": version, "release_tag": "", "release_sha256": "",
            "files": {path: sha256_bytes(members[path]) for path in sorted(manifest["files"])}}


def main(argv: list[str] | None = None, get: Callable[[str], bytes] = fetch) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--pack-dir", type=Path, default=PACK_DIR, help="vendored pack folder (default: the role's)")
    p.add_argument("--tarball", type=Path, help="compare with this release archive instead of downloading")
    p.add_argument("--tag", help="pack release tag to download and compare (default: manifest release_tag)")
    p.add_argument("--offline", action="store_true", help="manifest check only, never download")
    p.add_argument("--update-from", type=Path, metavar="TARBALL",
                   help="copy the listed files from this release archive and update the manifest")
    args = p.parse_args(argv)

    try:
        manifest = load_manifest(args.pack_dir)
        if args.update_from:
            updated = update_from(args.pack_dir, manifest, args.update_from.read_bytes(), args.update_from.name)
            (args.pack_dir / MANIFEST).write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
            print(f"check_vendored_pack: copied {len(updated['files'])} files of version {updated['version']}; "
                  "set commit, release_tag and release_sha256 in manifest.json")
            return 0
        findings = check_manifest(args.pack_dir, manifest)
        tag = args.tag if args.tag is not None else manifest.get("release_tag", "")
        if args.tag and args.tag != f"v{manifest['version']}":
            raise CheckError(f"--tag {args.tag} does not match the vendored version {manifest['version']}")
        if args.tarball:
            findings += compare_with_archive(args.pack_dir, manifest, args.tarball.read_bytes())
            release = f"compared with {args.tarball.name}"
        elif tag and not args.offline:
            findings += compare_with_archive(args.pack_dir, manifest, download_release(manifest, tag, get))
            release = f"compared with the release {tag}"
        else:
            release = ("release check skipped (--offline)" if args.offline and tag
                       else "release check skipped: no pack release configured (release_tag is empty)")
    except (CheckError, OSError) as exc:
        print(f"check_vendored_pack: error: {exc}", file=sys.stderr)
        return 2

    for line in findings:
        print(f"check_vendored_pack: {line}")
    print(f"check_vendored_pack: {len(findings)} finding(s) in {len(manifest['files'])} vendored file(s) of "
          f"gameserver-observability {manifest['version']} (commit {manifest['commit'][:12]}); {release}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
