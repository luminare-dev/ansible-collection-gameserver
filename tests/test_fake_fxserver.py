"""Tests for the fake server artifact in tests/fake-artifact/ (build.py and fake_fxserver.py).

The Molecule scenarios of the fxserver and txadmin roles start this fake through the systemd unit,
so these tests pin what the scenarios rely on: the archive layout, the endpoints and their
synthetic data, basic auth on /perf/, the refusal to start without a license key, the txAdmin mode
(TXHOST_* checks as in txAdmin 8.1.1, /host/status and its token, admins.json from the default
account, the game server checks) and that no secret is ever printed. The fake runs as a
subprocess on free loopback ports.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKE_DIR = ROOT / "tests" / "fake-artifact"
sys.path.insert(0, str(FAKE_DIR))

import build as fake_build  # noqa: E402

DUMMY_KEY = "unit-test-dummy-key"
PERF_USER = "prometheus"
PERF_PASSWORD = "unit-test-perf-password-0123"
# txAdmin mode: test values only. The hash has the shape of a bcrypt hash (22 salt and 31 hash
# characters) but is no hash of any password.
API_TOKEN = "unit-test-token-0123456789"
ADMIN_NAME = "unit_admin"
FAKE_HASH = "$2b$12$unit.test.salt.only.00unit.test.hash.not.a.password.0"


def temp_dir(prefix: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    unittest.addModuleCleanup(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def server_data(port: int, key: str | None = DUMMY_KEY, perf: bool = True, host: str = "127.0.0.1") -> Path:
    """A server-data folder as the role writes it: server.cfg runs secrets.cfg."""
    folder = temp_dir("fake-sd-")
    (folder / "server.cfg").write_text(
        f'endpoint_add_tcp "{host}:{port}"\n'
        f'endpoint_add_udp "{host}:{port}"\n'
        "# a comment\n"
        'sv_hostname "Unit test server"\n'
        'sets sv_projectName "Unit test"\n'
        "sv_maxclients 48\n"
        "set onesync on\n"
        "ensure mapmanager\n"
        "exec secrets.cfg\n",
        encoding="utf-8",
    )
    lines = []
    if key is not None:
        lines.append(f'sv_licenseKey "{key}"')
    if perf:
        lines += [f'set sv_prometheusBasicAuthUser "{PERF_USER}"',
                  f'set sv_prometheusBasicAuthPassword "{PERF_PASSWORD}"']
    (folder / "secrets.cfg").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def unpack(build: int, broken: bool = False) -> Path:
    archive = fake_build.build_archive(build, temp_dir("fake-tar-") / "fx.tar.xz", broken)
    dest = temp_dir("fake-art-")
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")
    return dest


def get(url: str, auth: tuple[str, str] | None = None, headers: dict[str, str] | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url, headers=headers or {})
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as resp:  # noqa: S310 (loopback test server)
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, exc.read().decode("utf-8")


class ArchiveTest(unittest.TestCase):
    def test_layout_and_modes(self):
        archive = fake_build.build_archive(35245, temp_dir("fake-tar-") / "fx.tar.xz")
        with tarfile.open(archive) as tar:
            files = {m.name: m for m in tar.getmembers() if m.isfile()}
            self.assertEqual(sorted(files), [
                "alpine/opt/cfx-server/FAKE-ARTIFACT.txt",
                "alpine/opt/cfx-server/build",
                "alpine/opt/cfx-server/fake_fxserver.py",
                "run.sh",
            ])
            self.assertEqual(files["run.sh"].mode, 0o755)
            self.assertEqual(tar.extractfile("alpine/opt/cfx-server/build").read(), b"35245\n")
            note = tar.extractfile("alpine/opt/cfx-server/FAKE-ARTIFACT.txt").read().decode()
            self.assertIn("not FXServer", note)

    def test_broken_build_never_starts(self):
        art = unpack(35247, broken=True)
        out = subprocess.run(["bash", str(art / "run.sh"), "+exec", "server.cfg"], cwd=art,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 1)
        self.assertIn("broken on purpose", out.stderr)

    def test_main_rejects_a_build_number_of_zero(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            fake_build.main(["--build", "0", "--out", str(temp_dir("fake-tar-") / "fx.tar.xz")])


class FakeServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.cwd = server_data(cls.port)
        art = unpack(35245)
        # Started like the role's unit does: run.sh of the artifact with +exec server.cfg.
        cls.proc = subprocess.Popen(["bash", str(art / "run.sh"), "+exec", "server.cfg"], cwd=cls.cwd,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    env={**os.environ, "FAKE_CLIENTS": "2"})
        cls.base = f"http://127.0.0.1:{cls.port}"
        deadline = time.monotonic() + 20
        while True:
            try:
                get(cls.base + "/info.json")
                break
            except OSError:
                if cls.proc.poll() is not None or time.monotonic() > deadline:
                    cls.tearDownClass()
                    raise
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "output"):
            return
        if cls.proc.poll() is None:
            cls.proc.terminate()
        cls.output = cls.proc.communicate(timeout=10)[0]

    def test_info_names_the_build_and_reads_the_config(self):
        status, body = get(self.base + "/info.json")
        self.assertEqual(status, 200)
        info = json.loads(body)
        self.assertEqual(info["server"], "FXServer-master SERVER v1.0.0.35245 linux")
        self.assertEqual(info["vars"]["sv_maxClients"], "48")
        self.assertEqual(info["vars"]["sv_projectName"], "Unit test")
        self.assertEqual(info["vars"]["onesync_enabled"], "true")
        self.assertEqual(info["resources"], ["mapmanager"])

    def test_dynamic_counts_the_synthetic_players(self):
        dynamic = json.loads(get(self.base + "/dynamic.json")[1])
        self.assertEqual(dynamic["clients"], 2)
        self.assertEqual(dynamic["sv_maxclients"], "48")
        self.assertEqual(dynamic["hostname"], "Unit test server")

    def test_players_are_synthetic(self):
        players = json.loads(get(self.base + "/players.json")[1])
        self.assertEqual([p["name"] for p in players], ["player-1", "player-2"])
        self.assertEqual(players[0]["identifiers"], ["license:" + "0" * 39 + "1"])

    def test_perf_needs_basic_auth(self):
        self.assertEqual(get(self.base + "/perf/")[0], 401)
        self.assertEqual(get(self.base + "/perf/", (PERF_USER, "wrong-password"))[0], 401)
        status, body = get(self.base + "/perf/", (PERF_USER, PERF_PASSWORD))
        self.assertEqual(status, 200)
        self.assertIn('tickTime_count{name="svMain"}', body)
        self.assertIn('tickTime_bucket{name="svSync",le="+Inf"}', body)

    def test_unknown_path_is_404(self):
        self.assertEqual(get(self.base + "/nothing")[0], 404)

    def test_zz_log_never_shows_the_key(self):
        """Runs last (name order): stops the server and reads everything it printed."""
        get(self.base + "/info.json")
        self.tearDownClass()
        self.assertIn("listening on 127.0.0.1", self.output)
        self.assertIn("GET /info.json -> 200", self.output)
        self.assertNotIn(DUMMY_KEY, self.output)
        self.assertNotIn(PERF_PASSWORD, self.output)
        self.assertNotIn("127.0.0.1 -", self.output, "client addresses must not be logged")


class PerfWithoutCredentialsTest(unittest.TestCase):
    """Without sv_prometheusBasicAuthUser/Password, /perf/ is open to anyone, as on build 35245.

    The fxserver role never leaves both empty (it writes a random password instead); this pins
    the behaviour its Molecule scenario relies on to prove that /perf/ is closed by default.
    """

    def test_perf_answers_without_credentials(self):
        port = free_port()
        proc = subprocess.Popen([sys.executable, "-I", str(FAKE_DIR / "fake_fxserver.py"), "+exec", "server.cfg"],
                                cwd=server_data(port, perf=False), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    status, body = get(f"http://127.0.0.1:{port}/perf/")
                    break
                except OSError:
                    if proc.poll() is not None or time.monotonic() > deadline:
                        raise
                    time.sleep(0.1)
            self.assertEqual(status, 200)
            self.assertIn('tickTime_count{name="svMain"}', body)
        finally:
            if proc.poll() is None:
                proc.terminate()
            output = proc.communicate(timeout=10)[0]
        self.assertIn("/perf/ basic auth off (open to anyone)", output)


class StartupTest(unittest.TestCase):
    def run_fake(self, cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", str(FAKE_DIR / "fake_fxserver.py"), "+exec", "server.cfg"],
                              cwd=cwd, capture_output=True, text=True, timeout=30)

    def test_refuses_to_start_without_a_license_key(self):
        out = self.run_fake(server_data(free_port(), key=None))
        self.assertEqual(out.returncode, 1)
        self.assertIn("sv_licenseKey is not set", out.stderr)

    def test_missing_config_file_fails(self):
        out = self.run_fake(temp_dir("fake-empty-"))
        self.assertEqual(out.returncode, 1)
        self.assertIn("cannot read server.cfg", out.stderr)


def start_txadmin(art: Path, cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    """Start run.sh without +exec (txAdmin mode), as the unit of fxserver_mode: txadmin does."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith("TXHOST_")}
    return subprocess.Popen(["bash", str(art / "run.sh")], cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env={**clean, "FAKE_CLIENTS": "2", **env})


