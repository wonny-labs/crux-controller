# SPDX-License-Identifier: Apache-2.0
"""Checks of the VS Code files: two Cortex-Debug board profiles and the build task they depend on.

Nothing here starts VS Code, a probe or a board. The files are read and compared with the build command of
docs/board-bring-up.md.
"""

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
VSCODE = ROOT / ".vscode"
DEVCONTAINER = ROOT / ".devcontainer"


def load(path):
    return json.loads(path.read_text())


class LaunchProfiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load(VSCODE / "launch.json")
        cls.by_name = {c["name"]: c for c in cls.data["configurations"]}

    def test_exactly_the_two_board_profiles(self):
        self.assertEqual({"Board: Flash and run to main", "Board: Attach (no reset)"}, set(self.by_name))

    def test_both_use_cortex_debug_with_the_jlink_server_over_swd(self):
        for name, profile in self.by_name.items():
            with self.subTest(name):
                self.assertEqual("cortex-debug", profile["type"])
                self.assertEqual("jlink", profile["servertype"])
                self.assertEqual("swd", profile["interface"])
                self.assertEqual("MIMXRT1062xxx6A", profile["device"])

    def test_speed_is_auto_and_no_fixed_speed_is_set(self):
        for profile in self.by_name.values():
            self.assertEqual(["-speed", "auto"], profile["serverArgs"])

    def test_flash_profile_builds_first_and_runs_to_main(self):
        profile = self.by_name["Board: Flash and run to main"]
        self.assertEqual("launch", profile["request"])
        self.assertEqual("Build firmware", profile["preLaunchTask"])
        self.assertEqual("main", profile["runToEntryPoint"])

    def test_attach_profile_does_not_build_reset_or_download(self):
        profile = self.by_name["Board: Attach (no reset)"]
        self.assertEqual("attach", profile["request"])
        for key in ("preLaunchTask", "runToEntryPoint", "overrideLaunchCommands", "overrideResetCommands"):
            self.assertNotIn(key, profile)

    def test_the_elf_is_the_one_of_the_documented_board_build(self):
        guide = (ROOT / "docs" / "board-bring-up.md").read_text()
        self.assertIn("-d crux-controller/build/net", guide)
        for profile in self.by_name.values():
            self.assertEqual("${workspaceFolder}/build/net/zephyr/zephyr.elf", profile["executable"])

    def test_gdb_comes_from_the_zephyr_sdk_of_the_container(self):
        for profile in self.by_name.values():
            self.assertEqual("${env:ZEPHYR_SDK_INSTALL_DIR}/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-gdb",
                             profile["gdbPath"])


class BuildTask(unittest.TestCase):
    def test_build_firmware_runs_the_documented_west_build_in_the_workspace(self):
        tasks = {t["label"]: t for t in load(VSCODE / "tasks.json")["tasks"]}
        task = tasks["Build firmware"]
        text = " ".join([task["command"], *task.get("args", [])])
        self.assertIn("west build", text)
        self.assertIn("mimxrt1060_evk@B//qspi", text)
        self.assertIn("-d crux-controller/build/net", text)
        self.assertEqual("/workspaces/ws", task["options"]["cwd"])


class FlashTask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = {t["label"]: t for t in load(VSCODE / "tasks.json")["tasks"]}

    def test_build_and_flash_builds_first_then_flashes_with_the_jlink_runner(self):
        task = self.tasks["Board: Build and flash"]
        self.assertEqual(["Build firmware"], task["dependsOn"])
        text = " ".join([task["command"], *task.get("args", [])])
        self.assertIn("west flash -d crux-controller/build/net --runner jlink", text)
        self.assertEqual("/workspaces/ws", task["options"]["cwd"])

    def test_the_flash_task_sets_no_fixed_speed_so_the_runner_uses_auto(self):
        text = " ".join([self.tasks["Board: Build and flash"]["command"],
                         *self.tasks["Board: Build and flash"].get("args", [])])
        self.assertNotIn("--speed", text)

    def test_nothing_flashes_unless_the_task_is_chosen(self):
        for label, task in self.tasks.items():
            if label != "Board: Build and flash":
                self.assertNotIn("west flash", " ".join([task["command"], *task.get("args", [])]), label)
            self.assertNotIn("runOn", task, label)


class Extension(unittest.TestCase):
    def test_the_dev_container_installs_cortex_debug(self):
        data = json.loads((DEVCONTAINER / "devcontainer.json").read_text())
        self.assertIn("marus25.cortex-debug", data["customizations"]["vscode"]["extensions"])

    def test_cortex_debug_dependencies_come_before_it(self):
        # Cortex-Debug's extensionDependencies (its package.json) are listed before it.
        data = json.loads((DEVCONTAINER / "devcontainer.json").read_text())
        extensions = data["customizations"]["vscode"]["extensions"]
        position = extensions.index("marus25.cortex-debug")
        for dependency in ("mcu-debug.debug-tracker-vscode", "mcu-debug.memory-view", "mcu-debug.rtos-views",
                           "mcu-debug.peripheral-viewer"):
            self.assertIn(dependency, extensions)
            self.assertLess(extensions.index(dependency), position, dependency)

    def test_one_troubleshooting_row_for_the_first_activation_popup(self):
        # One row: Reload Window once, and how to reset the extensions volume. No test trail in it.
        rows = [line for line in (ROOT / "docs" / "troubleshooting.md").read_text().splitlines()
                if "Cannot activate the 'Cortex-Debug' extension" in line]
        self.assertEqual(1, len(rows), rows)
        self.assertIn("Reload Window", rows[0])
        self.assertIn("docker volume rm crux-controller-vscode-extensions", rows[0])
        for trail in ("not yet tested", "not tested", "should not"):
            self.assertNotIn(trail, rows[0])


if __name__ == "__main__":
    unittest.main()
