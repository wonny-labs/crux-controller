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

    def run_script_args(self, *args, **extra):
        env = {k: v for k, v in os.environ.items() if k != "CRUX_BOOTSTRAP"}
        env.update(extra)
        return subprocess.run(["bash", str(self.repo / "scripts" / "bootstrap.sh"), *args],
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

    def test_keep_going_reports_the_failure_and_exits_zero(self):
        result = self.run_script_args("--keep-going", "zephyr", STUB_FAIL="setup.sh")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("rerun: CRUX_BOOTSTRAP=zephyr bash scripts/bootstrap.sh", result.stderr)
        self.assertIn("The Dev Container is usable", result.stderr)

    def test_keep_going_does_not_run_the_setup_after_a_failed_layout_check(self):
        result = self.run_script_args("--keep-going", "all", STUB_FAIL="check-host.sh")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["check-host.sh"], self.calls())

    def test_a_mode_on_the_command_line_wins_over_the_environment(self):
        self.assertEqual(0, self.run_script_args("host", CRUX_BOOTSTRAP="zephyr").returncode)
        self.assertEqual(["check-host.sh"], self.calls())

    def test_two_modes_or_an_unknown_argument_are_refused(self):
        self.assertEqual(2, self.run_script_args("host", "zephyr").returncode)
        self.assertEqual(2, self.run_script_args("--nope").returncode)
        self.assertEqual([], self.calls())

    def test_status_installs_nothing_and_says_what_is_missing(self):
        result = self.run_script_args("status", CRUX_DOCKERENV="/nonexistent", PATH="/usr/bin:/bin")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], self.calls())
        self.assertIn("workspace   not set up", result.stderr)
        self.assertIn("Zephyr SDK  not installed", result.stderr)

    def test_status_says_ok_for_a_workspace_and_an_sdk(self):
        workspace = self.repo.parent
        (workspace / ".west").mkdir()
        (workspace / ".west" / "config").write_text("")
        (workspace / "zephyr").mkdir()
        sdk = workspace / "sdk"
        sdk.mkdir()
        (sdk / ".crux-installed").write_text("")
        result = self.run_script_args("status", ZEPHYR_SDK_INSTALL_DIR=str(sdk), CRUX_DOCKERENV="/nonexistent")
        self.assertIn("workspace   ok", result.stderr)
        self.assertIn("Zephyr SDK  ok", result.stderr)

    def test_status_names_the_jlink_package_folder_in_a_container_without_the_software(self):
        flag = self.repo.parent / "dockerenv"
        flag.write_text("")
        result = self.run_script_args("status", CRUX_DOCKERENV=str(flag), PATH="/usr/bin:/bin")
        self.assertIn(".devcontainer/jlink/packages/", result.stderr)

    def test_board_host_is_refused_in_the_container(self):
        flag = self.repo.parent / "dockerenv"
        flag.write_text("")
        result = self.run_script_args("board-host", CRUX_DOCKERENV=str(flag))
        self.assertEqual(2, result.returncode)
        self.assertIn("not in the Dev Container", result.stderr)

    def test_board_host_without_the_crux_checkout_says_to_open_the_container_once(self):
        result = self.run_script_args("board-host", CRUX_DOCKERENV="/nonexistent")
        self.assertEqual(1, result.returncode)
        self.assertIn("open the Dev Container once", result.stderr)

    def test_board_host_runs_the_step_of_the_crux_checkout(self):
        crux = self.repo.parent / "crux-pilot" / "scripts"
        crux.mkdir(parents=True)
        (crux / "bootstrap.sh").write_text(f'#!/usr/bin/env bash\necho "crux $*" >> "{self.log}"\n')
        result = self.run_script_args("board-host", CRUX_DOCKERENV="/nonexistent")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["crux board-host"], self.calls())


class BootstrapWiring(unittest.TestCase):
    def test_script_is_executable_bash_with_spdx(self):
        text = SCRIPT.read_text()
        self.assertTrue(text.startswith("#!/usr/bin/env bash\n# SPDX-License-Identifier: Apache-2.0\n"))
        self.assertIn("set -euo pipefail", text)

    def test_dev_container_runs_it_after_creation(self):
        data = json.loads((ROOT / ".devcontainer" / "devcontainer.json").read_text())
        self.assertEqual("bash scripts/bootstrap.sh --keep-going", data["postCreateCommand"])

    def test_dev_shell_runs_it_before_the_command(self):
        self.assertIn("bash scripts/bootstrap.sh", (ROOT / "scripts" / "dev-shell.sh").read_text())


if __name__ == "__main__":
    unittest.main()