def wait_for(url: str, proc: subprocess.Popen) -> None:
    deadline = time.monotonic() + 20
    while True:
        try:
            get(url)
            return
        except OSError:
            if proc.poll() is not None or time.monotonic() > deadline:
                proc.kill()
                raise AssertionError(f"{url} never answered:\n{proc.communicate(timeout=10)[0]}") from None
            time.sleep(0.1)


def stop(proc: subprocess.Popen) -> str:
    if proc.poll() is None:
        proc.terminate()
    return proc.communicate(timeout=10)[0]


class TxAdminModeTest(unittest.TestCase):
    """run.sh without +exec: txAdmin with the TXHOST_* settings the txadmin role writes."""

    @classmethod
    def setUpClass(cls):
        cls.game_port, cls.txa_port = free_port(), free_port()
        cls.cwd = server_data(cls.game_port)
        cls.data = temp_dir("fake-txdata-") / "txData"  # created by the fake
        cls.proc = start_txadmin(unpack(35245), cls.cwd, {
            "TXHOST_DATA_PATH": str(cls.data),
            "TXHOST_TXA_PORT": str(cls.txa_port),
            "TXHOST_INTERFACE": "127.0.0.1",
            "TXHOST_API_TOKEN": API_TOKEN,
            "TXHOST_DEFAULT_ACCOUNT": f"{ADMIN_NAME}::{FAKE_HASH}",
            "TXHOST_MAX_SLOTS": "48",
            "TXHOST_QUIET_MODE": "true",
            "TXHOST_GAME_NAME": "fivem",
            "TXHOST_IGNORE_DEPRECATED_CONFIGS": "true",
        })
        cls.web = f"http://127.0.0.1:{cls.txa_port}"
        cls.game = f"http://127.0.0.1:{cls.game_port}"
        wait_for(cls.web + "/", cls.proc)
        wait_for(cls.game + "/info.json", cls.proc)

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, "output"):
            cls.output = stop(cls.proc)

    def status(self, headers: dict[str, str] | None = None, query: str = "") -> dict:
        code, body = get(self.web + "/host/status" + query, headers=headers)
        self.assertEqual(code, 200)  # txAdmin answers 200 also for token errors
        return json.loads(body)

    def test_web_pages(self):
        for path in ("/", "/login"):
            with self.subTest(path=path):
                code, body = get(self.web + path)
                self.assertEqual(code, 200)
                self.assertIn("fake txAdmin", body)
        self.assertEqual(get(self.web + "/nothing")[0], 404)

    def test_status_needs_the_token(self):
        self.assertEqual(self.status()["error"], "token missing")
        self.assertEqual(self.status({"x-txadmin-envtoken": "wrong-token-0123456789"})["error"], "invalid token")
        both = self.status({"x-txadmin-envtoken": API_TOKEN}, f"?envtoken={API_TOKEN}")
        self.assertEqual(both["error"], "token conflict")
        for status in (self.status({"x-txadmin-envtoken": API_TOKEN}), self.status(query=f"?envtoken={API_TOKEN}")):
            self.assertNotIn("error", status)
            self.assertEqual((status["status"], status["playerCount"], status["playerSlots"]), ("ONLINE", 2, 48))
            self.assertEqual(status["dataPath"], str(self.cwd))
            self.assertEqual(status["gameName"], "fivem")
            self.assertEqual(status["projectName"], "Unit test")

    def test_game_server_runs_from_server_cfg(self):
        code, body = get(self.game + "/info.json")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["server"], "FXServer-master SERVER v1.0.0.35245 linux")
        self.assertEqual(get(self.game + "/perf/", (PERF_USER, PERF_PASSWORD))[0], 200)

    def test_default_account_writes_admins_json(self):
        admins = self.data / "admins.json"
        self.assertEqual(admins.stat().st_mode & 0o777, 0o600)
        account = json.loads(admins.read_text(encoding="utf-8"))[0]
        self.assertEqual((account["name"], account["master"], account["password_hash"]), (ADMIN_NAME, True, FAKE_HASH))
        self.assertEqual(account["providers"], {})
        self.assertTrue((self.data / "default").is_dir())

    def test_zz_quiet_log_never_shows_secrets(self):
        """Runs last (name order): stops the fake and reads everything it printed."""
        get(self.game + "/info.json")
        self.status(query=f"?envtoken={API_TOKEN}")
        self.tearDownClass()
        self.assertIn(f"listening on 127.0.0.1:{self.txa_port}", self.output)
        self.assertIn(f"created the master account {ADMIN_NAME}", self.output)
        self.assertIn(f"game server started from server.cfg, listening on 127.0.0.1:{self.game_port}", self.output)
        self.assertIn("fake txAdmin: GET /host/status -> 200", self.output)
        self.assertNotIn("GET /info.json", self.output, "quiet mode keeps the game server's output out")
        for secret in (API_TOKEN, FAKE_HASH, DUMMY_KEY, PERF_PASSWORD):
            self.assertNotIn(secret, self.output)


