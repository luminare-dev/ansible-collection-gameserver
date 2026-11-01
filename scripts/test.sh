#!/usr/bin/env bash
# The repository's test command (CI lint-test and the release): ansible-lint, the vendored pack check
# and the unit tests. With CI=true it first installs the pinned tools.
set -euo pipefail
cd "$(dirname "$0")/.."

# Keep equal to the defaults in .github/workflows/reusable-gitleaks.yml (bumped by hand, monthly).
GITLEAKS_VERSION=8.30.1
GITLEAKS_SHA256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb

if [ "${CI:-}" = "true" ]; then
  tools="${RUNNER_TEMP:-$(mktemp -d)}/test-tools"
  python3 -m venv "$tools/venv"
  "$tools/venv/bin/pip" install --quiet --require-hashes --only-binary=:all: -r requirements-test.txt
  curl -fsSL -o "$tools/gitleaks.tar.gz" \
    "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
  echo "${GITLEAKS_SHA256}  $tools/gitleaks.tar.gz" | sha256sum -c -
  tar -xzf "$tools/gitleaks.tar.gz" -C "$tools" gitleaks
  export PATH="$tools/venv/bin:$tools:$PATH"
fi

ansible-lint
# The pack files in roles/gameserver_observability/files/pack/ against their manifest, and against
# the pack's release archive when the manifest names a release tag (skipped otherwise).
python3 scripts/check_vendored_pack.py
python3 -m unittest discover -s tests -v
