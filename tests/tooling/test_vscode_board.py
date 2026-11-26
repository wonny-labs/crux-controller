# SPDX-License-Identifier: Apache-2.0
"""Checks of the VS Code files: the board tasks, the three Cortex-Debug profiles and scripts/build-board.sh.

The tasks are named by the standard verbs with the target first (Board: Build, Board: Flash, Board: Clean). Board:
Build runs scripts/build-board.sh for one board and one build configuration of app/. The script builds in
build/<board folder>/<configuration> and points the link build/current at the folder it has just built, so the
profiles and Board: Flash use the last board build, whatever its board. Board: Flash checks for the J-Link probe and runs west flash in one process, so a missing probe
stops it; Board: Debug and Board: Attach run the same check as the hidden preLaunchTask. This repository has no native_sim application to build or run (its native_sim targets are the Twister
scenarios of tests/native_sim), so there is no native_sim task or profile, and CMake Tools covers tests/host, so
there is no Host task. Nothing here starts VS Code, west, a probe or a board: the script runs with a stub west in a
temporary folder.
"""

import json
import os
import pathlib
import re
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

# The default board, in full: board, revision, SoC and variant. The Budget job writes the same board with the default
# SoC left out (mimxrt1060_evk@B//qspi), which Zephyr fills in when it resolves the board.
BOARD = "mimxrt1060_evk@B/mimxrt1062/qspi"
BOARD_FOLDER = "mimxrt1060_evk_B_mimxrt1062_qspi"
JLINK_DEVICE = "MIMXRT1062xxx6A"
LINK = "build/current"
ELF = f"${{workspaceFolder}}/{LINK}/zephyr/zephyr.elf"
TASKS = ["Board: Build", "Board: Flash", "Board: Clean"]
HIDDEN = ["Board: Check probe", "Board: Check probe and build"]
PROBE_CHECK = ("grep -qsx 1366 /sys/bus/usb/devices/*/idVendor || { echo 'No J-Link probe found. Attach it to the "
               "Dev Container (on Windows with WSL2: usbipd attach --wsl --busid <BUSID>). "
               "See docs/board-bring-up.md, 2. Connect the probe.' >&2; exit 1; }")
FLASH = f"exec west flash -d {LINK} --runner jlink"
PROFILES = ["Board: Debug", "Board: Attach", "Board: Attach (external)"]
OLD_NAMES = ["Build firmware", "Board: Build and flash", "Board: Flash and run to main", "Board: Attach (no reset)",
             "crux-controller/build/net", "mimxrt1060_evk_B_qspi--current"]
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
    return " ".join([task.get("command", ""), *task.get("args", [])])


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
                self.assertEqual("${config:crux.jlinkDevice}", profile["device"])
                self.assertEqual(ELF, profile["executable"])
                self.assertEqual(GDB, profile["gdbPath"])
                self.assertEqual("${workspaceFolder}", profile["cwd"])

    def test_the_jlink_profiles_use_swd_and_auto_speed(self):
        for name in ("Board: Debug", "Board: Attach"):
            profile = self.by_name[name]
            self.assertEqual("jlink", profile["servertype"])
            self.assertEqual("swd", profile["interface"])
            self.assertEqual(["-speed", "auto"], profile["serverArgs"])

    def test_debug_checks_the_probe_builds_then_downloads_and_runs_to_main(self):
        profile = self.by_name["Board: Debug"]
        self.assertEqual("launch", profile["request"])
        self.assertEqual("Board: Check probe and build", profile["preLaunchTask"])
        self.assertEqual("main", profile["runToEntryPoint"])

    def test_the_attach_profiles_neither_build_reset_nor_download(self):
        for name in ("Board: Attach", "Board: Attach (external)"):
            profile = self.by_name[name]
            self.assertEqual("attach", profile["request"])
            for key in ("runToEntryPoint", "overrideLaunchCommands", "overrideResetCommands"):
                self.assertNotIn(key, profile, name)

    def test_attach_checks_the_probe_first_and_attach_external_checks_nothing(self):
        # A failing preLaunchTask stops the debug session before the GDB server starts.
        self.assertEqual("Board: Check probe", self.by_name["Board: Attach"]["preLaunchTask"])
        # The external GDB server may run where the probe is, so VS Code checks nothing.
        self.assertNotIn("preLaunchTask", self.by_name["Board: Attach (external)"])

    def test_attach_external_uses_a_gdb_server_that_vs_code_does_not_start(self):
        profile = self.by_name["Board: Attach (external)"]
        self.assertEqual("external", profile["servertype"])
        self.assertEqual("localhost:2331", profile["gdbTarget"])
        self.assertNotIn("serverArgs", profile)

    def test_the_profiles_ask_nothing_and_read_the_j_link_device_from_the_settings(self):
        # No inputs: the board, its key and the J-Link device are the settings of Crux's convention.
        self.assertNotIn("inputs", load(VSCODE / "launch.json"))
        self.assertNotIn("${input:", (VSCODE / "launch.json").read_text())

    def test_every_pre_launch_task_exists(self):
        for name, profile in self.by_name.items():
            if "preLaunchTask" in profile:
                self.assertIn(profile["preLaunchTask"], self.tasks, name)


