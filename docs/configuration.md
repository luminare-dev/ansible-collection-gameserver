# Configuration

Each role prefixes its variables with the role name, validates them with
`roles/<role>/meta/argument_specs.yml` and documents them in a table in `roles/<role>/README.md`.
Set them in your inventory (`group_vars/`, `host_vars/`) or in the play.

## Playbook

The playbook `luminare.gameserver.gameserver` ([`playbooks/gameserver.yml`](../playbooks/gameserver.yml))
reads two variables of its own. Ansible evaluates a play's `hosts` and `serial` before it loads
inventory variables, so pass them as extra variables (`-e`); in `group_vars` they have no effect.

| Option | Type | Default | Description |
|---|---|---|---|
| `gameserver_hosts` | str | `gameservers` | Host pattern the play runs on. |
| `gameserver_serial` | int or str | `1` | Hosts per batch (Ansible's `serial`, for example `2` or `"25%"`). The play stops at the first host that fails (`max_fail_percentage: 0`), so later hosts keep their build. |

In txAdmin mode the playbook first checks the firewall layout with the txadmin role's rules; it
reads `txadmin_firewall_required` (the check is skipped when it is `false`) and
`txadmin_firewall_manage` (then `/etc/nftables.d` and `nft` may still be missing). Everything
else comes from the role variables below. The example inventory
[`examples/inventory/`](../examples/inventory/) sets them for one host in the group `gameservers`:

| File | What it sets |
|---|---|
| `hosts.yml` | One host (`play.example.com`, `192.0.2.10`, documentation values) with a sudo user. |
| `group_vars/gameservers/main.yml` | `fxserver_mode: txadmin`, a minimal `server.cfg` with a neutral name (`fxserver_cfg`), the nightly backup, and for txAdmin its public URL, slot limit, game, master account name and one firewall source. |
| `group_vars/gameservers/secrets.yml` | `CHANGE_ME_` placeholders for the license key, the API token, the master account's bcrypt hash and the `/perf/` password. Replace them and encrypt the file. |

The server build is the role default (build 35245 with its sha256); to pin another, set
`fxserver_build`, `fxserver_artifact_url` and `fxserver_artifact_sha256` together
([upgrade guide](upgrade.md#update)).

## fxserver

The full table, with the keys of `fxserver_cfg`, is in the
[fxserver README](../roles/fxserver/README.md#variables). The settings you change most often:

| Option | Type | Default | Description |
|---|---|---|---|
| `fxserver_build` | int | `35245` | Build number to run; with a new build also set the next two ([upgrade guide](upgrade.md#update)). |
| `fxserver_artifact_url` | str | the official download of build 35245 | Download URL of the build; its path must name the build number. |
| `fxserver_artifact_sha256` | str | sha256 of that download | Required; the download fails when it differs. |
| `fxserver_license_key` | str | `""` | Server license key (secret, see below); required to start the server. |
| `fxserver_server_data_repo` | str | `""` | Git URL of your server-data; empty writes a minimal `server.cfg` from `fxserver_cfg`. |
| `fxserver_cfg` | dict | `{}` | Settings of the templated `server.cfg` (host name, slots, OneSync, resources, ...). |
| `fxserver_firewall_sources` | list of str | `["0.0.0.0/0", "::/0"]` | Who may reach the game port; written to `/etc/nftables.d/45-fxserver.nft`. |
| `fxserver_textfile_dir` | str | `""` | node_exporter textfile collector directory for the build and backup metrics. |
| `fxserver_backup_keep` | int | `3` | Backup archives kept in `/var/backups/fxserver`. |
| `fxserver_backup_timer_enabled` | bool | `false` | Adds a daily backup to the one before every build switch. |
| `fxserver_mode` | str | `plain` | `txadmin` starts txAdmin instead of the game server; use it with the txadmin role. |

## txadmin

The full table is in the [txadmin README](../roles/txadmin/README.md#variables). It needs the
fxserver role with `fxserver_mode: txadmin` first in the same play. The settings you change most
often:

| Option | Type | Default | Description |
|---|---|---|---|
| `txadmin_firewall_sources` | list of str | `[]` | Who may reach port 40120 besides the host itself, for example the tunnel connector; written to `/etc/nftables.d/40-txadmin.nft`. |
| `txadmin_default_account_name` | str | `""` | Master account that txAdmin creates on its first start (with a FiveM ID, a bcrypt hash or both). |
| `txadmin_api_token` | str | `""` | Token for `/host/status` (secret); empty keeps the endpoint off. |
| `txadmin_prometheus_basic_auth` | dict | `{enabled: false, user: prometheus, password: ""}` | Observability toggle: basic auth for `/perf/` in `secrets.cfg`; set it in the inventory, where the fxserver role reads it too. |
| `txadmin_interface` | str | `""` | Leave it empty; a loopback address is refused, because txAdmin would force the game server onto it. |
| `txadmin_max_slots` | int | `0` | Highest `sv_maxclients` txAdmin accepts; `0` leaves it unset. |

## gameserver_observability

The full table is in the
[gameserver_observability README](../roles/gameserver_observability/README.md#variables). The
role runs on the host of an existing Prometheus (the game server itself or a monitoring host), not
through the playbook `luminare.gameserver.gameserver`. The settings you change most often:

| Option | Type | Default | Description |
|---|---|---|---|
| `gameserver_observability_targets` | list of dict | `[{server: game-01, address: 127.0.0.1, port: 30120}]` | Game servers to watch: the `server` label the dashboard and alerts show, the address Prometheus reaches the game port on, and the port. |
| `gameserver_observability_perf_password` | str | `""` | The game servers' `/perf/` password (secret, required); the same value as `fxserver_perf_password` or the txadmin role's toggle. |
| `gameserver_observability_perf_user` | str | `prometheus` | The game servers' `/perf/` user. |
| `gameserver_observability_listen_address` | str | `127.0.0.1` | Where json_exporter (7979) and blackbox_exporter (9115) listen: loopback or a private address. |
| `gameserver_observability_prometheus_config_dir` | path | `/etc/prometheus` | Prometheus' configuration folder; `prometheus.yml` must include `scrape_configs/*.yml` and `rules/*.yml` below it. |
| `gameserver_observability_rule_files` | list of str | all five rule files of the pack | Rule files to install. |
| `gameserver_observability_admin_probes` | list of dict | `[]` | Admin hostnames behind an access-protected tunnel to probe. |
| `gameserver_observability_versions_job` | bool | `false` | Read the platform's version list for the alert about an outdated build (outbound HTTPS). |
| `gameserver_observability_grafana_dashboards` | bool | `false` | Add the dashboard "Game server overview" to a Grafana on the same host. |
| `gameserver_observability_firewall_sources` | list of str | `[]` | Who may reach the exporter ports from other hosts; written to `/etc/nftables.d/50-observability.nft`. |

## Secrets

Secrets never go into this repository, an issue or a log. Keep them in an encrypted variables file
(for example with SOPS or Ansible Vault) on the controller, and pass them to the roles as
variables. Tasks that handle a secret run with `no_log: true`; templates with secrets also use
`diff: false`.

The `fxserver` role takes these secrets: `fxserver_license_key`, `fxserver_perf_password`,
`fxserver_server_data_deploy_key` and the values of `fxserver_secrets_cfg_extra` (for example a
database connection string). It writes the first, second and fourth into
`/opt/fxserver/server-data/secrets.cfg` (mode 0600), which `server.cfg` runs with
`exec secrets.cfg`. Without `fxserver_perf_password` (and without the txadmin role's toggle) it
writes a random `/perf/` password there instead and keeps it on later runs, because the server
answers `/perf/` to anyone when no credentials are set. The deploy key is written to
`/opt/fxserver/.ssh/` (mode 0600) only for the git checkout and removed right after it; use a
read-only deploy key, because the server runs as the same user.

Server license keys need extra care: the platform scans public repositories for them, and a
leaked key has to be replaced. In examples and test data, write the placeholder
`CHANGE_ME_LICENSE_KEY`, never a value that starts like a real key; the role refuses to start the
server with that placeholder. CI scans every commit with gitleaks and two license-key rules in
`.gitleaks.toml`; a leaked secret is rotated first and removed from history second.

The `txadmin` role takes these secrets: `txadmin_api_token`,
`txadmin_default_account_password_hash`, the password in `txadmin_prometheus_basic_auth` and the
values of `txadmin_deployer_prefill`. It writes the token, the hash and the pre-fill values into
`/etc/fxserver/txadmin.env` (owner root, mode 0600), which systemd reads as root and passes to
txAdmin as `TXHOST_*` variables; the `/perf/` password goes into `secrets.cfg` through the
fxserver role. The role refuses `CHANGE_ME` placeholders for the token and the `/perf/` password, and checks every value before it writes
it, because txAdmin can print an invalid value to its log when it stops at boot.

The `gameserver_observability` role takes one secret, `gameserver_observability_perf_password`,
and writes it to `/etc/prometheus/secrets/fxserver_perf` (owner root, group of Prometheus, mode
0640, `no_log`, no diff), which Prometheus reads through `password_file`; the scrape
configuration holds only the file's path. The role refuses an empty value and `CHANGE_ME`
placeholders. Prometheus sends the password in plain HTTP to the game port, so scrape game
servers on the same host or over a private network only.

The backup archives in `/var/backups/fxserver` contain `secrets.cfg` and txAdmin's `admins.json`
(with the password hashes of its accounts); they are readable by root only. Treat copies of them
(for example in restic) as secrets too.
