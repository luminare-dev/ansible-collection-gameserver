# 0011. Service user `fxserver` and one directory layout

- **Status:** accepted
- **Date:** 2026-10-21

## Context

The `fxserver` role installs the game server, and other roles and projects (the `txadmin` role,
the gameserver-observability pack, the infra-edge-lab repository) need to find its user, paths,
unit and ports without reading the role. The plan text names the system user `fivem`, which puts
a platform mark into an identifier. The service must be able to write its own data, and nothing
else on the host.

## Considered options

1. User `fivem`, paths chosen per role.
2. User and group `fxserver` and one fixed layout shared by all projects: `/opt/fxserver` with
   `artifacts/<build>/` plus the links `current` and `previous`, `server-data/`, `txData/`,
   `server-data/secrets.cfg` (0600), unit `fxserver.service`, game port 30120 tcp and udp.
3. As option 2, but with the unpacked builds owned by root and read-only for the service.

## Decision

Chosen option 2. `fxserver` names the software the service runs, not a platform, and every path
is a role variable whose default is the shared layout. The service user has no login shell and
its home is `/opt/fxserver`; the unit runs with `ProtectSystem=strict` and
`ReadWritePaths=/opt/fxserver`, so the rest of the file system is read-only for it. Option 3 was
not taken because it cannot be tested here: system resources inside a build may write next to
their own files (for example a package cache), and only a real, keyed build would show it. It
stays a candidate once that test exists.

## Consequences

- Good: one set of names in every project; no platform mark in user, group or unit names.
- Good: backups and the firewall drop-in refer to the same paths as the observability pack.
- Bad: code that a server resource runs can change the build files of its own server.
- Bad: hosts set up by hand with a `fivem` user need the variables set or a migration.
- Bad: the git checkout of server-data runs as the service user, so the deploy key must be
  readable by the user that also runs the server. The role writes the key only for the checkout
  and removes it afterwards; a read-only deploy key limits what a leaked key allows.
- Bad: the unit always starts the server with `server.cfg`; this version has no `fxserver_mode`.
  Running the server under txAdmin needs a second `ExecStart` in this role's unit template,
  chosen by a role variable, rather than a drop-in that resets `ExecStart`, so that the unit file
  alone shows how the server starts; the txAdmin drop-in `fxserver.service.d/10-txadmin.conf`
  then only adds its environment file.
