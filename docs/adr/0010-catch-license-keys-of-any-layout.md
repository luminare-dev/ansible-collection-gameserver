# 0010. The secret scan catches license keys of any layout

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Game-server license keys start with `cfxk_`. The platform scans public repositories for them, and
a leaked key has to be replaced. The template's gitleaks rule `cfx-server-key` matches keys of the
form `<key>_<suffix>` only. This collection writes license keys into server configuration, so its
examples and test data are close to real keys.

## Considered options

1. Keep the template rule only.
2. Add a second rule, `cfx-license-key-any-shape`, that flags every `cfxk_` value of 20 or more
   key characters, with an allowlist for placeholders made of `x`.

## Decision

Chosen option 2. Examples use the placeholder `CHANGE_ME_LICENSE_KEY`, which the
`sv_licenseKey` rule also accepts. `tests/test_gitleaks_license_key.py` builds random keys at run
time and proves that the rules fire on them, that the placeholders stay clean and that the test
file itself contains nothing key-shaped. `scripts/test.sh` installs the pinned gitleaks binary in
CI, so these checks run on every pull request instead of being skipped.

## Consequences

- Good: a key in an unusual layout cannot slip through the scan.
- Bad: any 20-character `cfxk_` string is flagged, including a deliberately fake one; write
  placeholders without that prefix.
