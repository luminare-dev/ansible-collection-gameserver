# luminare.gameserver.fxserver

Installs a game server build (FXServer, for FiveM/RedM servers) on Debian 13 or Ubuntu 24.04 and
runs it as a hardened systemd service, either directly with `server.cfg` or under txAdmin
(`fxserver_mode`). Updates and rollbacks switch one symbolic link; the server is checked after
every switch and a build that does not answer is rolled back. server-data and txData are backed
up before every switch and, optionally, every night.

Not affiliated with or endorsed by Cfx.re, Rockstar Games or Take-Two.

All settings are checked before the first change, and the license key is never printed.

## Layout on the host

```text
/opt/fxserver/                    fxserver:fxserver 0750 (home of the service user)
├── artifacts/
│   ├── 35245/                    an unpacked build (run.sh at the top)
│   ├── 35246/
│   ├── current -> .../35246      the build the unit runs
│   └── previous -> .../35245     the rollback target
├── server-data/                  working directory: server.cfg, secrets.cfg (0600), resources
└── txData/
/etc/systemd/system/fxserver.service
/etc/systemd/system/fxserver-backup.{service,timer}
/etc/systemd/journald.conf.d/60-fxserver.conf
/etc/nftables.d/45-fxserver.nft   only with the luminare.infra_edge firewall layout
/usr/local/sbin/fxserver-backup
/var/backups/fxserver/            root:root 0700, fxserver-<UTC time>-<label>.tar.zst (0600)
```

## Example playbook

Install the collection first (see the [installation guide](../../docs/install.md)). Keep the
license key in an encrypted variables file, for example with SOPS or Ansible Vault:

```yaml
# group_vars/gameservers/secrets.yml (encrypted; the role refuses this placeholder)
fxserver_license_key: CHANGE_ME_LICENSE_KEY
```

Set `fxserver_perf_password` there as well (24 characters or more) when `/perf/` is scraped;
without it the role writes a random password, so `/perf/` is closed to everyone.

```yaml
- name: Game server
  hosts: gameservers
  become: true
  roles:
    - role: luminare.gameserver.fxserver
      vars:
        fxserver_server_data_repo: git@github.com:example/server-data.git
        fxserver_server_data_version: main
        fxserver_backup_timer_enabled: true
        fxserver_textfile_dir: /var/lib/node_exporter/textfile_collector
```

Without `fxserver_server_data_repo` the role writes a minimal `server.cfg` (connect button
disabled, no resources) from `fxserver_cfg`, for example
`fxserver_cfg: {hostname: "Test server", max_clients: 16, resources: [my-resource]}`.

## Variables

Every variable is validated by `meta/argument_specs.yml`.