class Settings(unittest.TestCase):
    """The board settings, with the names and the meaning that Crux's .vscode/settings.json gives them."""

    def test_the_board_the_key_and_the_j_link_device_are_settings_with_crux_s_names(self):
        settings = load(VSCODE / "settings.json")
        self.assertEqual(BOARD, settings["crux.board"])
        self.assertEqual(BOARD_FOLDER, settings["crux.boardKey"])
        self.assertEqual(JLINK_DEVICE, settings["crux.jlinkDevice"])

    def test_the_key_is_the_build_folder_of_the_board_under_crux_s_rule(self):
        # Crux: every run of characters other than letters, digits, '_', '.' and '-' becomes one '_'.
        key = re.sub(r"[^A-Za-z0-9_.-]+", "_", load(VSCODE / "settings.json")["crux.board"])
        self.assertEqual(load(VSCODE / "settings.json")["crux.boardKey"], key)
        # Crux's own default pair gives the same key, so the settings of one repository work in the other.
        self.assertEqual("mimxrt1060_evk_B_qspi", re.sub(r"[^A-Za-z0-9_.-]+", "_", "mimxrt1060_evk@B//qspi"))

    def test_tasks_and_profiles_use_only_these_settings_and_the_configuration_prompt(self):
        text = (VSCODE / "tasks.json").read_text() + (VSCODE / "launch.json").read_text()
        for used in re.findall(r"\$\{config:([^}]+)\}", text):
            self.assertIn(used, load(VSCODE / "settings.json"), used)
        self.assertEqual(["${input:configuration}"], sorted(set(re.findall(r"\$\{input:[^}]+\}", text))))


