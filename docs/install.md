# Installation

The collection is installed on the Ansible controller. Install it from a release tag with git, or
from the collection tarball attached to the GitHub release. The git, `requirements.yml` and
tarball installs below were checked on 2026-10-21 with ansible-core 2.21.5, against a local clone
of this repository and a tarball built from it.

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| ansible-core (controller) | 2.21 or later | `meta/runtime.yml` declares `>=2.21.0`. |
| Python (controller) | 3.12 or later | Required by ansible-core 2.21. |
| git (controller) | any current version | Only for the install from a git tag. |
| Managed hosts | Debian 13 "trixie" or Ubuntu 24.04 "noble", x86_64 | The platforms the Molecule scenarios run on. |
| Network (managed hosts) | HTTPS to the server build download | The `fxserver` role downloads a build only when it is not on the host yet; with `fxserver_server_data_repo` it also needs access to that git repository. |

## Install

From a release tag:

<!-- x-release-please-start-version -->
```bash
ansible-galaxy collection install git+https://github.com/luminare-dev/ansible-collection-gameserver.git,v0.1.0
```
<!-- x-release-please-end -->

Or pin it in a `requirements.yml` and install with
`ansible-galaxy collection install -r requirements.yml`:

<!-- x-release-please-start-version -->
```yaml
collections:
  - name: https://github.com/luminare-dev/ansible-collection-gameserver.git
    type: git
    version: v0.1.0
```
<!-- x-release-please-end -->

Or from the release files (the collection tarball and `SHA256SUMS`):

<!-- x-release-please-start-version -->
```bash
gh release download v0.1.0 --repo luminare-dev/ansible-collection-gameserver \
  --pattern 'luminare-gameserver-*.tar.gz' --pattern SHA256SUMS
sha256sum -c --ignore-missing SHA256SUMS
ansible-galaxy collection install luminare-gameserver-0.1.0.tar.gz
```
<!-- x-release-please-end -->

## Verify the release download

Every release has a `SHA256SUMS` file for both archives (the source archive
`ansible-collection-gameserver-X.Y.Z.tar.gz` and the collection tarball
`luminare-gameserver-X.Y.Z.tar.gz`) and a build provenance attestation for each of them:

```bash
sha256sum -c --ignore-missing SHA256SUMS
gh attestation verify luminare-gameserver-X.Y.Z.tar.gz --repo luminare-dev/ansible-collection-gameserver
```

## Check that it works

```bash
ansible-galaxy collection list luminare.gameserver
```

The output names the collection path and the installed version, for example
`luminare.gameserver 0.1.0`.

## Uninstall

Delete the collection folder that `ansible-galaxy collection list luminare.gameserver` shows,
for example:

```bash
rm -rf ~/.ansible/collections/ansible_collections/luminare/gameserver
```
