"""Tests for scripts/check_vendored_pack.py (the gameserver-observability files in the role).

The script checks roles/gameserver_observability/files/pack/ against its manifest.json and, when a
pack release is configured, against that release's source archive. These tests use temporary pack
folders and archives, and a fake download function instead of the network.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_vendored_pack as cvp  # noqa: E402

FILES = {
    "rules/a.yml": b"groups: []\n",
    "json_exporter/config.yml": b"modules: {}\n",
}
COMMIT = "0123456789abcdef0123456789abcdef01234567"
REPOSITORY = "https://github.com/luminare-dev/gameserver-observability"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_pack(pack_files: dict[str, bytes] = FILES, **manifest_overrides: object) -> Path:
    """A pack folder with the files and a matching manifest.json (fields replaced by the overrides)."""
    pack = Path(tempfile.mkdtemp(prefix="pack-test-"))
    unittest.addModuleCleanup(shutil.rmtree, pack, ignore_errors=True)
    for path, data in pack_files.items():
        (pack / path).parent.mkdir(parents=True, exist_ok=True)
        (pack / path).write_bytes(data)
    manifest = {
        "repository": REPOSITORY,
        "archive_name": "gameserver-observability",
        "version": "0.1.0",
        "commit": COMMIT,
        "release_tag": "",
        "release_sha256": "",
        "files": {path: sha(data) for path, data in pack_files.items()},
    }
    manifest.update(manifest_overrides)
    (pack / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return pack


def make_archive(files: dict[str, bytes], top: str = "gameserver-observability-0.1.0") -> bytes:
    """A .tar.gz like the pack's release archive (git archive with a top folder)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT,
                      pax_headers={"comment": COMMIT}) as tar:
        for path, data in {**files, "README.md": b"# pack\n"}.items():
            info = tarfile.TarInfo(f"{top}/{path}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def run(*args: str, get=None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cvp.main(list(args), get=get) if get else cvp.main(list(args))
    return code, out.getvalue(), err.getvalue()


def fake_get(responses: dict[str, bytes]):
    requested: list[str] = []

    def get(url: str) -> bytes:
        requested.append(url)
        if url not in responses:
            raise cvp.CheckError(f"cannot download {url}: 404")
        return responses[url]

    get.requested = requested  # type: ignore[attr-defined]
    return get


class ManifestCheckTest(unittest.TestCase):
    def test_matching_files_pass_and_the_release_check_is_skipped(self):
        code, out, _ = run("--pack-dir", str(make_pack()))
        self.assertEqual(code, 0)
        self.assertIn("0 finding(s) in 2 vendored file(s) of gameserver-observability 0.1.0", out)
        self.assertIn("release check skipped: no pack release configured", out)

    def test_a_changed_file_fails(self):
        pack = make_pack()
        (pack / "rules" / "a.yml").write_bytes(b"groups: [changed]\n")
        code, out, _ = run("--pack-dir", str(pack))
        self.assertEqual(code, 1)
        self.assertIn("rules/a.yml: differs from the sha256 in the manifest", out)

    def test_a_missing_file_fails(self):
        pack = make_pack()
        (pack / "rules" / "a.yml").unlink()
        code, out, _ = run("--pack-dir", str(pack))
        self.assertEqual(code, 1)
        self.assertIn("rules/a.yml: listed in the manifest but missing", out)

    def test_an_unlisted_file_fails(self):
        pack = make_pack()
        (pack / "rules" / "extra.yml").write_bytes(b"groups: []\n")
        code, out, _ = run("--pack-dir", str(pack))
        self.assertEqual(code, 1)
        self.assertIn("rules/extra.yml: in the pack folder but not listed in the manifest", out)

    def test_a_bad_manifest_is_a_usage_error(self):
        for overrides in ({"version": "1.0"}, {"commit": "abc"}, {"release_tag": "v9.9.9"},
                          {"files": {"../outside.yml": sha(b"")}}, {"release_sha256": "xyz"}):
            with self.subTest(overrides=overrides):
                code, _, err = run("--pack-dir", str(make_pack(**overrides)))
                self.assertEqual(code, 2)
                self.assertIn("manifest.json:", err)

    def test_a_tag_of_another_version_is_refused(self):
        code, _, err = run("--pack-dir", str(make_pack()), "--tag", "v0.2.0")
        self.assertEqual(code, 2)
        self.assertIn("does not match the vendored version 0.1.0", err)


class ReleaseCheckTest(unittest.TestCase):
    def test_a_tarball_is_compared_file_by_file(self):
        pack = make_pack()
        other = Path(tempfile.mkdtemp(prefix="pack-archive-"))
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        good, bad = other / "good.tar.gz", other / "bad.tar.gz"
        good.write_bytes(make_archive(FILES))
        bad.write_bytes(make_archive({"rules/a.yml": b"groups: [other]\n"}))
        code, out, _ = run("--pack-dir", str(pack), "--tarball", str(good))
        self.assertEqual(code, 0, out)
        self.assertIn("compared with good.tar.gz", out)
        self.assertIn(f"commit {COMMIT}", out)
        code, out, _ = run("--pack-dir", str(pack), "--tarball", str(bad))
        self.assertEqual(code, 1)
        self.assertIn("rules/a.yml: differs from the release archive", out)
        self.assertIn("json_exporter/config.yml: not in the release archive", out)

    def test_an_archive_of_another_version_is_a_usage_error(self):
        other = Path(tempfile.mkdtemp(prefix="pack-archive-"))
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        archive = other / "old.tar.gz"
        archive.write_bytes(make_archive(FILES, top="gameserver-observability-0.0.9"))
        code, _, err = run("--pack-dir", str(make_pack()), "--tarball", str(archive))
        self.assertEqual(code, 2)
        self.assertIn("has no folder gameserver-observability-0.1.0/", err)

    def test_a_configured_tag_downloads_and_checks_the_release(self):
        data = make_archive(FILES)
        base = f"{REPOSITORY}/releases/download/v0.1.0"
        sums = f"{sha(data)}  gameserver-observability-0.1.0.tar.gz\n{'0' * 64}  other.tar.gz\n".encode()
        get = fake_get({f"{base}/SHA256SUMS": sums, f"{base}/gameserver-observability-0.1.0.tar.gz": data})
        pack = make_pack(release_tag="v0.1.0", release_sha256=sha(data))
        code, out, _ = run("--pack-dir", str(pack), get=get)
        self.assertEqual(code, 0, out)
        self.assertIn("compared with the release v0.1.0", out)
        self.assertEqual(get.requested, [f"{base}/SHA256SUMS", f"{base}/gameserver-observability-0.1.0.tar.gz"])

    def test_offline_skips_the_download(self):
        get = fake_get({})
        code, out, _ = run("--pack-dir", str(make_pack(release_tag="v0.1.0")), "--offline", get=get)
        self.assertEqual(code, 0)
        self.assertIn("release check skipped (--offline)", out)
        self.assertEqual(get.requested, [])

    def test_a_download_that_does_not_match_its_checksums_fails(self):
        data = make_archive(FILES)
        base = f"{REPOSITORY}/releases/download/v0.1.0"
        cases = {
            "differs from the release's SHA256SUMS": (f"{'1' * 64}  gameserver-observability-0.1.0.tar.gz\n", ""),
            "differs from release_sha256": (f"{sha(data)}  gameserver-observability-0.1.0.tar.gz\n", "2" * 64),
            "has no line for": (f"{sha(data)}  something-else.tar.gz\n", ""),
        }
        for message, (sums, pinned) in cases.items():
            with self.subTest(message=message):
                get = fake_get({f"{base}/SHA256SUMS": sums.encode(),
                                f"{base}/gameserver-observability-0.1.0.tar.gz": data})
                code, _, err = run("--pack-dir", str(make_pack(release_tag="v0.1.0", release_sha256=pinned)),
                                   get=get)
                self.assertEqual(code, 2)
                self.assertIn(message, err)

    def test_a_failed_download_is_a_usage_error(self):
        code, _, err = run("--pack-dir", str(make_pack(release_tag="v0.1.0")), get=fake_get({}))
        self.assertEqual(code, 2)
        self.assertIn("cannot download", err)


class UpdateTest(unittest.TestCase):
    def test_update_copies_the_listed_files_and_resets_the_release_fields(self):
        pack = make_pack(release_tag="v0.1.0", release_sha256="3" * 64)
        new = {"rules/a.yml": b"groups: [new]\n", "json_exporter/config.yml": b"modules: {new: {}}\n",
               "rules/unlisted.yml": b"groups: []\n"}
        other = Path(tempfile.mkdtemp(prefix="pack-archive-"))
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        archive = other / "gameserver-observability-0.2.0.tar.gz"
        archive.write_bytes(make_archive(new, top="gameserver-observability-0.2.0"))
        code, out, _ = run("--pack-dir", str(pack), "--update-from", str(archive))
        self.assertEqual(code, 0, out)
        manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.2.0")
        self.assertEqual((manifest["release_tag"], manifest["release_sha256"]), ("", ""))
        self.assertEqual(set(manifest["files"]), set(FILES))
        self.assertEqual((pack / "rules" / "a.yml").read_bytes(), new["rules/a.yml"])
        self.assertFalse((pack / "rules" / "unlisted.yml").exists())
        self.assertEqual(run("--pack-dir", str(pack))[0], 0)

    def test_update_refuses_an_archive_without_a_listed_file(self):
        pack = make_pack()
        other = Path(tempfile.mkdtemp(prefix="pack-archive-"))
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        archive = other / "gameserver-observability-0.2.0.tar.gz"
        archive.write_bytes(make_archive({"rules/a.yml": b"x\n"}, top="gameserver-observability-0.2.0"))
        code, _, err = run("--pack-dir", str(pack), "--update-from", str(archive))
        self.assertEqual(code, 2)
        self.assertIn("not in gameserver-observability-0.2.0.tar.gz: json_exporter/config.yml", err)


class VendoredPackTest(unittest.TestCase):
    """The pack folder committed in this repository."""

    def test_the_committed_pack_matches_its_manifest(self):
        manifest = cvp.load_manifest(cvp.PACK_DIR)
        self.assertEqual(cvp.check_manifest(cvp.PACK_DIR, manifest), [])
        self.assertEqual(manifest["repository"], REPOSITORY)
        self.assertEqual(manifest["archive_name"], "gameserver-observability")

    def test_the_committed_pack_is_the_0_1_0_release(self):
        # The files come from the pack's published release, so CI compares them with its archive.
        manifest = cvp.load_manifest(cvp.PACK_DIR)
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["release_tag"], "v0.1.0")
        self.assertRegex(manifest["release_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
