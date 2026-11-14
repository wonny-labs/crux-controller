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
APP_SRC = ROOT / "app" / "src"


def c_code(path):
    """A C file without its comments."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", pathlib.Path(path).read_text(), flags=re.S)


def includes(path):
    return re.findall(r"^\s*#\s*include\s*([<\"][^>\"]+[>\"])", c_code(path), re.M)


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


class S4Policy(unittest.TestCase):
    """The policy is plain C: it includes ISO C only, so the host builds it with no Crux or
    Zephyr header, and the host test is registered next to the others."""

    ISO_C = {"<stdbool.h>", "<stddef.h>", "<stdint.h>", "<string.h>"}

    def test_the_policy_files_exist(self):
        self.assertTrue((APP_SRC / "health_policy.h").is_file())
        self.assertTrue((APP_SRC / "health_policy.c").is_file())

    def test_the_policy_includes_iso_c_and_its_own_header_only(self):
        for name in ("health_policy.h", "health_policy.c"):
            for include in includes(APP_SRC / name):
                self.assertTrue(
                    include in self.ISO_C or include == '"health_policy.h"', f"{name}: {include}"
                )

    def test_the_policy_names_no_crux_or_zephyr_symbol(self):
        for name in ("health_policy.h", "health_policy.c"):
            code = c_code(APP_SRC / name)
            self.assertNotRegex(code, r"\bcrux_|\bCRUX_|\bk_|\bCONFIG_|zephyr", name)

    def test_the_host_build_runs_the_policy_test_with_the_strict_flags(self):
        text = "\n".join(
            line.split("#", 1)[0]
            for line in (ROOT / "tests" / "host" / "CMakeLists.txt").read_text().splitlines()
        )
        self.assertRegex(
            text, r"add_executable\(test_health_policy test_health_policy\.c \.\./\.\./app/src/health_policy\.c\)"
        )
        self.assertRegex(text, r"target_compile_options\(test_health_policy PRIVATE[^)]*-Werror")
        self.assertRegex(text, r"add_test\(NAME health_policy COMMAND test_health_policy\)")
        self.assertNotIn("health.c", text.replace("health_policy.c", ""))

    def test_the_host_test_covers_each_rule_of_the_policy(self):
        source = (ROOT / "tests" / "host" / "test_health_policy.c").read_text()
        for needle in (
            "health_cause_classify", "health_boot_decide", "health_cause_text",
            "health_watchdog_timeout", "health_feed_result", "HEALTH_FEED_REPORT_AND_STOP",
            "HEALTH_FEED_IGNORED", "21334", "6400",
        ):
            self.assertIn(needle, source, needle)


if __name__ == "__main__":
    unittest.main()
