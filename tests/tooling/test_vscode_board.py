# SPDX-License-Identifier: Apache-2.0
"""Checks of the VS Code files: the board tasks, the three Cortex-Debug profiles and scripts/build-board.sh.

The tasks are named by the standard verbs with the target first (Board: Build, Board: Flash, Board: Clean). Board:
Build runs scripts/build-board.sh for one build configuration of app/, which points the link
build/mimxrt1060_evk_B_qspi--current at the folder it has just built, so the profiles and Board: Flash use the last
board build. This repository has no native_sim application to build or run (its native_sim targets are the Twister
scenarios of tests/native_sim), so there is no native_sim task or profile, and CMake Tools covers tests/host, so
there is no Host task. Nothing here starts VS Code, west, a probe or a board: the script runs with a stub west in a
temporary folder.
"""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
VSCODE = ROOT / ".vscode"
DEVCONTAINER = ROOT / ".devcontainer"
SCRIPT = ROOT / "scripts" / "build-board.sh"
BUDGET = ROOT / ".github" / "workflows" / "budget.yml"

BOARD = "mimxrt1060_evk@B//qspi"
LINK = "build/mimxrt1060_evk_B_qspi--current"
ELF = f"${{workspaceFolder}}/{LINK}/zephyr/zephyr.elf"
TASKS = ["Board: Build", "Board: Flash", "Board: Clean"]
PROFILES = ["Board: Debug", "Board: Attach", "Board: Attach (external)"]
OLD_NAMES = ["Build firmware", "Board: Build and flash", "Board: Flash and run to main", "Board: Attach (no reset)",
             "crux-controller/build/net"]
GDB = "${env:ZEPHYR_SDK_INSTALL_DIR}/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-gdb"


def load(path):
    return json.loads(path.read_text())


def budget_rows():
    """The build configurations of the Budget job: name -> (conf, overlay), in its order."""
    rows = yaml.safe_load(BUDGET.read_text())["jobs"]["budget"]["strategy"]["matrix"]["include"]
    return {row["config"]: (row["conf"], row["overlay"]) for row in rows}


def budget_build():
    """The board and the fixed CMake arguments of the Budget job's build step."""
    job = yaml.safe_load(BUDGET.read_text())["jobs"]["budget"]
    step = next(s for s in job["steps"] if s.get("name", "").startswith("Build the configuration"))
    fixed = step["run"].split("args=(", 1)[1].split(")", 1)[0].split()
    return job["env"]["BOARD"], fixed


def text_of(task):
    return " ".join([task["command"], *task.get("args", [])])


class LaunchProfiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_name = {c["name"]: c for c in load(VSCODE / "launch.json")["configurations"]}
        cls.tasks = {t["label"] for t in load(VSCODE / "tasks.json")["tasks"]}

    def test_exactly_the_three_board_profiles(self):
        # One profile set for every build configuration, never one per configuration.
        self.assertEqual(PROFILES, list(self.by_name))

    def test_all_use_cortex_debug_on_the_elf_behind_the_current_build_link(self):
        for name, profile in self.by_name.items():
            with self.subTest(name):
                self.assertEqual("cortex-debug", profile["type"])
                self.assertEqual("MIMXRT1062xxx6A", profile["device"])
                self.assertEqual(ELF, profile["executable"])
                self.assertEqual(GDB, profile["gdbPath"])
                self.assertEqual("${workspaceFolder}", profile["cwd"])

    def test_the_jlink_profiles_use_swd_and_auto_speed(self):
        for name in ("Board: Debug", "Board: Attach"):
            profile = self.by_name[name]
            self.assertEqual("jlink", profile["servertype"])
            self.assertEqual("swd", profile["interface"])
            self.assertEqual(["-speed", "auto"], profile["serverArgs"])

    def test_debug_builds_first_then_downloads_and_runs_to_main(self):
        profile = self.by_name["Board: Debug"]
        self.assertEqual("launch", profile["request"])
        self.assertEqual("Board: Build", profile["preLaunchTask"])
        self.assertEqual("main", profile["runToEntryPoint"])

    def test_the_attach_profiles_neither_build_reset_nor_download(self):
        for name in ("Board: Attach", "Board: Attach (external)"):
            profile = self.by_name[name]
            self.assertEqual("attach", profile["request"])
            for key in ("preLaunchTask", "runToEntryPoint", "overrideLaunchCommands", "overrideResetCommands"):
                self.assertNotIn(key, profile, name)

    def test_attach_external_uses_a_gdb_server_that_vs_code_does_not_start(self):
        profile = self.by_name["Board: Attach (external)"]
        self.assertEqual("external", profile["servertype"])
        self.assertEqual("localhost:2331", profile["gdbTarget"])
        self.assertNotIn("serverArgs", profile)

    def test_every_pre_launch_task_exists(self):
        for name, profile in self.by_name.items():
            if "preLaunchTask" in profile:
                self.assertIn(profile["preLaunchTask"], self.tasks, name)


