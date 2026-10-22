# Runbook

The first entries cover the `fxserver` and `txadmin` roles on a managed host; the last two cover
the automation in this repository (the weekly Molecule run and the release). Commands run as root
on the host.

## Failure: a playbook run stops with "did not answer … rolled back to build …"

| | |
|---|---|
| **Meaning** | The `fxserver` role switched to a new build (or back to an older one), and `fxserver_healthcheck_url` did not answer with status 200 within `fxserver_healthcheck_timeout` seconds. The role switched `current` back, restarted the old build and checked it again. |
| **Impact** | The server was down from the stop before the backup until the old build answered again (at most the backup time plus about twice the timeout). It runs the old build now; the inventory still names the new one. |
| **Diagnosis** | `journalctl -u fxserver --since "-30 min"` shows why the new build did not start or answer (license key refused, missing resource, `/info.json` answering "Nope.", see [troubleshooting](troubleshooting.md)). `readlink /opt/fxserver/artifacts/current /opt/fxserver/artifacts/previous` shows the links. |
| **Mitigation** | Set `fxserver_build`, `fxserver_artifact_url` and `fxserver_artifact_sha256` in the inventory back to the running build, so that the next run does not try again. |
| **Fix** | Fix the cause (on a test host first) and run the update again; the build is already on disk, so it is not downloaded twice. |

## Failure: the server does not answer (no switch)

| | |
|---|---|
| **Meaning** | A run without a build switch ended with "The server (build …) did not answer", or the service is failed or restarting (`Restart=on-failure`, every 10 seconds). |
| **Impact** | Players cannot connect while the server is down. |
| **Diagnosis** | `systemctl status fxserver` and `journalctl -u fxserver -n 200`. Common causes: an invalid or empty license key, a broken resource, `server.cfg` without `exec secrets.cfg`, the game port in use (`ss -ltnup 'sport = :30120'`). |
| **Mitigation** | If a configuration change caused it, revert it in the inventory or the server-data repository and run the playbook. If a data change caused it, restore the last backup (next entry). |
| **Fix** | Correct the configuration in the source (inventory or server-data repository), never only on the host: the next run overwrites `server.cfg` and `secrets.cfg`. |

## Restore a backup of server-data and txData

