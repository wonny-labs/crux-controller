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
    """The bind address text is checked by plain C, so the host builds and tests it. Crux's guide
    (docs/management-in-a-product.md at the pinned revision) says Zephyr's HTTP server falls back to
    every address for a text that is not an address, so a composition that sets one checks the text;
    the validator is that check."""

    ISO_C = {"<stdbool.h>", "<stddef.h>", "<stdint.h>"}

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

    def host_test_literals(self):
        """The text of every C string literal of the host test, as written between the quotes."""
        source = (ROOT / "tests" / "host" / "test_management_policy.c").read_text()
        return set(re.findall(r'"((?:[^"\\\n]|\\.)*)"', source))

    def test_the_host_test_covers_each_rule_of_the_address_text(self):
        literals = self.host_test_literals()
        cases = (
            "0.0.0.0", "255.255.255.255", "192.168.77.2",  # valid, with both ends
            "", " 1.2.3.4", "1.2.3.4 ", "1.2.3.4\\n",  # empty and whitespace
            "01.2.3.4", "1.2.3.04", "00.0.0.0",  # leading zeros
            "256.1.1.1", "1.1.1.256", "1000.1.1.1",  # above 255
            "1.2.3", "1.2.3.", "1.2..3", "1.2.3.4.5",  # parts
            "1.2.3.4x", "0x1.2.3.4", "+1.2.3.4", "1.2.3.4:443", "::1",  # other characters
            "1.2.3.4\\0junk", "1.2.3\\0.4",  # NUL
        )
        for case in cases:
            self.assertIn(case, literals, case)

    def test_the_host_test_covers_a_part_that_would_wrap_around_in_each_position(self):
        # Only the cap of three digits stops a long part from wrapping around to a small value:
        # 4294967296 is 0 and 4294967295 is 255 in 32 bits, and 4294967551 is 255 after 2^32 + 255.
        literals = self.host_test_literals()
        for part in ("4294967296", "4294967295", "4294967551", "1000000000000"):
            for text in (f"{part}.1.1.1", f"1.{part}.1.1", f"1.1.{part}.1", f"1.1.1.{part}"):
                self.assertIn(text, literals, text)

    def test_the_host_test_covers_the_public_functions_and_the_port_header(self):
        source = (ROOT / "tests" / "host" / "test_management_policy.c").read_text()
        for needle in ("management_address_valid", "management_policy_valid",
                       "management_version_valid", "management_port.h"):
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

    def header(self):
        return " ".join(self.POLICY_H.read_text().replace("*", " ").split())

    def test_the_header_does_not_claim_a_layout_that_nothing_checks(self):
        text = self.header()
        self.assertNotIn("The layout of crux_access_role_t", text)
        self.assertNotIn("The layout of crux_access_policy_t", text)
        for needle in ("same members as", "member by member", "sizeof", "offsetof",
                       "nothing in this repository checks"):
            self.assertIn(needle, text, needle)

    def test_the_header_says_where_each_permission_string_was_confirmed(self):
        text = self.header()
        for needle in ("access.manage", "crux/access.h", "config.save",
                       "docs/management-in-a-product.md", "status.read",
                       "to be confirmed against the header"):
            self.assertIn(needle, text, needle)

    def test_the_header_labels_what_it_has_not_verified_in_a_source(self):
        text = self.header()
        self.assertIn("docs/management-in-a-product.md", text)
        self.assertIn("components/web/ports/zephyr/web_http_server.c", text)
        self.assertIn("not verified", text)

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

    def start_order_comment(self):
        comments = re.findall(r"/\*(.*?)\*/", self.PORT.read_text(), re.S)
        return max(comments, key=len)

    def test_the_start_order_follows_the_crux_sources_it_cites(self):
        comment = self.start_order_comment()
        steps = {int(n): " ".join(text.replace("*", " ").split())
                 for n, text in re.findall(r"^\s*\*\s+(\d+)\.\s(.*(?:\n\s*\*\s{5,}.*)*)", comment, re.M)}
        self.assertEqual(list(range(1, 8)), sorted(steps), steps)
        # Each phrase, with the number of the step it must be in, in the order of the sources:
        # the guide's boot order, the module test's start calls and the header of web_zephyr.h.
        expected = (
            ("security event init", 1), ("realtime init", 1), ("bind", 1),
            ("credential store start", 2), ("Access init", 2),
            ("config service start", 3), ("management status start", 3),
            ("security event start", 3),
            ("TLS certificate start", 4),
            ("register", 5),
            ("web session init", 6), ("web management init", 6),
            ("web start", 7),
        )
        steps_text = comment[re.search(r"^\s*\*\s+1\.\s", comment, re.M).start():]
        last_step, last_position = 0, -1
        for phrase, number in expected:
            self.assertIn(phrase, steps[number], f"{phrase!r} is not in step {number}")
            position = steps_text.index(phrase)
            self.assertGreater(position, last_position, f"{phrase!r} is out of order")
            self.assertGreaterEqual(number, last_step, phrase)
            last_step, last_position = number, position

    def test_the_start_order_cites_its_sources_by_file_name_only(self):
        comment = self.start_order_comment()
        self.assertIn("docs/management-in-a-product.md", comment)
        self.assertIn("web_zephyr.h", comment)
        self.assertNotRegex(comment, r"(?i)\bline[s]? [0-9]+|:[0-9]+\b|/Users/|/home/")

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


