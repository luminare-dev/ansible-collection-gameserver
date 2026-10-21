# 0007. `requires_ansible` names only tested versions

- **Status:** accepted
- **Date:** 2026-10-21

## Context

`meta/runtime.yml` tells users and `ansible-galaxy` which ansible-core versions the collection
supports. A lower bound that was never tested promises more than the tests prove. CI and the local
toolchain use ansible-core 2.21.5.

## Considered options

1. A wide range such as `>=2.17.0`, because the modules used are old.
2. `>=2.21.0`, the tested release, lowered only after a Molecule converge passes with the older
   release.

## Decision

Chosen option 2: `requires_ansible: ">=2.21.0"`. The minimum drops to `>=2.20.0` only when a
Molecule converge of every role passes with ansible-core 2.20, and the result is recorded in the
README. ansible-lint's own list of supported releases ends at 2.19, so `.ansible-lint` adds 2.20
and 2.21 through `supported_ansible_also` instead of skipping the `meta-runtime` rule.

## Consequences

- Good: the declared range is exactly what the tests cover.
- Bad: users on ansible-core 2.20 or older have to upgrade first.
