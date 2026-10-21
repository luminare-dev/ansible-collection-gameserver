#!/usr/bin/env python3
"""List the Molecule CI jobs as a JSON array: one entry per role and platform.

Every directory under roles/ is a role, and every role must have a Molecule scenario in
roles/<role>/molecule/default/molecule.yml: a role without one fails the run, so that no role
leaves CI untested. Each role gets one entry per test platform (Debian 13 first, then Ubuntu
24.04) with the name of the Molecule instance that its scenario declares for that platform:
gs-<role>-<platform>, with "_" in the role name written as "-". CI runs
`molecule test --platform-name <instance>` once per entry. The role names end up in job names and
paths, so each one must be a valid role name (lower-case letter first, then lower-case letters,
digits or underscores); any other directory under roles/ fails the run.

Usage:
    python3 scripts/molecule_scenarios.py                    print the array, e.g.
        [{"role":"fxserver","platform":"debian13","instance":"gs-fxserver-debian13"},
         {"role":"fxserver","platform":"ubuntu2404","instance":"gs-fxserver-ubuntu2404"}]
    python3 scripts/molecule_scenarios.py --github-output    also append matrix=<array> to the
                                                             file named by $GITHUB_OUTPUT

Exit codes: 0 ok, 1 invalid role directory name or a role without a scenario,
2 --github-output without $GITHUB_OUTPUT.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SCENARIO_FILE = Path("molecule") / "default" / "molecule.yml"
# Test platforms, primary first. Each one is also an image name in molecule/resources/Dockerfile.j2
# (gs-<platform>) and the suffix of the instance names in every scenario.
PLATFORMS = ("debian13", "ubuntu2404")


def scenario_roles(root: Path) -> tuple[list[str], list[str]]:
    """Return (sorted role names, errors) for the directories under roles/.

    A directory is a role when its name is a valid role name and it has a default scenario; every
    other directory gives one error line.
    """
    roles_dir = root / "roles"
    if not roles_dir.is_dir():
        return [], []
    roles: list[str] = []
    errors: list[str] = []
    for name in sorted(d.name for d in roles_dir.iterdir() if d.is_dir()):
        if not ROLE_RE.match(name):
            errors.append(f"roles/{name}: not a valid role name (^[a-z][a-z0-9_]*$)")
        elif not (roles_dir / name / SCENARIO_FILE).is_file():
            errors.append(f"roles/{name}: no Molecule scenario (roles/{name}/{SCENARIO_FILE.as_posix()})")
        else:
            roles.append(name)
    return roles, errors


def instance_name(role: str, platform: str) -> str:
    """Molecule instance (and host) name of a role's scenario on one platform."""
    return f"gs-{role.replace('_', '-')}-{platform}"


def matrix(roles: list[str]) -> list[dict[str, str]]:
    """One CI matrix entry per role and platform, in role order, then platform order."""
    return [
        {"role": role, "platform": platform, "instance": instance_name(role, platform)}
        for role in roles
        for platform in PLATFORMS
    ]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    p.add_argument("--github-output", action="store_true", help="append matrix=<array> to $GITHUB_OUTPUT")
    args = p.parse_args(argv)

    roles, errors = scenario_roles(args.root)
    for line in errors:
        print(f"error: {line}", file=sys.stderr)
    if errors:
        return 1

    array = json.dumps(matrix(roles), separators=(",", ":"))
    print(array)
    if args.github_output:
        target = os.environ.get("GITHUB_OUTPUT")
        if not target:
            print("error: --github-output needs the GITHUB_OUTPUT environment variable", file=sys.stderr)
            return 2
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(f"matrix={array}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
