#!/usr/bin/env bash
# The repository's test command: ansible-lint (production profile) and the unit tests.
# CI runs it in the lint-test job (ci.yml) and on the release tag (release.yml). Locally, run it
# from any directory with the tools of requirements-test.txt (and gitleaks) on the PATH:
#
#   bash scripts/test.sh
#
# In CI (CI=true) it first installs the hash-pinned Python tools into a fresh virtual environment
# under $RUNNER_TEMP/test-tools and the sha256-pinned gitleaks binary, so that the gitleaks rule
# tests run instead of being skipped. Molecule runs in its own CI jobs (molecule-scenario).
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
python3 -m unittest discover -s tests -v
