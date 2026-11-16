"""Checks of the groundwork for step S6 (management over HTTPS): the declared limits, the address
validator, the management policy data and port, the findings note, and that no image build names any
of it yet. Written test first, one slice at a time. Nothing here builds or runs Zephyr."""

import json
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT / "scripts"))

import check_boundary  # noqa: E402

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
            "management_address_valid", "management_policy_valid", "management_version_valid",
            "management_port.h", "NULL", '"0.0.0.0"', '"255.255.255.255"', '"192.168.77.2"',
            '""', '" 1.2.3.4"', '"1.2.3.4 "', '"01.2.3.4"', '"1.2.3.04"', '"00.0.0.0"',
            '"256.1.1.1"', '"1.1.1.256"', '"1000.1.1.1"', '"1.2.3"', '"1.2.3."', '"1.2..3"',
            '"1.2.3.4.5"', '"1.2.3.4x"', '"0x1.2.3.4"', '"+1.2.3.4"', '"1.2.3.4:443"', '"::1"',
            r'"1.2.3.4\0junk"', r'"1.2.3\0.4"',
        ):
            self.assertIn(needle, source, needle)


class S6Policy(unittest.TestCase):
    """The role policy is data in plain C. Its names are the ones Crux Access and the Crux
    services define (crux/access.h, crux/management_status.h and crux/config_service.h at the
    pinned revision), copied as text because the policy builds on the host with no Crux header."""

    POLICY_C = APP_SRC / "management_policy.c"
    POLICY_H = APP_SRC / "management_policy.h"

    def test_the_header_defines_the_role_and_permission_names_as_text(self):
        header = c_code(self.POLICY_H)
        self.assertRegex(header, r'#define MANAGEMENT_ROLE_ADMINISTRATOR "administrator"')
        self.assertRegex(header, r'#define MANAGEMENT_ROLE_READ_ONLY "read-only"')
        for name, text in (
            ("MANAGEMENT_PERMISSION_ACCESS_MANAGE", "access.manage"),
            ("MANAGEMENT_PERMISSION_STATUS_READ", "status.read"),
            ("MANAGEMENT_PERMISSION_CONFIG_SAVE", "config.save"),
        ):
            self.assertRegex(header, rf'#define {name} "{re.escape(text)}"', name)

    def test_the_session_limits_are_fifteen_minutes_idle_and_eight_hours_absolute(self):
        header = c_code(self.POLICY_H)
        self.assertRegex(header, r"#define MANAGEMENT_SESSION_IDLE_LIMIT_S\s+\(?15u \* 60u\)?")
        self.assertRegex(header, r"#define MANAGEMENT_SESSION_ABSOLUTE_LIMIT_S\s+\(?8u \* 3600u\)?")

    def test_the_policy_leaves_the_password_rule_to_the_crux_reference(self):
        text = c_code(self.POLICY_H) + c_code(self.POLICY_C)
        self.assertNotRegex(text, r"password", "the policy states no password rule")
        self.assertIn("password", self.POLICY_H.read_text().lower(), "the header says why")

    def test_the_policy_names_no_permission_that_no_s6_route_needs(self):
        text = c_code(self.POLICY_H) + c_code(self.POLICY_C)
        for permission in ("network.", "system.reboot", "events.read", "tls.manage", "config.read",
                           "config.write", "file."):
            self.assertNotIn(permission, text, permission)