class S6Findings(unittest.TestCase):
    NOTE = ROOT / "docs" / "findings" / "s6-https-management-gaps.md"
    PIN = "8e3737d25d048b14a00c01da00494f58a62958c6"
    PREVIOUS_PIN = "dfd3ad7d4380b06a47d8c8b5b9f0ce46fbba0576"

    def text(self):
        return self.NOTE.read_text()

    def words(self):
        return " ".join(self.text().split())

    def test_the_note_exists_and_uses_the_three_labels(self):
        for label in ("**Verified**", "**Inferred**", "**Not verified**"):
            self.assertIn(label, self.text())

    def test_the_note_defines_its_labels_and_names_both_revisions(self):
        text = self.words()
        self.assertIn(self.PIN, text)
        self.assertIn(self.PREVIOUS_PIN, text)
        self.assertIn("read in a named file at a named revision", text)

    def test_the_note_claims_nothing_was_built_or_run(self):
        text = self.words()
        self.assertIn("No Zephyr build, Twister run, CI run or board run stands behind any statement", text)
        self.assertIn("not compiled into any firmware image", text)

    def test_every_verified_row_of_a_table_names_a_file_and_a_revision(self):
        rows = [line for line in self.text().splitlines()
                if line.startswith("|") and "**Verified**" in line]
        self.assertGreaterEqual(len(rows), 10)
        for row in rows:
            source = [cell for cell in row.split("|") if cell.strip()][-1]
            self.assertRegex(source, r"`[A-Za-z0-9_./-]*[/.][A-Za-z0-9_./-]*`", row)
            self.assertRegex(source, r"8e3737d2|dfd3ad7d|8b9c702", row)

    def test_the_note_covers_the_locks_gap_with_the_symbol_and_its_state(self):
        text = self.words()
        for needle in ("CONFIG_CRUX_PSA_THREADING", "Experimental", "off by default",
                       "zephyr/Kconfig", "open at the previous pin", "addressed at 8e3737d2"):
            self.assertIn(needle, text, needle)

    def test_the_note_covers_the_first_account_gap(self):
        text = self.words()
        for needle in ("<crux/cli_zephyr.h>", "crux_cli_serial_start", "crux_access_provision_first_account",
                       "COMPOSITION_CRUX_HEADERS", "reviewed change", "scripts/check_boundary.py",
                       "tests/tooling/test_boundary.py", "docs/composition-zone.md"):
            self.assertIn(needle, text, needle)

    def test_the_note_covers_the_route_sources_gap_without_a_workaround(self):
        text = self.words()
        for needle in ("crux_web_routes()", "unproven", "first native_sim build of the composition",
                       "no private include", "platform gap", "the owner decides"):
            self.assertIn(needle, text, needle)

    def test_the_note_covers_libc_the_group_and_the_wording_of_thread_and_sync(self):
        text = self.words()
        for needle in ("picolibc", "minimal libc", "CONFIG_EXTERNAL_LIBC",
                       "crux-secure-management", "runner of the S6 and budget jobs only",
                       "never in `west.yml`", "check_mbed_only.py",
                       "the Crux services select them for themselves", "product code includes none",
                       "app/Kconfig", "docs/architecture.md", "S1 to S5 only"):
            self.assertIn(needle, text, needle)

    def test_the_note_states_the_timeout_limit_of_one_silent_client(self):
        text = self.words()
        for needle in ("2,000 ms", "one silent client", "every other client", "docs/https-composition.md"):
            self.assertIn(needle, text, needle)

    def test_the_libc_default_is_not_presented_as_read_in_an_exported_file(self):
        row = next(line for line in self.text().splitlines()
                   if "selects the external libc by default" in line)
        self.assertRegex(row, r"\*\*(Inferred|Not verified)\*\*")
        self.assertIn("web_http_server.c", row)

    def test_the_command_table_row_says_the_cli_header_was_not_read(self):
        row = next(line for line in self.text().splitlines() if "components/cli/include/crux/cli.h" in line)
        self.assertIn("**Inferred**", row)
        self.assertIn("not read at the pin", row)

    def test_the_note_says_the_not_built_checks_are_meant_to_be_inverted(self):
        text = self.words()
        self.assertIn("S6NotBuilt", text)
        self.assertIn("approved behaviour change", text)

    def test_the_note_lists_what_is_not_verified(self):
        text = self.words()
        for needle in ("login", "sessions", "roles at run time", "first account", "browser", "any board",
                       "timing", "stack", "heap", "entropy"):
            self.assertIn(needle, text, needle)

    def test_the_note_uses_no_shorthand_or_private_wording(self):
        text = self.text()
        self.assertNotRegex(text, r"\b[OB][1-9]\b")
        self.assertNotRegex(text, r"(?i)\b(claude|assistant|chatgpt|llm|agent)\b")
        self.assertNotRegex(text, r"(?i)work package|skeleton plan|\b(?:OD|WD)[0-9]+\b")
        self.assertNotRegex(text, r"/Users/|/home/|/private/|/tmp/|[A-Z]:\\")

    def test_every_issue_reference_in_the_note_is_qualified(self):
        for number, line in enumerate(self.text().splitlines(), 1):
            for match in re.finditer(r"#[0-9]+", line):
                before = line[: match.start()]
                self.assertRegex(
                    before, r"wonny-labs/crux-(?:pilot|controller)$", f"{number}: {line.strip()}"
                )

    def test_the_note_and_the_readme_do_not_present_s6_as_a_step(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIsNone(re.search(r"^\|\s*S6\s*\|", readme, re.M))
        self.assertIn("not a step", self.words())

    def test_the_changelog_records_the_groundwork_and_that_no_image_changes(self):
        text = " ".join((ROOT / "CHANGELOG.md").read_text().split())
        self.assertIn("S6", text)
        self.assertIn("s6-https-management-gaps.md", text)
        self.assertIn("no firmware image", text)


if __name__ == "__main__":
    unittest.main()
