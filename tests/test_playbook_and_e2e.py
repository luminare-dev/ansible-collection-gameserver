"""The collection playbook, its example inventory and the manual end-to-end workflow.

They guard what docs/install.md and docs/e2e.md promise: the example inventory sets only real
role variables, uses documentation addresses and example names, and holds every secret as a
CHANGE_ME_ placeholder (which the roles refuse); the playbook runs fxserver before txadmin; the
end-to-end workflow can only be started by hand, in the protected environment "e2e", is skipped
unless E2E_ENABLED is "true", passes its secrets only through step environments, checks the
downloaded hcloud CLI against a pinned sha256 and deletes what it created in an always() step.
The Molecule scenario roles/txadmin/molecule/playbook runs the playbook itself. PyYAML comes with
requirements-test.txt (and requirements-dev.txt).
"""

from __future__ import annotations

import ipaddress
import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - the CI environment always has PyYAML
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "inventory"
PLAYBOOK = ROOT / "playbooks" / "gameserver.yml"
E2E = ROOT / ".github" / "workflows" / "e2e.yml"
DOC_NETWORKS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24",
                                                    "2001:db8::/32")]


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def role_options() -> dict[str, dict]:
    """Every option of every role, from meta/argument_specs.yml."""
    options: dict[str, dict] = {}
    for spec in sorted(ROOT.glob("roles/*/meta/argument_specs.yml")):
        options.update(load_yaml(spec)["argument_specs"]["main"]["options"])
    return options


