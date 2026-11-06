# luminare.gameserver.gameserver_observability

Adds game servers (FXServer, for FiveM/RedM servers) to an existing Prometheus with the
[gameserver-observability](https://github.com/luminare-dev/gameserver-observability) pack:
json_exporter and blackbox_exporter as hardened units, the pack's scrape jobs and rules, `/perf/`
basic auth through a password file and optionally the dashboard for Grafana on the same host. It
only collects counts and never reads `players.json`.

Not affiliated with or endorsed by Cfx.re, Rockstar Games or Take-Two.

## Before you start

- Run it on the Prometheus host: the game server itself (targets on `127.0.0.1`) or a monitoring
  host that reaches the game servers over a private network. `/perf/` sends basic auth in plain
  HTTP, so never scrape across the internet.
- Prometheus 2.43 or later with promtool. `prometheus.yml` must include the role's files (the
  `prometheus.prometheus.prometheus` role already does):

  ```yaml
  scrape_config_files:
    - /etc/prometheus/scrape_configs/*.yml
  rule_files:
    - /etc/prometheus/rules/*.yml
  ```

- The game servers' `/perf/` user and password (`fxserver_perf_password` or the txadmin role's
  toggle). The role needs the same values.
- HTTPS to github.com for the exporter downloads.

## Example playbook

Keep the `/perf/` password in an encrypted variables file, for example with SOPS or Ansible Vault,
where the game servers' plays read it too:

```yaml
# group_vars/all/secrets.yml (encrypted). The roles refuse this placeholder.
fxserver_perf_password: CHANGE_ME_AT_LEAST_24_CHARACTERS
```

One host with the game server and Prometheus:

```yaml
- name: Game server with metrics on the same host
  hosts: gameservers
  become: true
  roles:
    - role: luminare.gameserver.fxserver
    - role: prometheus.prometheus.prometheus
    - role: luminare.gameserver.gameserver_observability
      vars:
        gameserver_observability_perf_password: "{{ fxserver_perf_password }}"
```

A monitoring host that scrapes two game servers over a private network:

```yaml
- name: Metrics for the game servers
  hosts: monitoring
  become: true
  roles:
    - role: prometheus.prometheus.prometheus
    - role: luminare.gameserver.gameserver_observability
      vars:
        gameserver_observability_perf_password: "{{ fxserver_perf_password }}"
        gameserver_observability_targets:
          - server: game-01
            address: game-01.example.com
          - server: game-02
            address: 192.0.2.20
        gameserver_observability_versions_job: true
```

