# Troubleshooting

## Molecule stops with "Computed fully qualified role name … does not follow current galaxy requirements"

**Cause:** Molecule was started without this repository's base configuration, so its role-mode
"prerun" tries to install the role as a stand-alone Galaxy role, which needs a namespace and role
name in `meta/main.yml`. The base configuration (`.config/molecule/config.yml`) turns the prerun
off and puts the sibling roles on the roles path instead. Molecule finds it only inside a git
checkout of this repository.

**Fix:** run Molecule from the role's folder inside the git checkout:

```bash
cd roles/<role>
molecule test
```

## ansible-lint reports `meta-runtime[unsupported-version]` for `requires_ansible: ">=2.21.0"`

**Cause:** ansible-lint 26.10.1 knows only ansible-core 2.15 to 2.19 as supported releases unless
the configuration adds newer ones.

**Fix:** run ansible-lint from the repository root, so that it reads `.ansible-lint`, which adds
2.20 and 2.21 through `supported_ansible_also`:

```bash
ansible-lint
```

## `molecule create` fails with "Conflict. The container name "/gs-…" is already in use"

**Cause:** an earlier run was interrupted before its destroy step, and its container still exists.

**Fix:** `molecule test` starts with a destroy step and removes it. To remove it by hand, look at
the names first and delete only containers whose names start with `gs-`:

```bash
docker ps -a --filter name=^gs- --format '{{.Names}}'
docker rm -f <name>
```

## The playbook says "Could not match supplied host pattern" and "no hosts matched"

**Cause:** `luminare.gameserver.gameserver` runs on the group `gameservers`, and the inventory has
no such group, or `gameserver_hosts` was set in `group_vars` or `host_vars`, where Ansible reads
it too late for the play's `hosts`.

**Fix:** put the hosts into a group `gameservers` (as in `examples/inventory/hosts.yml`), or pass
the pattern as an extra variable:

```bash
ansible-playbook -i inventory luminare.gameserver.gameserver -e gameserver_hosts=<group or host>
```

## The playbook stops with "is placeholder", "is a placeholder" or "The default account is invalid"

**Cause:** `group_vars/gameservers/secrets.yml` from the example still holds a `CHANGE_ME_` value,
or the encrypted file was not loaded. The roles check every secret before their first change, so
the host is unchanged; the message names the variable, never its value.

**Fix:** replace every `CHANGE_ME_` value (license key, API token, the master account's bcrypt
hash, `/perf/` password) and encrypt the file. With Ansible Vault, run the playbook with
`--ask-vault-pass` or a vault password file; with SOPS, check that its vars plugin is enabled.

## The playbook updated one host and stopped before the others

**Cause:** this is on purpose: the play handles one host at a time (by default
`gameserver_serial` is 1) and stops at the first host that fails (`max_fail_percentage: 0`), so a
build that does not start reaches one host only. That host was rolled back if the update did not
answer.

**Fix:** find the cause on that host ([runbook](runbook.md)), fix it in the inventory, and run the
playbook again; hosts that already run the requested build report no change.

## The fxserver role stops with "Build … is not on this host yet, so it is downloaded"

**Cause:** `fxserver_build` names a build that is not in `/opt/fxserver/artifacts/` yet, and
`fxserver_artifact_url` does not name that build number in its path, or
`fxserver_artifact_sha256` is not 64 lower-case hex digits. Usually only `fxserver_build` was
changed.

