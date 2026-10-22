# 0009. One hash-pinned toolchain for lint, Molecule and the release

- **Status:** accepted
- **Date:** 2026-10-21

## Context

ansible-lint, Molecule, molecule-plugins and ansible-core pull in about 45 Python packages. ADR
0002 requires every downloaded tool to be pinned. The CI jobs (lint-test, molecule-scenario and
the release build) run on GitHub's ubuntu-24.04 runner with Python 3.12.

## Considered options

1. Unpinned `pip install ansible-lint molecule …` in each job.
2. Top-level pins only (`ansible-lint==26.10.1`), resolving the rest at run time.
3. `requirements-test.in` with the top-level pins, compiled by `pip-compile --generate-hashes`
   with Python 3.12 into `requirements-test.txt`, installed with
   `pip install --require-hashes --only-binary=:all:`.

## Decision

Chosen option 3. Every job installs the same 45 packages with verified hashes and wheels only (no
build scripts run during install). yamllint, PyYAML and pathspec are pinned to the versions of
`requirements-dev.txt`, so that `yamllint --strict` (from `requirements-dev.txt`) and ansible-lint
(from `requirements-test.txt`, in a separate virtual environment) check YAML with the same
versions. Dependabot's pip ecosystem recompiles the file; the collections that Molecule's docker
driver needs are pinned by exact version in `molecule/requirements.yml` and bumped by hand.

## Consequences

- Good: CI, release and local runs use exactly the same tool versions.
- Bad: the file must be recompiled with Python 3.12 when a pin changes (the command is in the
  header of `requirements-test.in`; it pins click 8.2.1 so that the generated header can be run
  again as written).