class Tasks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load(VSCODE / "tasks.json")
        cls.tasks = {t["label"]: t for t in cls.document["tasks"]}

    def test_exactly_the_three_board_tasks(self):
        self.assertEqual(TASKS, [t["label"] for t in self.document["tasks"]])
        for task in self.tasks.values():
            with self.subTest(task["label"]):
                self.assertEqual("process", task["type"])
                self.assertEqual("${workspaceFolder}", task["options"]["cwd"])
                self.assertNotIn("runOn", task.get("runOptions", {}))

    def test_build_runs_the_board_build_script_for_the_chosen_configuration(self):
        task = self.tasks["Board: Build"]
        self.assertEqual("bash", task["command"])
        self.assertEqual(["scripts/build-board.sh", "${input:configuration}"], task["args"])
        self.assertEqual("build", task["group"])
        self.assertEqual("$gcc", task["problemMatcher"])

    def test_the_prompt_offers_the_build_configurations_and_defaults_to_net(self):
        # net is the image of docs/board-bring-up.md, the one with a board record.
        inputs = self.document["inputs"]
        self.assertEqual(["configuration"], [i["id"] for i in inputs])
        self.assertEqual("pickString", inputs[0]["type"])
        self.assertEqual(list(budget_rows()), inputs[0]["options"])
        self.assertEqual("net", inputs[0]["default"])

    def test_flash_flashes_the_last_board_build_with_the_jlink_runner(self):
        task = self.tasks["Board: Flash"]
        self.assertEqual("west", task["command"])
        self.assertEqual(["flash", "-d", LINK, "--runner", "jlink"], task["args"])
        self.assertNotIn("dependsOn", task)
        # No fixed speed (the runner uses auto) and no mass erase.
        self.assertNotIn("--speed", text_of(task))
        self.assertNotIn("--erase", text_of(task))

    def test_clean_runs_the_clean_of_the_script(self):
        task = self.tasks["Board: Clean"]
        self.assertEqual("bash", task["command"])
        self.assertEqual(["scripts/build-board.sh", "--clean"], task["args"])
        self.assertEqual("clean", task["group"])

    def test_nothing_flashes_unless_board_flash_is_chosen(self):
        for label, task in self.tasks.items():
            if label != "Board: Flash":
                self.assertNotIn("west flash", text_of(task), label)

    def test_no_host_or_native_sim_task(self):
        for label in self.tasks:
            self.assertTrue(label.startswith("Board: "), label)


