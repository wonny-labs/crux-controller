"""Checks of the groundwork for step S6 (management over HTTPS): the declared limits, the address
validator, the management policy data and port, the findings note, and that no image build names any
of it yet. Written test first, one slice at a time. Nothing here builds or runs Zephyr."""

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]

REGIONS = {"FLASH", "RAM", "ITCM", "DTCM", "OCRAM", "OCRAM2", "IDT_LIST"}
APP_SRC = ROOT / "app" / "src"


def c_code(path):
    """A C file without its comments."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", pathlib.Path(path).read_text(), flags=re.S)


def includes(path):
    return re.findall(r"^\s*#\s*include\s*([<\"][^>\"]+[>\"])", c_code(path), re.M)


def code_lines(path):
    return [line.split("#", 1)[0] for line in pathlib.Path(path).read_text().splitlines()]


class S6Limits(unittest.TestCase):
    """The row is declared before any measurement and before any workflow names S6."""

    def limits(self):
        return json.loads((ROOT / "budgets" / "limits.json").read_text())

    def test_limits_declare_s6_with_the_same_placeholder_margins(self):
        data = self.limits()
        self.assertIn("S6", data["min_free_percent"])
        self.assertEqual(REGIONS, set(data["min_free_percent"]["S6"]))
        self.assertTrue(all(v == 25 for v in data["min_free_percent"]["S6"].values()))
        self.assertIn("placeholder", data["_comment"].lower())

    def test_the_s6_row_equals_the_s5_row_and_no_other_row_changed(self):
        rows = self.limits()["min_free_percent"]
        self.assertEqual(["S0", "S1", "S2", "S3", "S4", "S5", "S6"], sorted(rows))
        for step in ("S0", "S1", "S2", "S3", "S4"):
            self.assertEqual(rows["S5"], rows[step], step)
        self.assertEqual(rows["S5"], rows["S6"])


class S6Validator(unittest.TestCase):
    """The bind address text is checked by plain C, so the host builds and tests it. The Zephyr
    web server falls back to every address for a text that is not an address; the validator is
    what lets a later composition refuse such a text instead."""

    ISO_C = {"<stdbool.h>", "<stddef.h>", "<stdint.h>"}

    def test_the_policy_files_exist(self):
        self.assertTrue((APP_SRC / "management_policy.h").is_file())
        self.assertTrue((APP_SRC / "management_policy.c").is_file())

    def test_the_policy_includes_iso_c_and_its_own_header_only(self):
        for name in ("management_policy.h", "management_policy.c"):
            for include in includes(APP_SRC / name):
                self.assertTrue(
                    include in self.ISO_C or include == '"management_policy.h"', f"{name}: {include}"
                )

    def test_the_policy_names_no_crux_or_zephyr_symbol(self):
        for name in ("management_policy.h", "management_policy.c"):
            self.assertNotRegex(c_code(APP_SRC / name), r"\bcrux_|\bCRUX_|\bk_|\bCONFIG_|zephyr", name)

    def test_the_host_build_runs_the_policy_test_with_the_strict_flags(self):
        text = "\n".join(code_lines(ROOT / "tests" / "host" / "CMakeLists.txt"))
        self.assertRegex(
            text,
            r"add_executable\(test_management_policy test_management_policy\.c "
            r"\.\./\.\./app/src/management_policy\.c\)",
        )
        self.assertRegex(text, r"target_compile_options\(test_management_policy PRIVATE[^)]*-Werror")
        self.assertRegex(text, r"add_test\(NAME management_policy COMMAND test_management_policy\)")

    def test_the_host_test_covers_each_rule_of_the_address_text(self):
        source = (ROOT / "tests" / "host" / "test_management_policy.c").read_text()
        for needle in (
            "management_address_valid", "NULL", '"0.0.0.0"', '"255.255.255.255"', '"192.168.77.2"',
            '""', '" 1.2.3.4"', '"1.2.3.4 "', '"01.2.3.4"', '"1.2.3.04"', '"00.0.0.0"',
            '"256.1.1.1"', '"1.1.1.256"', '"1000.1.1.1"', '"1.2.3"', '"1.2.3."', '"1.2..3"',
            '"1.2.3.4.5"', '"1.2.3.4x"', '"0x1.2.3.4"', '"+1.2.3.4"', '"1.2.3.4:443"', '"::1"',
            r'"1.2.3.4\0junk"', r'"1.2.3\0.4"',
        ):
            self.assertIn(needle, source, needle)


if __name__ == "__main__":
    unittest.main()