| Variable | Type | Default | Description |
|---|---|---|---|
| `fxserver_user` | str | `fxserver` | System user and group that run the server; owner of the server directories. |
| `fxserver_base_dir` | path | `/opt/fxserver` | Base directory and home of the service user; the service may write below it. |
| `fxserver_artifacts_dir` | path | `{{ fxserver_base_dir }}/artifacts` | Unpacked builds (`<build>/`) and the links `current` and `previous`. |
| `fxserver_server_data_dir` | path | `{{ fxserver_base_dir }}/server-data` | server-data (`server.cfg`, `secrets.cfg`, resources); working directory of the unit. |
| `fxserver_txdata_dir` | path | `{{ fxserver_base_dir }}/txData` | txData directory; created empty and included in backups. |
| `fxserver_build` | int | `35245` | Build number to run. A build that is not on disk yet is downloaded from `fxserver_artifact_url`; one that is (the previous build, for example) is switched to without a download. |
| `fxserver_artifact_url` | str | the official download of build 35245 | Download URL of `fxserver_build` (`fx.tar.xz`); its path must name the build number. Only used when the build is not on disk yet. |
| `fxserver_artifact_sha256` | str | `16fcffd53a30a3909cbb2cfd26f89f950a59452792cafd0eda2174bdfeef9b2f` | sha256 of the download; required, the download fails when it differs. The platform publishes no checksums; record it from your own download ([upgrade guide](../../docs/upgrade.md)). |
| `fxserver_keep_builds` | int | `2` | Build directories kept on disk, in this order: the active build, the previous build, then the highest build numbers. |
| `fxserver_server_data_repo` | str | `""` | Git URL of your server-data repository; empty means the role writes a minimal `server.cfg` from `fxserver_cfg`. The repository's `server.cfg` must contain `exec secrets.cfg`; keep `secrets.cfg` and `cache/` out of it (`.gitignore`). |
| `fxserver_server_data_version` | str | `main` | Branch, tag or commit of `fxserver_server_data_repo`. |
| `fxserver_server_data_deploy_key` | str | `""` | Private SSH key for `fxserver_server_data_repo`; secret. Use a read-only deploy key: it is on disk (owner `fxserver`, mode 0600) only while the role checks out the repository, and the server runs as that user. |
| `fxserver_cfg` | dict | `{}` | Settings for the templated `server.cfg` (only without `fxserver_server_data_repo`); keys left out keep their defaults (table below). |
| `fxserver_license_key` | str | `""` | Server license key, written to `secrets.cfg` as `sv_licenseKey`; secret. Required when `fxserver_service_state` is `started`; the placeholder `CHANGE_ME_LICENSE_KEY` is refused. |
| `fxserver_perf_user` | str | `prometheus` | User name for `/perf/` (`sv_prometheusBasicAuthUser`). |
| `fxserver_perf_password` | str | `""` | Password for `/perf/` (`sv_prometheusBasicAuthPassword`), at least 24 characters. Empty never leaves `/perf/` open: the role keeps the password that `secrets.cfg` already has or writes a random one ([`/perf/`](#perf)); set it to scrape `/perf/`. With the txadmin role's observability toggle (`txadmin_prometheus_basic_auth`) enabled, its user and password are written instead, and this variable must stay empty. |
| `fxserver_secrets_cfg_extra` | dict | `{}` | Further secret convars for `secrets.cfg` as name/value pairs, for example `mysql_connection_string`. |
| `fxserver_mode` | str | `plain` | `plain` starts the server directly with `server.cfg`; `txadmin` starts txAdmin, which starts the server after its one-time web setup ([Running under txAdmin](#running-under-txadmin)). |
| `fxserver_game_port` | int | `30120` | Game port (tcp and udp); also used by the templated `server.cfg` and the firewall drop-in. |
| `fxserver_service_enabled` | bool | `true` | Start `fxserver.service` at boot. |
| `fxserver_service_state` | str | `started` | `started` or `stopped` after the run; the health check runs only for `started`. |
| `fxserver_healthcheck_url` | str | `http://127.0.0.1:{{ fxserver_game_port }}/info.json`, or `http://127.0.0.1:40120/` with `fxserver_mode: txadmin` | URL that must answer with status 200 after every run; change it when the server (or txAdmin) does not listen on 127.0.0.1 or on that port. |
| `fxserver_healthcheck_timeout` | int | `180` | Seconds to wait for the health check (at least 5). |
| `fxserver_rollback_on_failure` | bool | `true` | When the health check fails after a build switch, switch back to the previous build and fail the run. |
| `fxserver_journald_retention` | str | `14day` | `MaxRetentionSec` for journald (host-wide drop-in `60-fxserver.conf`); empty removes the drop-in. |
| `fxserver_firewall_manage` | bool | `false` | `false` writes `/etc/nftables.d/45-fxserver.nft` only when `/etc/nftables.d` exists; `true` also creates the directory and installs nftables. Either way, when the file is written, `/etc/nftables.conf` must exist, define `table inet filter` and include `/etc/nftables.d/*.nft` (and `nft` must be installed, unless this is `true`), or the run stops before any change. |
| `fxserver_firewall_reload` | bool | `true` | Restart `nftables.service` after the drop-in changed. |
| `fxserver_firewall_sources` | list of str | `["0.0.0.0/0", "::/0"]` | Addresses or networks that may reach the game port; an empty list writes no rule. |
| `fxserver_textfile_dir` | str | `""` | node_exporter textfile collector directory for `fxserver_artifact.prom` and `fxserver_backup.prom`; empty writes none. |
| `fxserver_backup_dir` | path | `/var/backups/fxserver` | Directory of the backup archives (root only, mode 0700). |
| `fxserver_backup_keep` | int | `3` | Newest archives kept in `fxserver_backup_dir`; older ones are removed after each backup. |
| `fxserver_backup_before_update` | bool | `true` | Stop the server and back up before every build switch (update or rollback), before the run writes server-data and `secrets.cfg`. |
| `fxserver_backup_timer_enabled` | bool | `false` | Enable `fxserver-backup.timer` (a backup while the server runs). |
| `fxserver_backup_timer_on_calendar` | str | `*-*-* 04:30:00` | `OnCalendar` of `fxserver-backup.timer` (local time of the host, plus up to 10 minutes random delay). |
| `fxserver_backup_paths` | list of path | `["{{ fxserver_server_data_dir }}", "{{ fxserver_txdata_dir }}"]` | Absolute paths in each archive; also the paths to give an off-host backup tool such as restic. |
| `fxserver_backup_exclude` | list of path | `["{{ fxserver_server_data_dir }}/cache"]` | Absolute paths left out of each archive (the server rebuilds its cache). |

Keys of `fxserver_cfg` (unknown keys are refused; the text values are written into quoted
`server.cfg` lines, so quotes and line breaks in them are refused too):

| Key | Default | `server.cfg` line |
|---|---|---|
| `endpoint` | `0.0.0.0` | `endpoint_add_tcp` and `endpoint_add_udp` with `fxserver_game_port` |
| `hostname` | `Game server` | `sv_hostname` (at most 120 characters) |
| `project_name` | `Game server` | `sets sv_projectName` (at most 40 characters) |
| `project_desc` | `A game server set up with Ansible.` | `sets sv_projectDesc` (at most 250 characters) |
| `locale` | `en-US` | `sets locale` |
| `max_clients` | `32` | `sv_maxclients` (1-2048; from 32 `onesync` must be `on` or `legacy`, above 64 `on`) |
| `onesync` | `"on"` | `set onesync` (`on`, `legacy` or `off`) |
| `enforce_game_build` | `""` | `sv_enforceGameBuild` (left out when empty) |
| `master1_disabled` | `true` | `sv_master1 ""`: disables the connect button in the server browser. It does **not** de-list the server; use `lan` for that. |
| `lan` | `false` | `sv_lan true` when `true`: LAN-only, the server does not appear in the public server list. The role still requires `fxserver_license_key`. |
| `appear_allowlisted` | `true` | `sets sv_appearAllowlisted true`: a lock icon in the server browser |
| `request_paranoia` | `1` | `set sv_requestParanoia` (0-3): 1 blocks JSON requests with a `Via` header (proxies), 2 also those with `Upgrade-Insecure-Requests` (browsers); they get "Nope." and the address is blocked. The health check sends neither header. |
| `resources` | `[]` | one `ensure <resource>` line each (letters, digits, `_`, `.` and `-`) |
| `extra_lines` | `[]` | further lines before `exec secrets.cfg` (never secrets) |

The template also writes `sv_scriptHookAllowed 0`, and no `rcon_password` (the remote console
stays off). It leaves out `sv_endpointPrivacy`: builds from July 2026 on (35245 included) never
show player addresses on the HTTP endpoints and print a warning when the setting is set to true.

The template also writes `sv_scriptHookAllowed 0` and no `rcon_password`. Gameplay-related
settings (`sv_pureLevel`, `sv_entityLockdown`, ...) depend on your resources, so add them with
`extra_lines` if you want them. A server-data repository brings its own `server.cfg` instead.

## `/perf/`

The server answers `/perf/` to anyone when no basic auth is set, so `secrets.cfg` always sets it:
`fxserver_perf_password` (or the txadmin role's toggle) if given, otherwise a random password that
stays on the host. To scrape `/perf/`, set `fxserver_perf_password` and give Prometheus the same
value (`gameserver_observability_perf_password`).

## Updates and rollbacks

- **Update:** set `fxserver_build`, `fxserver_artifact_url` and `fxserver_artifact_sha256`
  together and run the playbook.
- **Rollback:** set `fxserver_build` to the previous build; it is still on disk, so nothing is
  downloaded.

See the [upgrade guide](../../docs/upgrade.md) for finding the Recommended build and rolling back
by hand.

## Running under txAdmin

With `fxserver_mode: txadmin` the unit starts `run.sh` without `+exec`, which starts txAdmin, and
sets `TXHOST_DATA_PATH` to `fxserver_txdata_dir`. txAdmin starts the game server only after its
one-time web setup, so the health check waits for txAdmin's web page instead of `/info.json`.
Configure txAdmin with [`luminare.gameserver.txadmin`](../txadmin/README.md) right after this role.
Game ports 40120-40150 are refused in this mode.

## Backups

`fxserver-backup [label]` writes `fxserver-<UTC time>-<label>.tar.zst` into `fxserver_backup_dir`
(root only; the archives contain `secrets.cfg`) and keeps the newest `fxserver_backup_keep`. For
copies off the host, point a tool such as restic at the same paths:

```bash
restic backup /opt/fxserver/server-data /opt/fxserver/txData \
  --exclude /opt/fxserver/server-data/cache
```

Restoring is described in the [runbook](../../docs/runbook.md#restore-a-backup-of-server-data-and-txdata).

## Firewall

The role follows the layout of the `luminare.infra_edge` base role: `/etc/nftables.conf` defines
`table inet filter` and includes `/etc/nftables.d/*.nft`. The drop-in `45-fxserver.nft` only
accepts the game port from `fxserver_firewall_sources`, and it is checked with `nft --check`
before it replaces the old one. Without `/etc/nftables.d` (and `fxserver_firewall_manage: false`)
no firewall file is written.

## Metrics

With `fxserver_textfile_dir` set, the role writes `fxserver_artifact_build`,
`fxserver_artifact_installed_timestamp_seconds` and
`fxserver_backup_last_success_timestamp_seconds` for the node_exporter textfile collector.

## Tests

```bash
cd roles/fxserver
molecule test                    # default scenario
molecule test -s upgrade         # update and rollback
```

Both scenarios use a fake server build (`tests/fake-artifact/`), so the hardened unit has not been
run against a real build yet.