class TxAdminSettingsTest(unittest.TestCase):
    """Invalid TXHOST_* values stop the fake like txAdmin, but the value is never printed."""

    def run_txadmin(self, env: dict[str, str]) -> subprocess.CompletedProcess:
        clean = {k: v for k, v in os.environ.items() if not k.startswith("TXHOST_")}
        return subprocess.run([sys.executable, "-I", str(FAKE_DIR / "fake_fxserver.py")],
                              cwd=server_data(free_port()), capture_output=True, text=True, timeout=30,
                              env={**clean, "TXHOST_DATA_PATH": str(temp_dir("fake-txdata-")), **env})

    def test_invalid_values_stop_txadmin(self):
        cases = {
            "TXHOST_TXA_PORT": ('"40120"', "surrounded by quotes"),
            "TXHOST_API_TOKEN": ("bad token value!", "TXHOST_API_TOKEN must be"),
            "TXHOST_DEFAULT_ACCOUNT": ("someone::not-a-bcrypt-hash", "must be a bcrypt hash"),
            "TXHOST_INTERFACE": ("::1", "must be an IPv4 address"),
            "TXHOST_FXS_PORT": ("40125", "cannot be between 40120 and 40150"),
            "TXHOST_MAX_SLOTS": ("0", "positive whole number"),
            "TXHOST_DATA_PATH": ("relative/txData", "absolute path"),
        }
        for key, (value, message) in cases.items():
            with self.subTest(key=key):
                out = self.run_txadmin({key: value})
                self.assertEqual(out.returncode, 1)
                self.assertIn(key, out.stderr)
                self.assertIn(message, out.stderr)
                self.assertNotIn(value, out.stderr + out.stdout)

    def test_account_needs_an_id_or_a_hash(self):
        out = self.run_txadmin({"TXHOST_DEFAULT_ACCOUNT": "someone:"})
        self.assertEqual(out.returncode, 1)
        self.assertIn("needs a FiveM ID or a password hash", out.stderr)

    def test_web_port_cannot_be_the_game_port(self):
        out = self.run_txadmin({"TXHOST_TXA_PORT": "30120"})
        self.assertEqual(out.returncode, 1)
        self.assertIn("cannot be 30120", out.stderr)


