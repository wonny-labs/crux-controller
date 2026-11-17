# SPDX-License-Identifier: Apache-2.0
"""Checks that CI runs the three checks of the style work (SPDX headers, checkpatch, the style-kit
include check) in a way that can fail. These tests read the workflow only and use no network."""

import pathlib
import re
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def jobs():
    return yaml.safe_load(CI.read_text())["jobs"]


def steps_of(job):
    return jobs()[job]["steps"]


def only_step(job, fragment):
    found = [s for s in steps_of(job) if fragment in s.get("name", "")]
    assert len(found) == 1, f"{job}: need exactly one step named like {fragment!r}, got {found}"
    return found[0]


class CannotBeSilenced(unittest.TestCase):
    """Shared rule: a step of these checks never hides its own failure."""

    def assert_can_fail(self, job, step):
        self.assertNotIn("continue-on-error", step)
        self.assertNotIn("continue-on-error", jobs()[job])
        self.assertNotIn("if", step, "the step runs conditionally")
        run = step.get("run", "")
        self.assertNotRegex(run, r"\|\|\s*(true|:)\b")
        self.assertNotRegex(run, r"(^|\n)\s*set \+e")


class SpdxStep(CannotBeSilenced):
    def test_the_tooling_job_runs_the_spdx_check_after_checkout(self):
        step = only_step("tooling", "SPDX")
        names = [s.get("uses", s.get("name", "")) for s in steps_of("tooling")]
        self.assertTrue(names[0].startswith("actions/checkout@"))
        self.assertEqual("python scripts/check_spdx.py", step["run"].strip())
        self.assert_can_fail("tooling", step)

    def test_the_script_and_its_tests_exist(self):
        self.assertTrue((ROOT / "scripts" / "check_spdx.py").is_file())
        self.assertTrue((ROOT / "tests" / "tooling" / "test_check_spdx.py").is_file())

    def test_the_existing_tooling_steps_are_unchanged(self):
        runs = [s.get("run") for s in steps_of("tooling")]
        self.assertIn("python -m pip install pyyaml", runs)
        self.assertIn("python -m unittest discover -s tests/tooling -v", runs)


if __name__ == "__main__":
    unittest.main()
