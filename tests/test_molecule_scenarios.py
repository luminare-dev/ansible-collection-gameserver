"""Tests for scripts/molecule_scenarios.py (the role x scenario x platform list behind the Molecule CI matrix)."""

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


def repo(*roles_with_scenario: str, roles_without: tuple[str, ...] = (),
         extra: tuple[tuple[str, str], ...] = ()) -> Path:
    """A repository with a default scenario for each role, plus (role, scenario) pairs in extra."""
    tmp = Path(tempfile.mkdtemp(prefix="mol-test-"))
    unittest.addModuleCleanup(shutil.rmtree, tmp, ignore_errors=True)
    for role, name in [(r, "default") for r in roles_with_scenario] + list(extra):
        scenario = tmp / "roles" / role / "molecule" / name
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


def entry(role: str, platform: str, instance: str, scenario: str = "default") -> dict[str, str]:
    return {"role": role, "scenario": scenario, "platform": platform, "instance": instance}


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

    def test_further_scenarios_follow_default_in_name_order(self):
        root = repo("fxserver", extra=(("fxserver", "upgrade"), ("fxserver", "fresh_os")))
        (root / "roles" / "fxserver" / "molecule" / "resources").mkdir()  # no molecule.yml: not a scenario
        code, out, _ = run(root)
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out),
            [
                entry("fxserver", "debian13", "gs-fxserver-debian13"),
                entry("fxserver", "ubuntu2404", "gs-fxserver-ubuntu2404"),
                entry("fxserver", "debian13", "gs-fxserver-fresh-os-debian13", "fresh_os"),
                entry("fxserver", "ubuntu2404", "gs-fxserver-fresh-os-ubuntu2404", "fresh_os"),
                entry("fxserver", "debian13", "gs-fxserver-upgrade-debian13", "upgrade"),
                entry("fxserver", "ubuntu2404", "gs-fxserver-upgrade-ubuntu2404", "upgrade"),
            ],
        )

    def test_role_with_only_a_further_scenario_fails(self):
        """The default scenario stays mandatory; "upgrade" alone does not count."""
        code, out, err = run(repo(extra=(("fxserver", "upgrade"),)))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("roles/fxserver: no Molecule scenario", err)

    def test_invalid_scenario_name_fails(self):
        code, out, err = run(repo("fxserver", extra=(("fxserver", "Up-Grade"),)))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("roles/fxserver/molecule/Up-Grade: not a valid scenario name", err)

    def test_duplicate_instance_names_fail(self):
        """Role "a" with scenario "b" and role "a_b" would share gs-a-b-<platform>."""
        code, out, err = run(repo("a", "a_b", extra=(("a", "b"),)))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("instance name gs-a-b-debian13 is used by more than one role or scenario", err)

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
            'matrix=[{"role":"fxserver","scenario":"default","platform":"debian13","instance":"gs-fxserver-debian13"},'
            '{"role":"fxserver","scenario":"default","platform":"ubuntu2404","instance":"gs-fxserver-ubuntu2404"}]\n',
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
        self.assertEqual(list(roles), sorted(roles))
        self.assertEqual(ms.duplicate_instances(ms.matrix(roles)), [])
        self.assertEqual(roles.get("fxserver"), ["default", "upgrade"])

    def test_every_platform_has_an_image_in_the_shared_dockerfile(self):
        """The matrix platforms are exactly the images that Dockerfile.j2 can build."""
        text = (ROOT / "molecule" / "resources" / "Dockerfile.j2").read_text(encoding="utf-8")
        images = re.findall(r"item\.image == '([a-z0-9-]+)'", text)
        self.assertEqual(ms.PLATFORMS, ("debian13", "ubuntu2404"))
        self.assertEqual(images, [f"gs-{p}" for p in ms.PLATFORMS])


if __name__ == "__main__":
    unittest.main()
