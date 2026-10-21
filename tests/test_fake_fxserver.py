"""Tests for the fake server artifact in tests/fake-artifact/ (build.py and fake_fxserver.py).

The Molecule scenarios of the fxserver role start this fake through the role's systemd unit, so
these tests pin what the scenarios rely on: the archive layout, the endpoints and their synthetic
data, basic auth on /perf/, the refusal to start without a license key, and that the key is never
printed. The fake runs as a subprocess on a free loopback port.
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


def temp_dir(prefix: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    unittest.addModuleCleanup(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def server_data(port: int, key: str | None = DUMMY_KEY, perf: bool = True) -> Path:
    """A server-data folder as the role writes it: server.cfg runs secrets.cfg."""
    folder = temp_dir("fake-sd-")
    (folder / "server.cfg").write_text(
        f'endpoint_add_tcp "127.0.0.1:{port}"\n'
        f'endpoint_add_udp "127.0.0.1:{port}"\n'
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


def get(url: str, auth: tuple[str, str] | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url)
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


if __name__ == "__main__":
    unittest.main()