class Tasks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load(VSCODE / "tasks.json")
        cls.tasks = {t["label"]: t for t in cls.document["tasks"]}

    def test_exactly_the_three_board_tasks_and_the_two_hidden_checks(self):
        self.assertEqual(TASKS, [t["label"] for t in self.document["tasks"] if not t.get("hide")])
        self.assertEqual(HIDDEN, [t["label"] for t in self.document["tasks"] if t.get("hide")])
        for task in self.tasks.values():
            if "command" not in task:
                continue  # Board: Check probe and build only runs two tasks in turn.
            with self.subTest(task["label"]):
                self.assertEqual("process", task["type"])
                self.assertEqual("${workspaceFolder}", task["options"]["cwd"])
                self.assertNotIn("runOn", task.get("runOptions", {}))

    def test_build_runs_the_board_build_script_for_the_chosen_board_and_configuration(self):
        task = self.tasks["Board: Build"]
        self.assertEqual("bash", task["command"])
        self.assertEqual(["scripts/build-board.sh", "--board", "${config:crux.board}", "${input:configuration}"],
                         task["args"])
        self.assertEqual("build", task["group"])
        self.assertEqual("$gcc", task["problemMatcher"])

    def test_the_only_prompt_is_the_build_configuration(self):
        # net is the image of docs/board-bring-up.md, the one with a board record. The board is a setting.
        inputs = {i["id"]: i for i in self.document["inputs"]}
        self.assertEqual(["configuration"], list(inputs))
        self.assertEqual("pickString", inputs["configuration"]["type"])
        self.assertEqual(list(budget_rows()), inputs["configuration"]["options"])
        self.assertEqual("net", inputs["configuration"]["default"])

    def test_flash_checks_the_probe_then_flashes_the_last_board_build_in_one_process(self):
        # One bash process: a dependsOn task that fails does not stop the task that depends on it.
        task = self.tasks["Board: Flash"]
        self.assertEqual("bash", task["command"])
        self.assertEqual(["-c", f"{PROBE_CHECK}; {FLASH}"], task["args"])
        self.assertNotIn("dependsOn", task)
        # No "Executing task" line above the output.
        self.assertIs(False, task["presentation"]["echo"])
        # No fixed speed (the runner uses auto) and no mass erase.
        self.assertNotIn("--speed", text_of(task))
        self.assertNotIn("--erase", text_of(task))

    def test_the_hidden_check_stops_without_a_probe(self):
        task = self.tasks["Board: Check probe"]
        self.assertEqual("bash", task["command"])
        self.assertEqual(["-c", PROBE_CHECK], task["args"])
        self.assertNotIn("west", PROBE_CHECK)

    def test_the_hidden_check_and_build_runs_the_check_then_the_build(self):
        task = self.tasks["Board: Check probe and build"]
        self.assertEqual(["Board: Check probe", "Board: Build"], task["dependsOn"])
        self.assertEqual("sequence", task["dependsOrder"])
        self.assertNotIn("command", task)

    def test_clean_runs_the_clean_of_the_script_for_the_chosen_board(self):
        task = self.tasks["Board: Clean"]
        self.assertEqual("bash", task["command"])
        self.assertEqual(["scripts/build-board.sh", "--board", "${config:crux.board}", "--clean"], task["args"])
        self.assertEqual("clean", task["group"])

    def test_nothing_flashes_unless_board_flash_is_chosen(self):
        for label, task in self.tasks.items():
            if label != "Board: Flash":
                self.assertNotIn("west flash", text_of(task), label)

    def test_no_host_or_native_sim_task(self):
        for label in self.tasks:
            self.assertTrue(label.startswith("Board: "), label)


