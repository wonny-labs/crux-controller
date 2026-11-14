"""Checks of step S4 (Crux System): its limits, policy, configuration, build files, sources, CI
jobs, scenario and findings. Written test first, one slice at a time."""

import json
import pathlib
import re
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "budgets"))

import check  # noqa: E402

REGIONS = {"FLASH", "RAM", "ITCM", "DTCM", "OCRAM", "OCRAM2", "IDT_LIST"}


class S4Limits(unittest.TestCase):
    """The row is declared before the first measurement, with the margins of S0 to S3."""

    def limits(self):
        return json.loads((ROOT / "budgets" / "limits.json").read_text())

    def test_limits_declare_s4_with_the_same_placeholder_margins(self):
        data = self.limits()
        self.assertEqual(REGIONS, set(data["min_free_percent"]["S4"]))
        self.assertTrue(all(v == 25 for v in data["min_free_percent"]["S4"].values()))
        self.assertIn("placeholder", data["_comment"].lower())

    def test_the_s4_row_equals_the_s3_row_and_no_other_row_changed(self):
        rows = self.limits()["min_free_percent"]
        self.assertEqual(["S0", "S1", "S2", "S3", "S4"], sorted(rows))
        for step in ("S0", "S1", "S2", "S3"):
            self.assertEqual(rows["S3"], rows[step], step)
        self.assertEqual(rows["S3"], rows["S4"])

    def test_the_checker_accepts_a_measurement_of_s4_inside_the_margin(self):
        regions = {name: {"used": 0, "size": 1000} for name in REGIONS}
        regions["FLASH"] = {"used": 750, "size": 1000}
        self.assertEqual([], check.check({"step": "S4", "regions": regions}, self.limits()))

    def test_the_checker_fails_a_measurement_of_s4_beyond_the_margin(self):
        regions = {name: {"used": 0, "size": 1000} for name in REGIONS}
        regions["FLASH"] = {"used": 751, "size": 1000}
        messages = check.check({"step": "S4", "regions": regions}, self.limits())
        self.assertEqual(1, len(messages))
        self.assertIn("S4 FLASH", messages[0])


if __name__ == "__main__":
    unittest.main()
