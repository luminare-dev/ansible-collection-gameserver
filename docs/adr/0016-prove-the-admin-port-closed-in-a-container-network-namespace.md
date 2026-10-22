# 0016. Prove the admin port closed inside the test container's network namespace

- **Status:** accepted
- **Date:** 2026-10-21

## Context

The txadmin role must keep port 40120 closed to everyone but loopback and the listed sources,
and the plan's acceptance test is that Molecule shows the port closed from outside. The fxserver
scenarios only validate their drop-in with `nft --check` (ADR 0006: no virtual machines in CI).
Each Molecule container is privileged but has its own network namespace, so a ruleset loaded
inside it filters only that container's traffic, never the Docker host's.

## Considered options

1. File assertions and `nft --check` only; the real check waits for a virtual machine.
2. Load the ruleset in the container (the role's own handler restarts `nftables.service`), build a
   veth pair into a second network namespace inside the container and connect from two source
   addresses: one in `txadmin_firewall_sources`, one outside it.
3. A second container on a Docker network that connects to the test container.

## Decision

Chosen option 2. It tests the drop-ins as loaded rules (accept for a listed source, drop for
another, the game port open) with only `iproute2` added in `prepare.yml`, no extra image, no
Docker network and nothing published on the host. Option 3 needs a second image and network per
job and depends on how the runner's Docker sets up bridges.

## Consequences

- Good: the acceptance check runs on every pull request on both platforms.
- Good: the firewall handler (`nftables.service` restart) runs in the scenario as on a host.
- Bad: a network namespace in a container is not a host: interfaces, the kernel and the base
  role's real ruleset differ, so the check from outside a real server stays part of the
  end-to-end run.
- Bad: the IPv6 rule is validated and loaded, but not probed (txAdmin listens on IPv4 only).