| | |
|---|---|
| **Meaning** | Data under `/opt/fxserver/server-data` or `/opt/fxserver/txData` is damaged or was changed by mistake, for example by an update. |
| **Impact** | Restoring replaces the files with the state of the archive; changes made after it are lost. |
| **Diagnosis** | `ls -l /var/backups/fxserver/` lists the archives (`fxserver-<UTC time>-<label>.tar.zst`; `pre-update-<old>-to-<new>` was taken with the server stopped right before a switch, before that run changed server-data or `secrets.cfg`). `tar --zstd --list --file <archive>` shows the contents. |
| **Mitigation** | Copy the archive somewhere safe first; the next backups rotate old archives out (`fxserver_backup_keep`). |
| **Fix** | `systemctl stop fxserver`, move the damaged directories aside (`mv /opt/fxserver/server-data /opt/fxserver/server-data.broken`, the same for `txData`), `tar --zstd --extract --preserve-permissions --file <archive> --directory /`, then `systemctl start fxserver` and `curl -fsS http://127.0.0.1:30120/info.json`. If the archive was taken before a build switch, switch back to the build in its label as well ([upgrade guide](upgrade.md#roll-back)). |

## Failure: `fxserver-backup.service` failed

| | |
|---|---|
| **Meaning** | The scheduled backup (`fxserver-backup.timer`) or a manual `fxserver-backup` run did not write an archive. A failed pre-update backup stops the playbook run before the switch; the role starts the old build again if it was running. |
| **Impact** | The newest archive is older than expected; nothing else changes (a partial archive is deleted). |
| **Diagnosis** | `journalctl -u fxserver-backup -n 50`. tar exit status 2 means a real error, typically a full disk (`df -h /var/backups`) or a path in `fxserver_backup_paths` that does not exist. With `fxserver_textfile_dir` set, `fxserver_backup_last_success_timestamp_seconds` shows the last good run. |
| **Mitigation** | Free disk space, then run `systemctl start fxserver-backup.service` and check that a new archive appears. |
| **Fix** | Lower `fxserver_backup_keep`, add large rebuildable folders to `fxserver_backup_exclude`, or give `/var/backups` more space. |

## Failure: the game server is offline under txAdmin

| | |
|---|---|
| **Meaning** | With `fxserver_mode: txadmin`, `fxserver.service` runs and txAdmin answers on port 40120, but the game server does not answer on port 30120. |
| **Impact** | Players cannot connect. The playbook still passes: under txAdmin its health check only covers txAdmin's web page. |
| **Diagnosis** | Open the panel through an SSH tunnel (`ssh -L 40120:127.0.0.1:40120 <host>`) and read its live console, or query `curl -fsS -H "x-txadmin-envtoken: <token>" http://127.0.0.1:40120/host/status` (with `txadmin_api_token` set): `isConfigured: false` means the one-time setup is not done; `status: OFFLINE` with a finished setup means txAdmin did not start the server. Quiet mode keeps the server's own output out of the journal; it is in txAdmin's live console and under `/opt/fxserver/txData/default/logs/`. Common causes: the setup is not done, `server.cfg` breaks a `TXHOST_*` limit (endpoint address or port, `sv_maxclients`), or the license key in `secrets.cfg` is invalid. |
| **Mitigation** | Start the server from txAdmin's web page once the cause is fixed. |
| **Fix** | Finish the one-time setup (server data `/opt/fxserver/server-data`, config file `server.cfg`), or correct `server.cfg` or the `txadmin_*` variables in the inventory and run the playbook; the txadmin role checks `server.cfg` against the limits it sets. |

## Failure: the txadmin role says "txAdmin did not answer"

| | |
|---|---|
| **Meaning** | After the txadmin role restarted `fxserver.service` with new settings, txAdmin's web page did not answer within `txadmin_healthcheck_timeout` seconds. |
| **Impact** | The panel is unavailable, and so is the game server, which txAdmin supervises. |
| **Diagnosis** | `journalctl -u fxserver -n 100`. txAdmin stops at boot when a `TXHOST_*` value is invalid; its error names the variable and can print the value, so treat that log as secret and never paste it unredacted. `ss -ltnp 'sport = :40120'` shows whether another process holds the port. |
| **Mitigation** | Revert the last change of the `txadmin_*` variables in the inventory and run the playbook. On the host, `rm /etc/systemd/system/fxserver.service.d/10-txadmin.conf && systemctl daemon-reload && systemctl restart fxserver` starts txAdmin with its defaults (port 40120, still behind the nftables drop-in) until the next run. |
| **Fix** | Correct the variable. If a newer txAdmin changed its rules, see the [upgrade guide](upgrade.md#under-txadmin). |

## Failure: the `molecule` check is red

| | |
|---|---|
| **Meaning** | At least one `molecule-scenario (<role>, <scenario>, <platform>)` job failed or was cancelled, or the `plan` job could not list the scenarios. |
| **Impact** | The pull request (or the weekly run on Tuesdays) has a role that is untested on that platform; a new package or base image may have broken it. |
| **Diagnosis** | The job name says which role, scenario and platform failed. Open the job and find the first failed step: converge (a task failed), idempotence (a task reported `changed` on the second run), side_effect (the update and rollback steps of a scenario such as `upgrade`) or verify (an assertion failed). If only one platform failed, look for a package or path that differs between Debian 13 and Ubuntu 24.04. Reproduce it with `cd roles/<role> && molecule test --scenario-name <scenario> --platform-name <instance>`; the instance is `gs-<role>-<platform>` for `default` and `gs-<role>-<scenario>-<platform>` otherwise (write `_` as `-`). |
| **Mitigation** | Do not merge the pull request. For the weekly run, check whether the same job passed on `main` last week; if only the base image changed, a Dependabot pull request for `molecule/resources/Dockerfile.j2` is the likely trigger. |
| **Fix** | Fix the role or the test in a pull request; idempotence failures need a `changed_when` or a module that reports its state correctly. |

## Failure: the release `build` job stops after "Extra release archives"

| | |
|---|---|
| **Meaning** | `ansible-galaxy collection build` did not write `dist/luminare-gameserver-X.Y.Z.tar.gz` for the release tag `vX.Y.Z`. |
| **Impact** | The release stays a draft without files; nothing is published. |
| **Diagnosis** | Compare `version:` in `galaxy.yml` and `version.txt` at the tag: release-please updates both in the release pull request. A `galaxy.yml` without the `# x-release-please-version` marker keeps the old version. |
| **Mitigation** | Leave the draft release as it is. |
| **Fix** | Restore the marker on the `version:` line in `galaxy.yml` in a `fix:` pull request, so that the next release builds. Delete the unpublished draft release and its tag by hand; that version is skipped. |
