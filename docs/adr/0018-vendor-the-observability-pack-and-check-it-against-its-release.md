# 0018. Vendor the observability pack and check it against its release

- **Status:** accepted
- **Date:** 2026-10-22

## Context

The `gameserver_observability` role installs the files of the
[gameserver-observability](https://github.com/luminare-dev/gameserver-observability) pack: the
json_exporter and blackbox_exporter modules, the recording and alerting rules, the dashboard and
the scrape jobs. The pack is a separate repository with its own releases and promtool tests. The
role must install exactly one known pack version, work without network access to the pack, and
stay installable from a git tag or the collection tarball (ADR 0005). The pack's first release,
0.1.0, was published on 2026-10-22 from the same content that the role was built and tested with.

## Considered options

1. Download the pack's release archive on the managed host (or the controller) at run time, by a
   version variable.
2. Copy the pack files into the role (`files/pack/`) from one pack version, record that version,
   the source commit and the sha256 of every file in `files/pack/manifest.json`, and check them
   in CI: against the manifest always, and byte for byte against the pack's release archive once
   the manifest names its release tag.
3. A git submodule of the pack.

## Decision

Chosen option 2, with the files of the pack's 0.1.0 release (tag `v0.1.0`, commit `88543c9a`),
copied from its release archive, whose sha256 is in the manifest as well.
`scripts/check_vendored_pack.py` runs in `scripts/test.sh`, so in the `lint-test` job: every file
must match the manifest and no other file may sit in the folder. When `release_tag` in the
manifest is set, as it is now, it downloads that release's `SHA256SUMS` and source archive
(`gameserver-observability-X.Y.Z.tar.gz`), checks the archive against both and against
`release_sha256` when set, and compares every vendored file with the archive; without a tag the
comparison is skipped and the output says so. `--update-from <archive>` copies a new release into
the folder. The scrape jobs are not copied but rendered by the role's template with one entry per
game server; `tests/test_gameserver_observability.py` renders it with the pack's example values and
compares it job by job with the vendored scrape files, so a changed job in a new pack release fails
the unit tests until the template follows. Option 1 would make every run depend on GitHub and on a
version variable that could name files the role was never tested with. Option 3 does not survive
`ansible-galaxy collection build` and git installs without extra steps.

## Consequences

- Good: a collection version always installs the pack files it was tested with, offline, and a
  reviewer sees every change to them in the diff.
- Good: with the pack tag in the manifest, CI proves on every run that the files are the
  released ones.
- Bad: that comparison downloads the release archive from GitHub, so `lint-test` fails while
  GitHub is unreachable (`--offline` runs the manifest check only); for a new pack release
  `commit`, `release_tag` and `release_sha256` are set by hand after `--update-from`.
- Bad: a new pack release needs a collection release to reach users of the role.
