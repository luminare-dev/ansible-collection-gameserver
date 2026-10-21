# luminare.gameserver.fxserver

Installs a game server build (FXServer, for FiveM/RedM servers) on Debian 13 or Ubuntu 24.04 and
runs it as a hardened systemd service. It updates and rolls back by switching one symbolic link,
checks the server after every switch, and backs up server-data and txData before every switch
and, if you want, every night.

Not affiliated with or endorsed by Cfx.re, Rockstar Games or Take-Two.

## What the role does

1. Checks the settings: platform (Debian or Ubuntu on x86_64), port, limits from the platform
   documentation for `server.cfg` (and no quotes or line breaks in its quoted values), the
   license key (never shown; empty or the placeholder `CHANGE_ME_LICENSE_KEY` is refused when
   the server is to run) and, when the firewall drop-in is to be written, `nft` and an
   `/etc/nftables.conf` that includes `/etc/nftables.d/*.nft`. A failed check stops the run
   before any change.
2. Installs `ca-certificates`, `tar`, `xz-utils` and `zstd`, plus `git` and `acl` with
   `fxserver_server_data_repo` and `nftables` with `fxserver_firewall_manage: true`. It creates the
   system user and group `fxserver` (no login shell) and the directories. `acl` provides
   `setfacl`, which Ansible needs to run the git checkout as the service user when it connects
   as a non-root user (for example on a host without root login).
3. Downloads the build from `fxserver_artifact_url` only when it is not on disk yet, checks it
   against `fxserver_artifact_sha256` (required), unpacks it into a temporary directory and moves
   it to `artifacts/<build>/` in one step. The downloaded archive is deleted afterwards.
4. Sets the journald retention (`MaxRetentionSec`, default 14 days), writes the nftables drop-in
   `/etc/nftables.d/45-fxserver.nft` for the game port and installs the hardened unit
   `fxserver.service`.
5. Installs `/usr/local/sbin/fxserver-backup`, `fxserver-backup.service` and
   `fxserver-backup.timer`.
6. When the build changes: stops the server and runs a backup (`pre-update-<old>-to-<new>`)
   before it writes anything below server-data, so the archive holds server-data, `secrets.cfg`
   and txData from before this run. A failed backup stops the run and starts the old build again
   (if it was running).
