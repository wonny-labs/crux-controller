# SPDX-License-Identifier: Apache-2.0
"""Checks of the file capability (File): its configuration, build files, CI jobs, budget and scenario."""

import json
import pathlib
import re
import unittest

import yaml

import ci_map

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
BOARD = "mimxrt1060_evk@B//qspi"
REGIONS = {"FLASH", "RAM", "ITCM", "DTCM", "OCRAM", "OCRAM2", "IDT_LIST"}


def code_lines(path):
    return [line.split("#", 1)[0] for line in pathlib.Path(path).read_text().splitlines()]


def conf_options(path):
    options = {}
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            options[name] = value
    return options


class FileConfiguration(unittest.TestCase):
    CONF = ROOT / "app" / "conf" / "file.conf"

    def test_the_fragment_selects_the_step_and_the_fat_provider(self):
        options = conf_options(self.CONF)
        self.assertEqual("y", options.get("CONFIG_CRUX_CONTROLLER_FILE"))
        self.assertEqual("y", options.get("CONFIG_CRUX_FILE_FATFS_RT1060"))
        self.assertEqual("n", options.get("CONFIG_FS_FATFS_MOUNT_MKFS"))

    def test_the_image_has_no_format_service_and_no_other_storage(self):
        # The board image never formats: the composition keeps the volume as it finds it.
        options = conf_options(self.CONF)
        self.assertNotEqual("y", options.get("CONFIG_FILE_SYSTEM_MKFS"))
        for name in options:
            for forbidden in ("RELIANCE", "CRUX_FS_", "MMC_STACK", "EMMC", "LITTLEFS",
                              "SECURE", "CREDENTIAL", "CRUX_MGMT", "CRUX_WEB", "SSH"):
                self.assertNotIn(forbidden, name.upper(), name)

    def test_the_step_option_needs_the_workload_step_and_the_provider(self):
        kconfig = (ROOT / "app" / "Kconfig").read_text()
        block = re.search(r"config CRUX_CONTROLLER_FILE\n(.*?)(?=\nconfig |\nsource )", kconfig, re.S)
        self.assertIsNotNone(block)
        self.assertIn("depends on CRUX_CONTROLLER_WORKLOAD && CRUX_FILE_FATFS_RT1060", block.group(1))

    def test_the_overlay_declares_the_fstab_entry_the_zone_looks_up(self):
        text = (ROOT / "app" / "boards" / "file.overlay").read_text()
        self.assertIn('compatible = "zephyr,fstab,fatfs"', text)
        self.assertIn("controller_storage:", text)
        self.assertIn('mount-point = "/SD:"', text)
        self.assertNotIn("automount", text)


class FileBuildFiles(unittest.TestCase):
    def test_the_application_target_never_links_the_composition_interface(self):
        text = (ROOT / "app" / "CMakeLists.txt").read_text()
        self.assertNotIn("crux::file_zephyr", "\n".join(code_lines(ROOT / "app" / "CMakeLists.txt")))
        self.assertNotIn("compose/", "\n".join(
            line for line in code_lines(ROOT / "app" / "CMakeLists.txt") if "target_sources" in line
        ))
        self.assertIn("CONFIG_CRUX_CONTROLLER_FILE", text)

    def test_the_application_target_links_the_zone_as_a_library(self):
        text = "\n".join(code_lines(ROOT / "app" / "CMakeLists.txt"))
        self.assertRegex(text, r"add_subdirectory\(compose\)")
        self.assertRegex(text, r"target_link_libraries\(app PRIVATE[^)]*\bcompose\b")

    def test_the_zone_library_is_the_only_target_that_links_the_composition_interface(self):
        zone = "\n".join(code_lines(ROOT / "app" / "compose" / "CMakeLists.txt"))
        self.assertRegex(zone, r"target_link_libraries\(compose PRIVATE[^)]*crux::file_zephyr")
        for path in sorted(ROOT.glob("app/**/CMakeLists.txt")):
            if path.parent.name == "compose":
                continue
            self.assertNotIn("crux::file_zephyr", "\n".join(code_lines(path)), str(path))

    def test_the_zone_adds_no_include_path(self):
        for line in code_lines(ROOT / "app" / "compose" / "CMakeLists.txt"):
            for word in ("include_directories", "-include", "-I"):
                self.assertNotIn(word, line, line.strip())

    def test_the_zone_takes_sources_from_its_own_directory_only(self):
        for line in code_lines(ROOT / "app" / "compose" / "CMakeLists.txt"):
            if "add_library" in line or "target_sources" in line:
                self.assertNotIn("..", line, line.strip())

    def test_the_application_adds_the_store_source_from_app_src_only(self):
        text = "\n".join(code_lines(ROOT / "app" / "CMakeLists.txt"))
        self.assertIn("src/config_store.c", text)


