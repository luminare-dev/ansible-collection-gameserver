# 0019. Why the observability role adds to an existing Prometheus

- **Status:** accepted
- **Date:** 2026-10-22

## Context

The pack collects game server metrics from outside the server process: `/perf/` (basic auth),
`/dynamic.json` and `/info.json` through json_exporter, and probes through blackbox_exporter. Most
operators already run Prometheus (often with the `prometheus.prometheus` collection) and Grafana,
or want them on a separate monitoring host; Docker is never on a public game server host. `/perf/`
basic auth travels in plain HTTP. Exporters must listen on loopback or a private address only.

## Considered options

1. Install Prometheus, Grafana and all exporters with this role, or through `prometheus.prometheus`
   roles called from it.
2. Install json_exporter and blackbox_exporter from their official release archives (pinned
   version and sha256) as units of their own, and add plain files to an existing Prometheus:
   scrape jobs in `scrape_configs/`, rules in `rules/`, the password in `secrets/`, each checked
   with promtool. The role checks that Prometheus loaded them.
3. Ship only documentation and let operators copy the pack by hand.

## Decision

Chosen option 2. The role runs on the Prometheus host: one host with the game server (targets and
exporters on loopback) or a monitoring host that reaches the game servers over a private network.
The exporters run as `gameserver-observability-*` units with `DynamicUser` and a strict sandbox,
from versioned folders below `/usr/local/lib/gameserver-observability/`, so that exporters of
another setup on the same host stay untouched. The `/perf/` password goes into a file that
Prometheus reads through `password_file`, never into the scrape configuration. The file layout is
the one the `prometheus.prometheus` collection's `prometheus` role includes by default
(`scrape_configs/*`, `rules/*.yml`); for any other Prometheus the role names the two lines to add
when its check finds the jobs or rules missing. The Molecule scenario installs Prometheus 3.15.0
with that collection (0.30.2, a test-only dependency installed by Molecule's dependency step;
ansible-lint mocks the role, because the lint job installs no collections) and runs this role
with one loopback and one private-address target. Option 1 would make the role own services that
many hosts already manage, and a collection dependency that Galaxy installs cannot resolve while
this collection is installed from git (ADR 0005). Option 3 leaves the checks to the operator.

## Consequences

- Good: works with a Prometheus installed by `prometheus.prometheus`, a package or by hand, and
  never rewrites `prometheus.yml`.
- Good: a wrong include, a broken file or a Prometheus that did not reload fails the run with a
  message, instead of a silent gap in the metrics.
- Bad: the operator installs Prometheus (2.43 or later, for `scrape_config_files`), Grafana,
  node_exporter, mysqld_exporter and Alertmanager; the host and database alerts stay silent
  without them.
- Bad: only linux-amd64 exporter archives are pinned.
