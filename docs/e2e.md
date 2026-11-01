# End-to-end run on a cloud server

[`.github/workflows/e2e.yml`](../.github/workflows/e2e.yml) runs the playbook with the real server
build and a real license key on a throwaway Hetzner Cloud CX23 server. It runs both modes twice
(the second run must report `changed=0`), checks the host with
[`tests/e2e/check.yml`](../tests/e2e/check.yml), checks that port 40120 is closed from outside,
and deletes everything it created at the end. It has not run yet.

It only starts by hand, in the protected environment `e2e`, and is skipped unless the repository
variable `E2E_ENABLED` is `true`.

## Turn it on

1. Create a cloud project used for nothing else and an API token for it (the clean-up deletes by
   label).
2. Register a license key for test servers that serves no other server.
3. Create the environment `e2e` with a required reviewer, deployments from `main` only, and the
   secrets `HCLOUD_TOKEN` and `FXSERVER_LICENSE_KEY`.
4. Set the repository variable `E2E_ENABLED` to `true`.
5. Start it under Actions → `e2e` → Run workflow and approve the deployment.

A server with a valid key shows up in the public server list while it runs, so the example
inventory uses a neutral name. If the key ever appears in a log, regenerate it, replace the
secret and delete the log.

## When it fails

- Leftovers: `hcloud server list --selector e2e=ansible-collection-gameserver` (and `firewall`,
  `ssh-key`), then delete them. The next run also cleans them up.
- "port 40120 did not time out from outside": treat it as a security bug of the txadmin role.
- A failing playbook run can usually be reproduced with the fake build:
  `cd roles/txadmin && molecule test --scenario-name playbook`.
