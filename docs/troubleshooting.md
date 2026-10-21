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

## The fxserver role stops because it cannot check `45-fxserver.nft`

**Cause:** `/etc/nftables.d` exists (or `fxserver_firewall_manage` is `true`), so the role writes
the game port drop-in, but `/etc/nftables.conf` is missing, does not define `table inet filter`
or lacks the line `include "/etc/nftables.d/*.nft"`, or `nft` is not installed. The
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

## Still stuck?

Search the issues, then ask in the organization's
[Discussions](https://github.com/orgs/luminare-dev/discussions). Never post secrets, keys, IP
addresses, hostnames or player data; redact logs before you paste them.
