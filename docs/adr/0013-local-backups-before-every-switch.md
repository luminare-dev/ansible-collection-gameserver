# 0013. Local backups before every switch, off-host copies with any tool

- **Status:** accepted
- **Date:** 2026-10-21

## Context

The collection says it backs up game servers. What changes with an update or an operator
mistake is server-data (configuration, resources) and txData (admin accounts, player database).
The sibling collection plans a restic role for off-host backups, but this collection must not
depend on it, and a backup taken right before a build switch has to exist even on hosts without
any backup system.

## Considered options

1. Only document which paths an off-host backup tool should copy.
2. A local backup script: one zstd-compressed tar archive of server-data and txData in
   `/var/backups/fxserver`, run with the server stopped before every build switch (before the
   same run writes server-data or `secrets.cfg`) and optionally
   by a daily timer, newest `fxserver_backup_keep` archives kept; plus the same paths documented
   for off-host tools such as restic.
3. Run restic from this role.

## Decision

Chosen option 2. The script runs as root, writes the archive under a temporary name and renames it
when it is complete, keeps archives readable by root only (they contain `secrets.cfg`), leaves out
the rebuildable `server-data/cache`, and can write
`fxserver_backup_last_success_timestamp_seconds` for the node_exporter textfile collector. The
paths are a role variable (`fxserver_backup_paths`), so an off-host tool can reuse the same list.
Option 3 would tie this role to one backup tool and its credentials.

## Consequences

- Good: every update and rollback has a consistent backup taken just before it, with the
  server-data and `secrets.cfg` of the previous run even when the same run also changes them.
- Bad: during an update the server is down a little longer, because the role writes server-data
  and `secrets.cfg` after the stop; if that step fails, the role starts the old build again.
- Good: a restore is one `tar` command; the archives work without extra software beyond `zstd`.
- Bad: local archives do not survive the loss of the host; off-host copies are the operator's job.
- Bad: the timer backup runs while the server writes, so a file changed during the run can be
  inconsistent in that archive (tar reports it).
