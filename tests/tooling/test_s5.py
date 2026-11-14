"""Checks of step S5 (time synchronisation over SNTP): its limits, policy, configuration, build
files, sources, adapter, CI jobs, scenario and findings. Written test first, one slice at a time."""

import json
import pathlib
import re
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "budgets"))
sys.path.insert(0, str(ROOT / "scripts"))

import check  # noqa: E402
import check_boundary  # noqa: E402

WORKFLOWS = ROOT / ".github" / "workflows"
BOARD = "mimxrt1060_evk@B//qspi"

REGIONS = {"FLASH", "RAM", "ITCM", "DTCM", "OCRAM", "OCRAM2", "IDT_LIST"}
APP_SRC = ROOT / "app" / "src"
APP_OS = ROOT / "app" / "os"


def c_code(path):
    """A C file without its comments."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", pathlib.Path(path).read_text(), flags=re.S)


def includes(path):
    return re.findall(r"^\s*#\s*include\s*([<\"][^>\"]+[>\"])", c_code(path), re.M)


def code_lines(path):
    return [line.split("#", 1)[0] for line in pathlib.Path(path).read_text().splitlines()]


def conf_options(path):
    options = {}
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            options[name.strip()] = value.strip()
    return options


def kconfig_block(name):
    text = "\n".join(code_lines(ROOT / "app" / "Kconfig"))
    block = re.search(rf"^config {name}\n(.*?)(?=^config |^source |\Z)", text, re.S | re.M)
    assert block is not None, f"no config {name} in app/Kconfig"
    return block.group(1)


class S5Limits(unittest.TestCase):
    """The row is declared before the first measurement, with the margins of S0 to S4."""

    def limits(self):
        return json.loads((ROOT / "budgets" / "limits.json").read_text())

    def test_limits_declare_s5_with_the_same_placeholder_margins(self):
        data = self.limits()
        self.assertEqual(REGIONS, set(data["min_free_percent"]["S5"]))
        self.assertTrue(all(v == 25 for v in data["min_free_percent"]["S5"].values()))
        self.assertIn("placeholder", data["_comment"].lower())

    def test_the_s5_row_equals_the_s4_row_and_no_other_row_changed(self):
        rows = self.limits()["min_free_percent"]
        self.assertEqual(["S0", "S1", "S2", "S3", "S4", "S5"], sorted(rows))
        for step in ("S0", "S1", "S2", "S3", "S4"):
            self.assertEqual(rows["S4"], rows[step], step)
        self.assertEqual(rows["S4"], rows["S5"])

    def test_the_checker_accepts_a_measurement_of_s5_inside_the_margin(self):
        regions = {name: {"used": 0, "size": 1000} for name in REGIONS}
        regions["FLASH"] = {"used": 750, "size": 1000}
        self.assertEqual([], check.check({"step": "S5", "regions": regions}, self.limits()))

    def test_the_checker_fails_a_measurement_of_s5_beyond_the_margin(self):
        regions = {name: {"used": 0, "size": 1000} for name in REGIONS}
        regions["FLASH"] = {"used": 751, "size": 1000}
        messages = check.check({"step": "S5", "regions": regions}, self.limits())
        self.assertEqual(1, len(messages))
        self.assertIn("S5 FLASH", messages[0])


class S5Policy(unittest.TestCase):
    """The policy is plain C: it includes ISO C only, so the host builds it with no Crux or
    Zephyr header, and the host test is registered next to the others."""

    ISO_C = {"<stdbool.h>", "<stddef.h>", "<stdint.h>"}

    def test_the_policy_files_exist(self):
        self.assertTrue((APP_SRC / "time_sync_policy.h").is_file())
        self.assertTrue((APP_SRC / "time_sync_policy.c").is_file())

    def test_the_policy_includes_iso_c_and_its_own_header_only(self):
        for name in ("time_sync_policy.h", "time_sync_policy.c"):
            for include in includes(APP_SRC / name):
                self.assertTrue(
                    include in self.ISO_C or include == '"time_sync_policy.h"', f"{name}: {include}"
                )

    def test_the_policy_names_no_crux_or_zephyr_symbol(self):
        for name in ("time_sync_policy.h", "time_sync_policy.c"):
            code = c_code(APP_SRC / name)
            self.assertNotRegex(code, r"\bcrux_|\bCRUX_|\bk_|\bCONFIG_|zephyr|\bsntp_", name)

    def test_the_policy_calls_no_clock_or_network_function(self):
        code = c_code(APP_SRC / "time_sync_policy.c")
        self.assertNotRegex(code, r"\b(time|clock_gettime|clock_settime|sys_clock_\w+|gettimeofday)\(")

    def test_the_host_build_runs_the_policy_test_with_the_strict_flags(self):
        text = "\n".join(code_lines(ROOT / "tests" / "host" / "CMakeLists.txt"))
        self.assertRegex(
            text,
            r"add_executable\(test_time_sync_policy test_time_sync_policy\.c "
            r"\.\./\.\./app/src/time_sync_policy\.c\)",
        )
        self.assertRegex(text, r"target_compile_options\(test_time_sync_policy PRIVATE[^)]*-Werror")
        self.assertRegex(text, r"add_test\(NAME time_sync_policy COMMAND test_time_sync_policy\)")

    def test_the_host_test_covers_each_rule_and_boundary_of_the_policy(self):
        source = (ROOT / "tests" / "host" / "test_time_sync_policy.c").read_text()
        for needle in (
            "time_sync_decide", "time_sync_instant_from_sntp", "TIME_SYNC_APPLY_SET",
            "TIME_SYNC_REFUSE_RANGE", "TIME_SYNC_REFUSE_STEP", "TIME_SYNC_MARK_STALE",
            "946684799", "946684800", "4102444799", "4102444800", "1800u", "1801u",
            "0x80000000u", "0xFFFFFFFFu", "999999999u", "100 * MS", "1000 * MS",
        ):
            self.assertIn(needle, source, needle)


if __name__ == "__main__":
    unittest.main()
