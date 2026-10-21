# Configuration

Each role prefixes its variables with the role name, validates them with
`roles/<role>/meta/argument_specs.yml` and documents them in a table in `roles/<role>/README.md`.
Set them in your inventory (`group_vars/`, `host_vars/`) or in the play.

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
`.gitleaks.toml` (see [ADR 0010](adr/0010-catch-license-keys-of-any-layout.md)); a leaked secret
is rotated first and removed from history second.

The `txadmin` role takes these secrets: `txadmin_api_token`,
`txadmin_default_account_password_hash`, the password in `txadmin_prometheus_basic_auth` and the
values of `txadmin_deployer_prefill`. It writes the token, the hash and the pre-fill values into
`/etc/fxserver/txadmin.env` (owner root, mode 0600), which systemd reads as root and passes to
txAdmin as `TXHOST_*` variables; the `/perf/` password goes into `secrets.cfg` through the
fxserver role. The role refuses `CHANGE_ME`
placeholders for the token and the `/perf/` password, and checks every value before it writes
it, because txAdmin can print an invalid value to its log when it stops at boot.

The backup archives in `/var/backups/fxserver` contain `secrets.cfg` and txAdmin's `admins.json`
(with the password hashes of its accounts); they are readable by root only. Treat copies of them
(for example in restic) as secrets too.
