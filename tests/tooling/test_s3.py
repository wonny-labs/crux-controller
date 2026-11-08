"""Checks of step S3 (File): its configuration, build files, CI jobs, budget and scenario."""

import json
import pathlib
import re
import unittest

import yaml

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


class S3Configuration(unittest.TestCase):
    CONF = ROOT / "app" / "conf" / "s3.conf"

    def test_the_fragment_selects_the_step_and_the_fat_provider(self):
        options = conf_options(self.CONF)
        self.assertEqual("y", options.get("CONFIG_CRUX_CONTROLLER_S3"))
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

    def test_the_step_option_needs_the_thread_service_and_the_provider(self):
        kconfig = (ROOT / "app" / "Kconfig").read_text()
        block = re.search(r"config CRUX_CONTROLLER_S3\n(.*?)(?=\nconfig |\nsource )", kconfig, re.S)
        self.assertIsNotNone(block)
        self.assertIn("depends on CRUX_THREAD && CRUX_FILE_FATFS_RT1060", block.group(1))

    def test_the_overlay_declares_the_fstab_entry_the_zone_looks_up(self):
        text = (ROOT / "app" / "boards" / "s3.overlay").read_text()
        self.assertIn('compatible = "zephyr,fstab,fatfs"', text)
        self.assertIn("controller_storage:", text)
        self.assertIn('mount-point = "/SD:"', text)
        self.assertNotIn("automount", text)


class S3BuildFiles(unittest.TestCase):
    def test_the_application_target_never_links_the_composition_interface(self):
        text = (ROOT / "app" / "CMakeLists.txt").read_text()
        self.assertNotIn("crux::file_zephyr", "\n".join(code_lines(ROOT / "app" / "CMakeLists.txt")))
        self.assertNotIn("compose/", "\n".join(
            line for line in code_lines(ROOT / "app" / "CMakeLists.txt") if "target_sources" in line
        ))
        self.assertIn("CONFIG_CRUX_CONTROLLER_S3", text)

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


class S3Workflows(unittest.TestCase):
    def ci(self):
        return yaml.safe_load((WORKFLOWS / "ci.yml").read_text())

    def commands(self, job):
        return "\n".join(step.get("run", "") for step in self.ci()["jobs"][job]["steps"])

    def test_ci_has_an_s3_job_that_builds_the_board_image_with_the_gate_required(self):
        self.assertIn("s3", self.ci()["jobs"])
        job = self.ci()["jobs"]["s3"]
        self.assertEqual(BOARD, job["env"]["BOARD"])
        commands = self.commands("s3")
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", commands)
        self.assertIn("conf/s1.conf;conf/s3.conf", commands)
        self.assertIn("boards/s3.overlay", commands)
        self.assertIn("build/s3", commands)

    def test_the_s3_job_checks_what_the_build_resolved(self):
        commands = self.commands("s3")
        for needle in (
            "CONFIG_CRUX_CONTROLLER_S3=y",
            "CONFIG_CRUX_FILE_FATFS_RT1060=y",
            "CONFIG_FS_FATFS_MOUNT_MKFS=y",
            "CONFIG_CRUX_FS_RELIANCE_EDGE",
            "controller_storage",
            "zephyr.bin",
        ):
            self.assertIn(needle, commands, needle)

    def test_the_s3_job_runs_no_hardware_command(self):
        commands = self.commands("s3")
        for word in ("west flash", "west debug", "JLink", "pyocd", "openocd"):
            self.assertNotIn(word, commands, word)

    def test_the_native_sim_scenarios_run_in_ci(self):
        # The S1 job runs every scenario under tests/native_sim, so S3 is among them.
        self.assertIn("tests/native_sim", self.commands("s1"))
        cases = yaml.safe_load((ROOT / "tests" / "native_sim" / "s3" / "testcase.yaml").read_text())
        self.assertGreaterEqual(len(cases["tests"]), 5)

    def test_the_budget_matrix_has_an_s3_row_on_the_s1_base(self):
        budget = yaml.safe_load((WORKFLOWS / "budget.yml").read_text())
        rows = {row["step"]: row for row in budget["jobs"]["budget"]["strategy"]["matrix"]["include"]}
        self.assertIn("S3", rows)
        self.assertEqual("conf/s1.conf;conf/s3.conf", rows["S3"]["conf"])
        self.assertEqual("boards/s3.overlay", rows["S3"]["overlay"])

    def test_the_budget_job_checks_the_resolved_configuration_of_the_step(self):
        budget = yaml.safe_load((WORKFLOWS / "budget.yml").read_text())
        rows = {row["step"]: row for row in budget["jobs"]["budget"]["strategy"]["matrix"]["include"]}
        self.assertIn("CONFIG_CRUX_CONTROLLER_S3=y", rows["S3"]["require"])
        self.assertIn("CONFIG_CRUX_FILE_FATFS_RT1060=y", rows["S3"]["require"])
        commands = "\n".join(
            step.get("run", "") for step in budget["jobs"]["budget"]["steps"]
        )
        self.assertIn("matrix.require", yaml.safe_dump(budget))
        self.assertIn(".config", commands)

    def test_limits_declare_s3_with_the_same_placeholder_margins(self):
        data = json.loads((ROOT / "budgets" / "limits.json").read_text())
        self.assertEqual(REGIONS, set(data["min_free_percent"]["S3"]))
        self.assertTrue(all(v == 25 for v in data["min_free_percent"]["S3"].values()))
        self.assertIn("placeholder", data["_comment"].lower())


class S3Scenario(unittest.TestCase):
    DIRECTORY = ROOT / "tests" / "native_sim" / "s3"
    CASES = ("not_ready", "mounted_not_bound", "mount_failure", "roundtrip", "bind_failure")

    def scenarios(self):
        return yaml.safe_load((self.DIRECTORY / "testcase.yaml").read_text())

    def test_one_scenario_per_case_on_the_64_bit_simulator(self):
        data = self.scenarios()
        self.assertEqual(
            {f"controller.s3.native_sim.{case}" for case in self.CASES}, set(data["tests"])
        )
        for name, test in data["tests"].items():
            case = name.rsplit(".", 1)[1]
            self.assertEqual(f"S3_CASE={case}", test["extra_args"], name)
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
        source = (self.DIRECTORY / "src" / "test_s3.c").read_text()
        for case in self.CASES:
            self.assertIn(f"S3_CASE_{case}", source, case)

    def test_the_overlay_has_a_ram_disk_and_the_fstab_entry(self):
        text = (self.DIRECTORY / "app.overlay").read_text()
        self.assertIn('compatible = "zephyr,ram-disk"', text)
        self.assertIn('compatible = "zephyr,fstab,fatfs"', text)
        self.assertIn("controller_storage:", text)
        self.assertIn('mount-point = "/RAM:"', text)


class S3Findings(unittest.TestCase):
    NOTE = ROOT / "docs" / "findings" / "s3-file-composition.md"

    def test_the_findings_note_exists_and_labels_every_statement(self):
        text = self.NOTE.read_text()
        self.assertIn("Measured", text)
        self.assertIn("Inferred", text)

    def test_the_readme_lists_s3(self):
        readme = (ROOT / "README.md").read_text()
        self.assertRegex(readme, r"\|\s*S3\s*\|")


if __name__ == "__main__":
    unittest.main()
