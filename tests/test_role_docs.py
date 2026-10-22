"""Every role variable is defined, validated and documented in the same place.

For each role under roles/: the variables in defaults/main.yml, the options in
meta/argument_specs.yml and the rows of the "Variables" table in the role README are the same set,
and every option has a type and a description. PyYAML comes with requirements-test.txt (and
requirements-dev.txt).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - the CI environment always has PyYAML
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
ROLES = sorted(p.parent.parent for p in ROOT.glob("roles/*/meta/argument_specs.yml"))


def readme_variables(role: Path) -> set[str]:
    text = (role / "README.md").read_text(encoding="utf-8")
    section = text.split("## Variables", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(rf"^\| `({role.name}_[a-z0-9_]+)` \|", section, re.MULTILINE))


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class RoleVariablesTest(unittest.TestCase):
    def test_there_are_roles(self):
        self.assertIn("fxserver", [r.name for r in ROLES])

    def test_defaults_specs_and_readme_agree(self):
        for role in ROLES:
            with self.subTest(role=role.name):
                defaults = yaml.safe_load((role / "defaults" / "main.yml").read_text(encoding="utf-8"))
                specs = yaml.safe_load((role / "meta" / "argument_specs.yml").read_text(encoding="utf-8"))
                options = specs["argument_specs"]["main"]["options"]
                self.assertEqual(set(defaults), set(options), "defaults/main.yml vs meta/argument_specs.yml")
                self.assertEqual(readme_variables(role), set(options), "README Variables table vs argument_specs")
                for name in options:
                    self.assertTrue(name.startswith(f"{role.name}_"), name)

    def test_every_option_has_a_type_and_a_description(self):
        for role in ROLES:
            specs = yaml.safe_load((role / "meta" / "argument_specs.yml").read_text(encoding="utf-8"))
            for name, option in specs["argument_specs"]["main"]["options"].items():
                with self.subTest(role=role.name, option=name):
                    self.assertIn("type", option)
                    self.assertTrue(option.get("description"))

    def test_secret_options_are_marked_no_log(self):
        specs = yaml.safe_load((ROOT / "roles" / "fxserver" / "meta" / "argument_specs.yml").read_text(encoding="utf-8"))
        options = specs["argument_specs"]["main"]["options"]
        for name in ("fxserver_license_key", "fxserver_perf_password", "fxserver_server_data_deploy_key",
                     "fxserver_secrets_cfg_extra"):
            with self.subTest(option=name):
                self.assertIs(options[name].get("no_log"), True)
                self.assertEqual(options[name]["default"], {} if name.endswith("_extra") else "")


if __name__ == "__main__":
    unittest.main()
