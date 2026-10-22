# luminare.gameserver.gameserver_observability

Wires game servers (FXServer, for FiveM/RedM servers) into an existing Prometheus with the
[gameserver-observability](https://github.com/luminare-dev/gameserver-observability) pack:
json_exporter and blackbox_exporter from their official releases, the pack's scrape jobs, recording
and alerting rules, `/perf/` basic auth through a password file and, if you want, the pack's
dashboard for an existing Grafana. Everything is collected from outside the server process, and
only counts: the role never reads `players.json`.

Not affiliated with or endorsed by Cfx.re, Rockstar Games or Take-Two.

## What the role does

1. Checks every setting before it changes anything: the platform (Debian or Ubuntu on x86_64),
   the game servers in `gameserver_observability_targets` (unique `server` labels, addresses,
   ports), the exporters' listen address (loopback or private only), the exporter versions and
   their sha256, the rule files, the admin hostname probes, the firewall sources and the `/perf/`
   credentials (never shown; empty, short or `CHANGE_ME` passwords are refused). It also checks
   that Prometheus is installed on the host: its configuration folder and `prometheus.yml`,
   promtool 2.43 or later, the Prometheus group, its unit with a reload command and, with the
   dashboard enabled, Grafana's provisioning folder. A failed check stops the run before any
   change.
2. Downloads json_exporter and blackbox_exporter from their GitHub releases (linux-amd64) into
   `/var/cache/gameserver-observability/`, checks each archive against its pinned sha256, unpacks
   it into its own folder per version below `/usr/local/lib/gameserver-observability/`, writes the
   pack's module files to `/etc/gameserver-observability/` and runs each exporter as a hardened
   systemd unit (`DynamicUser`, `ProtectSystem=strict`, `NoNewPrivileges`, no capabilities) on
   `gameserver_observability_listen_address`. A changed program, module file or unit restarts the
   exporter; older versions are removed.
3. Writes three kinds of files below the Prometheus configuration folder, each checked with
   promtool before it replaces the old one: `secrets/fxserver_perf` with the `/perf/` password
   (root, group of Prometheus, 0640, `no_log`, no diff), `scrape_configs/gameserver-observability.yml`
   with the pack's scrape jobs for every game server, and `rules/gameserver-observability-*.yml`
   with the pack's rule files. Then it checks the whole configuration with
   `promtool check config`.
4. With `gameserver_observability_grafana_dashboards: true`, writes the dashboard "Game server
   overview" and a dashboard provider file for the Grafana on the host.
5. Writes the nftables drop-in `/etc/nftables.d/50-observability.nft` (see [Firewall](#firewall)).
6. Reloads Prometheus (and restarts a running Grafana or nftables) when their files changed,
   waits until both exporters answer, and asks Prometheus' API whether it loaded the scrape jobs
   of every game server and the rule files. If it did not, for example because `prometheus.yml`
   does not include the role's files, the run fails with a message that names what is missing.

The pack's files come with the role (`files/pack/`, see [The vendored pack](#the-vendored-pack));
the role needs no checkout of the pack.

## Where it runs

The role runs on the host of the Prometheus it adds to. Two setups are supported:

- **One host:** the game server, Prometheus and the exporters on one host. The targets use
  `127.0.0.1` and the exporters listen on `127.0.0.1` (the defaults).
- **A monitoring host:** Prometheus and the exporters on a separate host that reaches the game
  servers over a private network (or a VPN or tunnel). Each target is the game server's private
  address; the game server's firewall must let the monitoring host reach the game port (the
  fxserver role's `fxserver_firewall_sources`). `/perf/` sends its basic auth in plain HTTP, so
  never scrape a game server across the internet.

The exporters listen on a private address only when another host has to reach them, for example
a second Prometheus; list that host in `gameserver_observability_firewall_sources`.

## Before you start

- **Prometheus 2.43 or later** with promtool, installed on the host, for example with the
  `prometheus` role of the `prometheus.prometheus` collection or from the official release. Its
  `prometheus.yml` must include the role's files. The `prometheus.prometheus.prometheus` role
  already does (`scrape_config_files: [scrape_configs/*]` and
  `rule_files: [/etc/prometheus/rules/*.yml, …]` with its defaults; the Molecule scenario uses
  it). For a Prometheus of your own, add:

  ```yaml
  scrape_config_files:
    - /etc/prometheus/scrape_configs/*.yml
  rule_files:
    - /etc/prometheus/rules/*.yml
  ```

  The role checks after every run that Prometheus loaded its files.
- **`/perf/` basic auth on every game server:** `sv_prometheusBasicAuthUser` and
  `sv_prometheusBasicAuthPassword` in `secrets.cfg`, from the fxserver role's
  `fxserver_perf_user` and `fxserver_perf_password` or from the txadmin role's toggle
  `txadmin_prometheus_basic_auth`. This role needs the same user and password. Without
  `fxserver_perf_password` (and the toggle) the fxserver role writes a random password that
  only the game server knows, so `/perf/` is closed and its targets show 401. A server whose two
  convars are both empty (one not set up by the fxserver role) answers `/perf/` to everyone, and
  the pack's alert `FXServerPerfEndpointExposed` fires.
- **HTTPS to github.com** from the host, for the exporter downloads (only when a version is not
  in the cache yet).

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

## Layout on the host

```text
/var/cache/gameserver-observability/    release archives (one version of each exporter)
/usr/local/lib/gameserver-observability/
├── json_exporter-0.8.0.linux-amd64/
└── blackbox_exporter-0.29.0.linux-amd64/
/etc/gameserver-observability/          json_exporter.yml and blackbox.yml (the pack's modules)
/etc/systemd/system/gameserver-observability-json-exporter.service
/etc/systemd/system/gameserver-observability-blackbox-exporter.service
/etc/prometheus/
├── scrape_configs/gameserver-observability.yml
├── rules/gameserver-observability-<rule file>.yml
└── secrets/fxserver_perf               root:prometheus 0640 (folder 0750)
/etc/nftables.d/50-observability.nft    only with the luminare.infra_edge firewall layout
/etc/grafana/provisioning/dashboards/gameserver-observability.yml      with the dashboard only
/var/lib/grafana/dashboards/gameserver-observability/game-server-overview.json
```

The exporter folders and units, the scrape file and the rule files carry `gameserver-observability`
in their names, so exporters, jobs and rules of other setups on the same host stay untouched; the
password file keeps the pack's name `fxserver_perf`.

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

The role renders the pack's jobs (`prometheus/scrape/fxserver.yml`, `tunnel.yml` and `versions.yml`
of the pack) with one entry per game server; the job names, intervals, sample limits and relabel
rules are the pack's, which a unit test (`tests/test_gameserver_observability.py`) compares job by
job:

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

## Counts only

The player count comes from `/dynamic.json` (`clients`). `players.json`, which lists every player
with names and identifiers, is never a target, and no series carries a label that names a player:
the pack's checks fail on either, and the Molecule scenario checks the scrape file, the labels
Prometheus holds and the fake server's request log for it.

## The vendored pack

`files/pack/` holds the pack files the role installs or renders, copied byte for byte from one
pack version: the json_exporter and blackbox modules, the five rule files, the dashboard and its
provider file, and the three scrape files that the role's template follows. `files/pack/manifest.json`
records the pack version (0.1.0), the pack commit the files were copied from, the sha256 of every
file, the release tag (`v0.1.0`) and the sha256 of that release's source archive.

`scripts/check_vendored_pack.py` (run by `scripts/test.sh`, so in CI's `lint-test` job) checks
every file against the manifest. When the manifest names a release tag, it also downloads that
release's source archive, checks it against the release's `SHA256SUMS` and compares every file
byte for byte; without a tag that comparison is skipped, and the output says so. To move to a new
pack release:

```bash
gh release download v0.2.0 --repo luminare-dev/gameserver-observability --pattern 'gameserver-observability-*.tar.gz'
python3 scripts/check_vendored_pack.py --update-from gameserver-observability-0.2.0.tar.gz
# set commit, release_tag and release_sha256 in files/pack/manifest.json, then:
python3 scripts/check_vendored_pack.py
```

Check the pack's changelog for changed jobs, and the role's template (`templates/scrape_configs.yml.j2`)
against the new scrape files: the unit test fails while they differ.

## Firewall

The role follows the firewall layout of the `luminare.infra_edge` base role: `/etc/nftables.conf`
defines `table inet filter` with input policy drop and includes `/etc/nftables.d/*.nft` last. The
drop-in holds accept rules for the two exporter ports from `gameserver_observability_firewall_sources`
only, for example:

```text
add rule inet filter input ip saddr { 198.51.100.0/24 } tcp dport 7979 accept
add rule inet filter input ip saddr { 198.51.100.0/24 } tcp dport 9115 accept
```

Without sources it holds no rule: Prometheus on the same host reaches the exporters through the
loopback interface, which the base layout accepts. List only Prometheus hosts: both exporters
fetch whatever target a request names (`/probe?target=…`), so anyone who reaches them can make
the host send requests. The file is checked with `nft --check` together
with `/etc/nftables.conf` before it replaces the old one. When the role writes the file
(`/etc/nftables.d` exists or `gameserver_observability_firewall_manage` is `true`), it stops at
its first checks, before any change, unless `/etc/nftables.conf` defines `table inet filter` and
has the line `include "/etc/nftables.d/*.nft"`: without that line (as in the nftables package's
own file) the drop-in would validate but never be loaded. The game port on the game servers
belongs to the fxserver role (`45-fxserver.nft`).

## Tests

The Molecule scenario `default` runs in systemd containers on Debian 13 and Ubuntu 24.04. Its
`prepare.yml` installs the fake build (`tests/fake-artifact/`) the way the fxserver role's
scenario does and Prometheus 3.15.0 with the `prometheus` role of `prometheus.prometheus` 0.30.2
(its download checked against the release's sha256); `converge.yml` runs the fxserver role with
`/perf/` basic auth and then this role, with two targets on the same fake server: `game-01` over
loopback and `game-02` over the container's private address, as a monitoring host would reach it.
After the idempotence run, `verify.yml` checks:

- both exporter units (running, enabled, hardened, on the private address and not on loopback)
  and their archives against the pinned sha256;
- every installed pack file against the sha256 in the manifest, the password file (owner, group,
  mode, content) and the scrape file (jobs, targets, `password_file`, no `players.json`);
- the nftables drop-in (exact lines, accept rules only) with `nft --check`;
- in Prometheus' API: all 13 targets of the pack up, the three probes of each server successful
  (game port, `/info.json`, `/perf/` refused without credentials), every `fxserver_*` series of
  the pack for both servers with the fake's values (3 clients, 48 slots, build 35245, three
  threads), no label or metric name about a player, the five rule groups evaluated without an
  error, the recorded tick-time p95 and no outage alert;
- `/perf/` directly: status 401 without credentials and with a wrong password, the histogram with
  the password; the fake server's request log shows `/perf/`, `/dynamic.json` and `/info.json`,
  never `players.json` and never the password;
- the dashboard provider file;
- six runs with settings that must be refused (listen address `0.0.0.0`, a `CHANGE_ME` password,
  two targets with one label, firewall sources with a loopback listen address, no Prometheus at
  the configured place, an `/etc/nftables.conf` without the drop-in include), which leave the
  role's files unchanged, and a run whose files Prometheus does not include, which fails with the
  missing job;
- a last run with the two game server rule files only, which removes the other three and a rule
  file left over from an older pack version.

```bash
cd roles/gameserver_observability
molecule test
```

## Limitations

- Tested with the fake build only, so the `/perf/` answer of a real server with and without
  credentials, and the fields of its `/info.json` and `/dynamic.json`, were not checked by this
  role (the pack documents which of its sources were checked).
- Grafana is not installed in the test: the scenario checks the provider file and the dashboard
  JSON the role writes, not that Grafana loads them (the pack's demo does that).
- The firewall drop-in is validated with `nft --check` but not loaded in the test container.
- Only x86_64 hosts: the exporter downloads are the linux-amd64 archives.
- No metrics from txAdmin's `/host/status` (a json_exporter module with the `x-txadmin-envtoken`
  header): the pack has no such module yet, because the fields of that answer have not been read
  from a real txAdmin.
- The role installs neither Prometheus nor Grafana, nor node_exporter and mysqld_exporter for the
  host and database alerts, and no Alertmanager: alerts show in Prometheus' web page until you
  connect one.
- The role reloads Prometheus through its unit's reload command (`ExecReload`, for example
  `kill -HUP` as in the `prometheus.prometheus` unit) and refuses a unit without one; for such a
  Prometheus set `gameserver_observability_prometheus_reload: false` and reload it yourself.
