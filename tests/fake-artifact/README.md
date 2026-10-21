# Fake server artifact (test double)

The Molecule scenarios never download a real server build. Instead, their `prepare.yml` builds a
small `fx.tar.xz` with `build.py`, copies it into the test container and points
`fxserver_artifact_url` at it with a `file://` URL. The archive has the layout of a Linux server
build (`run.sh` at the top), but `run.sh` starts `fake_fxserver.py`, a Python 3 standard-library
HTTP server. It is neither FXServer nor txAdmin and contains no part of them.

| File | Purpose |
|---|---|
| `build.py` | Writes the archive: `python3 -I build.py --build 35245 --out <dir>/fx.tar.xz`; `--broken` gives a `run.sh` that exits 1 (a build that never starts). |
| `fake_fxserver.py` | The fake server. It reads `server.cfg` and the files it runs with `exec` from its working directory, refuses to start without `sv_licenseKey` (as the real server does) and never prints the key. Without `+exec` it behaves like txAdmin (below). |

What the fake answers on the TCP endpoint from `endpoint_add_tcp` (default `0.0.0.0:30120`):

| Path | Answer |
|---|---|
| `/info.json` | `"server": "FXServer-master SERVER v1.0.0.<build> linux"`, convars such as `sv_maxClients` and `onesync_enabled`, the resources from `ensure` lines |
| `/dynamic.json` | `clients` (3 by default, `FAKE_CLIENTS` changes it) and `sv_maxclients` |
| `/players.json` | synthetic players only: `player-1`, `license:000…1`, endpoint `127.0.0.1` |
| `/perf/` | `tickTime` histograms for `svMain`, `svNetwork` and `svSync` in the Prometheus text format. When `sv_prometheusBasicAuthUser` or `sv_prometheusBasicAuthPassword` is set, only with exactly these HTTP basic auth credentials (401 otherwise); when both are empty, to anyone, as build 35245 does (without its rate limit) |

The request log lists method, path and status only, never client addresses or query strings.

## txAdmin mode

Like the real launcher, `run.sh` without a `+exec` argument starts txAdmin instead of the game
server (`fxserver_mode: txadmin` of the fxserver role). The fake then:

- reads the `TXHOST_*` variables with the rules of txAdmin 8.1.1 and stops with exit status 1 on
  a quoted or invalid value; it names the variable, never the value;
- listens on `TXHOST_INTERFACE:TXHOST_TXA_PORT` (default `0.0.0.0:40120`) and answers `/` and
  `/login` with a fake page and `/host/status` with txAdmin's token checks (header
  `x-txadmin-envtoken` or `?envtoken=`; status 200 with an `error` field when the token is
  missing, wrong or not configured);
- creates `TXHOST_DATA_PATH` (default: `txData` next to `run.sh`) and, with
  `TXHOST_DEFAULT_ACCOUNT`, writes `admins.json` (mode 0600) when it does not exist yet;
- starts the fake game server from `server.cfg` in its working directory, as a txAdmin whose
  one-time web setup is done, unless txAdmin's checks refuse it (no license key, an endpoint on
  another address than `TXHOST_INTERFACE`, a port other than `TXHOST_FXS_PORT` or in 40120-40150,
  `sv_maxclients` above `TXHOST_MAX_SLOTS`); txAdmin then keeps running with status `OFFLINE`;
- with `TXHOST_QUIET_MODE=true`, leaves the game server's request log out of its output.

The unit tests in `tests/test_fake_fxserver.py` pin this behaviour. The real answers can differ
in fields that the fake does not model; the roles only rely on `/info.json` (plain mode) or
txAdmin's web page (txAdmin mode) answering with status 200.