class FlashTask(unittest.TestCase):
    """The command of Board: Flash, run by bash with a stub west and a stand-in for /sys/bus/usb/devices."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = pathlib.Path(self.temporary.name)
        self.devices = base / "devices"
        self.devices.mkdir()
        self.stubs = base / "stubs"
        self.stubs.mkdir()
        self.log = base / "west.log"
        west = self.stubs / "west"
        west.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{self.log}"\n')
        west.chmod(0o755)

    def run_flash(self):
        tasks = {t["label"]: t for t in load(VSCODE / "tasks.json")["tasks"]}
        script = tasks["Board: Flash"]["args"][1].replace("/sys/bus/usb/devices", str(self.devices))
        env = dict(os.environ, PATH=f"{self.stubs}:{os.environ['PATH']}")
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)

    def test_without_a_probe_it_stops_before_west_flash(self):
        (self.devices / "1-1").mkdir()
        (self.devices / "1-1" / "idVendor").write_text("0bda\n")
        result = self.run_flash()
        self.assertEqual(1, result.returncode)
        self.assertIn("No J-Link probe found", result.stderr)
        self.assertIn("usbipd attach --wsl --busid <BUSID>", result.stderr)
        # Native Linux has no WSL2: the message names WSL2 only for the Windows case.
        self.assertNotIn("Attach it to WSL2", result.stderr)
        self.assertIn("on Windows with WSL2:", result.stderr)
        # One line: the failure, one action and the page to read.
        self.assertEqual(1, len(result.stderr.strip().splitlines()))
        self.assertIn("See docs/board-bring-up.md", result.stderr)
        self.assertFalse(self.log.exists())

    def test_with_a_probe_it_runs_west_flash(self):
        (self.devices / "1-2").mkdir()
        (self.devices / "1-2" / "idVendor").write_text("1366\n")
        result = self.run_flash()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["flash", "-d", LINK, "--runner", "jlink"], self.log.read_text().splitlines())


class BuildBoardScript(unittest.TestCase):
    """scripts/build-board.sh with a stub west, in a copy of the scripts folder."""

    # A board that is not supported, used only to show how the folder follows the board name.
    OTHER = "example_board@2.1/example_soc/cpu0"
    OTHER_FOLDER = "example_board_2.1_example_soc_cpu0"

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
        self.west_board = ""

    def run_script(self, *arguments, west_exit=0, cwd=None, board_target=None):
        # The stub answers `west config build.board` with self.west_board (unset: exit 1, as west does), logs one
        # line per argument of any other call, then writes the ELF of the build folder it was given.
        west = self.stubs / "west"
        west.write_text("#!/bin/sh\n"
                        'if [ "$1" = config ]; then\n'
                        f'  [ "$2" = build.board ] && [ -n "{self.west_board}" ] && echo "{self.west_board}" && exit 0\n'
                        "  exit 1\n"
                        "fi\n"
                        f'printf "%s\\n" "$@" > "{self.log}"\n'
                        f"[ {west_exit} -eq 0 ] || exit {west_exit}\n"
                        'while [ $# -gt 0 ]; do if [ "$1" = -d ]; then d=$2; fi; shift; done\n'
                        'mkdir -p "$d/zephyr" && echo elf > "$d/zephyr/zephyr.elf"\n')
        west.chmod(0o755)
        env = dict(os.environ, PATH=f"{self.stubs}:{os.environ['PATH']}")
        env.pop("CRUX_BOARD_TARGET", None)
        if board_target is not None:
            env["CRUX_BOARD_TARGET"] = board_target
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
                _, fixed = budget_build()
                expected = ["build", "--pristine=never", "-b", BOARD, "-d", f"build/{BOARD_FOLDER}/{name}", "app",
                            "--", *fixed]
                if conf:
                    expected.append(f"-DEXTRA_CONF_FILE={conf}")
                if overlay:
                    expected.append(f"-DEXTRA_DTC_OVERLAY_FILE={overlay}")
                self.assertEqual(expected, self.west_arguments())

    def test_the_board_option_selects_the_board_and_its_folder(self):
        result = self.run_script("--board", self.OTHER, "net")
        self.assertEqual(0, result.returncode, result.stderr)
        arguments = self.west_arguments()
        self.assertEqual(["build", "--pristine=never", "-b", self.OTHER, "-d", f"build/{self.OTHER_FOLDER}/net",
                          "app"], arguments[:7])
        self.assertEqual(f"{self.OTHER_FOLDER}/net", os.readlink(self.link()))

    def test_without_the_option_the_board_of_west_config_is_used(self):
        # west's own setting, build.board, as `west build` reads it when no board is given.
        self.west_board = self.OTHER
        result = self.run_script("workload")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["-b", self.OTHER, "-d", f"build/{self.OTHER_FOLDER}/workload"], self.west_arguments()[2:6])

    def test_the_environment_variable_of_crux_wins_over_west_config(self):
        # CRUX_BOARD_TARGET is the name that Crux's own scripts read.
        self.west_board = BOARD
        result = self.run_script("workload", board_target=self.OTHER)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["-b", self.OTHER, "-d", f"build/{self.OTHER_FOLDER}/workload"], self.west_arguments()[2:6])

    def test_the_board_option_wins_over_the_environment_variable(self):
        result = self.run_script("--board", BOARD, "workload", board_target=self.OTHER)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["-b", BOARD, "-d", f"build/{BOARD_FOLDER}/workload"], self.west_arguments()[2:6])

    def test_the_board_option_wins_over_west_config(self):
        self.west_board = self.OTHER
        result = self.run_script("--board", BOARD, "workload")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["-b", BOARD, "-d", f"build/{BOARD_FOLDER}/workload"], self.west_arguments()[2:6])

    def test_a_configured_build_folder_is_built_incrementally_without_cmake_arguments(self):
        # Extra CMake arguments make west configure the build again; the folder keeps them in its cache.
        (self.root / f"build/{BOARD_FOLDER}/net").mkdir(parents=True)
        (self.root / f"build/{BOARD_FOLDER}/net/build.ninja").write_text("")
        (self.root / f"build/{BOARD_FOLDER}/.board-build").write_text("")
        result = self.run_script("net")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["build", "--pristine=never", "-b", BOARD, "-d", f"build/{BOARD_FOLDER}/net", "app"],
                         self.west_arguments())

    def test_it_runs_from_the_repository_root_wherever_it_is_started(self):
        result = self.run_script("workload", cwd=self.root / "app")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.root / f"build/{BOARD_FOLDER}/workload/zephyr/zephyr.elf").is_file())

    def test_a_successful_build_points_the_current_link_at_its_folder(self):
        self.assertEqual(0, self.run_script("net").returncode)
        self.assertEqual(f"{BOARD_FOLDER}/net", os.readlink(self.link()))
        self.assertEqual(0, self.run_script("system").returncode)
        self.assertEqual(f"{BOARD_FOLDER}/system", os.readlink(self.link()))
        self.assertTrue((self.root / LINK / "zephyr/zephyr.elf").is_file())

    def test_a_failed_build_leaves_the_link_as_it_was(self):
        self.assertEqual(0, self.run_script("net").returncode)
        result = self.run_script("file", west_exit=3)
        self.assertEqual(3, result.returncode)
        self.assertEqual(f"{BOARD_FOLDER}/net", os.readlink(self.link()))

    def test_an_unknown_or_missing_configuration_is_refused_before_west_runs(self):
        for arguments in (("nett",), (), ("net", "file"), ("--board",), ("--board", BOARD), ("--board", "", "net")):
            with self.subTest(arguments):
                result = self.run_script(*arguments)
                self.assertEqual(2, result.returncode)
                self.assertIn("Usage:", result.stderr)
                self.assertIsNone(self.west_arguments())

    def test_a_board_name_that_is_not_a_zephyr_board_target_is_refused_before_west_runs(self):
        # The name becomes a folder below build/, so nothing that could leave it is accepted.
        for board in ("..", "../x", "a b", "/abs", "x;rm", "@B", "x/../y"):
            with self.subTest(board):
                result = self.run_script("--board", board, "net")
                self.assertEqual(2, result.returncode)
                self.assertIn("not a board target", result.stderr)
                self.assertIsNone(self.west_arguments())

    def test_a_board_whose_folder_is_another_folder_of_build_is_refused_and_kept(self):
        # Without the marker of a board folder, neither a build nor --clean touches it.
        for name in ("host", "current"):
            (self.root / "build" / name).mkdir(parents=True, exist_ok=True)
            (self.root / "build" / name / "keep").write_text("x")
            for arguments in (("--board", name, "net"), ("--board", name, "--clean")):
                with self.subTest(arguments):
                    result = self.run_script(*arguments)
                    self.assertEqual(2, result.returncode)
                    self.assertIn("is not a board folder", result.stderr)
                    self.assertTrue((self.root / "build" / name / "keep").is_file())
                    self.assertIsNone(self.west_arguments())

    def test_a_board_build_marks_its_board_folder(self):
        self.assertEqual(0, self.run_script("net").returncode)
        self.assertTrue((self.root / f"build/{BOARD_FOLDER}/.board-build").is_file())

    def test_the_short_and_full_spellings_of_a_board_get_their_own_folders(self):
        # The script does not resolve the default SoC; Zephyr does, inside the build.
        # A run of '@' and '/' becomes one '_', as in Crux's board key.
        self.assertEqual(0, self.run_script("--board", "mimxrt1060_evk@B//qspi", "net").returncode)
        self.assertEqual("mimxrt1060_evk_B_qspi/net", os.readlink(self.link()))

    def test_the_default_board_is_the_board_of_the_budget_job_and_the_gate_is_its_gate(self):
        board, fixed = budget_build()
        # The Budget job leaves the default SoC out; Zephyr resolves both spellings to the same board target.
        self.assertEqual(BOARD, board.replace("//", "/mimxrt1062/"))
        self.assertEqual(["-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON"], fixed)

    def test_a_real_folder_in_place_of_the_link_is_refused_and_kept(self):
        (self.root / LINK).mkdir(parents=True)
        (self.root / LINK / "keep").write_text("x")
        result = self.run_script("net")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("is a folder, not a link", result.stderr)
        self.assertTrue((self.root / LINK / "keep").is_file())

    def test_clean_removes_the_board_builds_of_one_board_and_its_link_only(self):
        for name in ("net", "workload"):
            self.assertEqual(0, self.run_script(name).returncode)
        self.assertEqual(0, self.run_script("--board", self.OTHER, "net").returncode)
        for keep in ("build/host", "build/host-asan", "twister-out"):
            (self.root / keep).mkdir(parents=True)
        self.log.unlink()
        # The link points at the other board, so cleaning the default board keeps it.
        result = self.run_script("--clean")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(sorted(["current", "host", "host-asan", self.OTHER_FOLDER]),
                         sorted(p.name for p in (self.root / "build").iterdir()))
        self.assertTrue(self.link().is_symlink())
        # Cleaning the board that the link points at removes the link too.
        result = self.run_script("--board", self.OTHER, "--clean")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["host", "host-asan"], sorted(p.name for p in (self.root / "build").iterdir()))
        self.assertFalse(self.link().is_symlink())
        self.assertTrue((self.root / "twister-out").is_dir())
        self.assertIsNone(self.west_arguments())
        # Nothing left to clean is not an error.
        self.assertEqual(0, self.run_script("--clean").returncode)

    def test_the_script_names_the_link_that_the_vs_code_files_use(self):
        text = SCRIPT.read_text()
        self.assertIn(f"link='{LINK.split('/')[-1]}'", text)
        self.assertIn(f"default_board='{BOARD}'", text)
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
        # Board: Flash and the two J-Link profiles stop without a probe, with the message of the check.
        self.assertIn("No J-Link probe found", body)
        self.assertIn("**Board: Check probe**", body)
        # The management configuration needs the Mbed TLS group, which the Dev Container does not switch on.
        self.assertRegex(body, r"`management`[^.]*Mbed TLS group")

    def test_the_board_page_has_one_table_of_the_build_optimisation(self):
        # Only the board route: this repository has no Host preset and no native_sim application.
        text = (ROOT / "docs" / "board-bring-up.md").read_text()
        section = text[text.index("### VS Code tasks and debug profiles"):text.index("## The `net` image")]
        self.assertEqual(1, section.count("| Build | Optimisation |"))
        self.assertIn("| **Board: Build**, flashed by **Board: Flash** | Size (`-Os`), Zephyr's default |", section)
        self.assertIn("A debug optimisation level for the board builds is not decided", section)
        for other in ("native_sim", "host-debug", "Linux Host"):
            self.assertNotIn(other, section, other)
        # The table stands apart from the text around it (documentation-guidelines.md).
        self.assertIn("\n\n| Build | Optimisation |\n", section)

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
