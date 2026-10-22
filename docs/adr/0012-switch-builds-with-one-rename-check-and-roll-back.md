# 0012. Switch builds with one rename, check them and roll back

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Server builds are published as one archive per build number. An update must not leave the
service running a half-unpacked build, a failed update must be undone quickly, and the download
must be the file the operator approved. The platform publishes no checksums for its downloads.
Recommended builds change about monthly, and builds older than three months are not joinable
from the server browser, so updates are routine.

## Considered options

1. Unpack each new build over the old one in place.
2. Unpack each build into `artifacts/<build>/` and point a `current` link at the active one;
   switch by replacing the link, keep the previous build, check the server after the switch.
3. As option 2, but accept a download without a known checksum and print the computed sha256
   (trust on first use) for the operator to record.

## Decision

Chosen option 2, with a required sha256. A build is downloaded only when its directory is not on
disk, checked against `fxserver_artifact_sha256`, unpacked into a temporary directory and moved
into place in one step. The switch creates the new link under a temporary name and renames it
over `current` (`rename(2)` replaces it in one step); `previous` names the old build. After every
run the role waits for `/info.json` to answer; after a switch that fails this check it restores
both links, restarts the old build and fails the run. Builds are pruned only after a passed check,
keeping the active build, the previous one and then the highest numbers. A rollback is the same
switch in the other direction and needs only the build number. Option 3 was rejected: the
defaults carry the sha256 of the official download recorded on 2026-10-21, and recording the hash
of a new build is one `sha256sum` on the workstation that downloaded it.

## Consequences

- Good: the unit never sees a missing or partial build; rollback is a link switch, not a download.
- Good: a bad build is undone without the operator. The server is down from the stop before the
  pre-update backup until the old build answers again: at most the backup time plus about twice
  `fxserver_healthcheck_timeout` (the new build's check, then the old build's check).
- Bad: every kept build costs disk space until it is pruned (the download of build 35245 alone
  is 70.6 MB; unpacked it is larger).
- Bad: every update needs three values (build, URL, sha256) from the operator.
