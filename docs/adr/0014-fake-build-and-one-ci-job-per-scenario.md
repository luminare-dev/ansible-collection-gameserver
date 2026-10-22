# 0014. Test with a fake build, one CI job per scenario

- **Status:** accepted
- **Date:** 2026-10-21

## Context

A real server build must never be downloaded, re-hosted or committed by the tests, and it refuses
to start without a license key, which CI does not have. The role's main promises (the unit starts,
the health check, update, automatic rollback and rollback) can only be shown with a process that
starts and answers. ADR 0006 runs one Molecule job per role and platform from the `default`
scenario only; a role with a second scenario would leave it untested in CI.

## Considered options

1. Test with the unit enabled but not started, and only check files.
2. A fake build: `tests/fake-artifact/build.py` writes an `fx.tar.xz` with the layout of a real
   build whose `run.sh` starts a small Python standard-library HTTP server that reads
   `server.cfg` and answers `/info.json`, `/dynamic.json`, `/players.json` and `/perf/` (basic
   auth) with synthetic data, and a deliberately broken variant.
3. A mock HTTP server outside the unit, started by the test.

## Decision

Chosen option 2, because the unit, `ExecStart`, the hardening and the `current` link are then
really used. The fake refuses to start without `sv_licenseKey`, never prints it and logs no client
addresses; `tests/test_fake_fxserver.py` pins its behaviour. This extends ADR 0006:
`scripts/molecule_scenarios.py` lists every scenario of a role (`default` first, which stays
mandatory) on both platforms, and CI runs one `molecule-scenario (<role>, <scenario>, <platform>)`
job each. Instance names are `gs-<role>-<platform>` for `default` and
`gs-<role>-<scenario>-<platform>` otherwise; a name that two entries would share fails the list.

## Consequences

- Good: the update, the automatic rollback and the rollback run end to end on every pull request.
- Good: a new scenario is tested by adding its folder; CI needs no change.
- Bad: the fake models only the fields the tests use; real answers may differ, and the real build
  (with its own needs under the hardened unit) is only tested by hand.
- Bad: two more CI jobs per extra scenario.
