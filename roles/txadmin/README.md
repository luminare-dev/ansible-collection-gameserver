# luminare.gameserver.txadmin

Configures txAdmin, the web admin panel that ships with every server build (FXServer, for
FiveM/RedM servers), as code: its settings become `TXHOST_*` environment variables in a root-only
file that systemd hands to `fxserver.service`. An nftables drop-in keeps the panel's port 40120
closed to everyone but the host itself and the sources you list.

Not affiliated with or endorsed by Cfx.re, Rockstar Games or Take-Two.

## What the role does

1. Checks every setting before it changes anything: ports, the address, the URL, the secrets
   (never shown, also not when a check fails), the firewall sources, and the installed
   `fxserver.service`, which must run txAdmin (`fxserver_mode: txadmin` of the
   [fxserver role](../fxserver/README.md)). With `txadmin_max_slots`, `txadmin_interface` or
   `txadmin_fxs_port` set, it also checks `server.cfg` against the limits txAdmin enforces, so a
   mismatch stops the playbook instead of leaving the game server offline. A loopback address in
   `txadmin_interface` is refused ([the `TXHOST_INTERFACE` gotcha](#the-txhost_interface-gotcha)).
2. Writes `/etc/fxserver/txadmin.env` (owner root, mode 0600, `no_log`, no diff) with one unquoted
   `TXHOST_*=value` line per setting that is set, and the drop-in
   `/etc/systemd/system/fxserver.service.d/10-txadmin.conf` with `EnvironmentFile=` pointing at
   it.
3. Writes `/etc/nftables.d/40-txadmin.nft` with `add rule inet filter input … accept` lines only:
   the web port from loopback and from `txadmin_firewall_sources`. The new file is checked with
   `nft --check` together with `/etc/nftables.conf` before it replaces the old one; then
   `nftables.service` is restarted.
4. Restarts `fxserver.service` when the environment file or the drop-in changed and the service
   runs (a server stopped on purpose stays stopped), then waits until txAdmin's web page answers.
   txAdmin stops at boot when a `TXHOST_*` value is invalid, so the answer also shows that it
   accepted the file.

The role never writes txAdmin's own files (`admins.json`, `config.json` and the logs in txData):
txAdmin owns them and changes their format between releases.

## Before you start

- Run [`luminare.gameserver.fxserver`](../fxserver/README.md) first in the same play, with
  `fxserver_mode: txadmin`. Its unit then starts `run.sh` without `+exec`, which makes the server
  build start txAdmin instead of the game server, and sets `TXHOST_DATA_PATH` to
  `/opt/fxserver/txData` (`fxserver_txdata_dir`). Its default health check then waits for
  txAdmin's web page on port 40120 instead of `/info.json`.
- Set up the firewall layout of the `luminare.infra_edge` base role on the host: nftables with
  `/etc/nftables.conf` that defines `table inet filter` with input policy drop and includes
  `/etc/nftables.d/*.nft` last. Without `/etc/nftables.d` the role stops (see
  `txadmin_firewall_required`), because txAdmin listens on every IPv4 address.

## Example playbook

Keep the secrets in an encrypted variables file, for example with SOPS or Ansible Vault:

```yaml
# group_vars/gameservers/secrets.yml (encrypted). The roles refuse these placeholders.
fxserver_license_key: CHANGE_ME_LICENSE_KEY
txadmin_api_token: CHANGE_ME_API_TOKEN                # 16-48 letters, digits, "_" or "-"
txadmin_default_account_password_hash: CHANGE_ME_BCRYPT_HASH
txadmin_prometheus_basic_auth:
  enabled: true
  user: prometheus
  password: CHANGE_ME_AT_LEAST_24_CHARACTERS
```

```yaml
# group_vars/gameservers/main.yml
fxserver_mode: txadmin
txadmin_default_account_name: admin_name
txadmin_firewall_sources:
  - 192.0.2.10        # the host that runs the tunnel connector
```

```yaml
- name: Game server with txAdmin
  hosts: gameservers
  become: true
  roles:
    - role: luminare.gameserver.fxserver
    - role: luminare.gameserver.txadmin
```

Create the bcrypt hash for the default account on your workstation, for example with Python's
`bcrypt` package (Debian and Ubuntu: `python3-bcrypt`). It asks for the password, so the password
stays out of your shell history:

```bash
python3 -c 'import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt(12)).decode())'
```

## First start and the one-time setup

txAdmin starts the game server only after its setup in the web page is done:

1. Open the panel through an SSH tunnel (`ssh -L 40120:127.0.0.1:40120 <host>`, then
   `http://127.0.0.1:40120/`) or through your tunnel hostname.
2. Log in with the default account (`txadmin_default_account_*`). Without one, txAdmin prints a
   PIN to the journal (`journalctl -u fxserver`) and asks you to link an account.
3. Choose the existing server data `/opt/fxserver/server-data` (`fxserver_server_data_dir`) and the
   config file `server.cfg`, which the fxserver role writes and which runs `secrets.cfg`.

After that, txAdmin starts the game server on every start of `fxserver.service` (its Autostart
setting, on by default). The default
account only applies while txData has no `admins.json`; later changes to it do nothing, and the
role does not edit `admins.json`.

## Variables

Every variable is validated by `meta/argument_specs.yml`. Empty strings and `0` leave the
variable out of the environment file, so txAdmin uses its own default.

| Variable | Type | Default | Description |
|---|---|---|---|
| `txadmin_port` | int | `40120` | Web port (`TXHOST_TXA_PORT`); not 30120. The fxserver role's default health check uses 40120: set `fxserver_healthcheck_url` too when you change it. |
| `txadmin_interface` | str | `""` | `TXHOST_INTERFACE`. Keep it empty: txAdmin then listens on every IPv4 address and leaves the game endpoints alone. An IPv4 address makes txAdmin listen there only **and** forces every `endpoint_add_*` line of `server.cfg` onto it; loopback addresses are refused. |
| `txadmin_public_url` | str | `""` | Public URL shown in txAdmin's boot message (`TXHOST_TXA_URL`), for example `https://demo-tx.example.com`. |
| `txadmin_max_slots` | int | `0` | Highest `sv_maxclients` txAdmin accepts (`TXHOST_MAX_SLOTS`); `0` leaves it unset. |
| `txadmin_game_name` | str | `""` | `fivem` or `redm` limits txAdmin's setup to one game (`TXHOST_GAME_NAME`). |
| `txadmin_fxs_port` | int | `0` | Game port txAdmin enforces for every `endpoint_add_*` line (`TXHOST_FXS_PORT`); `0` leaves it unset. Not 40120-40150. |
| `txadmin_quiet_mode` | bool | `true` | `TXHOST_QUIET_MODE`: keeps the game server's console (joins, chat, resource output) out of txAdmin's output and so out of the journal; it stays in txAdmin's live console. |
| `txadmin_ignore_deprecated_configs` | bool | `true` | `TXHOST_IGNORE_DEPRECATED_CONFIGS`: txAdmin ignores the old `txAdminPort`, `txAdminInterface` and `txDataPath` convars. |
| `txadmin_api_token` | str | `""` | Token for `/host/status` (`TXHOST_API_TOKEN`), 16-48 letters, digits, `_` or `-`; secret. Empty keeps the endpoint off; `disabled` (no token needed) is refused. |
| `txadmin_default_account_name` | str | `""` | User name of the master account txAdmin creates on its first start (`TXHOST_DEFAULT_ACCOUNT`); empty creates none. |
| `txadmin_default_account_fivem_id` | str | `""` | Numeric Cfx.re account ID (1-8 digits) for the Cfx.re login; the user name must then be that account's name. |
| `txadmin_default_account_password_hash` | str | `""` | bcrypt hash (`$2a$`, `$2b$` or `$2y$`) of the account's backup password; secret. The ID, the hash or both must be set with a user name. |
| `txadmin_deployer_prefill` | dict | `{}` | Suggestions for txAdmin's deployer of new servers; secret. Keys `db_host`, `db_port`, `db_user`, `db_password`, `db_name`, `license_key` (`TXHOST_DEFAULT_DBHOST` … `TXHOST_DEFAULT_CFXKEY`). They never change an existing `server.cfg`. |
| `txadmin_prometheus_basic_auth` | dict | `{enabled: false, user: prometheus, password: ""}` | Observability toggle, see [below](#observability-toggle). The password is a secret (at least 24 characters). |
| `txadmin_firewall_manage` | bool | `false` | `false` writes `/etc/nftables.d/40-txadmin.nft` only when `/etc/nftables.d` exists; `true` also creates the directory and installs nftables. Either way `/etc/nftables.conf` must define `table inet filter` and include `/etc/nftables.d/*.nft`. |
| `txadmin_firewall_required` | bool | `true` | Stop before any change when the drop-in cannot be written. Set `false` only when another firewall blocks the port. |
| `txadmin_firewall_reload` | bool | `true` | Restart `nftables.service` after the drop-in changed. |
| `txadmin_firewall_sources` | list of str | `[]` | IPv4 or IPv6 addresses or networks that may reach the web port besides loopback, for example the host that runs the tunnel connector; `/0` networks are refused. |
| `txadmin_healthcheck_timeout` | int | `120` | Seconds to wait for txAdmin's web page after a restart (at least 5). |

`TXHOST_DATA_PATH` is not a variable of this role: the fxserver role's unit sets it to
`fxserver_txdata_dir`, so txAdmin uses that folder from its very first start and the fxserver
backups include it. Provider name and logo (`TXHOST_PROVIDER_*`) are left unset.

## The `TXHOST_INTERFACE` gotcha

It looks natural to bind the admin panel to `127.0.0.1`. txAdmin, however, uses
`TXHOST_INTERFACE` twice: it listens on that address, and it refuses to start the game server
unless every `endpoint_add_tcp` and `endpoint_add_udp` line of `server.cfg` uses the same address
(txAdmin 8.1.1, `core/lib/fxserver/fxsConfigHelper.ts`). With `127.0.0.1` the game server would
listen on loopback only, and no player could connect. The role therefore refuses loopback
addresses and leaves the variable unset by default. The panel stays private through the
nftables drop-in and a tunnel instead. When you do set an address (for a host with several),
every endpoint in `server.cfg` must use it, and IPv6 endpoints are not possible.

## Firewall

The role follows the firewall layout of the `luminare.infra_edge` base role: `/etc/nftables.conf`
defines `table inet filter` with input policy drop and includes `/etc/nftables.d/*.nft` last. The
drop-in holds accept rules only, for example:

```text
add rule inet filter input iif "lo" tcp dport 40120 accept
add rule inet filter input ip saddr { 192.0.2.10 } tcp dport 40120 accept
```

Everything else that reaches port 40120 meets the drop policy. The role checks that
`/etc/nftables.conf` includes the drop-in folder: without that line the rules would validate but
never be loaded. To publish the panel, run a tunnel connector on the host (it connects to
`127.0.0.1:40120`) or list the connector's address in `txadmin_firewall_sources`, and put an
access policy in front of the public hostname.

## Observability toggle

`txadmin_prometheus_basic_auth` with `enabled: true` writes `sv_prometheusBasicAuthUser` and
`sv_prometheusBasicAuthPassword` into `secrets.cfg`, which protects `/perf/` on the game port with
HTTP basic auth (a scrape without the credentials gets status 401). `secrets.cfg` belongs to the
fxserver role, which writes these two lines from this variable, so:

- set the toggle in the inventory or the play (where both roles read it), not as a variable of
  this role alone;
- leave `fxserver_perf_password` empty (the fxserver role refuses both at once).

The txadmin role reads `secrets.cfg` (without showing it) and stops when the two lines do not
match the toggle.

## Secrets

- The environment file is readable by root only; systemd reads it as root and passes the values
  to txAdmin's process. Ansible writes it with `no_log` and without a diff.
- Send the API token in the `x-txadmin-envtoken` header, not as `?envtoken=` in a URL that ends
  up in logs: `curl -H "x-txadmin-envtoken: <token>" http://127.0.0.1:40120/host/status`.
- txAdmin answers `/host/status` with status 200 also when the token is missing or wrong; the
  body then holds an `error` field.
- When txAdmin stops at boot because of an invalid `TXHOST_*` value, its error can print that
  value to the journal. The role refuses such values before it writes them.

## Verified facts

Checked on 2026-10-21 against txAdmin 8.1.1 (the version that build 35245 ships; its release tag
points to commit `8a9a41410000fd92a527fe11bae2b8eeeb8b10e0` of citizenfx/txAdmin):

- Variable names and rules from `docs/env-config.md`, `core/boot/getHostVars.ts`,
  `core/globalData.ts` and `shared/consts.ts`: `TXHOST_DATA_PATH` (absolute), `TXHOST_TXA_PORT`
  (default 40120, not 30120), `TXHOST_FXS_PORT` (not 40120-40150), `TXHOST_INTERFACE` (IPv4),
  `TXHOST_TXA_URL`, `TXHOST_MAX_SLOTS`, `TXHOST_GAME_NAME` (`fivem`, `redm`),
  `TXHOST_QUIET_MODE`, `TXHOST_API_TOKEN` (`disabled` or `[A-Za-z0-9_-]{16,48}`),
  `TXHOST_DEFAULT_ACCOUNT` (`username:fivemId[:bcrypt]`), `TXHOST_DEFAULT_DB*`,
  `TXHOST_DEFAULT_CFXKEY`, `TXHOST_PROVIDER_NAME`, `TXHOST_PROVIDER_LOGO` and
  `TXHOST_IGNORE_DEPRECATED_CONFIGS`; a value in quotes stops txAdmin at boot.
- Interface handling from `core/modules/WebServer/index.ts` (unset: listen on `0.0.0.0`) and
  `core/lib/fxserver/fxsConfigHelper.ts` (set: every endpoint must use it); the token checks of
  `/host/status` from `core/modules/WebServer/middlewares/authMws.ts`.
- From the server source (`code/server/launcher/src/Server.cpp` of citizenfx/fivem): without a
  `+exec` argument the build starts txAdmin.
- By running txAdmin 8.1.1 from the official build 35245 (sha256 as in the fxserver role) in an
  isolated container without network: it starts without a license key, listens on
  `0.0.0.0:40120` (IPv4 only), creates the master account from `user::<bcrypt hash>`, answers `/`
  and `/login` with status 200 before its setup, refuses a quoted value (error E1020, which
  prints the value), listens on `127.0.0.1` only with `TXHOST_INTERFACE=127.0.0.1`, and writes
  `server-monitor-token.key` and `crashes/` into the build directory (allowed by the unit's
  `ReadWritePaths=/opt/fxserver`).

## Tests

The Molecule scenario `default` runs in systemd containers on Debian 13 and Ubuntu 24.04: the
fxserver role with `fxserver_mode: txadmin` and the fake build (`tests/fake-artifact/`, which
behaves like txAdmin when `run.sh` has no `+exec`), then this role. After the idempotence run,
`verify.yml` checks:

- the environment file (root, 0600, exactly the expected unquoted lines, no `TXHOST_INTERFACE`),
  the drop-in, and the unit as systemd sees it (`EnvironmentFiles`, `TXHOST_DATA_PATH`, no
  `+exec`);
- that the values reached txAdmin: `/host/status` refuses a request without the token and
  answers with it, `admins.json` holds the default account with the exact hash, and the fake game
  server still starts and answers `/info.json`;
- the observability toggle: both convars in `secrets.cfg`, `/perf/` 401 without and 200 with
  the credentials;
- the journal: settings applied, no secret in it;
- the nftables drop-in (exact lines, `nft --check`), the ruleset loaded into the container's own
  network namespace, and connections from a second network namespace: port 40120 answers a
  source in `txadmin_firewall_sources` and drops one outside it, while port 30120 stays open;
- six runs with settings that must be refused (loopback interface, a `/0` source, the token
  `disabled`, a toggle that did not reach `secrets.cfg`, `/perf/` credentials set in both roles,
  a slot limit below `sv_maxclients`): each stops at the checks and leaves the environment file
  unchanged.

```bash
cd roles/txadmin
molecule test
```

## Limitations

- Tested with the fake build only. The real txAdmin 8.1.1 was started by hand in a container
  (see [Verified facts](#verified-facts)), but not under this role's unit, and no game server
  was started through it (that needs a license key, or LAN mode with `sv_lan`, which was not
  tried). The one-time web setup is manual.
- The firewall test runs in the container's own network namespace, not on a virtual machine or
  cloud server; the check from outside a real host is part of the end-to-end run that is still
  open.
- txAdmin's environment, including the API token, the default account hash and the deployer
  pre-fill, is visible in `/proc/<pid>/environ` to processes of the service user, and the game
  server's resources run as that user. Treat these values like `secrets.cfg`, which that user
  can read anyway.
- txAdmin keeps its own logs in txData (`default/logs/`); `fxserver_journald_retention` does not
  apply to them. Set their retention in txAdmin's settings.
- The default account applies only on txAdmin's first start (no `admins.json` yet).
