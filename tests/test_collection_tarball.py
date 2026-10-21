"""The release checks the collection tarball before it is published.

release.yml's extra-dist-command builds luminare-gameserver-X.Y.Z.tar.gz and runs
scripts/check_collection_tarball.sh on it, which installs the tarball into an empty folder and runs
--syntax-check on the installed playbook (with the installed example inventory) and on a play with
every installed role. These tests pin that order in the workflow and run the script on a tarball
built from this checkout, so a file missing from the tarball (build_ignore in galaxy.yml) fails on
every pull request, not only on the release tag.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - the CI environment always has PyYAML
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
SCRIPT = ROOT / "scripts" / "check_collection_tarball.sh"


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class ReleaseWorkflowTest(unittest.TestCase):
    def test_extra_dist_command_checks_the_built_tarball(self):
        release = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
        command = release["jobs"]["release"]["with"]["extra-dist-command"]
        steps = [
            "ansible-galaxy collection build --output-path dist",
            'test -f "dist/luminare-gameserver-${TAG#v}.tar.gz"',
            'bash scripts/check_collection_tarball.sh "dist/luminare-gameserver-${TAG#v}.tar.gz"',
        ]
        positions = [command.find(step) for step in steps]
        self.assertNotIn(-1, positions, command)
        self.assertEqual(positions, sorted(positions), "build, name check, then the tarball check")
        self.assertIn('"$RUNNER_TEMP/test-tools/venv/bin:$PATH"', command, "the hash-pinned tools")


@unittest.skipUnless(shutil.which("ansible-galaxy") and shutil.which("ansible-playbook"),
                     "ansible-core is not on the PATH")
class TarballCheckTest(unittest.TestCase):
    def test_tarball_built_from_this_checkout_passes(self):
        with tempfile.TemporaryDirectory(prefix="collection-tarball-") as tmp:
            subprocess.run(["ansible-galaxy", "collection", "build", "--output-path", tmp], cwd=ROOT,
                           check=True, capture_output=True, text=True, timeout=300)
            tarballs = sorted(Path(tmp).glob("luminare-gameserver-*.tar.gz"))
            self.assertEqual(len(tarballs), 1)
            out = subprocess.run(["bash", str(SCRIPT), str(tarballs[0])], cwd=tmp,
                                 capture_output=True, text=True, timeout=300)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn("pass --syntax-check", out.stdout)

    def test_refuses_a_missing_tarball(self):
        out = subprocess.run(["bash", str(SCRIPT), "/nonexistent/luminare-gameserver-0.0.0.tar.gz"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 2)
        self.assertIn("usage:", out.stderr)


if __name__ == "__main__":
    unittest.main()
