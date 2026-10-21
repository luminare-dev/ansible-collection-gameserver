#!/usr/bin/env python3
"""Fake game server for tests: a stand-in for FXServer, not the real server and no part of it.

The Molecule scenarios install a fake artifact (fx.tar.xz, built by build.py next to this file)
instead of a real server build, so that the fxserver role's systemd unit really starts and the
tests can query the same HTTP endpoints as on a real server. Python 3 standard library only; every
answer is synthetic.

Command line, as the role's unit passes it through run.sh (working directory = server-data):

    fake_fxserver.py [+exec <file>] [+set <name> <value>] ...

Config files are read like the real server reads them: one command per line, "#" and "//" start
comments, values may be quoted. The fake understands:

    endpoint_add_tcp "<address>:<port>"      where to listen (default 0.0.0.0:30120)
    exec <file>                              run another file (for example secrets.cfg)
    sv_licenseKey "<value>"                  required, as on the real server; never printed
    set|sets|setr <name> <value>             convars, e.g. sv_projectName, onesync,
                                             sv_prometheusBasicAuthUser/Password (protect /perf/)
    sv_hostname, sv_maxclients, ...          any other "sv_<name> <value>" line is a convar too
    ensure|start <resource>                  listed in /info.json

HTTP endpoints:

    /info.json      server string with the build number, convars, resources
    /dynamic.json   player count ("clients") and sv_maxclients
    /players.json   synthetic players (player-1, license:000...1, ...)
    /perf/          Prometheus text (tickTime histograms). When sv_prometheusBasicAuthUser or
                    sv_prometheusBasicAuthPassword is set, only with exactly these HTTP basic
                    auth credentials (401 otherwise); when both are empty, to anyone, as build
                    35245 does (PerfHttpHandler.cpp; the fake has no rate limit)

Environment: FAKE_CLIENTS (number of synthetic players, default 3). The build number is read
from the file "build" next to this script (build.py writes it).
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import shlex
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUCKETS = ("0.005", "0.01", "0.025", "0.05", "0.075", "0.1", "0.25", "0.5", "0.75", "1", "2.5", "5",
           "7.5", "10", "+Inf")
# Fake tick rates (ticks per second) and the share of ticks per bucket; every tick takes 2-8 ms.
THREADS = {"svMain": 20, "svNetwork": 100, "svSync": 40}
SHARES = (0.9, 1.0)  # <= 5 ms: 90 %, <= 10 ms: 100 %
MAX_EXEC_DEPTH = 8


class ConfigError(Exception):
    """A config file could not be read."""


class Config:
    def __init__(self) -> None:
        self.endpoint = ("0.0.0.0", 30120)
        self.convars: dict[str, str] = {}
        self.license_key = ""
        self.resources: list[str] = []

    def command(self, words: list[str], depth: int) -> None:
        if not words:
            return
        name, args = words[0], words[1:]
        lname = name.lower()
        if lname in ("+exec", "exec") and args:
            self.exec_file(args[0], depth + 1)
        elif lname == "endpoint_add_tcp" and args:
            host, _, port = args[0].rpartition(":")
            self.endpoint = (host.strip("[]") or "0.0.0.0", int(port))
        elif lname == "sv_licensekey" and args:
            self.license_key = args[0]
        elif lname in ("+set", "set", "sets", "setr") and len(args) >= 2:
            if args[0].lower() == "sv_licensekey":
                self.license_key = args[1]
            else:
                self.convars[args[0]] = args[1]
        elif lname in ("ensure", "start") and args:
            if args[0] not in self.resources:
                self.resources.append(args[0])
        elif lname.startswith("sv_") and args:
            self.convars[name] = args[0]

    def exec_file(self, filename: str, depth: int) -> None:
        if depth > MAX_EXEC_DEPTH:
            raise ConfigError(f"exec nested deeper than {MAX_EXEC_DEPTH} levels at {filename}")
        try:
            text = Path(filename).read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read {filename}: {exc.strerror}") from exc
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(("#", "//")):
                continue
            try:
                words = shlex.split(line, comments=False, posix=True)
            except ValueError as exc:
                raise ConfigError(f"{filename}: cannot parse a line ({exc})") from exc
            self.command(words, depth)

    def convar(self, name: str, default: str = "") -> str:
        for key, value in self.convars.items():
            if key.lower() == name.lower():
                return value
        return default

    @classmethod
    def from_argv(cls, argv: list[str]) -> Config:
        cfg = cls()
        i = 0
        while i < len(argv):
            word = argv[i]
            if word.lower() == "+exec" and i + 1 < len(argv):
                cfg.command(["+exec", argv[i + 1]], 0)
                i += 2
            elif word.lower() == "+set" and i + 2 < len(argv):
                cfg.command(["+set", argv[i + 1], argv[i + 2]], 0)
                i += 3
            else:
                i += 1
        return cfg


def read_build() -> str:
    try:
        return (HERE / "build").read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


class FakeServer:
    def __init__(self, cfg: Config, build: str, clients: int) -> None:
        self.cfg = cfg
        self.build = build
        self.started = time.monotonic()
        self.max_clients = int(cfg.convar("sv_maxclients", "32") or "32")
        self.clients = max(0, min(clients, self.max_clients))

    def info(self) -> dict:
        onesync = self.cfg.convar("onesync", "off").lower()
        variables = {
            "sv_maxClients": str(self.max_clients),
            "sv_projectName": self.cfg.convar("sv_projectName"),
            "sv_projectDesc": self.cfg.convar("sv_projectDesc"),
            "locale": self.cfg.convar("locale", "en-US"),
            "onesync_enabled": "true" if onesync in ("on", "legacy", "true") else "false",
            "gamename": "gta5",
        }
        if self.cfg.convar("sv_enforceGameBuild"):
            variables["sv_enforceGameBuild"] = self.cfg.convar("sv_enforceGameBuild")
        return {
            "enhancedHostSupport": True,
            "icon": "",
            "requestSteamTicket": "off",
            "resources": list(self.cfg.resources),
            "server": f"FXServer-master SERVER v1.0.0.{self.build} linux",
            "vars": variables,
            "version": 1,
        }

    def dynamic(self) -> dict:
        return {
            "clients": self.clients,
            "gametype": "",
            "hostname": self.cfg.convar("sv_hostname", "Fake game server"),
            "iv": "0",
            "mapname": "",
            "sv_maxclients": str(self.max_clients),
        }

    def players(self) -> list:
        return [
            {"endpoint": "127.0.0.1", "id": i, "identifiers": [f"license:{i:040d}"],
             "name": f"player-{i}", "ping": 42}
            for i in range(1, self.clients + 1)
        ]

    def perf(self) -> str:
        uptime = time.monotonic() - self.started
        lines = ["# HELP tickTime Time spent in one server tick (synthetic data from the fake server).",
                 "# TYPE tickTime histogram"]
        for thread, rate in THREADS.items():
            count = int(uptime * rate) + 1
            for le in BUCKETS:
                share = SHARES[0] if le == "0.005" else SHARES[1]
                lines.append(f'tickTime_bucket{{name="{thread}",le="{le}"}} {int(count * share)}')
            lines.append(f'tickTime_sum{{name="{thread}"}} {count * 0.004:.6f}')
            lines.append(f'tickTime_count{{name="{thread}"}} {count}')
        return "\n".join(lines) + "\n"

    def perf_authorised(self, header: str | None) -> bool:
        user = self.cfg.convar("sv_prometheusBasicAuthUser")
        password = self.cfg.convar("sv_prometheusBasicAuthPassword")
        if not user and not password:
            return True  # open to anyone, like the real server without credentials
        if not header or not header.startswith("Basic "):
            return False
        try:
            given = base64.b64decode(header[6:].strip(), validate=True)
        except ValueError:
            return False
        return hmac.compare_digest(given, f"{user}:{password}".encode("utf-8"))


def make_handler(server: FakeServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "FakeFXServer"
        sys_version = ""

        def send_body(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def send_json(self, data: object) -> None:
            self.send_body(200, json.dumps(data).encode("utf-8"), "application/json")

        def do_GET(self) -> None:  # noqa: N802 (http.server naming)
            path = self.path.split("?", 1)[0]
            if path == "/info.json":
                self.send_json(server.info())
            elif path == "/dynamic.json":
                self.send_json(server.dynamic())
            elif path == "/players.json":
                self.send_json(server.players())
            elif path in ("/perf", "/perf/"):
                if server.perf_authorised(self.headers.get("Authorization")):
                    self.send_body(200, server.perf().encode("utf-8"), "text/plain; version=0.0.4")
                else:
                    self.send_body(401, b"Unauthorized\n", "text/plain",
                                   {"WWW-Authenticate": 'Basic realm="perf"'})
            else:
                self.send_body(404, b"Not found\n", "text/plain")

        do_HEAD = do_GET

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 (base class name)
            # Path and status only: no client addresses in the log.
            sys.stdout.write(f"fake FXServer: {self.command} {self.path.split('?', 1)[0]} -> {args[1]}\n")
            sys.stdout.flush()

    return Handler


def main(argv: list[str]) -> int:
    build = read_build()
    try:
        cfg = Config.from_argv(argv)
    except ConfigError as exc:
        print(f"fake FXServer {build}: {exc}", file=sys.stderr, flush=True)
        return 1
    if not cfg.license_key:
        print(f"fake FXServer {build}: sv_licenseKey is not set; the real server refuses to start "
              "without it, so the fake does too", file=sys.stderr, flush=True)
        return 1
    clients = int(os.environ.get("FAKE_CLIENTS", "3"))
    fake = FakeServer(cfg, build, clients)
    httpd = ThreadingHTTPServer(cfg.endpoint, make_handler(fake))
    httpd.daemon_threads = True

    def stop(signum: int, _frame: object) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    auth = ("on" if cfg.convar("sv_prometheusBasicAuthUser") or cfg.convar("sv_prometheusBasicAuthPassword")
            else "off (open to anyone)")
    print(f"fake FXServer {build}: listening on {cfg.endpoint[0]}:{cfg.endpoint[1]}; sv_licenseKey "
          f"is set (value not shown); /perf/ basic auth {auth}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        print(f"fake FXServer {build}: stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
