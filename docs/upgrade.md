# Upgrading

Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0.0 a minor
release may contain breaking changes; they are listed under "BREAKING CHANGES" in the
[changelog](../CHANGELOG.md).

## General steps

1. Read the changelog entries between your version and the new one.
2. Back up what the roles manage on your hosts (configuration, data).
3. Install the new release over the old one (see [Installation](install.md)) and verify its
   checksum when you use the release tarball. With a git tag:

   ```bash
   ansible-galaxy collection install --force git+https://github.com/luminare-dev/ansible-collection-gameserver.git,vX.Y.Z
   ```

   With a `requirements.yml`, change `version:` to the new tag and run
   `ansible-galaxy collection install --force -r requirements.yml`.
4. Run `ansible-galaxy collection list luminare.gameserver` to see the new version, then run your
   playbook against a test host first.

## Updating the game server build (fxserver role)

This part is about the server build that the `fxserver` role runs, not about the collection.
Plan a check once a month.

### Which build to run

- Run the **Recommended** build in production. **Latest** builds are for testing.
- The platform supports a Recommended build until 6 weeks after the next Recommended build is
  released, and a Latest build until 2 weeks after the next one. Builds older than 3 months
  cannot be joined from the server browser.
- The role's default is build 35245, the Recommended build on 2026-10-21, with the sha256 of its
  official download recorded that day.

### Find the Recommended build and its support end

The platform's version API lists the current builds and a `support_policy` map from build number
to the date its support ends (`9999-12-31` means no end date is set yet):

```bash
api=https://changelogs-live.fivem.net/api/changelog/versions/linux/server
curl -fsS "$api" | jq '{recommended, recommended_download, latest}'
curl -fsS "$api" | jq -r --arg build 35245 '.support_policy[$build]'
```

Compare `recommended` with the build in `fxserver_build` (or with the metric
`fxserver_artifact_build`), and look up the support end of the build you run.

### Update

1. Download the new build on your workstation, never into a repository, and record its sha256
   (the platform publishes no checksums):

   ```bash
   curl -fsSLo fx.tar.xz "<recommended_download from the API>"
   sha256sum fx.tar.xz
   ```

2. Set all three values together in your inventory:

   ```yaml
   fxserver_build: 35245
   fxserver_artifact_url: https://runtime.fivem.net/artifacts/fivem/build_proot_linux/master/35245-6efb47dff473c0e2a12fb50b08d74c0eb24a50d5/fx.tar.xz
   fxserver_artifact_sha256: 16fcffd53a30a3909cbb2cfd26f89f950a59452792cafd0eda2174bdfeef9b2f
   ```

3. Run the playbook against a test host first, then against the production host. For each
   host the role downloads the build and checks its sha256, stops the server, writes a backup
   (`/var/backups/fxserver/fxserver-<time>-pre-update-<old>-to-<new>.tar.zst`) before it writes
   this run's server-data and `secrets.cfg`, switches the
   `current` link, starts the server and waits up to `fxserver_healthcheck_timeout` seconds
   (default 180) for `/info.json` (txAdmin's web page with `fxserver_mode: txadmin`). If the new
   build does not answer, the role switches back,
   starts the old build again and fails with a message naming both builds.
4. Check the result:

   ```bash
   readlink /opt/fxserver/artifacts/current /opt/fxserver/artifacts/previous
   curl -fsS http://127.0.0.1:30120/info.json | jq -r .server
   ```

### Roll back

With Ansible, set `fxserver_build` to the previous build and run the playbook. That build is
still on disk (it is the `previous` link, and `fxserver_keep_builds` keeps at least two builds by
default), so nothing is downloaded; the role backs up, switches and checks as for an update.

Without Ansible, on the host, swap the two links and restart:

```bash
cd /opt/fxserver/artifacts
old="$(readlink current)"
ln -sfn "$(readlink previous)" current.new && mv -T current.new current
ln -sfn "$old" previous
systemctl restart fxserver
```

Then set `fxserver_build` in your inventory to the build that now runs; otherwise the next
playbook run switches forward again. To restore data from a backup as well, see the
[runbook](runbook.md#restore-a-backup-of-server-data-and-txdata).

### Under txAdmin

txAdmin ships with every server build, so updating `fxserver_build` also updates txAdmin (build
35245 ships txAdmin 8.1.1). With `fxserver_mode: txadmin` the role's health check waits for
txAdmin's web page, not for the game server: after the update, check in txAdmin, or with
`curl -fsS http://127.0.0.1:30120/info.json`, that txAdmin started the game server again. The
txadmin role checks its `TXHOST_*` values against the rules of txAdmin 8.1.1; before you move to a
build with a newer txAdmin, read txAdmin's release notes and its `docs/env-config.md` for changed
variables.

## Version notes

No release needs manual upgrade steps yet. Releases that do get a section here.