class BuildBoardScript(unittest.TestCase):
    """scripts/build-board.sh with a stub west, in a copy of the scripts folder."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name) / "crux-controller"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "app").mkdir()
        shutil.copy(SCRIPT, self.root / "scripts" / SCRIPT.name)
        self.stubs = pathlib.Path(self.temporary.name) / "stubs"
        self.stubs.mkdir()
        self.log = pathlib.Path(self.temporary.name) / "west.log"

    def run_script(self, *arguments, west_exit=0, cwd=None):
        # The stub logs one line per argument, then writes the ELF of the build folder it was given.
        west = self.stubs / "west"
        west.write_text("#!/bin/sh\n"
                        f'printf "%s\\n" "$@" > "{self.log}"\n'
                        f"[ {west_exit} -eq 0 ] || exit {west_exit}\n"
                        'while [ $# -gt 0 ]; do if [ "$1" = -d ]; then d=$2; fi; shift; done\n'
                        'mkdir -p "$d/zephyr" && echo elf > "$d/zephyr/zephyr.elf"\n')
        west.chmod(0o755)
        env = dict(os.environ, PATH=f"{self.stubs}:{os.environ['PATH']}")
        return subprocess.run(["bash", str(self.root / "scripts" / SCRIPT.name), *arguments],
                              cwd=cwd or self.root, capture_output=True, text=True, env=env)

    def west_arguments(self):
        return self.log.read_text().splitlines() if self.log.exists() else None

    def link(self):
        return self.root / LINK

    def test_a_first_build_passes_the_cmake_arguments_of_the_budget_job(self):
        for name, (conf, overlay) in budget_rows().items():
            with self.subTest(name):
                self.log.unlink(missing_ok=True)
                result = self.run_script(name)
                self.assertEqual(0, result.returncode, result.stderr)
                board, fixed = budget_build()
                expected = ["build", "--pristine=never", "-b", board, "-d", f"build/{name}", "app", "--", *fixed]
                if conf:
                    expected.append(f"-DEXTRA_CONF_FILE={conf}")
                if overlay:
                    expected.append(f"-DEXTRA_DTC_OVERLAY_FILE={overlay}")
                self.assertEqual(expected, self.west_arguments())

    def test_a_configured_build_folder_is_built_incrementally_without_cmake_arguments(self):
        # Extra CMake arguments make west configure the build again; the folder keeps them in its cache.
        (self.root / "build/net").mkdir(parents=True)
        (self.root / "build/net/build.ninja").write_text("")
        result = self.run_script("net")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["build", "--pristine=never", "-b", BOARD, "-d", "build/net", "app"],
                         self.west_arguments())

    def test_it_runs_from_the_repository_root_wherever_it_is_started(self):
        result = self.run_script("workload", cwd=self.root / "app")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.root / "build/workload/zephyr/zephyr.elf").is_file())

    def test_a_successful_build_points_the_current_link_at_its_folder(self):
        self.assertEqual(0, self.run_script("net").returncode)
        self.assertEqual("net", os.readlink(self.link()))
        self.assertEqual(0, self.run_script("system").returncode)
        self.assertEqual("system", os.readlink(self.link()))
        self.assertTrue((self.root / LINK / "zephyr/zephyr.elf").is_file())

    def test_a_failed_build_leaves_the_link_as_it_was(self):
        self.assertEqual(0, self.run_script("net").returncode)
        result = self.run_script("file", west_exit=3)
        self.assertEqual(3, result.returncode)
        self.assertEqual("net", os.readlink(self.link()))

    def test_an_unknown_or_missing_configuration_is_refused_before_west_runs(self):
        for arguments in (("nett",), (), ("net", "file")):
            with self.subTest(arguments):
                result = self.run_script(*arguments)
                self.assertEqual(2, result.returncode)
                self.assertIn("Usage:", result.stderr)
                self.assertIsNone(self.west_arguments())

    def test_the_board_and_the_gate_are_those_of_the_budget_job(self):
        board, fixed = budget_build()
        self.assertEqual(BOARD, board)
        self.assertEqual(["-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON"], fixed)

    def test_a_real_folder_in_place_of_the_link_is_refused_and_kept(self):
        (self.root / LINK).mkdir(parents=True)
        (self.root / LINK / "keep").write_text("x")
        result = self.run_script("net")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("is a folder, not a link", result.stderr)
        self.assertTrue((self.root / LINK / "keep").is_file())

    def test_clean_removes_the_board_builds_and_the_link_only(self):
        for name in ("net", "workload"):
            self.assertEqual(0, self.run_script(name).returncode)
        for keep in ("build/host", "build/host-asan", "twister-out"):
            (self.root / keep).mkdir(parents=True)
        self.log.unlink()
        result = self.run_script("--clean")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["host", "host-asan"], sorted(p.name for p in (self.root / "build").iterdir()))
        self.assertFalse(self.link().is_symlink())
        self.assertTrue((self.root / "twister-out").is_dir())
        self.assertIsNone(self.west_arguments())
        # Nothing left to clean is not an error.
        self.assertEqual(0, self.run_script("--clean").returncode)

    def test_the_script_names_the_link_that_the_vs_code_files_use(self):
        text = SCRIPT.read_text()
        self.assertIn(LINK.split("/")[-1], text)
        self.assertTrue(text.startswith("#!/usr/bin/env bash\n# SPDX-License-Identifier: Apache-2.0\n"))


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
        # Docker refuses to remove a volume that a stopped container still uses, so the row says to remove it.
        self.assertIn("remove the Dev Container's container", rows[0])
        for trail in ("not yet tested", "not tested", "should not"):
            self.assertNotIn(trail, rows[0])


class Docs(unittest.TestCase):
    def test_the_board_page_names_every_task_and_profile_and_says_that_debug_flashes(self):
        body = " ".join((ROOT / "docs" / "board-bring-up.md").read_text().split())
        for name in TASKS + PROFILES:
            self.assertIn(f"**{name}**", body, name)
        self.assertIn("scripts/build-board.sh", body)
        self.assertIn(LINK, body)
        self.assertRegex(body, r"\*\*Board: Debug\*\*[^.]*flashes")
        # The management configuration needs the Mbed TLS group, which the Dev Container does not switch on.
        self.assertRegex(body, r"`management`[^.]*Mbed TLS group")

    def test_no_current_file_names_an_old_task_profile_or_build_path(self):
        names = subprocess.check_output(["git", "-C", str(ROOT), "ls-files"], text=True).splitlines()
        current = [n for n in names
                   if (n.endswith(".md") or n.startswith((".vscode/", ".clangd")))
                   and not n.startswith(("docs/history/", "docs/findings/")) and n != "CHANGELOG.md"]
        self.assertTrue(current)
        for name in current:
            text = (ROOT / name).read_text()
            for old in OLD_NAMES:
                with self.subTest(file=name, old=old):
                    self.assertNotIn(old, text)


if __name__ == "__main__":
    unittest.main()