class TxAdminGameChecksTest(unittest.TestCase):
    """txAdmin keeps running with status OFFLINE when the game server must not start."""

    def check_offline(self, cwd: Path, env: dict[str, str], reason: str, game_port: int) -> None:
        txa_port = free_port()
        proc = start_txadmin(unpack(35245), cwd, {"TXHOST_TXA_PORT": str(txa_port), "TXHOST_INTERFACE": "127.0.0.1",
                                                  "TXHOST_API_TOKEN": "disabled", **env})
        try:
            wait_for(f"http://127.0.0.1:{txa_port}/", proc)
            code, body = get(f"http://127.0.0.1:{txa_port}/host/status")  # "disabled": no token needed
            self.assertEqual((code, json.loads(body)["status"]), (200, "OFFLINE"))
            with self.assertRaises(OSError):
                get(f"http://127.0.0.1:{game_port}/info.json")
        finally:
            output = stop(proc)
        self.assertIn(f"game server not started: {reason}", output)

    def test_slots_above_max_slots(self):
        port = free_port()
        self.check_offline(server_data(port), {"TXHOST_MAX_SLOTS": "8"}, "sv_maxclients 48 is above", port)

    def test_endpoint_on_another_interface(self):
        """With TXHOST_INTERFACE set, txAdmin requires every endpoint on that address."""
        port = free_port()
        self.check_offline(server_data(port, host="0.0.0.0"), {}, "the endpoint_add_tcp interface MUST be 127.0.0.1", port)

    def test_no_license_key(self):
        port = free_port()
        self.check_offline(server_data(port, key=None), {}, "sv_licenseKey is not set", port)

    def test_default_data_path_and_unconfigured_token(self):
        port, txa_port = free_port(), free_port()
        art = unpack(35245)
        proc = start_txadmin(art, server_data(port), {"TXHOST_TXA_PORT": str(txa_port), "TXHOST_INTERFACE": "127.0.0.1"})
        try:
            wait_for(f"http://127.0.0.1:{txa_port}/", proc)
            body = json.loads(get(f"http://127.0.0.1:{txa_port}/host/status")[1])
            self.assertEqual(body["error"], "token not configured")
            self.assertTrue((art / "txData" / "default").is_dir(), "txData next to run.sh, as txAdmin's default")
            self.assertFalse((art / "txData" / "admins.json").exists())
        finally:
            stop(proc)


if __name__ == "__main__":
    unittest.main()
