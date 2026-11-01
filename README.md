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

## Roles

| Role | What it does |
|---|---|
| [`fxserver`](roles/fxserver/README.md) | Installs a server build checked against its sha256 and runs it as a hardened systemd unit, directly or under txAdmin. Switches builds with one rename, rolls a failed update back and backs up server-data and txData before every switch. |
| [`txadmin`](roles/txadmin/README.md) | Configures txAdmin through `TXHOST_*` environment variables and keeps port 40120 closed except for loopback and the sources you list. |
| [`gameserver_observability`](roles/gameserver_observability/README.md) | Adds the game servers to an existing Prometheus with the exporters, scrape jobs, rules and dashboard of the [gameserver-observability](https://github.com/luminare-dev/gameserver-observability) pack. |

The playbook `luminare.gameserver.gameserver` runs `fxserver` and, with `fxserver_mode: txadmin`,
`txadmin` on the group `gameservers`, one host at a time.

## Quickstart

Install the collection from a release tag (needs `git` on the controller):

<!-- x-release-please-start-version -->
```bash
ansible-galaxy collection install git+https://github.com/luminare-dev/ansible-collection-gameserver.git,v0.2.0
```
<!-- x-release-please-end -->

Copy the example inventory, set your host, replace the `CHANGE_ME_` values in
`group_vars/gameservers/secrets.yml`, encrypt that file and run the playbook:

```bash
cp -R ~/.ansible/collections/ansible_collections/luminare/gameserver/examples/inventory ./inventory
ansible-playbook -i inventory luminare.gameserver.gameserver
```

In txAdmin mode the host needs the nftables layout of
[luminare.infra_edge](https://github.com/luminare-dev/ansible-collection-infra_edge) (or an
`/etc/nftables.conf` that includes `/etc/nftables.d/*.nft`). The collection is not on Galaxy;
see [Installation](docs/install.md) for the release tarball and `requirements.yml`.

## Supported versions

- ansible-core 2.21 or later, Python 3.12 or later on the controller
- Debian 13 or Ubuntu 24.04 (x86_64) on the managed hosts
- Server build 35245 by default (txAdmin 8.1.1); see the [upgrade guide](docs/upgrade.md#which-build-to-run)
- Prometheus 2.43 or later for `gameserver_observability`

The tests run the roles in Molecule with a fake server build, not a real one.

## Documentation

- [Installation](docs/install.md) · [Configuration](docs/configuration.md) ·
  [Upgrade](docs/upgrade.md) · [Troubleshooting](docs/troubleshooting.md) ·
  [Runbook](docs/runbook.md) · [End-to-end run](docs/e2e.md)
- [Changelog](CHANGELOG.md) · [Releases](https://github.com/luminare-dev/ansible-collection-gameserver/releases)
- [Contributing](https://github.com/luminare-dev/.github/blob/main/CONTRIBUTING.md) ·
  [Code of conduct](https://github.com/luminare-dev/.github/blob/main/CODE_OF_CONDUCT.md) ·
  [Security](https://github.com/luminare-dev/.github/blob/main/SECURITY.md) ·
  [Support](https://github.com/luminare-dev/.github/blob/main/SUPPORT.md)

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
