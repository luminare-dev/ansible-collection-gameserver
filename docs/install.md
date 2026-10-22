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
| Firewall layout (managed hosts) | nftables | With `fxserver_mode: txadmin`: `/etc/nftables.conf` with `table inet filter`, input policy drop and the last line `include "/etc/nftables.d/*.nft"`, as the `luminare.infra_edge` base role writes it. The roles add their drop-ins to `/etc/nftables.d/`. |
| Access (managed hosts) | SSH with sudo, or root | The playbook uses `become`. |
| Prometheus (`gameserver_observability` role) | 2.43 or later with promtool, on the host the role runs on | Tested with 3.15.0. `prometheus.yml` must include `scrape_configs/*.yml` and `rules/*.yml` of its folder, as the `prometheus` role of the `prometheus.prometheus` collection writes it. The role also needs HTTPS to github.com for the json_exporter and blackbox_exporter downloads. |

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

## Run the playbook

The playbook `luminare.gameserver.gameserver` runs the `fxserver` role and, with
`fxserver_mode: txadmin`, the `txadmin` role on every host of the group `gameservers`, one host
at a time. The example inventory in `examples/inventory/` sets it up for one host in txAdmin
mode; the Molecule scenario `roles/txadmin/molecule/playbook` runs exactly this inventory on
every pull request, with test values for the placeholders and a fake server build.

1. Set up the firewall layout on the host (see Requirements): run the `luminare.infra_edge` base
   role, or write such an `/etc/nftables.conf` yourself. In txAdmin mode the playbook checks it
   first and stops before any change without it: txAdmin listens on port 40120 of every IPv4
   address from the moment the `fxserver` role starts it, and only the `txadmin` role's drop-in
   closes the port again.
2. Copy the example inventory from the installed collection (below the path that
   `ansible-galaxy collection list luminare.gameserver` prints):

   ```bash
   cp -R ~/.ansible/collections/ansible_collections/luminare/gameserver/examples/inventory ./inventory
   ```

3. In `inventory/hosts.yml`, set the host name, `ansible_host` and `ansible_user`. In
   `inventory/group_vars/gameservers/main.yml`, set `txadmin_public_url` and
   `txadmin_firewall_sources` (the address of the host that runs your tunnel connector, or remove
   the entry) and the names of the server.
4. Replace every `CHANGE_ME_` value in `inventory/group_vars/gameservers/secrets.yml`, then
   encrypt the file before it is stored anywhere, for example with
   `ansible-vault encrypt inventory/group_vars/gameservers/secrets.yml` or with SOPS. The roles
   refuse the placeholders, so the playbook stops before its first change until they are
   replaced. To make the bcrypt hash of the txAdmin master account, see the
   [txadmin README](../roles/txadmin/README.md#example-playbook).
5. Run the playbook (add the option your encryption needs, for example `--ask-vault-pass`):

   ```bash
   ansible-playbook -i inventory luminare.gameserver.gameserver
   ```

   A second run reports `changed=0`. To run it on another group or on several hosts at once, pass
   `-e gameserver_hosts=<pattern>` or `-e gameserver_serial=<number>`
   ([configuration](configuration.md#playbook)).
6. In txAdmin mode, open txAdmin through an SSH tunnel
   (`ssh -L 40120:127.0.0.1:40120 <host>`, then `http://127.0.0.1:40120/`) or through your
   tunnel connector, log in with the master account and finish its one-time web setup: server
   data folder `/opt/fxserver/server-data`, config file `server.cfg`. txAdmin then starts the game
   server; `curl -fsS http://127.0.0.1:30120/info.json` on the host shows it. In plain mode
   (`fxserver_mode: plain`) the game server starts at once.

## Add the metrics

The `gameserver_observability` role adds the game servers to an existing Prometheus with the
[gameserver-observability](https://github.com/luminare-dev/gameserver-observability) pack. Run it
in a play of its own on the host of that Prometheus: the game server itself (targets on
`127.0.0.1`) or a monitoring host that reaches the game servers over a private network. Give it
the game servers' `/perf/` password from the same encrypted variable that sets it for them: in
txAdmin mode, as in the example inventory, `txadmin_prometheus_basic_auth.password` (the
observability toggle in `group_vars/gameservers/secrets.yml`); in plain mode
`fxserver_perf_password`. The example inventory sets these for the group `gameservers` only, so
a play on a monitoring host reads them through that game server's `hostvars`:

```yaml
- name: Metrics for the game servers
  hosts: monitoring
  become: true
  roles:
    - role: luminare.gameserver.gameserver_observability
      vars:
        # txAdmin mode (the example inventory). In plain mode:
        # "{{ hostvars['play.example.com'].fxserver_perf_password }}"
        gameserver_observability_perf_password: >-
          {{ hostvars['play.example.com'].txadmin_prometheus_basic_auth.password }}
        gameserver_observability_targets:
          - server: game-01
            address: 192.0.2.10
```

With several game servers, keep one `/perf/` password in `group_vars/all` instead, where every
play reads it (see the [role README](../roles/gameserver_observability/README.md#example-playbook)).

The role installs the two exporters, writes the scrape jobs, rules and password file, reloads
Prometheus and checks that it loaded them; a second run reports `changed=0`. The
[role README](../roles/gameserver_observability/README.md) describes both setups, the dashboard
and the firewall drop-in.

## Uninstall

Delete the collection folder that `ansible-galaxy collection list luminare.gameserver` shows,
for example:

```bash
rm -rf ~/.ansible/collections/ansible_collections/luminare/gameserver
```