def example_vars() -> dict:
    merged: dict = {}
    for path in sorted((EXAMPLE / "group_vars" / "gameservers").glob("*.yml")):
        merged.update(load_yaml(path) or {})
    return merged


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class ExampleInventoryTest(unittest.TestCase):
    def test_only_role_variables(self):
        """A typo in the example would silently fall back to a role default."""
        unknown = set(example_vars()) - set(role_options())
        self.assertEqual(unknown, set())

    def test_secrets_are_placeholders(self):
        """Every secret option the example sets (no_log in the specs) is a CHANGE_ME_ placeholder."""
        options = role_options()
        found = []
        for name, value in example_vars().items():
            option = options.get(name, {})  # unknown names fail test_only_role_variables
            if option.get("no_log"):
                found.append(name)
                self.assertRegex(str(value), r"^CHANGE_ME_[A-Z0-9_]+$", name)
            for sub, sub_option in (option.get("options") or {}).items():
                if sub_option.get("no_log") and isinstance(value, dict) and sub in value:
                    found.append(f"{name}.{sub}")
                    self.assertRegex(str(value[sub]), r"^CHANGE_ME_[A-Z0-9_]+$", f"{name}.{sub}")
        self.assertIn("fxserver_license_key", found)
        self.assertEqual(example_vars()["fxserver_license_key"], "CHANGE_ME_LICENSE_KEY")
        self.assertIn("txadmin_prometheus_basic_auth.password", found)

    def test_documentation_addresses_and_names_only(self):
        hosts = load_yaml(EXAMPLE / "hosts.yml")["gameservers"]["hosts"]
        self.assertTrue(hosts)
        for name, host_vars in hosts.items():
            with self.subTest(host=name):
                self.assertRegex(name, r"(^|\.)example\.(com|org|net)$")
                address = ipaddress.ip_address(host_vars["ansible_host"])
                self.assertTrue(any(address in net for net in DOC_NETWORKS), address)
        for source in example_vars().get("txadmin_firewall_sources", []):
            with self.subTest(source=source):
                network = ipaddress.ip_network(source, strict=False)
                self.assertTrue(any(network.subnet_of(net) for net in DOC_NETWORKS
                                    if net.version == network.version), source)
        url = example_vars().get("txadmin_public_url", "")
        self.assertRegex(url, r"^https://[a-z0-9-]+\.example\.com$")

    def test_txadmin_mode_with_its_firewall_source(self):
        """The example is the txAdmin setup the playbook scenario and the end-to-end run use."""
        values = example_vars()
        self.assertEqual(values["fxserver_mode"], "txadmin")
        self.assertTrue(values["txadmin_firewall_sources"])


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class PlaybookTest(unittest.TestCase):
    def setUp(self):
        self.plays = load_yaml(PLAYBOOK)

    def test_one_play_fxserver_then_txadmin(self):
        self.assertEqual(len(self.plays), 1)
        play = self.plays[0]
        self.assertIs(play["become"], True)
        self.assertEqual([r["role"] for r in play["roles"]], ["fxserver", "txadmin"])
        self.assertNotIn("when", play["roles"][0])
        self.assertEqual(play["roles"][1]["when"], "fxserver_mode | default('plain') == 'txadmin'")

    def test_firewall_layout_is_checked_before_the_roles_in_txadmin_mode(self):
        """txAdmin listens on 40120 from the fxserver role's start until the txadmin drop-in loads."""
        play = self.plays[0]
        self.assertEqual(len(play["pre_tasks"]), 1)
        check = play["pre_tasks"][0]
        self.assertEqual(check["ansible.builtin.include_tasks"], "tasks/check_firewall_layout.yml")
        self.assertEqual(check["when"], ["fxserver_mode | default('plain') == 'txadmin'",
                                         "txadmin_firewall_required | default(true) | bool"])
        tasks = load_yaml(PLAYBOOK.parent / "tasks" / "check_firewall_layout.yml")
        check_task = tasks[-1]
        that = check_task["ansible.builtin.assert"]["that"]
        # The same patterns as the txadmin role's own check (roles/txadmin/tasks/assert.yml),
        # passed as variables like there.
        role_vars = load_yaml(ROOT / "roles" / "txadmin" / "vars" / "main.yml")
        for mine, role in (("gameserver_nft_table_re", "__txadmin_nft_table_re"),
                           ("gameserver_nft_include_re", "__txadmin_nft_include_re")):
            with self.subTest(pattern=mine):
                self.assertEqual(check_task["vars"][mine], role_vars[role])
                self.assertIn(f"gameserver_nft_text is search({mine}, multiline=true)", that)
        self.assertFalse([t for t in tasks if set(t) & {"ansible.builtin.copy", "ansible.builtin.template",
                                                          "ansible.builtin.file", "ansible.builtin.apt"}],
                         "the pre-check must not change anything")

    def test_one_host_at_a_time_and_stop_at_the_first_failure(self):
        play = self.plays[0]
        self.assertEqual(play["serial"], "{{ gameserver_serial | default(1) }}")
        self.assertEqual(play["max_fail_percentage"], 0)

    def test_default_group_is_the_example_group(self):
        self.assertEqual(self.plays[0]["hosts"], "{{ gameserver_hosts | default('gameservers') }}")
        self.assertIn("gameservers", load_yaml(EXAMPLE / "hosts.yml"))

    def test_playbook_scenario_uses_the_example_and_the_e2e_playbooks(self):
        scenario = ROOT / "roles" / "txadmin" / "molecule" / "playbook"
        molecule = load_yaml(scenario / "molecule.yml")
        self.assertEqual(molecule["provisioner"]["inventory"]["links"],
                         {"group_vars": "../../../../examples/inventory/group_vars/"})
        for platform in molecule["platforms"]:
            self.assertEqual(platform["groups"], ["gameservers"])
        imports = {p["ansible.builtin.import_playbook"] for f in ("prepare.yml", "converge.yml", "verify.yml")
                   for p in load_yaml(scenario / f) if "ansible.builtin.import_playbook" in p}
        self.assertEqual(imports, {"../../../../playbooks/gameserver.yml", "../../../../tests/e2e/prepare.yml",
                                   "../../../../tests/e2e/check.yml"})


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class EndToEndWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = E2E.read_text(encoding="utf-8")
        self.workflow = load_yaml(E2E)
        self.job = self.workflow["jobs"]["e2e"]
        self.steps = self.job["steps"]

    def test_started_by_hand_only(self):
        # PyYAML reads the key "on" as the boolean True.
        triggers = self.workflow.get("on", self.workflow.get(True))
        self.assertEqual(list(triggers), ["workflow_dispatch"])
        self.assertNotIn("pull_request", self.text)

    def test_protected_environment_and_skipped_unless_enabled(self):
        self.assertEqual(self.job["environment"], "e2e")
        # Repository variables are strings: a comparison with the boolean true would never match.
        self.assertEqual(self.job["if"], "${{ vars.E2E_ENABLED == 'true' }}")
        self.assertEqual(self.workflow["permissions"], {})
        self.assertEqual(self.job["permissions"], {"contents": "read"})
        self.assertEqual(self.workflow["concurrency"]["cancel-in-progress"], False)

    def test_secrets_only_in_step_environments(self):
        expression = re.compile(r"\$\{\{[^}]*secrets\.")
        for step in self.steps:
            with self.subTest(step=step.get("name")):
                self.assertNotRegex(step.get("run", ""), expression)
                self.assertNotRegex(str(step.get("with", "")), expression)
        self.assertNotRegex(str(self.job.get("env", {})), expression)
        used = set(re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", self.text))
        self.assertEqual(used, {"HCLOUD_TOKEN", "FXSERVER_LICENSE_KEY"})

    def test_hcloud_cli_is_checked_against_a_pinned_sha256(self):
        self.assertRegex(self.job["env"]["HCLOUD_CLI_VERSION"], r"^\d+\.\d+\.\d+$")
        self.assertRegex(self.job["env"]["HCLOUD_CLI_SHA256"], r"^[0-9a-f]{64}$")
        install = next(s for s in self.steps if "hcloud.tar.gz" in s.get("run", ""))
        self.assertIn('| sha256sum -c -', install["run"])

    def test_clean_up_always_runs_last_and_checks_that_nothing_is_left(self):
        last = self.steps[-1]
        self.assertEqual(last["if"], "${{ always() }}")
        for kind in ("server", "firewall", "ssh-key"):
            self.assertIn(kind, last["run"])
        self.assertIn('--selector "${E2E_LABEL}"', last["run"])
        self.assertIn('left', last["run"])

    def test_runs_the_playbook_twice_per_mode_and_both_checks(self):
        runs = "\n".join(s.get("run", "") for s in self.steps)
        self.assertEqual(runs.count("luminare.gameserver.gameserver"), 2)
        self.assertEqual(runs.count("for run in 1 2; do"), 2)
        self.assertEqual(runs.count("changed=0 +unreachable=0 +failed=0"), 2)
        self.assertIn("tests/e2e/check.yml -e e2e_mode=plain", runs)
        self.assertIn("tests/e2e/check.yml -e e2e_mode=txadmin", runs)
        self.assertIn("tests/e2e/prepare.yml", runs)
        self.assertIn("/dev/tcp/${SERVER_IP}/40120", runs)


if __name__ == "__main__":
    unittest.main()
