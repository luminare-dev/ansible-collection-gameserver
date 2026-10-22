# 0017. One playbook, tested with its example inventory, and a manual cloud run

- **Status:** accepted
- **Date:** 2026-10-21

## Context

The two roles have to be combined in the right order (fxserver before txadmin, the observability
toggle where both roles read it) on a host with the firewall layout of the `luminare.infra_edge`
base role. Users start from an example, so an example that drifts from the roles is worse than
none. The roles' Molecule scenarios use a fake build (ADR 0014) in containers (ADR 0006); a real
build needs a license key, and a check of port 40120 from outside needs a real host. Neither may
reach pull requests: secrets must not be exposed to code under review, and every run of a cloud
server must end with nothing left.

## Considered options

1. A playbook snippet in the README only, and the cloud check as a written checklist.
2. A playbook in the collection (`playbooks/gameserver.yml`, run as
   `luminare.gameserver.gameserver`) with an example inventory in `examples/inventory/`, a
   Molecule scenario that runs both unchanged except for the placeholders and the download, and
   a workflow for the cloud run that only starts by hand, in a protected environment.
3. Option 2 with the cloud run on every pull request.

## Decision

Chosen option 2. In txAdmin mode the playbook checks the firewall layout with the txadmin role's
rules before either role changes anything, because the fxserver role starts txAdmin (port 40120
on every IPv4 address) before the txadmin role can refuse a host without that layout. The
scenario `roles/txadmin/molecule/playbook` links the example's `group_vars` into its inventory,
replaces only the placeholders and the download, and runs the host playbooks of the cloud run
(`tests/e2e/prepare.yml`, `tests/e2e/check.yml`); it also proves that the unchanged example and a
layout without the drop-in include are refused before any change. It sits in the txadmin role,
the last role of the playbook, because the CI matrix lists scenarios per role (ADR 0014); a
scenario outside `roles/` would need a change to the matrix script and the CI job. The workflow
`e2e.yml` runs only on `workflow_dispatch`, in the environment `e2e` with a required reviewer and
its two environment secrets, and is skipped unless the repository variable `E2E_ENABLED` is
`'true'` (a string, because repository variables are strings). Everything it creates carries one
label, and an `always()` step deletes and recounts it. Option 3 would expose a license key and a
cloud token to pull request code.

## Consequences

- Good: the example in the documentation is the one CI converges on both platforms, with
  idempotence, on every pull request.
- Good: a green scenario predicts most of the cloud run, because both use the same playbook,
  inventory and host checks.
- Bad: the real build, the license key and the outside check of port 40120 are covered only by
  the manual run, which has not run yet.
- Bad: the cloud run depends on an outside address echo service and on the cloud API being
  available. The clean-up runs in any case, and the next run's clean-up also deletes leftovers
  with the label.
