<!-- header:begin: brand-repos 0.1.0, variant studio, files in https://raw.githubusercontent.com/luminare-dev/ansible-collection-gameserver/main/docs/brand/; the project-page sync drops this block -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/luminare-dev/ansible-collection-gameserver/main/docs/brand/readme-header-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/luminare-dev/ansible-collection-gameserver/main/docs/brand/readme-header-light.svg">
  <img alt="luminare.gameserver" src="https://raw.githubusercontent.com/luminare-dev/ansible-collection-gameserver/main/docs/brand/readme-header-light.svg">
</picture>

<!-- byline:studio -->
*a [Luminare Development](https://luminare.tech/open-source/ansible-collection-gameserver/) open-source project*
<!-- /byline:studio -->
<!-- byline:personal
*by [ItsPaulAT](https://github.com/ItsPaulAT) · [project page](https://luminare.tech/open-source/ansible-collection-gameserver/)*
/byline:personal -->
<!-- header:end -->

# luminare.gameserver

Ansible roles that install, configure, update and back up game servers, for FiveM/RedM servers (FXServer).

[![ci](https://github.com/luminare-dev/ansible-collection-gameserver/actions/workflows/ci.yml/badge.svg)](https://github.com/luminare-dev/ansible-collection-gameserver/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/luminare-dev/ansible-collection-gameserver?sort=semver)](https://github.com/luminare-dev/ansible-collection-gameserver/releases)
[![licence](https://img.shields.io/github/license/luminare-dev/ansible-collection-gameserver)](LICENSE)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/luminare-dev/ansible-collection-gameserver/badge)](https://scorecard.dev/viewer/?uri=github.com/luminare-dev/ansible-collection-gameserver)

## Why

Running a FiveM or RedM server (FXServer) on Linux by hand is a list of steps that are easy to get
wrong: download a server build, create a service user and a systemd unit, keep the admin port off
the internet and keep the license key out of git. This Ansible collection is built to turn that
list into roles, and it holds every role to the same test bar: a Molecule scenario that CI runs on
Debian 13 and Ubuntu 24.04 in systemd containers with an idempotence check, ansible-lint with its
production profile, and a secret scan that recognises server license keys.

## Quickstart

Install the collection from a release tag with `ansible-galaxy` (needs `git` on the controller):

<!-- x-release-please-start-version -->
```bash
ansible-galaxy collection install git+https://github.com/luminare-dev/ansible-collection-gameserver.git,v0.1.0
ansible-galaxy collection list luminare.gameserver
```
<!-- x-release-please-end -->

Each release also carries the collection tarball and `SHA256SUMS`; see
[Installation](docs/install.md) for that path and for a `requirements.yml` entry.

## How it works

```mermaid
flowchart LR
    operator(["Operator"]) -->|"ansible-galaxy install<br/>from a git tag"| collection["luminare.gameserver"]
    collection -->|"roles in a playbook"| host[("Debian 13 or<br/>Ubuntu 24.04 host")]
    edge["luminare.infra_edge base role<br/>(optional)"] -.->|"/etc/nftables.conf<br/>with drop-in include"| host
    ci["CI: ansible-lint, unit tests,<br/>Molecule per role and platform,<br/>secret scan"] -.->|"checks every change"| collection
```

- **Roles** added to this collection go into `roles/<role>/`, each with its own Molecule scenario
  in `roles/<role>/molecule/default/`; a role directory without one fails the `plan` job and the
  unit tests. This version has no roles yet.
- **Tests:** every scenario reuses one base configuration (`.config/molecule/config.yml`) and one
  test image (`molecule/resources/Dockerfile.j2`: `debian:trixie` or `ubuntu:24.04`, pinned by
  digest, with systemd as PID 1). Instance names start with `gs-`. The sequence is dependency,
  syntax, create, prepare, converge, idempotence (must report `changed=0`), verify and destroy.
- **CI:** the `plan` job builds a matrix with one entry for each role on each platform (Debian 13
  and Ubuntu 24.04). Each `molecule-scenario (<role>, <platform>)` job runs
  `molecule test --platform-name gs-<role>-<platform>` with a 30-minute limit, on pull requests,
  by hand and every Tuesday. The `molecule` job reports one result for all of them; it fails when
  a scenario fails and passes when there is none. The `lint-test` job runs ansible-lint
  (production profile) and the unit tests through `scripts/test.sh`. The Python tools come from
  the hash-pinned `requirements-test.txt`.
- **Releases:** release-please tags `vX.Y.Z` and updates the version in `galaxy.yml`. The release
  then attaches the source archive, the collection tarball built by `ansible-galaxy collection
  build` (`luminare-gameserver-X.Y.Z.tar.gz`) and one `SHA256SUMS` file for both.

### Works with luminare.infra_edge

This collection does not list
[luminare.infra_edge](https://github.com/luminare-dev/ansible-collection-infra_edge) as a
dependency in `galaxy.yml`. Roles added here will follow that collection's firewall layout, in
which the infra_edge `base` role owns `/etc/nftables.conf` and other roles add drop-in files; the
convention is recorded in
[ADR 0008](docs/adr/0008-soft-dependency-on-the-infra-edge-firewall-layout.md). This version has
no roles, so it writes no firewall rules.

## Design decisions

The decisions behind this project are recorded as short ADRs in [docs/adr/](docs/adr/):

- [ADR 0001: Record architecture decisions](docs/adr/0001-record-architecture-decisions.md)
- [ADR 0002: Pin every action and downloaded tool](docs/adr/0002-pin-actions-and-downloaded-tools.md)
- [ADR 0003: Secret scanning with the gitleaks binary](docs/adr/0003-secret-scanning-with-the-gitleaks-binary.md)
- [ADR 0004: Draft releases with checksums and provenance](docs/adr/0004-draft-releases-with-checksums-and-provenance.md)
- [ADR 0005: Why git tags and release tarballs instead of a registry install](docs/adr/0005-install-from-git-tags-and-release-tarballs.md)
- [ADR 0006: Why Molecule in systemd containers, one CI job per role and platform](docs/adr/0006-molecule-in-systemd-containers-one-job-per-role-and-platform.md)
- [ADR 0007: Why `requires_ansible` names only tested versions](docs/adr/0007-requires-ansible-from-tested-versions-only.md)
- [ADR 0008: Why a soft dependency on the infra_edge firewall layout](docs/adr/0008-soft-dependency-on-the-infra-edge-firewall-layout.md)
- [ADR 0009: Why one hash-pinned toolchain for lint, Molecule and the release](docs/adr/0009-one-hash-pinned-test-toolchain.md)
- [ADR 0010: Why the secret scan catches license keys of any layout](docs/adr/0010-catch-license-keys-of-any-layout.md)

## Supported versions

| Component | Tested with | Supported |
|---|---|---|
| ansible-core (controller) | 2.21.5 | 2.21 and later (`meta/runtime.yml`: `>=2.21.0`) |
| Python (controller) | 3.12 (the CI runner's version, in `python:3.12-slim`) and 3.14 | 3.12 and later, as ansible-core 2.21 requires |
| Debian 13 "trixie" (managed host) | Molecule image from `debian:trixie`, pinned by digest | primary platform |
| Ubuntu 24.04 "noble" (managed host) | Molecule image from `ubuntu:24.04`, pinned by digest | second platform |
| Test tools | ansible-lint 26.10.1, Molecule 26.10.0, molecule-plugins[docker] 26.10.12 | as pinned in `requirements-test.txt` |

Fixes go into the latest minor release only. See the
[security policy](https://github.com/luminare-dev/.github/blob/main/SECURITY.md) for reporting.

## Limitations

- This version holds the collection metadata, the shared Molecule setup, CI and the release
  workflow. It has no roles yet, so it changes nothing on a host.
- Molecule runs in privileged systemd containers, not on virtual machines or cloud servers.
  Kernel-level behaviour, such as a loaded nftables ruleset, is not proven by these tests.
- Only ansible-core 2.21 is tested; older releases are not declared as supported.
- Managed hosts other than Debian 13 and Ubuntu 24.04 on x86_64 are not tested.
- The collection is not published on Ansible Galaxy, so `ansible-galaxy collection install
  luminare.gameserver` by name does not work: install it from a git tag or the release tarball
  ([ADR 0005](docs/adr/0005-install-from-git-tags-and-release-tarballs.md)). The `luminare`
  namespace has not been requested on Galaxy. If Galaxy does not grant it, the collection is
  renamed `luminare_dev.gameserver`, which changes every fully qualified name
  (`luminare.gameserver.<role>`) in your playbooks; that rename ships as a breaking change with
  upgrade notes.
- The `molecule` check is not a required check, and pushes to `main` skip the scenarios, so
  `main` itself is tested by the weekly scheduled run or a manual run.

## Results

Measured on 2026-10-21 in this repository.

| What | Value | How it was measured |
|---|---|---|
| Unit tests | 123 run: 122 passed, 1 skipped (a check that applies only to the template repository) | `python3 -m unittest discover -s tests` with gitleaks 8.30.1 and markdownlint-cli2 0.23.2 on the PATH, Python 3.14.3 |
| ansible-lint | 0 failures, 0 warnings in 22 files; profile `production` passed | `ansible-lint` from the repository root, ansible-lint 26.10.1 with ansible-core 2.21.5 |
| Collection tarball | `luminare-gameserver-0.0.0.tar.gz`: 29 entries, 20.8 to 20.9 KB; no `docs/brand/`, scripts, unit tests or Molecule files | `ansible-galaxy collection build` (ansible-core 2.21.5) three times in a fresh clone, then `tar -tzf` and the file size; the size varies by a few bytes between builds, because the archive stores file and build times |
| Hash-pinned test tools | 45 packages installed, `pip check` clean | `pip install --require-hashes --only-binary=:all: -r requirements-test.txt` in a `python:3.12-slim` container |
| Release build | `ansible-collection-gameserver-0.1.0.tar.gz` and `luminare-gameserver-0.1.0.tar.gz`, one `SHA256SUMS` that verifies both; with `galaxy.yml` left at 0.0.0 the step fails | `release.yml`'s test-command and extra-dist-command in `python:3.12-slim`, on a local `v0.1.0` tag with the release-please version edits applied by hand |
| Install paths | git URL with a ref, `requirements.yml` with `type: git`, and the tarball: each installs `luminare.gameserver` | `ansible-galaxy collection install` against a local clone (`file://` URL) and the locally built tarball |

## Documentation and links

- [Installation](docs/install.md) · [Configuration](docs/configuration.md) ·
  [Upgrade](docs/upgrade.md) · [Troubleshooting](docs/troubleshooting.md) ·
  [Runbook](docs/runbook.md) · [ADRs](docs/adr/)
- [Changelog](CHANGELOG.md) and [releases](https://github.com/luminare-dev/ansible-collection-gameserver/releases)
  (each release has the source archive, the collection tarball, `SHA256SUMS` and a build
  provenance attestation)
- [Contributing](https://github.com/luminare-dev/.github/blob/main/CONTRIBUTING.md) ·
  [Code of conduct](https://github.com/luminare-dev/.github/blob/main/CODE_OF_CONDUCT.md) ·
  [Security](https://github.com/luminare-dev/.github/blob/main/SECURITY.md) ·
  [Support](https://github.com/luminare-dev/.github/blob/main/SUPPORT.md)
- Project page: <https://luminare.tech/open-source/ansible-collection-gameserver/>

<!-- fxserver:begin -->
## Not affiliated

Not affiliated with or endorsed by Cfx.re, Rockstar Games or Take-Two. FiveM, RedM and FXServer
are named only to describe what this project works with.
<!-- fxserver:end -->

## Licence

[Apache-2.0](LICENSE). The licence covers the code only: the project name, logo, header images
and `docs/brand/` are not licensed (see [NOTICE](NOTICE)).

<!-- byline:studio -->
*a [Luminare Development](https://luminare.tech/open-source/ansible-collection-gameserver/) open-source project*
<!-- /byline:studio -->
<!-- byline:personal
*by [ItsPaulAT](https://github.com/ItsPaulAT) · [project page](https://luminare.tech/open-source/ansible-collection-gameserver/)*
/byline:personal -->
