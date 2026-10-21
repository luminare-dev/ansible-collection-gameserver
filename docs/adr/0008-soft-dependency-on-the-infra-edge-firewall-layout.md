# 0008. Soft dependency on the infra_edge firewall layout

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Game servers need open ports (the game port) and closed ones (the admin panel). The sibling
collection `luminare.infra_edge` hardens hosts; its `base` role owns `/etc/nftables.conf` with
input policy drop and a last line `include "/etc/nftables.d/*.nft"`. A Galaxy-style dependency on
it would force every user to install it, and it cannot resolve while both collections are
installed from git tags.

## Considered options

1. `dependencies: {"luminare.infra_edge": …}` in `galaxy.yml`, and roles that call its `base` role.
2. No dependency; roles here own their firewall rules as drop-in files in `/etc/nftables.d/` that
   fit the `base` role's layout.
3. Each role writes a complete nftables configuration.

## Decision

Chosen option 2. `galaxy.yml` lists only community collections that the roles use. A role here
that needs a port writes `/etc/nftables.d/<NN>-<role>.nft` with `add rule inet filter input …
accept` lines only (the input policy is drop, so drop-ins only accept), writes it only when the
directory exists or `<role>_firewall_manage` is `true`, and validates with
`nft -c -f /etc/nftables.conf` before a reload. Numbers: 40 for the admin panel, 45 for the game
port. Molecule scenarios create a minimal file of the same shape in `prepare.yml` instead of
running the other collection.

## Consequences

- Good: works on hosts hardened by infra_edge and on hosts with their own nftables setup.
- Good: no cross-repository dependency in tests.
- Bad: the layout is a documented convention; a change in infra_edge needs a matching change here.
