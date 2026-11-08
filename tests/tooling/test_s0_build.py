"""Checks that the S0 build job keeps the gate required and publishes no build output."""

import pathlib
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
BOARD = "mimxrt1060_evk@B//qspi"


def load_ci():
    return yaml.safe_load((WORKFLOWS / "ci.yml").read_text())


def s0_commands():
    jobs = load_ci()["jobs"]
    assert "s0" in jobs, "ci.yml has no s0 job"
    return "\n".join(step.get("run", "") for step in jobs["s0"]["steps"])


class S0BuildJob(unittest.TestCase):
    def test_build_requires_the_verified_zephyr_gate(self):
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", s0_commands())

    def test_build_targets_the_rt1060_evkb_qspi_board(self):
        job = load_ci()["jobs"]["s0"]
        self.assertEqual(BOARD, job["env"]["BOARD"])
        self.assertIn("-b '${{ env.BOARD }}'", s0_commands())

    def test_job_checks_the_binary_and_its_metadata(self):
        commands = s0_commands()
        self.assertIn("zephyr.bin", commands)
        self.assertIn("zephyr.meta", commands)

    def test_every_firmware_build_requires_the_gate(self):
        for path in sorted(WORKFLOWS.glob("*.yml")):
            data = yaml.safe_load(path.read_text())
            for name, job in data["jobs"].items():
                for step in job["steps"]:
                    run = step.get("run", "")
                    if "west build" in run and "-t rom_report" not in run and "-t ram_report" not in run:
                        self.assertIn(
                            "-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", run, f"{path.name} job {name}"
                        )

    def test_no_workflow_uploads_build_output(self):
        for path in sorted(WORKFLOWS.glob("*.yml")):
            data = yaml.safe_load(path.read_text())
            for name, job in data["jobs"].items():
                for step in job["steps"]:
                    uses = step.get("uses", "")
                    self.assertNotIn(
                        "upload-artifact", uses, f"{path.name} job {name} uploads output"
                    )


class S0Application(unittest.TestCase):
    def test_the_crux_module_switch_is_never_turned_off(self):
        # The baseline gate lives in the Crux module. Turning it off would turn the gate off.
        text = (ROOT / "app" / "prj.conf").read_text()
        self.assertNotIn("CONFIG_CRUX_PILOT_MODULE=n", text)
        self.assertNotIn("# CONFIG_CRUX_PILOT_MODULE is not set", text)

    def test_application_is_named_for_this_repository(self):
        cmake = (ROOT / "app" / "CMakeLists.txt").read_text()
        self.assertIn("project(crux_controller)", cmake)
        self.assertNotIn("product_x", cmake)

    def test_application_links_only_public_crux_targets_and_the_workload(self):
        cmake = (ROOT / "app" / "CMakeLists.txt").read_text()
        links = [line for line in cmake.splitlines() if "target_link_libraries" in line]
        self.assertTrue(links)
        for line in links:
            # The workload is this repository's own portable library.
            self.assertTrue("crux::" in line or "workload" in line, line)


if __name__ == "__main__":
    unittest.main()
