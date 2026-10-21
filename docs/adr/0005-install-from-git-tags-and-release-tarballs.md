# 0005. Install from git tags and release tarballs

- **Status:** accepted
- **Date:** 2026-10-21

## Context

An Ansible collection is usually installed with `ansible-galaxy collection install`. That command
also accepts a git URL with a tag and a local tarball. Users need a version that cannot change
after it is published, a way to verify the download, and an install path that works the same for
the lab repository that pins this collection.

## Considered options

1. Install from a collection registry by name and version.
2. Install from a git tag (`git+https://…,vX.Y.Z`) or from the tarball that `ansible-galaxy
   collection build` produces, attached to the GitHub release with `SHA256SUMS` and a build
   provenance attestation.
3. Ask users to clone the repository and point `collections_path` at it.

## Decision

Chosen option: "git tag or release tarball", because both are immutable per release, both are
covered by the existing release workflow (ADR 0004), and the tarball gets the same checksum and
attestation as the source archive. The release workflow builds the tarball on the tag
(`extra-dist-command` in `release.yml`), fails when `galaxy.yml` does not carry the tag's version,
and writes one `SHA256SUMS` for both archives. The workflow uploads nothing to a registry; that
would be a separate decision with its own ADR.

## Consequences

- Good: one source of truth (the tag); `requirements.yml` entries use `type: git` and the tag.
- Good: the tarball is verifiable with `sha256sum -c` and `gh attestation verify`.
- Bad: installing from git needs `git` on the controller, and `ansible-galaxy collection install
  luminare.gameserver` by name alone does not work.
- Bad: the `luminare` namespace has not been requested on Galaxy. If Galaxy does not grant it,
  the fallback name is `luminare_dev.gameserver`, which changes every fully qualified name in
  users' playbooks; that rename would ship as a breaking change with upgrade notes.
