# SPDX-License-Identifier: Apache-2.0
"""Checks that the base build job keeps the gate required and publishes no build output.

The base job of ci.yml runs the checks of the job base of scripts/ci/checks.toml (ci_map)."""

import pathlib
import unittest

import yaml

import ci_map

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
BOARD = "mimxrt1060_evk@B//qspi"


def load_ci():
    return yaml.safe_load((WORKFLOWS / "ci.yml").read_text())


def base_commands():
    jobs = load_ci()["jobs"]
    assert "base" in jobs, "ci.yml has no base job"
    return ci_map.commands("base")


class BaseBuildJob(unittest.TestCase):
    @ci_map.needs_tomllib
    def test_build_requires_the_verified_zephyr_gate(self):
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", base_commands())

    @ci_map.needs_tomllib
    def test_build_targets_the_rt1060_evkb_qspi_board(self):
        self.assertEqual(BOARD, ci_map.job_env("base")["BOARD"])
        self.assertIn('-b "$BOARD"', base_commands())

    @ci_map.needs_tomllib
    def test_job_checks_the_binary_and_its_metadata(self):
        commands = base_commands()
        self.assertIn("zephyr.bin", commands)
        self.assertIn("zephyr.meta", commands)

    @ci_map.needs_tomllib
    def test_every_firmware_build_requires_the_gate(self):
        runs = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            data = yaml.safe_load(path.read_text())
            for name, job in data["jobs"].items():
                for step in job["steps"]:
                    runs.append((f"{path.name} job {name}", step.get("run", "")))
        runs += [(f"checks.toml check {c['id']}", c["run"]) for c in ci_map.checks()]
        runs.append(("scripts/ci/budget.sh", ci_map.BUDGET.read_text()))
        for where, run in runs:
            if "west build" in run and "-t rom_report" not in run and "-t ram_report" not in run:
                self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", run, where)
        # The Budget script also builds with rom_report and ram_report; its board build has the gate.
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", ci_map.BUDGET.read_text())

    def test_no_workflow_uploads_build_output(self):
        for path in sorted(WORKFLOWS.glob("*.yml")):
            data = yaml.safe_load(path.read_text())
            for name, job in data["jobs"].items():
                for step in job["steps"]:
                    uses = step.get("uses", "")
                    self.assertNotIn(
                        "upload-artifact", uses, f"{path.name} job {name} uploads output"
                    )


class BaseApplication(unittest.TestCase):
    def test_the_crux_module_switch_is_never_turned_off(self):
        # The baseline gate lives in the Crux module. Turning it off would turn the gate off.
        text = (ROOT / "app" / "prj.conf").read_text()
        self.assertNotIn("CONFIG_CRUX_MODULE=n", text)
        self.assertNotIn("# CONFIG_CRUX_MODULE is not set", text)

    def test_application_is_named_for_this_repository(self):
        cmake = (ROOT / "app" / "CMakeLists.txt").read_text()
        self.assertIn("project(crux_controller)", cmake)
        self.assertNotIn("product_x", cmake)

    def test_application_links_only_public_crux_targets_and_the_workload(self):
        cmake = (ROOT / "app" / "CMakeLists.txt").read_text()
        links = [line for line in cmake.splitlines() if "target_link_libraries" in line]
        self.assertTrue(links)
        for line in links:
            # The workload is this repository's own portable library, and controller::framework is
            # the interface header of the framework module of this repository.
            self.assertTrue("crux::" in line or "workload" in line or "controller::framework" in line, line)


if __name__ == "__main__":
    unittest.main()
