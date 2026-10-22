"""The gameserver_observability role against the gameserver-observability files it vendors.

The role renders the pack's scrape jobs from its own template (one entry per game server) instead
of copying the pack's scrape files, so these tests render that template with the pack's example
values (game-01 on 127.0.0.1:30120, the exporters on loopback, one admin hostname, the version
list) and compare the result job by job with the vendored prometheus/scrape/*.yml. They also
check the rule file lists, the firewall drop-in template and that no shipped config reads
players.json. Jinja2 and PyYAML come with requirements-test.txt (Jinja2 through ansible-core).
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

try:
    import jinja2
    import yaml
except ImportError:  # pragma: no cover - the CI environment always has both
    jinja2 = yaml = None

ROOT = Path(__file__).resolve().parent.parent
ROLE = ROOT / "roles" / "gameserver_observability"
PACK = ROLE / "files" / "pack"
PLAYER_LABELS = {"name", "identifier", "identifiers", "license", "ip", "endpoint", "player", "players", "ping"}


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def to_bool(value: object) -> bool:
    """Ansible's bool filter for the values the templates pass to it."""
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def render(template: str, **variables: object) -> str:
    # Ansible's template module renders with trim_blocks on and keeps the trailing newline.
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, trim_blocks=True, keep_trailing_newline=True)
    env.filters["bool"] = to_bool
    env.tests["search"] = lambda value, pattern: re.search(pattern, str(value)) is not None
    text = (ROLE / "templates" / template).read_text(encoding="utf-8")
    return env.from_string(text).render(ansible_managed="Ansible managed", **variables)


def role_values(**overrides: object) -> dict:
    """The role defaults plus the internal values the templates read, for the pack's example."""
    values = dict(load_yaml(ROLE / "defaults" / "main.yml"))
    values.update({
        "gameserver_observability_admin_probes": [{"server": "game-01", "url": "https://demo-tx.example.com/"}],
        "gameserver_observability_versions_job": True,
        "__gameserver_observability_pack": json.loads((PACK / "manifest.json").read_text(encoding="utf-8")),
        "__gameserver_observability_perf_password_file": "/etc/prometheus/secrets/fxserver_perf",
        "__gameserver_observability_json_exporter_address": "127.0.0.1:7979",
        "__gameserver_observability_blackbox_exporter_address": "127.0.0.1:9115",
    })
    values.update(overrides)
    return values


@unittest.skipIf(jinja2 is None or yaml is None, "Jinja2 or PyYAML is not installed")
class ScrapeJobsTest(unittest.TestCase):
    def test_the_template_renders_the_pack_jobs(self):
        rendered = yaml.safe_load(render("scrape_configs.yml.j2", **role_values()))["scrape_configs"]
        pack_jobs = []
        for name in ("fxserver.yml", "tunnel.yml", "versions.yml"):
            pack_jobs += load_yaml(PACK / "prometheus" / "scrape" / name)["scrape_configs"]
        self.assertEqual([j["job_name"] for j in rendered], [j["job_name"] for j in pack_jobs])
        for ours, theirs in zip(rendered, pack_jobs):
            with self.subTest(job=theirs["job_name"]):
                self.assertEqual(ours, theirs)

    def test_optional_jobs_are_left_out_by_default(self):
        values = role_values(gameserver_observability_admin_probes=[], gameserver_observability_versions_job=False)
        jobs = yaml.safe_load(render("scrape_configs.yml.j2", **values))["scrape_configs"]
        self.assertEqual([j["job_name"] for j in jobs], ["fxserver_perf", "fxserver_json", "fxserver_blackbox"])

    def test_every_target_gets_its_own_entries(self):
        targets = [
            {"server": "game-01", "address": "127.0.0.1"},
            {"server": "game-02", "address": "2001:db8::20", "port": 30130},
            {"server": "game-03", "address": "game-03.example.com", "port": 30120},
        ]
        values = role_values(gameserver_observability_targets=targets, gameserver_observability_admin_probes=[],
                             gameserver_observability_versions_job=False)
        jobs = {j["job_name"]: j for j in yaml.safe_load(render("scrape_configs.yml.j2", **values))["scrape_configs"]}
        perf = jobs["fxserver_perf"]["static_configs"]
        self.assertEqual([c["targets"] for c in perf],
                         [["127.0.0.1:30120"], ["[2001:db8::20]:30130"], ["game-03.example.com:30120"]])
        self.assertEqual([c["labels"]["server"] for c in perf], ["game-01", "game-02", "game-03"])
        json_targets = [t for c in jobs["fxserver_json"]["static_configs"] for t in c["targets"]]
        self.assertEqual(len(json_targets), 6)
        self.assertIn("http://[2001:db8::20]:30130/dynamic.json", json_targets)
        self.assertEqual(len(jobs["fxserver_blackbox"]["static_configs"]), 9)

    def test_no_shipped_config_reads_players_json(self):
        text = render("scrape_configs.yml.j2", **role_values())
        targets = [t for job in yaml.safe_load(text)["scrape_configs"]
                   for c in job["static_configs"] for t in c["targets"]]
        self.assertTrue(targets)
        self.assertFalse([t for t in targets if "players" in t])
        for path in [*PACK.rglob("*.yml"), *(ROLE / "templates").glob("*.j2")]:
            with self.subTest(file=str(path.relative_to(ROOT))):
                lines = [x for x in path.read_text(encoding="utf-8").splitlines()
                         if "players.json" in x and not x.lstrip().startswith("#")]
                self.assertEqual(lines, [])

    def test_no_label_names_a_player(self):
        config = load_yaml(PACK / "json_exporter" / "config.yml")
        for module, spec in config["modules"].items():
            for metric in spec["metrics"]:
                with self.subTest(module=module, metric=metric["name"]):
                    self.assertFalse(set(metric.get("labels", {})) & PLAYER_LABELS)
        text = render("scrape_configs.yml.j2", **role_values())
        labels = {k for job in yaml.safe_load(text)["scrape_configs"]
                  for c in job["static_configs"] for k in c.get("labels", {})}
        self.assertEqual(labels, {"server", "module"})


