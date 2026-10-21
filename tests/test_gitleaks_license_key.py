"""Tests for the license-key rules in .gitleaks.toml (cfx-server-key, cfx-license-key-any-shape).

Every key-shaped value is built at run time from random characters, so no secret-shaped string is
ever committed: this file itself must stay clean under the same configuration, which the last test
checks. The checks need the gitleaks binary on the PATH; scripts/test.sh installs the pinned
version in CI, so they run there and are skipped only where gitleaks is missing.
"""

from __future__ import annotations

import json
import secrets
import shutil
import string
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".gitleaks.toml"
PREFIX = "cfx" + "k_"  # split so that no line of this file starts a key
KEY_CHARS = string.ascii_letters + string.digits


def rand(n: int) -> str:
    return "".join(secrets.choice(KEY_CHARS) for _ in range(n))


def temp_dir(prefix: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    unittest.addModuleCleanup(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


@unittest.skipUnless(shutil.which("gitleaks"), "gitleaks is not on the PATH")
class LicenseKeyRuleTest(unittest.TestCase):
    def scan(self, target: Path) -> list[dict]:
        report = temp_dir("gl-report-") / "report.json"  # never inside the scanned folder
        subprocess.run(["gitleaks", "dir", "--no-banner", "--redact", "--exit-code", "0",
                        "--config", str(CONFIG), "--report-format", "json",
                        "--report-path", str(report), str(target)],
                       check=True, capture_output=True, text=True)
        return json.loads(report.read_text(encoding="utf-8") or "[]")

    def rules_for(self, filename: str, content: str) -> set[str]:
        folder = temp_dir("gl-key-")
        (folder / filename).write_text(content, encoding="utf-8")
        return {f["RuleID"] for f in self.scan(folder)}

    def test_key_without_inner_underscore_is_found(self):
        """The usual-shape rule cannot see this one; the any-shape rule must."""
        key = PREFIX + rand(32)
        self.assertIn("cfx-license-key-any-shape", self.rules_for("secrets.cfg", f'sv_licenseKey "{key}"\n'))

    def test_usual_shape_is_found_by_both_rules(self):
        key = f"{PREFIX}{rand(20)}_{rand(6)}"
        found = self.rules_for("host_vars.yml", f"fxserver_license_key: {key}\n")
        self.assertTrue({"cfx-server-key", "cfx-license-key-any-shape"} <= found, found)

    def test_key_in_an_environment_file_is_found(self):
        key = PREFIX + rand(24)
        self.assertIn("cfx-license-key-any-shape", self.rules_for("txadmin.env", f"TXHOST_DEFAULT_CFXKEY={key}\n"))

    def test_documented_placeholders_stay_clean(self):
        content = (
            'sv_licenseKey "CHANGE_ME_LICENSE_KEY"\n'
            "fxserver_license_key: CHANGE_ME_LICENSE_KEY\n"
            'sv_licenseKey "{{ fxserver_license_key }}"\n'
            f"sv_licenseKey {PREFIX}{'x' * 24}\n"
            f"sv_licenseKey {PREFIX}{'x' * 12}_{'x' * 6}\n"
        )
        self.assertEqual(self.rules_for("placeholders.md", content), set())

    def test_this_file_stays_clean(self):
        """The fixture builds its keys at run time, so the committed source has nothing to find."""
        folder = temp_dir("gl-self-")
        shutil.copy(Path(__file__), folder / Path(__file__).name)
        self.assertEqual(self.scan(folder), [])


if __name__ == "__main__":
    unittest.main()
