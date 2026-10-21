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

## Still stuck?

Search the issues, then ask in the organization's
[Discussions](https://github.com/orgs/luminare-dev/discussions). Never post secrets, keys, IP
addresses, hostnames or player data; redact logs before you paste them.