@unittest.skipIf(jinja2 is None or yaml is None, "Jinja2 or PyYAML is not installed")
class PackFilesTest(unittest.TestCase):
    def test_the_rule_lists_match_the_vendored_rule_files(self):
        pack_rules = sorted(p.name for p in (PACK / "rules").glob("*.yml"))
        internal = load_yaml(ROLE / "vars" / "main.yml")["__gameserver_observability_pack_rules"]
        option = load_yaml(ROLE / "meta" / "argument_specs.yml")["argument_specs"]["main"]["options"][
            "gameserver_observability_rule_files"]
        default = load_yaml(ROLE / "defaults" / "main.yml")["gameserver_observability_rule_files"]
        self.assertEqual(sorted(internal), pack_rules)
        self.assertEqual(sorted(option["choices"]), pack_rules)
        self.assertEqual(sorted(default), pack_rules)

    def test_every_vendored_file_is_installed_or_compared(self):
        manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
        used = "\n".join(p.read_text(encoding="utf-8") for p in [*(ROLE / "tasks").glob("*.yml"),
                                                                    ROLE / "vars" / "main.yml"])
        for path in manifest["files"]:
            with self.subTest(file=path):
                if path.startswith("prometheus/scrape/"):
                    continue  # rendered by the template and compared above
                if path.startswith("rules/"):
                    self.assertIn("pack/rules/", used)
                elif path == "grafana/provisioning/dashboards/gameserver-observability.yml":
                    continue  # its settings are the template grafana-dashboards.yml.j2 (test below)
                else:
                    self.assertIn(f"pack/{path}", used)

    def test_the_dashboard_provider_follows_the_pack(self):
        theirs = load_yaml(PACK / "grafana" / "provisioning" / "dashboards" / "gameserver-observability.yml")
        ours = yaml.safe_load(render("grafana-dashboards.yml.j2", **role_values()))
        self.assertEqual(ours["apiVersion"], theirs["apiVersion"])
        mine, pack = ours["providers"][0], theirs["providers"][0]
        for key in ("name", "orgId", "folder", "folderUid", "type", "disableDeletion", "allowUiUpdates",
                    "updateIntervalSeconds"):
            with self.subTest(key=key):
                self.assertEqual(mine[key], pack[key])
        self.assertEqual(mine["options"]["path"], "/var/lib/grafana/dashboards/gameserver-observability")

    def test_the_dashboard_title_has_no_platform_name(self):
        dashboard = json.loads((PACK / "grafana" / "dashboards" / "game-server-overview.json").read_text(
            encoding="utf-8"))
        self.assertEqual(dashboard["title"], "Game server overview")


@unittest.skipIf(jinja2 is None or yaml is None, "Jinja2 or PyYAML is not installed")
class FirewallDropInTest(unittest.TestCase):
    def rules(self, sources: list[str]) -> list[str]:
        text = render("50-observability.nft.j2", **role_values(gameserver_observability_firewall_sources=sources))
        return [x for x in text.splitlines() if x and not x.startswith("#")]

    def test_accept_rules_for_both_ports_and_both_families(self):
        self.assertEqual(self.rules(["198.51.100.0/24", "192.0.2.7", "2001:db8::/32"]), [
            "add rule inet filter input ip saddr { 198.51.100.0/24, 192.0.2.7 } tcp dport 7979 accept",
            "add rule inet filter input ip6 saddr { 2001:db8::/32 } tcp dport 7979 accept",
            "add rule inet filter input ip saddr { 198.51.100.0/24, 192.0.2.7 } tcp dport 9115 accept",
            "add rule inet filter input ip6 saddr { 2001:db8::/32 } tcp dport 9115 accept",
        ])

    def test_no_sources_no_rules(self):
        self.assertEqual(self.rules([]), [])

    def test_only_accept_rules(self):
        for line in self.rules(["198.51.100.0/24", "2001:db8::/32"]):
            self.assertRegex(line, r"^add rule inet filter input ip6? saddr \{ [^}]+ \} tcp dport \d+ accept$")
            self.assertNotRegex(line, re.compile(r"\b(drop|reject)\b"))


if __name__ == "__main__":
    unittest.main()
