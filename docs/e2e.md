# End-to-end run on a cloud server

The Molecule scenarios test the roles in systemd containers with a fake server build. The
end-to-end run covers what they cannot: the real server build with a real license key, under the
hardened unit, on a fresh cloud server, and port 40120 checked from outside the host. It is the
GitHub Actions workflow [`.github/workflows/e2e.yml`](../.github/workflows/e2e.yml), started by
hand once per release on a Hetzner Cloud CX23 server that exists only for the run.

**Status:** the workflow has not run yet. It needs a server license key and a cloud project that
were not available when it was written, so it is committed but skipped (see
[Turn it on](#turn-it-on)). The README lists it under Limitations, and its Results say that it
has not run.

## What it checks

| Step | What it does | Pass condition |
|---|---|---|
| Check the secrets | Reads the environment secrets `HCLOUD_TOKEN` and `FXSERVER_LICENSE_KEY`. | Both are set. |
| Install the tools | Test tools from the hash-pinned `requirements-test.txt`; the `hcloud` CLI 1.70.1, checked against the sha256 in its release's `checksums.txt` (bumped by hand; Dependabot does not see it). | Every checksum matches. |
| Install the collection | `ansible-galaxy collection build`, then installs that tarball. | The release path, not the checkout, is what runs. |
| Create the server | A CX23 (`debian-13` or `ubuntu-24.04`, without IPv6), a cloud firewall that admits TCP, UDP and ICMP from this runner's IPv4 address only, and an SSH key made for this run. All three carry the label `e2e=ansible-collection-gameserver`. | The server answers SSH and cloud-init finishes within 5 minutes. |
| Prepare the host | [`tests/e2e/prepare.yml`](../tests/e2e/prepare.yml): the firewall layout of the `luminare.infra_edge` base role (nftables, input policy drop, SSH open, `/etc/nftables.d/*.nft` included last). | nftables loads the ruleset. |
| Plain mode, two runs | `ansible-playbook luminare.gameserver.gameserver` with the [example inventory](../examples/inventory/) and `fxserver_mode=plain`: the real build 35245 (default URL and sha256), started directly with `server.cfg`. | Both runs pass; the second reports `changed=0`. |
| Plain mode, checks | [`tests/e2e/check.yml`](../tests/e2e/check.yml) `-e e2e_mode=plain` on the host, then `/info.json` from the runner. | The service is enabled and active; `/info.json` names build 35245 on the host and from outside. |
| txAdmin mode, two runs | The same playbook with the example inventory as it is (`fxserver_mode: txadmin`): it checks the firewall layout first, then the txadmin role runs too. | Both runs pass; the second reports `changed=0`. |
| txAdmin mode, checks | `tests/e2e/check.yml -e e2e_mode=txadmin` on the host, then a TCP connection to port 40120 from the runner. | txAdmin answers on the host and listens on every IPv4 address, the loaded input chain has the drop-in rules for 40120; from the runner the connection times out (dropped by nftables, since the cloud firewall admits the runner). |
| Timings | Seconds per step in the job summary. | Always written. |
| Clean-up | `if: always()`: deletes every server, firewall and SSH key with the label, also any left by an earlier run, then counts them again. | Nothing with the label is left. |

The run replaces the example's placeholders with extra variables (`-e @file`), which outrank
inventory variables: the license key from the secret, a random API token and `/perf/` password
made for the run, and no default account (the run never logs in to txAdmin). Under txAdmin the
game server starts only after txAdmin's one-time web setup, so the run checks txAdmin, not the
game port, in that mode.

The Molecule scenario `roles/txadmin/molecule/playbook` runs the same playbook with the same
example inventory and the same `prepare.yml` and `check.yml` on every pull request, with the fake
build instead of the real one:

```bash
cd roles/txadmin
molecule test --scenario-name playbook
```

## How it is protected

- **Started by hand only:** the only trigger is `workflow_dispatch`. Pull requests, pushes and
  forks never start it.
- **Skipped unless turned on:** the job runs only when the repository variable `E2E_ENABLED` is
  the string `true` (repository variables are strings, so the condition compares with `'true'`).
  Without it the workflow ends as skipped, without an error.
- **Protected environment `e2e`:** the job uses the environment `e2e`, whose required reviewer
  approves each run. The two secrets are environment secrets of `e2e`, so no other workflow or job
  can read them, and workflows from forks never get them.
- **One run at a time:** the concurrency group `e2e` queues a second run, because the clean-up
  deletes everything with the run's label.
- **Least access:** the job token can only read the repository contents. The cloud firewall
  admits only the runner, and the server gets no hostname and no IPv6 address.

## Turn it on

1. Create a cloud project that is used for nothing else, and an API token with read and write
   access for it. Never use a token of a project with other servers: the clean-up deletes by
   label, and a token of a shared project could reach other servers.
2. Register a server license key for test servers in the platform's key portal. Use a key that
   serves no other server.
3. In the repository settings, create the environment `e2e`: add yourself as required reviewer
   and allow deployments from the `main` branch only. Add the environment secrets
   `HCLOUD_TOKEN` and `FXSERVER_LICENSE_KEY`.
4. Add the repository variable `E2E_ENABLED` with the value `true`.
5. Start it under Actions → `e2e` → Run workflow (choose the image and the location), and approve
   the deployment to `e2e`.

To turn it off again, delete the variable (or set any other value).

## Secrets and the public server list

- The license key reaches the runner only as an environment secret: one step writes it into a
  file only that user can read (mode 0600, in the runner's temporary folder), and
  `ansible-playbook -e @file` reads it from there. The roles handle it in tasks with
  `no_log: true`, and GitHub masks secret values in the log. The clean-up deletes the file.
- If the key ever appears in a log anyway, regenerate it in the platform's key portal at once,
  replace the environment secret and delete the run's log.
- A server with a valid license key can appear in the public server list while it runs. The
  template's `sv_master1 ""` disables the connect button but does not remove the entry, so the
  example inventory uses the neutral name "Private test server". The server lives only for the
  run.
- LAN mode (`fxserver_cfg` key `lan: true`, which writes `sv_lan true`) would keep the server out
  of the list, but the run does not use it: according to the platform documentation that mode
  skips the license key check, which is one of the things the run is there to prove, and the
  plain-mode check reads `/info.json` from outside the host. The real build was not tried in LAN
  mode either, neither here nor locally.

## When it fails

| Symptom | Cause and fix |
|---|---|
| The job is skipped | `E2E_ENABLED` is not `true`. |
| "secrets missing in the environment e2e" | Add the missing environment secret (step 3 above). |
| "could not read the public IPv4 address of this runner" | The address service did not answer; start the run again. |
| "the test server did not accept SSH within 5 minutes" | The server booted slowly, or the address service named another address than the one the runner connects from, so the cloud firewall blocked SSH. The clean-up still deletes what was created; start the run again. |
| A playbook run fails | Read the task error in the log (the roles never print secrets), and reproduce it with the Molecule scenario above where the fake build allows. |
| "port 40120 did not time out from outside" | The drop-in did not protect the port: read the output of `tests/e2e/check.yml` in the step before. Treat it as a security bug of the txadmin role. |
| "resources with the label e2e=ansible-collection-gameserver are left" | Delete them by hand in the cloud console or with `hcloud server list --selector e2e=ansible-collection-gameserver` and the matching `delete` commands. The next run's clean-up also deletes leftovers with the label. |