class S6Port(unittest.TestCase):
    """The port is the product's own header: ISO C and the policy header of this repository, no
    Crux, Zephyr or composition header, so it can sit in app/src."""

    PORT = APP_SRC / "management_port.h"

    def test_the_port_header_exists_and_declares_the_start_function(self):
        code = c_code(self.PORT)
        self.assertRegex(code, r"\bmanagement_port_status_t\b")
        self.assertRegex(code, r"\bmanagement_port_config_t\b")
        self.assertRegex(code, r"management_port_status_t\s+management_port_start\(")

    def test_the_port_includes_iso_c_and_the_policy_header_only(self):
        # The port could include <crux/access.h>, which the boundary allows in app/src. It does not:
        # the policy type of this repository is enough, and the composition that implements the
        # port would copy it into the Crux type. So the port needs no Crux header at all.
        allowed = {"<stdbool.h>", "<stddef.h>", "<stdint.h>", '"management_policy.h"'}
        found = includes(self.PORT)
        self.assertIn('"management_policy.h"', found)
        for include in found:
            self.assertIn(include, allowed, include)
        self.assertNotIn("crux/", "\n".join(found))

    def test_the_port_includes_no_zephyr_composition_or_frozen_header(self):
        text = self.PORT.read_text()
        for needle in ("zephyr/", "crux/web_zephyr.h", "crux/file_zephyr.h", "crux/thread.h",
                       "crux/sync.h", "crux/queue.h", "crux/serial.h", "compose/", "CONFIG_"):
            self.assertNotIn(needle, c_code(self.PORT), needle)
        self.assertNotRegex("\n".join(includes(self.PORT)), r"compose|zephyr")
        self.assertIn("management_port_start", text)

    def test_the_boundary_check_accepts_the_port_header_against_a_crux_that_publishes_time(self):
        with tempfile.TemporaryDirectory() as directory:
            crux = pathlib.Path(directory)
            for name in ("time.h", "time_authority.h", "logging.h", "status.h", "system.h", "file.h"):
                header = crux / "components" / "x" / "include" / "crux" / name
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text("")
            composition = crux / "components" / "file" / "ports" / "zephyr" / "include" / "crux"
            composition.mkdir(parents=True)
            (composition / "file_zephyr.h").write_text("")
            self.assertEqual([], check_boundary.check(ROOT, crux))
            self.assertEqual([], check_boundary.check(ROOT))

    def test_a_zephyr_include_in_the_port_would_be_found_by_the_boundary_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "app" / "src" / "management_port.h"
            path.parent.mkdir(parents=True)
            path.write_text("#include <zephyr/kernel.h>\n")
            found = check_boundary.check(directory)
            self.assertEqual(["zephyr/kernel.h"], [v.include for v in found])


class S6NotBuilt(unittest.TestCase):
    """This groundwork changes no firmware image: no build file, option or configuration under
    app/ names the new files or step S6. The host tests are the only users."""

    BUILD_FILES = ("CMakeLists.txt", "*.cmake", "Kconfig*", "*.conf", "*.overlay", "*.dts")

    def build_text(self):
        parts = []
        for pattern in self.BUILD_FILES:
            for path in sorted((ROOT / "app").rglob(pattern)):
                parts.append(f"{path.relative_to(ROOT)}\n{path.read_text()}")
        self.assertTrue(parts)
        return "\n".join(parts)

    def test_no_build_file_under_app_names_the_management_sources(self):
        text = self.build_text()
        for needle in ("management_policy", "management_port", "management_start"):
            self.assertNotIn(needle, text, needle)

    def test_no_build_file_or_option_under_app_names_step_s6(self):
        text = self.build_text()
        self.assertNotRegex(text, r"CRUX_CONTROLLER_S6|conf/s6|boards/s6|\bS6\b")

    def test_no_source_under_app_includes_the_management_headers(self):
        for path in sorted(p for p in (ROOT / "app").rglob("*") if p.suffix in (".c", ".h")):
            if path.name.startswith("management_"):
                continue
            for include in includes(path):
                self.assertNotIn("management_", include, f"{path.relative_to(ROOT)}: {include}")

    def test_no_crux_symbol_for_the_web_or_access_is_set_under_app(self):
        text = self.build_text()
        for symbol in ("CONFIG_CRUX_ACCESS", "CONFIG_CRUX_WEB", "CONFIG_CRUX_TLS_CERTIFICATE",
                       "CONFIG_CRUX_PSA_THREADING", "CONFIG_CRUX_CONFIG_SERVICE"):
            self.assertNotIn(symbol, text, symbol)


if __name__ == "__main__":
    unittest.main()
