# SPDX-License-Identifier: Apache-2.0
"""Checks of scripts/bootstrap.sh, the one entry that the Dev Container runs after it is created.

The script is a dispatcher: CRUX_BOOTSTRAP=host runs the layout check, zephyr runs the workspace setup, all
(the default) runs both in that order. The tests run the real script in a temporary clone against stand-ins
for the two scripts it calls, so nothing here starts Docker, west or the network.
"""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "bootstrap.sh"


class BootstrapDispatch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = pathlib.Path(self._tmp.name) / "crux-controller"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / ".devcontainer").mkdir()
        shutil.copy(SCRIPT, self.repo / "scripts" / "bootstrap.sh")
        self.log = pathlib.Path(self._tmp.name) / "calls.log"
        for name in ("check-host.sh", "setup.sh"):
            stub = self.repo / ".devcontainer" / name
            stub.write_text(f'#!/usr/bin/env bash\necho "{name}" >> "{self.log}"\n'
                            f'[[ -z "${{STUB_FAIL:-}}" || "{name}" != "$STUB_FAIL" ]] || exit 7\n')

    def run_script(self, value=None, **extra):
        env = {k: v for k, v in os.environ.items() if k != "CRUX_BOOTSTRAP"}
        env.update(extra)
        if value is not None:
            env["CRUX_BOOTSTRAP"] = value
        return subprocess.run(["bash", str(self.repo / "scripts" / "bootstrap.sh")],
                              capture_output=True, text=True, env=env)

    def calls(self):
        return self.log.read_text().split("\n")[:-1] if self.log.exists() else []

    def test_default_is_all_in_order(self):
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["check-host.sh", "setup.sh"], self.calls())

    def test_host_runs_only_the_layout_check(self):
        self.assertEqual(0, self.run_script("host").returncode)
        self.assertEqual(["check-host.sh"], self.calls())

    def test_zephyr_runs_only_the_setup(self):
        self.assertEqual(0, self.run_script("zephyr").returncode)
        self.assertEqual(["setup.sh"], self.calls())

    def test_all_runs_both(self):
        self.assertEqual(0, self.run_script("all").returncode)
        self.assertEqual(["check-host.sh", "setup.sh"], self.calls())

    def test_other_value_is_refused_with_status_2_and_runs_nothing(self):
        result = self.run_script("everything")
        self.assertEqual(2, result.returncode)
        self.assertIn("bootstrap: CRUX_BOOTSTRAP must be host, zephyr or all", result.stderr)
        self.assertEqual([], self.calls())

    def test_failed_layout_check_stops_before_the_setup(self):
        result = self.run_script("all", STUB_FAIL="check-host.sh")
        self.assertEqual(7, result.returncode)
        self.assertEqual(["check-host.sh"], self.calls())

    def test_failed_setup_is_reported_with_the_rerun_line(self):
        result = self.run_script("zephyr", STUB_FAIL="setup.sh")
        self.assertEqual(7, result.returncode)
        self.assertIn("rerun: CRUX_BOOTSTRAP=zephyr bash scripts/bootstrap.sh", result.stderr)

    def test_standard_output_stays_clean(self):
        self.assertEqual("", self.run_script().stdout)


class BootstrapWiring(unittest.TestCase):
    def test_script_is_executable_bash_with_spdx(self):
        text = SCRIPT.read_text()
        self.assertTrue(text.startswith("#!/usr/bin/env bash\n# SPDX-License-Identifier: Apache-2.0\n"))
        self.assertIn("set -euo pipefail", text)

    def test_dev_container_runs_it_after_creation(self):
        data = json.loads((ROOT / ".devcontainer" / "devcontainer.json").read_text())
        self.assertEqual("bash scripts/bootstrap.sh", data["postCreateCommand"])

    def test_dev_shell_runs_it_before_the_command(self):
        self.assertIn("bash scripts/bootstrap.sh", (ROOT / "scripts" / "dev-shell.sh").read_text())


if __name__ == "__main__":
    unittest.main()