The `server` label is the name the dashboard and the alerts show for a game server; give
node_exporter and mysqld_exporter targets the same label (the pack's
[configuration guide](https://github.com/luminare-dev/gameserver-observability/blob/main/docs/configuration.md#host-and-database-jobs)),
so that the host, build and database alerts name the game server too.

## Variables

Every variable is validated by `meta/argument_specs.yml`.

| Variable | Type | Default | Description |
|---|---|---|---|
| `gameserver_observability_targets` | list of dict | `[{server: game-01, address: 127.0.0.1, port: 30120}]` | Game servers to watch: `server` (the `server` label: letters, digits, `.`, `_` and `-`, unique), `address` (host name, IPv4 or IPv6 address as seen from this host) and `port` (game port, default 30120). |
| `gameserver_observability_perf_user` | str | `prometheus` | `/perf/` basic auth user, equal to `sv_prometheusBasicAuthUser` on the game servers. |
| `gameserver_observability_perf_password` | str | `""` | `/perf/` basic auth password, equal to `sv_prometheusBasicAuthPassword`; secret, required, at least 24 characters without spaces or quotes. Written to `secrets/fxserver_perf` and read by Prometheus through `password_file`. |
| `gameserver_observability_admin_probes` | list of dict | `[]` | Admin hostnames behind an access-protected tunnel (job `fxserver_tunnel`): `server` (label of one of the targets) and `url` (`https://…`). A request without a login must be redirected or refused. |
| `gameserver_observability_versions_job` | bool | `false` | Adds the job `fxserver_versions`, which reads the platform's public version list for the alert `FXServerBuildBehindRecommended`; json_exporter then needs outbound HTTPS. |
| `gameserver_observability_listen_address` | str | `127.0.0.1` | Address both exporters listen on: loopback or private (RFC 1918, RFC 6598, IPv6 unique local); `0.0.0.0` and public addresses are refused. |
| `gameserver_observability_json_exporter_port` | int | `7979` | Port of json_exporter. |
| `gameserver_observability_json_exporter_version` | str | `0.8.0` | json_exporter release; change it together with the sha256. |
| `gameserver_observability_json_exporter_sha256` | str | `bd25fe58…a4fe1` | sha256 of `json_exporter-<version>.linux-amd64.tar.gz` from the release's `sha256sums.txt`. |
| `gameserver_observability_blackbox_exporter_port` | int | `9115` | Port of blackbox_exporter. |
| `gameserver_observability_blackbox_exporter_version` | str | `0.29.0` | blackbox_exporter release; change it together with the sha256. |
| `gameserver_observability_blackbox_exporter_sha256` | str | `55129292…88fb4` | sha256 of `blackbox_exporter-<version>.linux-amd64.tar.gz` from the release's `sha256sums.txt`. |
| `gameserver_observability_prometheus_config_dir` | path | `/etc/prometheus` | Configuration folder of the existing Prometheus; the role writes `scrape_configs/`, `rules/` and `secrets/` files below it. |
| `gameserver_observability_prometheus_config_file` | path | `<config dir>/prometheus.yml` | Main configuration file; checked with promtool after every change. |
| `gameserver_observability_prometheus_group` | str | `prometheus` | Group Prometheus runs as; it may read the password file. |
| `gameserver_observability_prometheus_service` | str | `prometheus.service` | systemd unit of Prometheus, reloaded after a change. |
| `gameserver_observability_prometheus_reload` | bool | `true` | Reload Prometheus after a change and check what it loaded; `false` leaves both to you. |
| `gameserver_observability_prometheus_url` | str | `http://127.0.0.1:9090` | Prometheus' web address for the check of the loaded jobs and rules; `""` skips the check. |
| `gameserver_observability_promtool` | str | `promtool` | promtool command (a name in the `PATH` or a path) of the Prometheus release in use. |
| `gameserver_observability_rule_files` | list of str | all five | Rule files of the pack to install: `fxserver.recording.yml`, `fxserver.alerts.yml`, `build.alerts.yml`, `host.alerts.yml`, `mariadb.alerts.yml`. The others are removed; `fxserver.alerts.yml` needs `fxserver.recording.yml`. Rules without data stay silent. |
| `gameserver_observability_grafana_dashboards` | bool | `false` | Adds the dashboard "Game server overview" to a Grafana on this host (provider file and dashboard JSON); a running Grafana is restarted when the provider file changes. |
| `gameserver_observability_grafana_provisioning_dir` | path | `/etc/grafana/provisioning` | Grafana's provisioning folder; must exist when the dashboard is enabled. |
| `gameserver_observability_grafana_dashboards_dir` | path | `/var/lib/grafana/dashboards/gameserver-observability` | Folder for the dashboard JSON. |
| `gameserver_observability_grafana_service` | str | `grafana-server.service` | systemd unit of Grafana; restarted only when it runs. |
| `gameserver_observability_firewall_manage` | bool | `false` | `false` writes `/etc/nftables.d/50-observability.nft` only when `/etc/nftables.d` exists; `true` also creates the directory and installs nftables. |
| `gameserver_observability_firewall_reload` | bool | `true` | Restart `nftables.service` after the drop-in changed. |
| `gameserver_observability_firewall_sources` | list of str | `[]` | IPv4 or IPv6 addresses or networks that may reach both exporter ports, for example a second Prometheus. Needs a private, not a loopback, listen address; `/0` networks are refused. |

## The scrape jobs

The role renders the pack's scrape jobs with one entry per game server:

| Job | What it reads | Interval |
|---|---|---|
| `fxserver_perf` | `/perf/` on the game port with basic auth: the tick-time histogram, renamed to `fxserver_tick_time_seconds_*{thread=…}` | 15 s |
| `fxserver_json` | `/dynamic.json` (client count, slots) and `/info.json` (version, build, OneSync) through json_exporter | 30 s |
| `fxserver_blackbox` | the game port accepts TCP, `/info.json` answers, `/perf/` refuses a request without credentials (401) | 30 s |
| `fxserver_tunnel` | with `gameserver_observability_admin_probes`: each hostname redirects or refuses a request without a login | 60 s |
| `fxserver_versions` | with `gameserver_observability_versions_job`: the platform's current Recommended build | 4 min |

The pack's metrics reference, alerts and runbook are in its repository
([metrics](https://github.com/luminare-dev/gameserver-observability/blob/main/docs/metrics.md),
[runbook](https://github.com/luminare-dev/gameserver-observability/blob/main/docs/runbook.md)).

The pack's metrics and alert runbook are in its repository
([metrics](https://github.com/luminare-dev/gameserver-observability/blob/main/docs/metrics.md),
[runbook](https://github.com/luminare-dev/gameserver-observability/blob/main/docs/runbook.md)).

## The vendored pack

`files/pack/` holds the files of one pack release, with their sha256 in `manifest.json`.
`scripts/check_vendored_pack.py` checks them against the manifest and against the release archive.
To move to a new pack release:

```bash
gh release download v0.2.0 --repo luminare-dev/gameserver-observability --pattern 'gameserver-observability-*.tar.gz'
python3 scripts/check_vendored_pack.py --update-from gameserver-observability-0.2.0.tar.gz
# set commit, release_tag and release_sha256 in files/pack/manifest.json, then:
python3 scripts/check_vendored_pack.py
```

Then compare `templates/scrape_configs.yml.j2` with the new scrape files; the unit test fails
while they differ.

## Firewall

The drop-in `50-observability.nft` accepts the two exporter ports from
`gameserver_observability_firewall_sources` only (none by default; a Prometheus on the same host
uses loopback). List only Prometheus hosts: both exporters fetch whatever target a request names.

## Tests

```bash
cd roles/gameserver_observability
molecule test
```

The scenario runs the fake server build, Prometheus 3.15.0 and the role in one container and
checks the result through Prometheus' API. Grafana and Alertmanager are not installed by the role
or the test.