7. Writes server-data: a git checkout of `fxserver_server_data_repo` as the service user, or a
   minimal `server.cfg` from `fxserver_cfg`. A deploy key is written only for the checkout and
   removed right after it, also when the checkout fails. It writes `secrets.cfg` (mode 0600,
   `no_log`) with the license key and the `/perf/` credentials (see [`/perf/`](#perf)) and checks
   that `server.cfg` contains the line `exec secrets.cfg`. If this step fails after the server
   was stopped for the backup, the role starts the old build again and stops the run.
8. When the build changes: points `artifacts/previous` at the old build and replaces
   `artifacts/current` with one `rename(2)`.
9. Restarts the server when the build, the unit, `server.cfg` or `secrets.cfg` changed. On every
   run that leaves the server started it then waits until `fxserver_healthcheck_url` (default
   `/info.json` on the game port) answers with status 200. If that fails within
   `fxserver_healthcheck_timeout` seconds after a switch, the role switches back to the old build,
   restarts it, checks it again and fails the run with a message that names both builds.
10. Removes builds beyond `fxserver_keep_builds` (never the active one; the previous one second)
    and writes the textfile metrics.

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
| `fxserver_perf_password` | str | `""` | Password for `/perf/` (`sv_prometheusBasicAuthPassword`), at least 24 characters. Empty never leaves `/perf/` open: the role keeps the password that `secrets.cfg` already has or writes a random one ([`/perf/`](#perf)); set it to scrape `/perf/`. |
| `fxserver_secrets_cfg_extra` | dict | `{}` | Further secret convars for `secrets.cfg` as name/value pairs, for example `mysql_connection_string`. |
| `fxserver_game_port` | int | `30120` | Game port (tcp and udp); also used by the templated `server.cfg` and the firewall drop-in. |
| `fxserver_service_enabled` | bool | `true` | Start `fxserver.service` at boot. |
| `fxserver_service_state` | str | `started` | `started` or `stopped` after the run; the health check runs only for `started`. |
| `fxserver_healthcheck_url` | str | `http://127.0.0.1:{{ fxserver_game_port }}/info.json` | URL that must answer with status 200 after every run; change it when the server does not listen on 127.0.0.1 (`fxserver_cfg.endpoint`). |
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
| `master1_disabled` | `true` | `sv_master1 ""`: disables the connect button in the server browser. It does **not** de-list the server (see [Limitations](#limitations)). |
| `lan` | `false` | `sv_lan true` when `true`: LAN-only, the server does not appear in the public server list. The platform documentation says that this mode also skips the license key check; the role still requires `fxserver_license_key`. |
| `appear_allowlisted` | `true` | `sets sv_appearAllowlisted true`: a lock icon in the server browser |
| `request_paranoia` | `1` | `set sv_requestParanoia` (0-3): 1 blocks JSON requests with a `Via` header (proxies), 2 also those with `Upgrade-Insecure-Requests` (browsers); they get "Nope." and the address is blocked. The health check sends neither header. |
| `resources` | `[]` | one `ensure <resource>` line each (letters, digits, `_`, `.` and `-`) |
| `extra_lines` | `[]` | further lines before `exec secrets.cfg` (never secrets) |

The template also writes `sv_scriptHookAllowed 0`, and no `rcon_password` (the remote console
stays off). It leaves out `sv_endpointPrivacy`: builds from July 2026 on (35245 included) never
show player addresses on the HTTP endpoints and print a warning when the setting is set to true.

### Why `server.cfg` is minimal

The template sets what the role needs to run and check the server (endpoints, names, slots,
OneSync, the HTTP endpoint settings above) and nothing that changes gameplay. Settings such as
`sv_pureLevel`, `sv_entityLockdown`, `sv_filterRequestControl`, `sv_enableNetworkedSounds` and
`sv_enableNetworkedScriptEntityStates` limit what clients and resources may do, so the right
values depend on the resources a server runs: entity lockdown, for example, blocks entities that
client scripts create, which many resources do. None of them was tested with a real build here.
Add them with `extra_lines` after checking them against your resources, for example:

```yaml
fxserver_cfg:
  extra_lines:
    - sv_pureLevel 1
    - set sv_entityLockdown relaxed
    - set sv_filterRequestControl 2
    - set sv_enableNetworkedSounds false
    - set sv_enableNetworkedScriptEntityStates false
```

A server-data repository (`fxserver_server_data_repo`) brings its own `server.cfg` instead.

## `/perf/`

`/perf/` on the game port serves the server's tick-time metrics. Build 35245 answers it to anyone
when `sv_prometheusBasicAuthUser` and `sv_prometheusBasicAuthPassword` are both empty (its source,
`PerfHttpHandler.cpp`), so `secrets.cfg` always sets both:

- with `fxserver_perf_password`, that password and `fxserver_perf_user`;
- without it, the password that `secrets.cfg` already has from an earlier run, or on the first
  run a random password of 32 letters and digits. It stays in `secrets.cfg` on the host, so later
  runs keep it (`changed=0`); nothing that scrapes `/perf/` knows it.

To collect the metrics, set `fxserver_perf_password` from an encrypted variables file and give
Prometheus the same value.

## Updates and rollbacks

- **Update:** set `fxserver_build`, `fxserver_artifact_url` and `fxserver_artifact_sha256` of the
  new build together and run the playbook. The role backs up, switches, restarts and checks; a
  build that does not answer is rolled back automatically.
- **Rollback:** set `fxserver_build` to the previous build and run the playbook. The build is
  still on disk (it is the `previous` link), so nothing is downloaded and the URL and checksum are
  not used. On the host itself the same switch is one command; see the
  [upgrade guide](../../docs/upgrade.md), which also covers the Recommended-build policy and how
  to read the support window of a build from the version API.

## Backups

`fxserver-backup [label]` writes `fxserver-<UTC time>-<label>.tar.zst` into
`fxserver_backup_dir` (root only; the archives contain `secrets.cfg`) and keeps the newest
`fxserver_backup_keep` archives. It archives `fxserver_backup_paths` without
`fxserver_backup_exclude`. The role runs it with the server stopped before every build switch,
before that run writes server-data or `secrets.cfg`;
`fxserver_backup_timer_enabled: true` adds a daily run while the server runs (GNU tar's
"file changed as we read it" is reported, not fatal). With `fxserver_textfile_dir` set, every
backup updates `fxserver_backup_last_success_timestamp_seconds`.

These archives stay on the same disk. For backups that survive the host, point an off-host tool
at the same paths, for example restic:

```bash
restic backup /opt/fxserver/server-data /opt/fxserver/txData \
  --exclude /opt/fxserver/server-data/cache
```

To restore an archive (`--zstd` needs the `zstd` package, which the role installs):

```bash
systemctl stop fxserver
tar --zstd --extract --preserve-permissions --file /var/backups/fxserver/<archive>.tar.zst --directory /
systemctl start fxserver
```

The archive is extracted over the current files; to get an exact copy, move the old
`server-data` and `txData` aside first. The [runbook](../../docs/runbook.md) has the full steps,
which the `default` scenario runs on its newest archive.

## Firewall

The role follows the firewall layout of the `luminare.infra_edge` base role: `/etc/nftables.conf`
defines `table inet filter` with input policy drop and includes `/etc/nftables.d/*.nft` last. The
drop-in `45-fxserver.nft` holds only `add rule inet filter input … accept` lines for the game port
(tcp and udp) from `fxserver_firewall_sources`. Each new version of the file is checked together
with `/etc/nftables.conf` (`nft --check`) before it replaces the old one; then `nftables.service`
is restarted. Without `/etc/nftables.d` and with `fxserver_firewall_manage: false` the role writes
no firewall file. When it writes the file but `/etc/nftables.conf`, its `table inet filter`, its
line `include "/etc/nftables.d/*.nft"` or the `nft` command is missing, the role stops at its
first checks, before it changes anything, and says what is missing. Without the include line (as
in the `/etc/nftables.conf` of the nftables package) the drop-in would pass `nft --check` but
never be loaded.

## Metrics

With `fxserver_textfile_dir` set, the role writes `fxserver_artifact.prom` for the node_exporter
textfile collector:

```text
fxserver_artifact_build 35245
fxserver_artifact_installed_timestamp_seconds 1792540800
```

`fxserver_artifact_installed_timestamp_seconds` is the time of the `current` link, so it changes
only when that link is replaced. No metric has labels.

## Tests

Two Molecule scenarios run in systemd containers on Debian 13 and Ubuntu 24.04 with a fake build
(`tests/fake-artifact/`: a stand-in for the server that answers `/info.json`, `/dynamic.json`,
`/players.json` and `/perf/` with synthetic data). No real server build is downloaded.

- `default` (Ansible connects as root): a first install with the templated `server.cfg` (LAN
  mode on), the nftables drop-in (validated with `nft --check`), metrics and the backup timer;
  idempotence; then the unit, its hardening, the endpoints, `/perf/` basic auth, owners and
  modes, the metrics, the drop-in content, the journald retention, the absence of the key in the
  journal, four timer backups (three kept, no cache folder, mode 0600), and the runbook's restore
  of the newest archive (owners, modes and `secrets.cfg` restored, the server answers again).
- `upgrade` (Ansible connects as a non-root user with sudo, as on a host without root login):
  server-data from a git repository, with a dummy deploy key that must be gone afterwards, and
  no `/perf/` password; install 35245, idempotence, update to 35246 together with a new
  server-data commit (the backup holds the old `server.cfg`, the switch, the health check), a
  switch whose backup fails (refused), runs that stop at their checks (`/etc/nftables.d` without
  `/etc/nftables.conf`, an `/etc/nftables.conf` without the drop-in include, a quote or a line
  break in `fxserver_cfg`, a resource name with other characters), the broken build 35247
  (rolled back to 35246 automatically), then a rollback to 35245 by setting `fxserver_build`
  only; at the end `/perf/` refuses a request without credentials and answers with the random
  password from `secrets.cfg`.

```bash
cd roles/fxserver
molecule test                    # default scenario, both platforms
molecule test -s upgrade         # update and rollback scenario
```

## Limitations

- Tested only with the fake build. The unit's hardening (`ProtectSystem=strict`,
  `NoNewPrivileges` and the others) has not been run against a real, keyed server build.
- The server is started directly with `server.cfg`; running it under txAdmin is not part of this
  role.
- In containers the nftables ruleset is validated but not loaded, so the effect of the drop-in on
  traffic is not proven by the tests.
- A server with a valid license key appears in the public server list unless it runs LAN-only
  (`lan: true`, `sv_lan true`). According to the platform documentation, `sv_master1 ""`
  (`master1_disabled`) only disables the connect button and cannot de-list a server, and
  `sv_appearAllowlisted` only shows a lock icon. Outside LAN mode the `hostname`,
  `project_name` and `project_desc` of every keyed server are therefore public: give a test
  server a neutral name and description. LAN mode was tested with the fake build only, so its
  effect on a real server (listing, license key check, who may connect) was not observed here.
- Without `fxserver_perf_password` the random password closes `/perf/` according to the source of
  build 35245; a real build's answer was not probed (the fake build answers like the source).
- Backups stay on the host; copying them elsewhere (restic or similar) is up to you.
- While the role checks out server-data, the deploy key is a file of the service user, so a
  running server could read it during that time; use a read-only deploy key. The checkout over
  SSH is not tested: the scenario uses a local repository, for which the key is written and
  removed but not used.
