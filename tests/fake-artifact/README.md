# Fake server artifact (test double)

The Molecule scenarios never download a real server build. Instead, their `prepare.yml` builds a
small `fx.tar.xz` with `build.py`, copies it into the test container and points
`fxserver_artifact_url` at it with a `file://` URL. The archive has the layout of a Linux server
build (`run.sh` at the top), but `run.sh` starts `fake_fxserver.py`, a Python 3 standard-library
HTTP server. It is not FXServer and contains no part of it.

| File | Purpose |
|---|---|
| `build.py` | Writes the archive: `python3 -I build.py --build 35245 --out <dir>/fx.tar.xz`; `--broken` gives a `run.sh` that exits 1 (a build that never starts). |
| `fake_fxserver.py` | The fake server. It reads `server.cfg` and the files it runs with `exec` from its working directory, refuses to start without `sv_licenseKey` (as the real server does) and never prints the key. |

What the fake answers on the TCP endpoint from `endpoint_add_tcp` (default `0.0.0.0:30120`):

| Path | Answer |
|---|---|
| `/info.json` | `"server": "FXServer-master SERVER v1.0.0.<build> linux"`, convars such as `sv_maxClients` and `onesync_enabled`, the resources from `ensure` lines |
| `/dynamic.json` | `clients` (3 by default, `FAKE_CLIENTS` changes it) and `sv_maxclients` |
| `/players.json` | synthetic players only: `player-1`, `license:000…1`, endpoint `127.0.0.1` |
| `/perf/` | `tickTime` histograms for `svMain`, `svNetwork` and `svSync` in the Prometheus text format. When `sv_prometheusBasicAuthUser` or `sv_prometheusBasicAuthPassword` is set, only with exactly these HTTP basic auth credentials (401 otherwise); when both are empty, to anyone, as build 35245 does (without its rate limit) |

The request log lists method, path and status only, never client addresses. The unit tests in
`tests/test_fake_fxserver.py` pin this behaviour. The real server's answers can differ in fields
that the fake does not model; the role only relies on `/info.json` answering with status 200.