@ci_map.needs_tomllib
class FileWorkflows(unittest.TestCase):
    """A job of a workflow runs the checks of the job of the same name in scripts/ci/checks.toml."""

    def ci(self):
        return yaml.safe_load((WORKFLOWS / "ci.yml").read_text())

    def commands(self, job):
        return ci_map.commands(job)

    def test_ci_has_a_file_job_that_builds_the_board_image_with_the_gate_required(self):
        self.assertIn("file", self.ci()["jobs"])
        self.assertEqual(BOARD, ci_map.job_env("file")["BOARD"])
        commands = self.commands("file")
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", commands)
        self.assertIn("conf/workload.conf;conf/file.conf", commands)
        self.assertIn("boards/file.overlay", commands)
        self.assertIn("build/file", commands)

    def test_the_file_job_checks_what_the_build_resolved(self):
        commands = self.commands("file")
        for needle in (
            "CONFIG_CRUX_CONTROLLER_FILE=y",
            "CONFIG_CRUX_FILE_FATFS_RT1060=y",
            "CONFIG_FS_FATFS_MOUNT_MKFS=y",
            "CONFIG_CRUX_FS_RELIANCE_EDGE",
            "controller_storage",
            "zephyr.bin",
        ):
            self.assertIn(needle, commands, needle)

    def test_the_file_job_runs_no_hardware_command(self):
        commands = self.commands("file")
        for word in ("west flash", "west debug", "JLink", "pyocd", "openocd"):
            self.assertNotIn(word, commands, word)

    def test_the_native_sim_scenarios_run_in_ci(self):
        # The workload job runs every scenario under tests/native_sim, so file is among them.
        self.assertIn("tests/native_sim", self.commands("workload"))
        cases = yaml.safe_load((ROOT / "tests" / "native_sim" / "file" / "testcase.yaml").read_text())
        self.assertGreaterEqual(len(cases["tests"]), 5)

    def test_the_budget_matrix_has_a_file_row_on_the_workload_base(self):
        budget = yaml.safe_load((WORKFLOWS / "budget.yml").read_text())
        self.assertIn("file", budget["jobs"]["budget"]["strategy"]["matrix"]["config"])
        row = ci_map.job_env("budget-file")
        self.assertEqual("conf/workload.conf;conf/file.conf", row["CONF"])
        self.assertEqual("boards/file.overlay", row["OVERLAY"])

    def test_the_budget_job_checks_the_resolved_configuration_of_the_step(self):
        row = ci_map.job_env("budget-file")
        self.assertIn("CONFIG_CRUX_CONTROLLER_FILE=y", row["REQUIRE"])
        self.assertIn("CONFIG_CRUX_FILE_FATFS_RT1060=y", row["REQUIRE"])
        commands = ci_map.BUDGET.read_text()
        self.assertIn("for option in $REQUIRE", commands)
        self.assertIn(".config", commands)

    def test_limits_declare_file_with_the_same_placeholder_margins(self):
        data = json.loads((ROOT / "budgets" / "limits.json").read_text())
        self.assertEqual(REGIONS, set(data["min_free_percent"]["file"]))
        self.assertTrue(all(v == 25 for v in data["min_free_percent"]["file"].values()))
        self.assertIn("placeholder", data["_comment"].lower())


class FileScenario(unittest.TestCase):
    DIRECTORY = ROOT / "tests" / "native_sim" / "file"
    CASES = ("not_ready", "mounted_not_bound", "mount_failure", "roundtrip", "bind_failure")

    def scenarios(self):
        return yaml.safe_load((self.DIRECTORY / "testcase.yaml").read_text())

    def test_one_scenario_per_case_on_the_64_bit_simulator(self):
        data = self.scenarios()
        self.assertEqual(
            {f"controller.file.native_sim.{case}" for case in self.CASES}, set(data["tests"])
        )
        for name, test in data["tests"].items():
            case = name.rsplit(".", 1)[1]
            self.assertEqual(f"FILE_CASE={case}", test["extra_args"], name)
        self.assertEqual(["native_sim/native/64"], data["common"]["platform_allow"])

    def test_the_scenario_uses_the_simulator_provider_and_no_board(self):
        options = conf_options(self.DIRECTORY / "prj.conf")
        self.assertEqual("y", options.get("CONFIG_CRUX_FILE_FATFS_SIMULATOR"))
        self.assertEqual("n", options.get("CONFIG_FS_FATFS_MOUNT_MKFS"))
        for name in options:
            self.assertNotIn("RELIANCE", name)
            self.assertNotIn("RT1060", name)

    def test_the_scenario_builds_the_zone_and_the_store_not_copies(self):
        text = (self.DIRECTORY / "CMakeLists.txt").read_text()
        self.assertIn("app/compose", text)
        self.assertIn("app/src/config_store.c", text)

    def test_every_case_has_a_source_section(self):
        source = (self.DIRECTORY / "src" / "test_file.c").read_text()
        for case in self.CASES:
            self.assertIn(f"FILE_CASE_{case}", source, case)

    def test_the_overlay_has_a_ram_disk_and_the_fstab_entry(self):
        text = (self.DIRECTORY / "app.overlay").read_text()
        self.assertIn('compatible = "zephyr,ram-disk"', text)
        self.assertIn('compatible = "zephyr,fstab,fatfs"', text)
        self.assertIn("controller_storage:", text)
        self.assertIn('mount-point = "/RAM:"', text)


class FileFindings(unittest.TestCase):
    NOTE = ROOT / "docs" / "findings" / "s3-file-composition.md"

    def test_the_findings_note_exists_and_uses_both_labels(self):
        text = self.NOTE.read_text()
        self.assertIn("Measured", text)
        self.assertIn("Inferred", text)

    def test_the_readme_lists_file(self):
        readme = (ROOT / "README.md").read_text()
        self.assertRegex(readme, r"\|\s*`file`\s*\|")


if __name__ == "__main__":
    unittest.main()
