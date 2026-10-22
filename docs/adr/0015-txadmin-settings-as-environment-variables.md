# 0015. txAdmin settings as environment variables, started by a launcher mode

- **Status:** accepted
- **Date:** 2026-10-21

## Context

txAdmin, the admin panel that ships with every server build, reads its host settings from
`TXHOST_*` environment variables since version 8; the old convars are deprecated. The server
build starts txAdmin only when `run.sh` gets no `+exec` argument (checked in the server's launcher
source), and txAdmin starts the game server only after a one-time web setup. txAdmin stops at
boot on an invalid `TXHOST_*` value and can print that value to its log. With
`TXHOST_INTERFACE` set, it listens on that address only and also requires every game endpoint in
`server.cfg` to use it, so `127.0.0.1` hides the game server. Its own files (`admins.json`,
`config.json`) change format between releases. The admin port must never be public.

## Considered options

1. A txadmin drop-in that resets `ExecStart` and adds everything; the fxserver role stays unaware
   of txAdmin.
2. `fxserver_mode` in the fxserver role chooses the launcher (`run.sh +exec server.cfg` or
   `run.sh`) and sets `TXHOST_DATA_PATH` in the unit; the txadmin role writes the other variables
   into a root-only environment file that its drop-in `10-txadmin.conf` adds with
   `EnvironmentFile=`.
3. Template txAdmin's `config.json` and `admins.json`.

## Decision

Chosen option 2, the plan recorded in ADR 0011: the unit file alone shows how the server starts,
the fxserver role's health check can follow the mode (txAdmin's web page instead of
`/info.json`), and txAdmin uses the shared txData folder from its very first start, before the
txadmin role runs. Option 3 was not taken, because txAdmin owns those files.

The txadmin role leaves `TXHOST_INTERFACE` unset by default and refuses loopback addresses; it
writes `40-txadmin.nft` (loopback and listed sources only) and stops when it cannot, unless
`txadmin_firewall_required` is false. It checks every value before the first change, against
txAdmin 8.1.1's own rules, and checks `server.cfg` against the limits txAdmin enforces. The
observability toggle (`txadmin_prometheus_basic_auth`) is read by the fxserver role, which owns
`secrets.cfg`; the txadmin role checks that the two convars arrived. The fake build behaves like
txAdmin when `run.sh` has no `+exec`, so Molecule runs the real unit and drop-in.

## Consequences

- Good: no txAdmin file is ever overwritten; a txAdmin update needs no role change unless the
  variables change.
- Good: a mistake that would leave the game server offline or the panel open stops the playbook
  before any change.
- Bad: the one-time web setup (server-data folder and `server.cfg`) stays manual.
- Bad: the toggle must be set where both roles read it (inventory or play), which the txadmin
  role can only detect afterwards in `secrets.cfg`.
- Bad: the fxserver health check uses txAdmin's default port 40120; a changed `txadmin_port`
  needs `fxserver_healthcheck_url` as well.
