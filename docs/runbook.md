# Runbook

This version has no roles, so nothing runs on a managed host yet. The entries below cover the
automation that runs in this repository: the weekly Molecule run and the release.

## Failure: the `molecule` check is red

| | |
|---|---|
| **Meaning** | At least one `molecule-scenario (<role>, <platform>)` job failed or was cancelled, or the `plan` job could not list the scenarios. |
| **Impact** | The pull request (or the weekly run on Tuesdays) has a role that is untested on that platform; a new package or base image may have broken it. |
| **Diagnosis** | The job name says which role and platform failed. Open the job and find the first failed step: converge (a task failed), idempotence (a task reported `changed` on the second run) or verify (an assertion failed). If only one platform failed, look for a package or path that differs between Debian 13 and Ubuntu 24.04. Reproduce it with `cd roles/<role> && molecule test --platform-name gs-<role>-<platform>` (write `_` in the role name as `-`). |
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
