# 0006. Molecule in systemd containers, one CI job per role and platform

- **Status:** accepted
- **Date:** 2026-10-21

## Context

The roles manage systemd units, users, files and firewall drop-ins on Debian 13 and Ubuntu 24.04.
They must be tested on every pull request without cloud credentials, and several test runs share
one Docker daemon on the maintainer's machine. Third-party test images can change under a tag.
When a test fails, the check name should already say which role and which platform failed.

## Considered options

1. Molecule with the docker driver and community images such as `geerlingguy/docker-*-ansible`.
2. Molecule with the docker driver and one repository-local `Dockerfile.j2` built from
   `debian:trixie` and `ubuntu:24.04` pinned by digest, with systemd as PID 1.
3. Virtual machines (Vagrant or a cloud provider) for every pull request.

For CI, two layouts were considered: one job per role that tests both platforms in turn, and
one job per role and platform.

## Decision

Chosen option 2, because the images are built from official base images whose digests are
reviewed (Dependabot proposes digest updates, not new releases), and nothing else runs inside
them. Shared pieces live in one place: the base configuration `.config/molecule/config.yml`
(driver, sequence with idempotence, roles path) and `molecule/resources/Dockerfile.j2`. Each
role's scenario only lists its two platforms, named `gs-<role>-debian13` and
`gs-<role>-ubuntu2404` so they never collide with other projects on the same daemon.

CI runs one job per role and platform. The `plan` job builds the matrix at run time
(`scripts/molecule_scenarios.py`: every role, once with `debian13` and once with `ubuntu2404`; a
directory under `roles/` without `molecule/default/molecule.yml` fails the `plan` job and the
unit tests). Each `molecule-scenario (<role>, <platform>)` job runs
`molecule test --platform-name gs-<role>-<platform>` with its own 30-minute limit, on pull
requests, by hand and weekly. An aggregate job reports a single `molecule` result. Pushes to
`main` skip the scenarios, because the pull request ran them on the same changes. `molecule` is
not one of the required checks of the `main` ruleset, so a pull request can be merged while it
is red or still running; the weekly scheduled run tests `main` itself.

## Consequences

- Good: a new role is tested by adding `roles/<role>/molecule/default/`; CI needs no change.
- Good: a failure names its platform, and a slow platform cannot use up the other's time.
- Good: the weekly run catches breakage from new distribution packages.
- Bad: two runners per role, and each one installs the test tools and builds its image.
- Bad: while `molecule` is not a required check, a red scenario does not block a merge, and a
  commit on `main` gets Molecule results only from the weekly or a manual run.
- Bad: containers are not virtual machines; kernel-level checks (a loaded nftables ruleset) are
  tagged `molecule-notest` and listed as limitations.
