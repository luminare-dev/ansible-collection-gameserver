#!/usr/bin/env python3
"""List the Molecule CI jobs as a JSON array: one entry per role, scenario and platform.

Every directory under roles/ is a role, and every role must have a Molecule scenario in
roles/<role>/molecule/default/molecule.yml: a role without one fails the run, so that no role
leaves CI untested. Every other directory roles/<role>/molecule/<scenario>/ with a molecule.yml is
a further scenario of that role (for example "upgrade"); default comes first, the others follow in
name order. Each scenario gets one entry per test platform (Debian 13 first, then Ubuntu 24.04)
with the name of the Molecule instance that it declares for that platform:
gs-<role>-<platform> for default and gs-<role>-<scenario>-<platform> for the others, with "_" in
role and scenario names written as "-". CI runs
`molecule test --scenario-name <scenario> --platform-name <instance>` once per entry. Role and
scenario names end up in job names and paths, so each one must be a valid name (lower-case letter
first, then lower-case letters, digits or underscores); any other directory fails the run, and so
do two entries with the same instance name.

Usage:
    python3 scripts/molecule_scenarios.py                    print the array, e.g.
        [{"role":"fxserver","scenario":"default","platform":"debian13","instance":"gs-fxserver-debian13"},
         {"role":"fxserver","scenario":"default","platform":"ubuntu2404","instance":"gs-fxserver-ubuntu2404"}]
    python3 scripts/molecule_scenarios.py --github-output    also append matrix=<array> to the
                                                             file named by $GITHUB_OUTPUT

Exit codes: 0 ok, 1 invalid role or scenario directory name, a role without a default scenario
or a duplicate instance name, 2 --github-output without $GITHUB_OUTPUT.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
DEFAULT = "default"
SCENARIO_FILE = Path("molecule") / DEFAULT / "molecule.yml"
# Test platforms, primary first. Each one is also an image name in molecule/resources/Dockerfile.j2
# (gs-<platform>) and the suffix of the instance names in every scenario.
PLATFORMS = ("debian13", "ubuntu2404")


def role_scenarios(roles_dir: Path, role: str) -> tuple[list[str], list[str]]:
    """Return (scenario names, errors) of one role: default first, then the others sorted."""
    molecule_dir = roles_dir / role / "molecule"
    scenarios: list[str] = []
    errors: list[str] = []
    for name in sorted(d.name for d in molecule_dir.iterdir() if (d / "molecule.yml").is_file()):
        if not NAME_RE.match(name):
            errors.append(f"roles/{role}/molecule/{name}: not a valid scenario name (^[a-z][a-z0-9_]*$)")
        elif name != DEFAULT:
            scenarios.append(name)
    return [DEFAULT, *scenarios], errors


def scenario_roles(root: Path) -> tuple[dict[str, list[str]], list[str]]:
    """Return ({role: scenario names}, errors) for the directories under roles/, roles sorted.

    A directory is a role when its name is a valid role name and it has a default scenario; every
    other directory gives one error line.
    """
    roles_dir = root / "roles"
    if not roles_dir.is_dir():
        return {}, []
    roles: dict[str, list[str]] = {}
    errors: list[str] = []
    for name in sorted(d.name for d in roles_dir.iterdir() if d.is_dir()):
        if not NAME_RE.match(name):
            errors.append(f"roles/{name}: not a valid role name (^[a-z][a-z0-9_]*$)")
        elif not (roles_dir / name / SCENARIO_FILE).is_file():
            errors.append(f"roles/{name}: no Molecule scenario (roles/{name}/{SCENARIO_FILE.as_posix()})")
        else:
            scenarios, scenario_errors = role_scenarios(roles_dir, name)
            errors.extend(scenario_errors)
            roles[name] = scenarios
    return roles, errors


def instance_name(role: str, platform: str, scenario: str = DEFAULT) -> str:
    """Molecule instance (and host) name of a role's scenario on one platform."""
    parts = [role] if scenario == DEFAULT else [role, scenario]
    return "-".join(["gs", *(p.replace("_", "-") for p in parts), platform])


def matrix(roles: dict[str, list[str]]) -> list[dict[str, str]]:
    """One CI matrix entry per role, scenario and platform, in that order."""
    return [
        {"role": role, "scenario": scenario, "platform": platform,
         "instance": instance_name(role, platform, scenario)}
        for role, scenarios in roles.items()
        for scenario in scenarios
        for platform in PLATFORMS
    ]


def duplicate_instances(entries: list[dict[str, str]]) -> list[str]:
    """Instance names that more than one entry would use (in order of first repetition)."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for entry in entries:
        if entry["instance"] in seen and entry["instance"] not in duplicates:
            duplicates.append(entry["instance"])
        seen.add(entry["instance"])
    return duplicates


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    p.add_argument("--github-output", action="store_true", help="append matrix=<array> to $GITHUB_OUTPUT")
    args = p.parse_args(argv)

    roles, errors = scenario_roles(args.root)
    entries = matrix(roles)
    errors += [f"instance name {name} is used by more than one role or scenario"
               for name in duplicate_instances(entries)]
    for line in errors:
        print(f"error: {line}", file=sys.stderr)
    if errors:
        return 1

    array = json.dumps(entries, separators=(",", ":"))
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
