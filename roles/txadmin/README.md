# luminare.gameserver.txadmin

Configures txAdmin, the admin panel that ships with every server build (FXServer, for FiveM/RedM
servers): its settings become `TXHOST_*` variables in a root-only environment file
(`/etc/fxserver/txadmin.env`) that systemd passes to `fxserver.service`. An nftables drop-in keeps
port 40120 closed except for loopback and the sources you list.

Not affiliated with or endorsed by Cfx.re, Rockstar Games or Take-Two.

## Before you start

- Run [`luminare.gameserver.fxserver`](../fxserver/README.md) first in the same play, with
  `fxserver_mode: txadmin`.
- Set up the firewall layout of the `luminare.infra_edge` base role first (`/etc/nftables.conf`
  with `table inet filter` that includes `/etc/nftables.d/*.nft`). txAdmin listens on every IPv4
  address as soon as the fxserver role starts it, and the role stops if it cannot write its
  drop-in (see `txadmin_firewall_required`). The collection's playbook checks this up front.

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

The playbook `luminare.gameserver.gameserver` does the same with `examples/inventory/`.

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

After that, txAdmin starts the game server on every start of `fxserver.service`. The default
account only applies while txData has no `admins.json`; the role never edits txAdmin's own files.

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

Binding the panel to `127.0.0.1` looks natural, but txAdmin also forces every `endpoint_add_*`
line of `server.cfg` onto that address, so no player could connect. The role refuses loopback
addresses and leaves the variable unset; the panel stays private through the nftables drop-in and
a tunnel instead. If you set an address, every endpoint in `server.cfg` must use it.

## Firewall

The drop-in `40-txadmin.nft` holds accept rules only, for example:

```text
add rule inet filter input iif "lo" tcp dport 40120 accept
add rule inet filter input ip saddr { 192.0.2.10 } tcp dport 40120 accept
```

Everything else hits the drop policy. To publish the panel, run a tunnel connector on the host (or
list its address in `txadmin_firewall_sources`) and put an access policy in front of the hostname.

## Observability toggle

`txadmin_prometheus_basic_auth` with `enabled: true` protects `/perf/` with basic auth. The
fxserver role writes the two lines into `secrets.cfg`, so set the toggle in the inventory (where
both roles read it) and leave `fxserver_perf_password` empty.

## Secrets

- The environment file is root-only and written with `no_log` and without a diff.
- Send the API token as the `x-txadmin-envtoken` header, not as `?envtoken=` in a URL. txAdmin
  answers `/host/status` with status 200 and an `error` field when the token is missing or wrong.
- txAdmin's environment, including the token, is visible to processes of the service user.

## Tests

```bash
cd roles/txadmin
molecule test                       # the role with a fake txAdmin
molecule test -s playbook           # the collection playbook with the example inventory
```

The settings were checked against the source of txAdmin 8.1.1 (the version build 35245 ships).
