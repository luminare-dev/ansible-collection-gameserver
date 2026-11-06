# Runbook

Commands run as root on the game server host. The alerts of the observability pack have their
own runbook in the
[pack's repository](https://github.com/luminare-dev/gameserver-observability/blob/main/docs/runbook.md).

## A playbook run stops with "did not answer … rolled back to build …"

The new build did not answer `fxserver_healthcheck_url` within `fxserver_healthcheck_timeout`
seconds, so the role switched back and started the old build again.

- `journalctl -u fxserver --since "-30 min"` shows why (license key refused, missing resource,
  `/info.json` answering "Nope.", see [troubleshooting](troubleshooting.md)).
- Set `fxserver_build`, `fxserver_artifact_url` and `fxserver_artifact_sha256` back to the running
  build in the inventory, fix the cause on a test host and update again. The build is already on
  disk, so it is not downloaded twice.

## The server does not answer (no build switch)

- `systemctl status fxserver` and `journalctl -u fxserver -n 200`. Common causes: an invalid
  license key, a broken resource, `server.cfg` without `exec secrets.cfg`, or the game port in use
  (`ss -ltnup 'sport = :30120'`).
- Revert the change in the inventory or the server-data repository and run the playbook, or
  restore the last backup (next section). Fix things in the source, not only on the host: the next
  run overwrites `server.cfg` and `secrets.cfg`.

## Restore a backup of server-data and txData

`ls -l /var/backups/fxserver/` lists the archives (`fxserver-<UTC time>-<label>.tar.zst`;
`pre-update-<old>-to-<new>` was taken right before a build switch). Copy the archive somewhere
safe first, because later backups rotate old ones out. Then:

```bash
systemctl stop fxserver
mv /opt/fxserver/server-data /opt/fxserver/server-data.broken
mv /opt/fxserver/txData /opt/fxserver/txData.broken
tar --zstd --extract --preserve-permissions --file <archive> --directory /
systemctl start fxserver
curl -fsS http://127.0.0.1:30120/info.json
```

If the archive was taken before a build switch, switch back to the build in its label as well
([upgrade guide](upgrade.md#roll-back)).

## `fxserver-backup.service` failed

`journalctl -u fxserver-backup -n 50`. tar exit status 2 is a real error, usually a full disk
(`df -h /var/backups`) or a path in `fxserver_backup_paths` that does not exist. Free space, run
`systemctl start fxserver-backup.service` and check that a new archive appears. Longer term, lower
`fxserver_backup_keep` or add large rebuildable folders to `fxserver_backup_exclude`.

## The game server is offline under txAdmin

`fxserver.service` runs and txAdmin answers on 40120, but nothing answers on 30120.

- Open the panel through an SSH tunnel (`ssh -L 40120:127.0.0.1:40120 <host>`) and read its live
  console, or with `txadmin_api_token` set:
  `curl -fsS -H "x-txadmin-envtoken: <token>" http://127.0.0.1:40120/host/status`.
  `isConfigured: false` means the one-time setup is not done.
- Logs of the game server are in txAdmin's live console and `/opt/fxserver/txData/default/logs/`
  (quiet mode keeps them out of the journal).
- Common causes: setup not done, `server.cfg` breaks a `TXHOST_*` limit, or an invalid license
  key.

## The txadmin role says "txAdmin did not answer"

txAdmin stops at boot when a `TXHOST_*` value is invalid. `journalctl -u fxserver -n 100` names
the variable and may print its value, so do not paste that log unredacted. Revert the last change
to the `txadmin_*` variables and run the playbook. To get txAdmin up with its defaults until the
next run:

```bash
rm /etc/systemd/system/fxserver.service.d/10-txadmin.conf
systemctl daemon-reload && systemctl restart fxserver
```

## The gameserver_observability role says "Prometheus … did not load …"

Prometheus was reloaded but does not list the role's scrape jobs or rule files.

- `grep -n -A3 -e scrape_config_files -e rule_files /etc/prometheus/prometheus.yml` must include
  `scrape_configs/*.yml` and `rules/*.yml`.
- `journalctl -u prometheus -n 50` shows a failed reload.
- Add the includes in whatever manages `prometheus.yml` (or point
  `gameserver_observability_prometheus_config_dir` at the right folder) and run the playbook again.

## An exporter of the gameserver_observability role does not run

`systemctl status gameserver-observability-json-exporter` (or `…-blackbox-exporter`) and its
journal. Usual causes: the listen address is no longer on the host (`ip -br address`), or another
process holds the port (`ss -ltnp 'sport = :7979'`). Correct the variables and run the playbook;
it rewrites the units and module files.