**Fix:** set the build, its download URL and its sha256 together, as described in the
[upgrade guide](upgrade.md#update). A rollback to a build that is still on disk needs only
`fxserver_build`.

## The download fails with "The checksum for … did not match"

**Cause:** the file at `fxserver_artifact_url` is not the one whose sha256 is in
`fxserver_artifact_sha256`: a typo in either value, a URL of another build, or a changed file.

**Fix:** download the build again on your workstation, compare `sha256sum fx.tar.xz` with the
value in your inventory and correct the wrong one. Never turn the check off; the role has no
setting for that.

## The fxserver role says "fxserver_license_key is missing" or "placeholder"

**Cause:** the license key variable is empty or still `CHANGE_ME_LICENSE_KEY`, and
`fxserver_service_state` is `started`. The value is never printed.

**Fix:** put your key into an encrypted variables file for the host or group (for example with
SOPS or Ansible Vault) and check that the playbook loads it. Never commit the key in plain text:
the platform scans public repositories for keys.

## "server.cfg has no line exec secrets.cfg"

**Cause:** with `fxserver_server_data_repo`, the repository's `server.cfg` does not run
`secrets.cfg`, so the server would start without its license key.

**Fix:** add `exec secrets.cfg` as the last line of `server.cfg` in the repository, and add
`secrets.cfg` and `cache/` to its `.gitignore`.

## The fxserver or gameserver_observability role stops because it cannot check its drop-in

**Cause:** `/etc/nftables.d` exists (or `fxserver_firewall_manage` or
`gameserver_observability_firewall_manage` is `true`), so the role writes its drop-in
(`45-fxserver.nft` or `50-observability.nft`), but `/etc/nftables.conf` is missing, does not
define `table inet filter` or lacks the line `include "/etc/nftables.d/*.nft"`, or `nft` is not
installed. The
`/etc/nftables.conf` of the nftables package has no include line: a drop-in would pass
`nft --check` there but never be loaded. The message names what is missing; nothing was changed.

**Fix:** set up the firewall layout of the `luminare.infra_edge` base role, or write an
`/etc/nftables.conf` of that shape. Remove an unused `/etc/nftables.d` when the host has no
nftables firewall.

## `/info.json` answers "Nope." (status 403)

**Cause:** `sv_requestParanoia` refused the request. At 1 (the template's default) the server
refuses requests to `/info.json`, `/dynamic.json` and `/players.json` that carry a `Via` header,
which proxies add; at 2 or higher also requests with an `Upgrade-Insecure-Requests` header, which
browsers send. It answers "Nope." and then refuses new connections from the sending address
(IPv4 loopback excepted) until the server restarts. The role's health check sends neither header
and connects to 127.0.0.1. (The platform documentation says that from level 2 every request to
these endpoints answers "Nope."; the server source of build 35245 refuses only requests with one
of these headers.)

**Fix:** query the endpoints with a client that sends neither header (`curl`, a monitoring
probe) and not through a proxy that adds `Via`; `systemctl restart fxserver` clears the blocked
addresses. For the templated `server.cfg`, `fxserver_cfg.request_paranoia` sets the level (0-3).

## The txadmin role says "fxserver.service is … starting the server directly"

**Cause:** the unit starts `run.sh +exec server.cfg`, which runs the game server without txAdmin,
so txAdmin's settings would do nothing. The fxserver role ran without `fxserver_mode: txadmin`,
or the txadmin role ran before it.

**Fix:** set `fxserver_mode: txadmin` in the inventory and list
`luminare.gameserver.fxserver` before `luminare.gameserver.txadmin` in the play.

## The txadmin role refuses `txadmin_interface: 127.0.0.1`

**Cause:** txAdmin listens on `TXHOST_INTERFACE` and also forces every `endpoint_add_*` line of
`server.cfg` onto it, so with a loopback address no player could reach the game server (see the
[txadmin README](../roles/txadmin/README.md#the-txhost_interface-gotcha)).

**Fix:** leave `txadmin_interface` empty. Port 40120 stays private through
`/etc/nftables.d/40-txadmin.nft` (loopback and `txadmin_firewall_sources` only); reach the panel
through an SSH tunnel or a tunnel connector.

## The playbook stops with "fxserver_mode is txadmin: txAdmin listens on port 40120 …"

**Cause:** the playbook's first task found no firewall layout for the txadmin role's drop-in:
`nft`, `/etc/nftables.d` or an `/etc/nftables.conf` with `table inet filter` and the line
`include "/etc/nftables.d/*.nft"` is missing. The message lists which of them exist. Nothing was
changed, and txAdmin was not started.

**Fix:** as in the next entry: set up the firewall layout of the `luminare.infra_edge` base role
(or such an `/etc/nftables.conf` with `txadmin_firewall_manage: true`), or set
`txadmin_firewall_required: false` only when another firewall already blocks the port.

## The txadmin role stops because it cannot write `40-txadmin.nft`

**Cause:** `/etc/nftables.d` does not exist and `txadmin_firewall_manage` is `false`, or
`/etc/nftables.conf` lacks `table inet filter` or the line `include "/etc/nftables.d/*.nft"`.
Without the drop-in, port 40120 would be open on every IPv4 address.

**Fix:** set up the firewall layout of the `luminare.infra_edge` base role, or write an
`/etc/nftables.conf` of that shape and set `txadmin_firewall_manage: true`. Only when another
firewall already blocks the port, set `txadmin_firewall_required: false`.

## The txadmin role says secrets.cfg does not set the `/perf/` credentials

**Cause:** `txadmin_prometheus_basic_auth` is enabled, but the fxserver role, which writes
`secrets.cfg`, did not see it: it was set only for the txadmin role (role `vars:`), or the
fxserver role did not run first in the same play. With `fxserver_perf_password` set as well, the
fxserver role stops earlier and says that the credentials come from two places.

**Fix:** set `txadmin_prometheus_basic_auth` in `group_vars`, `host_vars` or the play, leave
`fxserver_perf_password` empty and run both roles in one play, fxserver first.

## `/host/status` answers `{"error": "token missing"}` or `"token not configured"`

**Cause:** txAdmin answers with status 200 and an `error` field when the request has no token or
when `txadmin_api_token` is empty (the endpoint is off then).

**Fix:** set `txadmin_api_token` and send it in the header:
`curl -fsS -H "x-txadmin-envtoken: <token>" http://127.0.0.1:40120/host/status`.

## The gameserver_observability role says "This role adds to an existing Prometheus"

**Cause:** the role found no Prometheus on the host where it runs: no
`gameserver_observability_prometheus_config_dir` (default `/etc/prometheus`) with
`prometheus.yml`, no promtool 2.43 or later under the name or path in
`gameserver_observability_promtool`, or no group `gameserver_observability_prometheus_group`. It
stopped before any change.

**Fix:** install Prometheus first in the same play (for example with the `prometheus` role of the
`prometheus.prometheus` collection), or point the variables at your installation. Run the role on
the Prometheus host, not on a game server that has no Prometheus.

## The gameserver_observability role says the unit "does not exist or has no reload command"

**Cause:** `gameserver_observability_prometheus_service` (default `prometheus.service`) is not the
unit of your Prometheus, or that unit has no `ExecReload=` line, so `systemctl reload` cannot make
Prometheus read the new files.

**Fix:** set the variable to your Prometheus unit, add `ExecReload=/bin/kill -HUP $MAINPID` to it
(the `prometheus.prometheus` collection's unit has it), or set
`gameserver_observability_prometheus_reload: false` and reload Prometheus yourself after each run.

## The gameserver_observability role says "must be a loopback or private address"

**Cause:** `gameserver_observability_listen_address` is `0.0.0.0`, `::` or a public address. The
exporters would then answer probe requests from the internet.

**Fix:** keep `127.0.0.1` when Prometheus runs on the same host, or use the host's private
address and list the hosts that may connect in `gameserver_observability_firewall_sources`.

## The gameserver_observability role says the `/perf/` password is "missing", "placeholder" or "invalid"

**Cause:** `gameserver_observability_perf_password` is empty, still a `CHANGE_ME` value, shorter
than 24 characters, or holds spaces or quotes. It must be the password the game servers use for
`/perf/` (`fxserver_perf_password` or the txadmin role's toggle).

**Fix:** set it from the same encrypted variable as the game servers' password, for example
`gameserver_observability_perf_password: "{{ fxserver_perf_password }}"` in plain mode, or
`"{{ txadmin_prometheus_basic_auth.password }}"` with the txadmin role's toggle (as in the
example inventory; on another host through that game server's `hostvars`).

## The `fxserver_perf` targets are down with "401 Unauthorized"

**Cause:** the user or password in `gameserver_observability_perf_*` differs from
`sv_prometheusBasicAuthUser` or `sv_prometheusBasicAuthPassword` in the game server's
`secrets.cfg`. When the game server has neither `fxserver_perf_password` nor the txadmin role's
toggle, the fxserver role wrote a random password there, which no Prometheus knows.

**Fix:** use one encrypted variable for both roles and run the playbooks of the game server and of
the Prometheus host again. `curl -s -o /dev/null -w '%{http_code}\n' -u prometheus http://<game server>:30120/perf/`
(it asks for the password) answers 200 with the right credentials.

## `lint-test` stops in `check_vendored_pack.py` with "cannot download"

**Cause:** the check compares the vendored pack files with the pack release that
`files/pack/manifest.json` names (`release_tag`), and downloads that release's `SHA256SUMS` and
archive from github.com for it. The download failed: no network access, or GitHub did not answer.

**Fix:** run the job again once github.com answers. `python3 scripts/check_vendored_pack.py --offline`
runs the manifest check alone, for example on a machine without internet access; CI always runs
the full check.

## Still stuck?

Search the issues, then ask in the organization's
[Discussions](https://github.com/orgs/luminare-dev/discussions). Never post secrets, keys, IP
addresses, hostnames or player data; redact logs before you paste them.
