# Configuration

This version of the collection has no roles, so there are no options to set yet. Each role that
is added documents its variables in a table here and in `roles/<role>/README.md`, prefixes every
variable with the role name and validates it with `roles/<role>/meta/argument_specs.yml`.

| Option | Type | Default | Description |
|---|---|---|---|
| (none in this version) | | | |

## Secrets

Secrets never go into this repository, an issue or a log. Keep them in an encrypted variables file
(for example with SOPS or Ansible Vault) on the controller, and pass them to the roles as
variables. Tasks that handle a secret run with `no_log: true`.

Server license keys need extra care: the platform scans public repositories for them, and a
leaked key has to be replaced. In examples and test data, write the placeholder
`CHANGE_ME_LICENSE_KEY`, never a value that starts like a real key. CI scans every commit with
gitleaks and two license-key rules in `.gitleaks.toml` (see
[ADR 0010](adr/0010-catch-license-keys-of-any-layout.md)); a leaked secret is rotated first and
removed from history second.
