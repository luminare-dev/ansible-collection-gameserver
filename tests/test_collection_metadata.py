"""Consistency checks for the collection metadata and the shared Molecule setup.

They guard the values that release-please, ansible-galaxy and the CI matrix rely on: galaxy.yml
and version.txt move together, the installable tarball leaves out development files and the brand
files, and every Molecule scenario uses the shared, digest-pinned test image with "gs-" instance
names. PyYAML comes with requirements-test.txt (and requirements-dev.txt).
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - the CI environment always has PyYAML
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
PURPOSE = ("Ansible roles that install, configure, update and back up game servers, "
           "for FiveM/RedM servers (FXServer)")
SLUG = "ansible-collection-gameserver"
SHARED_DOCKERFILE = "../../../../molecule/resources/Dockerfile.j2"


def load_yaml(rel: str) -> dict:
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class GalaxyMetadataTest(unittest.TestCase):
    def setUp(self):
        self.galaxy = load_yaml("galaxy.yml")

    def test_name_and_namespace(self):
        self.assertEqual((self.galaxy["namespace"], self.galaxy["name"]), ("luminare", "gameserver"))

    def test_version_follows_version_txt_and_release_please(self):
        version = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(self.galaxy["version"], version)
        line = next(x for x in (ROOT / "galaxy.yml").read_text(encoding="utf-8").splitlines()
                    if x.startswith("version:"))
        self.assertIn("x-release-please-version", line, "release-please's generic updater needs the marker")
        config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
        extra = config["packages"]["."]["extra-files"]
        self.assertIn({"type": "generic", "path": "galaxy.yml"}, extra)

    def test_role_address_and_licence(self):
        self.assertEqual(self.galaxy["authors"], ["Luminare Development <oss@luminare.tech>"])
        self.assertEqual(self.galaxy["license"], ["Apache-2.0"])
        self.assertEqual(" ".join(self.galaxy["description"].split()), PURPOSE)

    def test_links(self):
        self.assertEqual(self.galaxy["homepage"], f"https://luminare.tech/open-source/{SLUG}/")
        for key in ("repository", "documentation", "issues"):
            self.assertTrue(self.galaxy[key].startswith(f"https://github.com/luminare-dev/{SLUG}"), key)

    def test_no_dependency_on_other_luminare_collections(self):
        """luminare.infra_edge is a documented soft dependency, never a Galaxy dependency."""
        deps = self.galaxy.get("dependencies") or {}
        self.assertEqual([d for d in deps if d.startswith("luminare.")], [])

    def test_build_ignore_keeps_development_and_brand_files_out(self):
        ignored = set(self.galaxy["build_ignore"])
        required = {"docs/brand", "scripts", ".github", "dist", "tests/test_*.py", "*.tar.gz",
                    ".forbidden-words-allow", "requirements-*.txt", ".venv", "molecule", "roles/*/molecule"}
        self.assertEqual(required - ignored, set())

    def test_requires_ansible(self):
        runtime = load_yaml("meta/runtime.yml")
        self.assertRegex(runtime["requires_ansible"], r"^>=2\.\d+\.\d+$")


class DocumentedVersionTest(unittest.TestCase):
    """Versions in the install commands sit in release-please blocks and name the current tag.

    Before the first release they name the first tag (initial-version); afterwards the version in
    version.txt. release-please rewrites every version inside
    "x-release-please-start-version" ... "x-release-please-end" (extra-files, generic updater).
    """

    BLOCK_RE = re.compile(r"x-release-please-start-version(.*?)x-release-please-end", re.DOTALL)

    def expected(self) -> str:
        version = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
        config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
        return config["initial-version"] if version == "0.0.0" else version

    def test_install_commands_name_the_current_tag(self):
        config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
        extra = config["packages"]["."]["extra-files"]
        for rel in ("README.md", "docs/install.md"):
            with self.subTest(file=rel):
                self.assertIn({"type": "generic", "path": rel}, extra)
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn(f"git+https://github.com/luminare-dev/{SLUG}.git,v", text)
                blocks = self.BLOCK_RE.findall(text)
                self.assertTrue(blocks, "no release-please version block")
                versions = set(re.findall(r"\d+\.\d+\.\d+", "".join(blocks)))
                self.assertEqual(versions, {self.expected()})
                outside = self.BLOCK_RE.sub("", text)
                self.assertNotRegex(outside, rf"{SLUG}\.git,v\d", "a versioned install command outside a block")


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class MoleculeSetupTest(unittest.TestCase):
    def test_base_images_are_pinned_by_digest(self):
        text = (ROOT / "molecule" / "resources" / "Dockerfile.j2").read_text(encoding="utf-8")
        froms = [x for x in text.splitlines() if x.startswith("FROM ")]
        self.assertEqual(len(froms), 2, froms)
        for line in froms:
            self.assertRegex(line, r"^FROM (debian:trixie|ubuntu:24\.04)@sha256:[0-9a-f]{64}$")

    def test_scenarios_use_the_shared_image_and_prefixed_names(self):
        for scenario in sorted(ROOT.glob("roles/*/molecule/*/molecule.yml")):
            role = scenario.parts[-4]
            with self.subTest(scenario=str(scenario.relative_to(ROOT))):
                platforms = yaml.safe_load(scenario.read_text(encoding="utf-8"))["platforms"]
                self.assertEqual(sorted(p["image"] for p in platforms), ["gs-debian13", "gs-ubuntu2404"])
                for p in platforms:
                    # CI runs "molecule test --platform-name gs-<role>-<platform>" (ci.yml), so the
                    # name must match the image exactly: gs-debian13 -> gs-<role>-debian13.
                    platform = p["image"].removeprefix("gs-")
                    self.assertEqual(p["name"], f"gs-{role.replace('_', '-')}-{platform}")
                    self.assertEqual(p.get("dockerfile"), SHARED_DOCKERFILE)
                    self.assertIs(p.get("privileged"), True)
                    self.assertEqual(p.get("cgroupns_mode"), "host")
                    self.assertEqual(p.get("command"), "/lib/systemd/systemd")


if __name__ == "__main__":
    unittest.main()
