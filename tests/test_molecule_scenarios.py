"""Tests for scripts/molecule_scenarios.py (the role x platform list behind the Molecule CI matrix)."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import molecule_scenarios as ms  # noqa: E402


def repo(*roles_with_scenario: str, roles_without: tuple[str, ...] = ()) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="mol-test-"))
    unittest.addModuleCleanup(shutil.rmtree, tmp, ignore_errors=True)
    for name in roles_with_scenario:
        scenario = tmp / "roles" / name / "molecule" / "default"
        scenario.mkdir(parents=True)
        (scenario / "molecule.yml").write_text("platforms: []\n", encoding="utf-8")
    for name in roles_without:
        (tmp / "roles" / name / "tasks").mkdir(parents=True)
    return tmp


def run(root: Path, *extra: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ms.main(["--root", str(root), *extra])
    return code, out.getvalue(), err.getvalue()


def entry(role: str, platform: str, instance: str) -> dict[str, str]:
    return {"role": role, "platform": platform, "instance": instance}


class ScenarioListTest(unittest.TestCase):
    def test_no_roles_directory_gives_an_empty_array(self):
        code, out, _ = run(repo())
        self.assertEqual((code, json.loads(out)), (0, []))

    def test_empty_roles_directory_gives_an_empty_array(self):
        root = repo()
        (root / "roles").mkdir()
        (root / "roles" / ".gitkeep").write_text("", encoding="utf-8")
        code, out, _ = run(root)
        self.assertEqual((code, out), (0, "[]\n"))

    def test_role_without_a_scenario_fails(self):
        """A role that CI would not test is an error, not a silent gap in the matrix."""
        code, out, err = run(repo("fxserver", roles_without=("txadmin",)))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("roles/txadmin: no Molecule scenario (roles/txadmin/molecule/default/molecule.yml)", err)
        self.assertNotIn("fxserver", err)

    def test_invalid_directory_name_without_a_scenario_fails(self):
        code, out, err = run(repo(roles_without=("Bad-Name",)))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("roles/Bad-Name: not a valid role name", err)

    def test_one_entry_per_role_and_platform_sorted(self):
        code, out, _ = run(repo("txadmin", "fxserver"))
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out),
            [
                entry("fxserver", "debian13", "gs-fxserver-debian13"),
                entry("fxserver", "ubuntu2404", "gs-fxserver-ubuntu2404"),
                entry("txadmin", "debian13", "gs-txadmin-debian13"),
                entry("txadmin", "ubuntu2404", "gs-txadmin-ubuntu2404"),
            ],
        )

    def test_underscore_in_a_role_name_is_a_dash_in_the_instance_name(self):
        code, out, _ = run(repo("gameserver_observability"))
        self.assertEqual(code, 0)
        self.assertEqual(
            [e["instance"] for e in json.loads(out)],
            ["gs-gameserver-observability-debian13", "gs-gameserver-observability-ubuntu2404"],
        )
        self.assertEqual({e["role"] for e in json.loads(out)}, {"gameserver_observability"})

    def test_invalid_directory_name_fails(self):
        code, out, err = run(repo("fxserver", "Bad-Name"))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("roles/Bad-Name", err)

    def test_github_output(self):
        root = repo("fxserver")
        target = root / "github-output"
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(target)}):
            code, _, _ = run(root, "--github-output")
        self.assertEqual(code, 0)
        self.assertEqual(
            target.read_text(encoding="utf-8"),
            'matrix=[{"role":"fxserver","platform":"debian13","instance":"gs-fxserver-debian13"},'
            '{"role":"fxserver","platform":"ubuntu2404","instance":"gs-fxserver-ubuntu2404"}]\n',
        )

    def test_github_output_needs_the_variable(self):
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
        with mock.patch.dict(os.environ, env, clear=True):
            code, _, err = run(repo("fxserver"), "--github-output")
        self.assertEqual(code, 2)
        self.assertIn("GITHUB_OUTPUT", err)

    def test_this_repository(self):
        """Every directory under roles/ in this checkout is a validly named role with a scenario."""
        roles, errors = ms.scenario_roles(ROOT)
        self.assertEqual(errors, [])
        self.assertEqual(roles, sorted(roles))

    def test_every_platform_has_an_image_in_the_shared_dockerfile(self):
        """The matrix platforms are exactly the images that Dockerfile.j2 can build."""
        text = (ROOT / "molecule" / "resources" / "Dockerfile.j2").read_text(encoding="utf-8")
        images = re.findall(r"item\.image == '([a-z0-9-]+)'", text)
        self.assertEqual(ms.PLATFORMS, ("debian13", "ubuntu2404"))
        self.assertEqual(images, [f"gs-{p}" for p in ms.PLATFORMS])


if __name__ == "__main__":
    unittest.main()
