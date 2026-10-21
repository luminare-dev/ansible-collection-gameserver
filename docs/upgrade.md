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

## Version notes

No release needs manual upgrade steps yet. Releases that do get a section here.
