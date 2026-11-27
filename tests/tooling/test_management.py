# SPDX-License-Identifier: Apache-2.0
"""Checks of the groundwork for the management capability (management over HTTPS): the declared limits, the address
validator, the management policy data and port, the findings note, and that no image build names any
of it yet. Written test first, one slice at a time. Nothing here builds or runs Zephyr."""

import json
import pathlib
import re
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT / "scripts"))

import check_boundary  # noqa: E402
import ci_map  # noqa: E402
import fake_crux  # noqa: E402

REGIONS = {"FLASH", "RAM", "ITCM", "DTCM", "OCRAM", "OCRAM2", "IDT_LIST"}
APP_SRC = ROOT / "app" / "src"
FRAMEWORK_SRC = ROOT / "framework" / "src"


def c_code(path):
    """A C file without its comments."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", pathlib.Path(path).read_text(), flags=re.S)


def includes(path):
    return re.findall(r"^\s*#\s*include\s*([<\"][^>\"]+[>\"])", c_code(path), re.M)


def code_lines(path):
    return [line.split("#", 1)[0] for line in pathlib.Path(path).read_text().splitlines()]


class ManagementLimits(unittest.TestCase):
    """The row is declared before any measurement and before any workflow names management."""

    def limits(self):
        return json.loads((ROOT / "budgets" / "limits.json").read_text())

    def test_limits_declare_management_with_the_same_placeholder_margins(self):
        data = self.limits()
        self.assertIn("management", data["min_free_percent"])
        self.assertEqual(REGIONS, set(data["min_free_percent"]["management"]))
        self.assertTrue(all(v == 25 for v in data["min_free_percent"]["management"].values()))
        self.assertIn("placeholder", data["_comment"].lower())

    def test_the_management_row_equals_the_sntp_row_and_no_other_row_changed(self):
        rows = self.limits()["min_free_percent"]
        self.assertEqual(["minimal", "workload", "net", "file", "system", "sntp", "management", "base"], list(rows))
        for step in ("minimal", "workload", "net", "file", "system"):
            self.assertEqual(rows["sntp"], rows[step], step)
        self.assertEqual(rows["sntp"], rows["management"])


class ManagementValidator(unittest.TestCase):
    """The bind address text is checked by plain C, so the host builds and tests it. Crux's guide
    (docs/management-in-a-product.md at the pinned revision) says Zephyr's HTTP server falls back to
    every address for a text that is not an address, so a composition that sets one checks the text;
    the validator is that check."""

    ISO_C = {"<stdbool.h>", "<stddef.h>", "<stdint.h>"}

    def test_the_policy_includes_iso_c_and_its_own_header_only(self):
        for name in ("management_policy.h", "management_policy.c"):
            for include in includes(FRAMEWORK_SRC / name):
                self.assertTrue(
                    include in self.ISO_C or include == '"management_policy.h"', f"{name}: {include}"
                )

    def test_the_policy_names_no_crux_or_zephyr_symbol(self):
        for name in ("management_policy.h", "management_policy.c"):
            self.assertNotRegex(c_code(FRAMEWORK_SRC / name), r"\bcrux_|\bCRUX_|\bk_|\bCONFIG_|zephyr", name)

    def test_the_host_build_runs_the_policy_test_with_the_strict_flags(self):
        text = "\n".join(code_lines(ROOT / "tests" / "host" / "CMakeLists.txt"))
        self.assertRegex(
            text,
            r"add_executable\(test_management_policy test_management_policy\.c "
            r"\.\./\.\./framework/src/management_policy\.c\)",
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
        for needle in ("management_address_valid", "management_address_parse",
                       "management_policy_valid", "management_version_valid", "management_port.h"):
            self.assertIn(needle, source, needle)

    def test_the_permission_name_check_is_plain_c_and_has_a_host_test_of_the_mismatch_path(self):
        header = c_code(FRAMEWORK_SRC / "management_policy.h")
        self.assertRegex(header, r"bool management_permission_names_match\(const char \*access_manage,\s*const char \*status_read,\s*const char \*config_save\);")
        source = (ROOT / "tests" / "host" / "test_management_policy.c").read_text()
        self.assertIn("management_permission_names_match", source)
        for mismatch in ("access.manag", "status.reed", "config.savee"):
            self.assertIn(mismatch, source, mismatch)
        text = " ".join((FRAMEWORK_SRC / "management_policy.h").read_text().replace("*", " ").split())
        self.assertIn("start-time refusal", text)

    def test_the_parser_is_declared_with_the_octets_and_defined_beside_the_validator(self):
        header = c_code(FRAMEWORK_SRC / "management_policy.h")
        source = c_code(FRAMEWORK_SRC / "management_policy.c")
        self.assertRegex(header, r"bool management_address_parse\(const char \*text, uint8_t octets\[4\]\);")
        self.assertRegex(source, r"bool management_address_parse\(const char \*text, uint8_t octets\[4\]\)")
        # One rule, not two: the validator calls the parser, so they cannot drift apart.
        self.assertRegex(source, r"management_address_valid\(const char \*text\)\s*\{[^}]*management_address_parse\(")


class ManagementPolicy(unittest.TestCase):
    """The role policy is data in plain C. Its names are the ones Crux Access and the Crux
    services define (crux/access.h, crux/management_status.h and crux/config_service.h at the
    pinned revision), copied as text because the policy builds on the host with no Crux header."""

    POLICY_C = FRAMEWORK_SRC / "management_policy.c"
    POLICY_H = FRAMEWORK_SRC / "management_policy.h"

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
                       "read from that header at the pinned revision",
                       "management_permission_names_match() at start"):
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

    def test_the_policy_names_no_permission_that_no_management_route_needs(self):
        text = c_code(self.POLICY_H) + c_code(self.POLICY_C)
        for permission in ("network.", "system.reboot", "events.read", "tls.manage", "config.read",
                           "config.write", "file."):
            self.assertNotIn(permission, text, permission)


class ManagementPort(unittest.TestCase):
    """The port is the product's own header: ISO C and the policy header of this repository, no
    Crux, Zephyr or composition header, so it can sit in app/src."""

    PORT = FRAMEWORK_SRC / "management_port.h"

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
        # Extended by the composition change: the fixture now comes from fake_crux.py and also
        # publishes the Access and web headers that the zone of the management capability includes.
        with tempfile.TemporaryDirectory() as directory:
            crux = fake_crux.publish(directory)
            self.assertEqual([], check_boundary.check(ROOT, crux))
            self.assertEqual([], check_boundary.check(ROOT))

    def test_a_zephyr_include_in_the_port_would_be_found_by_the_boundary_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "app" / "src" / "management_port.h"
            path.parent.mkdir(parents=True)
            path.write_text("#include <zephyr/kernel.h>\n")
            found = check_boundary.check(directory)
            self.assertEqual(["zephyr/kernel.h"], [v.include for v in found])


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


class ManagementConfiguration(unittest.TestCase):
    """The step option, its fragment and its overlay. An unmet Kconfig dependency only warns in a
    build, so the option's dependencies are pinned here and the resolved configuration is read by
    the CI job."""

    CONF = ROOT / "app" / "conf" / "management.conf"
    OVERLAY = ROOT / "app" / "boards" / "management.overlay"

    def test_the_step_option_builds_on_the_network_step_and_the_crux_services(self):
        block = kconfig_block("CRUX_CONTROLLER_MANAGEMENT")
        self.assertIn("bool", block)
        depends = re.search(r"depends on ([^\n]+)", block).group(1)
        for needed in ("CRUX_CONTROLLER_NET", "CRUX_ACCESS", "CRUX_WEB_MANAGEMENT",
                       "CRUX_TLS_CERTIFICATE", "CRUX_SYSTEM"):
            self.assertRegex(depends, rf"\b{needed}\b", needed)

    def test_the_step_option_excludes_the_steps_it_cannot_share_an_image_with(self):
        depends = re.search(r"depends on ([^\n]+)", kconfig_block("CRUX_CONTROLLER_MANAGEMENT")).group(1)
        # file and management each own a file provider, and system clears the reset cause that management reads once.
        self.assertRegex(depends, r"!CRUX_CONTROLLER_FILE\b")
        self.assertRegex(depends, r"!CRUX_CONTROLLER_SYSTEM\b")
        self.assertNotRegex(depends, r"!CRUX_CONTROLLER_SNTP\b")

    def test_the_step_option_selects_nothing(self):
        self.assertNotRegex(kconfig_block("CRUX_CONTROLLER_MANAGEMENT"), r"^\s*select\b")

    def test_the_help_states_the_limits_in_words(self):
        text = " ".join(kconfig_block("CRUX_CONTROLLER_MANAGEMENT").split())
        for needle in ("TLS 1.3", "self-signed", "RAM disk", "nothing persists", "no account",
                       "nobody can log in", "never run on a board", "not measured",
                       "save route", "It does not combine with file,", "or with system,", "192.168.77.2"):
            self.assertIn(needle, text, needle)

    def test_the_help_names_no_provider_symbol_that_the_product_does_not_select(self):
        text = kconfig_block("CRUX_CONTROLLER_MANAGEMENT")
        self.assertNotRegex(text, r"\bCRUX_(?:THREAD|SYNC|QUEUE)(?:_\w+)?\b")

    def test_the_first_step_help_no_longer_says_no_provider_is_selected_by_any_step(self):
        text = " ".join(kconfig_block("CRUX_CONTROLLER_WORKLOAD").split())
        self.assertNotIn("so none is selected for it", text)
        self.assertIn("Product code includes none of their headers", text)
        self.assertIn("select them for themselves", text)

    def test_the_fragment_selects_the_step_and_the_crux_services_and_the_locks(self):
        options = conf_options(self.CONF)
        for name in ("CONFIG_CRUX_CONTROLLER_MANAGEMENT", "CONFIG_CRUX_PSA_THREADING", "CONFIG_CRUX_ACCESS",
                     "CONFIG_CRUX_CONFIG_SERVICE", "CONFIG_CRUX_MGMT_STATUS",
                     "CONFIG_CRUX_TLS_CERTIFICATE", "CONFIG_CRUX_WEB", "CONFIG_CRUX_WEB_SESSION",
                     "CONFIG_CRUX_WEB_MANAGEMENT", "CONFIG_CRUX_SYSTEM",
                     "CONFIG_CRUX_FILE_FATFS_RT1060_RAM_DISK", "CONFIG_MBEDTLS",
                     "CONFIG_PSA_CRYPTO_PROVIDER_MBEDTLS"):
            self.assertEqual("y", options.get(name), name)

    def test_the_fragment_names_no_thread_sync_or_queue_symbol_because_the_services_select_them(self):
        for name in conf_options(self.CONF):
            self.assertNotRegex(name, r"^CONFIG_CRUX_(?:THREAD|SYNC|QUEUE|SERIAL)(?:_\w+)?$", name)

    def test_the_fragment_sets_the_worker_priorities_between_the_workload_and_the_log_thread(self):
        options = conf_options(self.CONF)
        for name in ("CONFIG_CRUX_WEB_SESSION_WORKER_PRIORITY",
                     "CONFIG_CRUX_WEB_MANAGEMENT_WORKER_PRIORITY",
                     "CONFIG_CRUX_SECURITY_EVENT_DRAIN_PRIORITY"):
            self.assertEqual("11", options.get(name), name)

    def test_the_fragment_binds_the_one_address_of_the_board_on_port_443(self):
        options = conf_options(self.CONF)
        self.assertEqual('"192.168.77.2"', options.get("CONFIG_CRUX_WEB_BIND_ADDRESS"))
        self.assertEqual("443", options.get("CONFIG_CRUX_WEB_PORT"))
        self.assertEqual("3", options.get("CONFIG_HTTP_SERVER_MAX_CLIENTS"))

    def test_the_fragment_declares_the_unmeasured_sizes_and_says_they_are_unmeasured(self):
        options = conf_options(self.CONF)
        self.assertEqual("16384", options.get("CONFIG_MAIN_STACK_SIZE"))
        self.assertEqual("16384", options.get("CONFIG_HTTP_SERVER_STACK_SIZE"))
        self.assertEqual("120000", options.get("CONFIG_MBEDTLS_HEAP_SIZE"))
        self.assertEqual("y", options.get("CONFIG_THREAD_STACK_INFO"))
        self.assertEqual("y", options.get("CONFIG_INIT_STACKS"))
        text = " ".join(self.CONF.read_text().split())
        self.assertIn("not measured", text)

    def test_the_fragment_keeps_the_entropy_on_the_hardware_source_and_off_test_sources(self):
        options = conf_options(self.CONF)
        self.assertEqual("y", options.get("CONFIG_ENTROPY_GENERATOR"))
        for name in ("CONFIG_TEST_RANDOM_GENERATOR", "CONFIG_FAKE_ENTROPY_NATIVE_SIM"):
            self.assertNotEqual("y", options.get(name), name)

    def test_the_fragment_turns_the_card_off_because_the_ram_disk_is_the_only_disk(self):
        options = conf_options(self.CONF)
        self.assertEqual("n", options.get("CONFIG_DISK_DRIVER_SDMMC"))
        self.assertEqual("n", options.get("CONFIG_IMX_USDHC"))
        self.assertEqual("y", options.get("CONFIG_FILE_SYSTEM_MKFS"))
        self.assertEqual("n", options.get("CONFIG_FS_FATFS_MOUNT_MKFS"))

    def test_the_fragment_sets_none_of_what_the_step_leaves_off(self):
        options = conf_options(self.CONF)
        for name in ("CONFIG_CRUX_REBOOT", "CONFIG_CRUX_NETWORK_SETTINGS", "CONFIG_CRUX_FILE_SERVICE",
                     "CONFIG_CRUX_SSH", "CONFIG_CRUX_CLI", "CONFIG_CRUX_CLI_CONSOLE",
                     "CONFIG_CRUX_WEB_PLAIN_HTTP_FOR_TESTS", "CONFIG_CRUX_DEVELOPMENT_IMAGE",
                     "CONFIG_CRUX_CONFIGURATION_SETTINGS_FILE", "CONFIG_SHELL", "CONFIG_WOLFSSL",
                     "CONFIG_CRUX_CONTROLLER_FILE", "CONFIG_CRUX_CONTROLLER_SYSTEM"):
            self.assertNotEqual("y", options.get(name), name)
        self.assertFalse([n for n in options if n.startswith("CONFIG_WOLF")])

    def test_the_fragment_names_the_fragments_it_is_built_with(self):
        text = " ".join(self.CONF.read_text().split())
        self.assertIn("conf/workload.conf;conf/net.conf;conf/management.conf", text)
        self.assertIn("boards/net.overlay;boards/management.overlay", text)

    def test_the_overlay_has_the_ram_disk_the_fstab_entry_and_the_system_watchdog(self):
        text = "\n".join(line.split("//", 1)[0] for line in self.OVERLAY.read_text().splitlines())
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        self.assertIn('compatible = "zephyr,ram-disk"', text)
        self.assertIn('disk-name = "RAM"', text)
        self.assertIn("controller_storage:", text)
        self.assertIn('compatible = "zephyr,fstab,fatfs"', text)
        self.assertIn('mount-point = "/RAM:"', text)
        self.assertIn("crux-watchdog0 = &wdog0;", text)
        self.assertRegex(text, r"&wdog0\s*\{\s*status = \"okay\";")

    def test_the_overlay_does_not_repeat_the_logging_or_the_network_overlays(self):
        text = self.OVERLAY.read_text()
        for needle in ("lpuart1", "enet_mac", "zephyr,log-uart"):
            self.assertNotIn(needle, text, needle)

    def test_the_wording_of_thread_and_sync_in_the_first_fragment_is_the_corrected_one(self):
        text = " ".join((ROOT / "app" / "conf" / "workload.conf").read_text().split())
        self.assertNotIn("neither is selected.", text)
        self.assertIn("selects none of them", text)
        self.assertIn("select them for themselves", text)


# A build file names the management configuration by its option, its fragment or overlay, its old step id, or
# in prose as the capability, image, fragment, overlay, job or configuration ("secure management group" does not
# match).
MANAGEMENT_NAMED = (r"CRUX_CONTROLLER_MANAGEMENT|conf/management|boards/management|\bS6\b"
                    r"|\bmanagement (?:capability|image|fragment|overlay|job|configuration)\b")

class ManagementNotBuilt(unittest.TestCase):
    """What the build files under app/ may name. Management is built, so the groundwork's assertions
    that no file names it were replaced, one by one, by assertions that only the files of management
    do. The findings note of the groundwork names this class by its step id, S6NotBuilt."""

    BUILD_FILES = ("CMakeLists.txt", "*.cmake", "Kconfig*", "*.conf", "*.overlay", "*.dts")

    def build_text(self):
        parts = []
        for pattern in self.BUILD_FILES:
            for path in sorted((ROOT / "app").rglob(pattern)):
                parts.append(f"{path.relative_to(ROOT)}\n{path.read_text()}")
        self.assertTrue(parts)
        return "\n".join(parts)

    # Approved behaviour change: the management sources are wired now. The assertion that no build
    # file names them is replaced by one that says which build file names which source.
    def test_each_management_source_is_named_by_the_build_file_that_owns_it(self):
        # The sources live in the framework module's tree. The policy is named by the file that adds
        # it to the management configuration of app/ and by the module's build file for the base
        # image; the start sequence only by the zone's build file.
        app = "\n".join(code_lines(ROOT / "app" / "CMakeLists.txt"))
        configurations = "\n".join(code_lines(ROOT / "framework" / "configurations.cmake"))
        module = "\n".join(code_lines(ROOT / "zephyr" / "CMakeLists.txt"))
        compose = "\n".join(code_lines(ROOT / "framework" / "compose" / "CMakeLists.txt"))
        self.assertNotIn("management_policy", app)
        self.assertIn("src/management_policy.c", configurations)
        self.assertIn("framework/src/management_policy.c", module)
        for text in (app, configurations, module):
            self.assertNotIn("management_start", text)
        self.assertIn("management_start.c", compose)
        self.assertNotIn("management_policy", compose)
        for tree in ("app", "framework", "zephyr"):
            for path in sorted((ROOT / tree).rglob("CMakeLists.txt")):
                self.assertNotIn("management_port", "\n".join(code_lines(path)), str(path))

    # Approved behaviour change: the management capability is now built, so the old assertion that no build file names
    # it is replaced by one that only its own files do. The files of the other steps stay clean.
    # The base image (conf/base.conf) builds on the overlay of management and names it.
    MANAGEMENT_FILES = {"Kconfig", "conf/workload.conf", "conf/management.conf", "boards/management.overlay", "CMakeLists.txt",
                "management/management.cmake", "management/entropy.cmake",
                "management/reviewed-routes.txt", "compose/CMakeLists.txt", "conf/base.conf"}

    def test_only_the_files_of_step_management_name_it(self):
        for pattern in self.BUILD_FILES:
            for path in sorted((ROOT / "app").rglob(pattern)):
                relative = path.relative_to(ROOT / "app").as_posix()
                if relative in self.MANAGEMENT_FILES:
                    continue
                self.assertNotRegex(path.read_text(), MANAGEMENT_NAMED, relative)

    def test_the_other_steps_fragments_and_overlays_do_not_name_management(self):
        for name in ("conf/net.conf", "conf/file.conf", "conf/system.conf", "conf/sntp.conf", "prj.conf",
                     "boards/net.overlay", "boards/file.overlay", "boards/system.overlay"):
            self.assertNotRegex((ROOT / "app" / name).read_text(), MANAGEMENT_NAMED, name)

    # Approved behaviour change: composition.c includes the port header, and the composition source
    # includes it and the policy header. The assertion that nothing includes them becomes a list of
    # the files that may.
    def test_only_the_composition_and_the_zone_include_the_management_headers(self):
        # The framework start (framework/src/framework.c) calls the port in the base image.
        allowed = {"app/src/composition.c", "framework/compose/management_start.c",
                   "framework/src/framework.c"}
        paths = [p for tree in ("app", "framework", "include")
                 for p in (ROOT / tree).rglob("*") if p.suffix in (".c", ".h")]
        for path in sorted(paths):
            relative = path.relative_to(ROOT).as_posix()
            if path.name.startswith("management_policy") or path.name == "management_port.h":
                continue
            for include in includes(path):
                if "management_" in include:
                    self.assertIn(relative, allowed, f"{relative}: {include}")

    # Approved behaviour change: the management fragment now sets the symbols of the web server and Access.
    # The assertion that no file sets them becomes: no fragment but the management one does.
    def test_only_the_management_fragment_sets_the_crux_symbol_for_the_web_or_access(self):
        # The base image (conf/base.conf) runs web management and sets the same symbols.
        for path in sorted((ROOT / "app").rglob("*.conf")):
            if path.name in ("management.conf", "base.conf"):
                continue
            options = conf_options(path)
            for symbol in ("CONFIG_CRUX_ACCESS", "CONFIG_CRUX_WEB", "CONFIG_CRUX_TLS_CERTIFICATE",
                           "CONFIG_CRUX_PSA_THREADING", "CONFIG_CRUX_CONFIG_SERVICE",
                           "CONFIG_CRUX_MGMT_STATUS", "CONFIG_CRUX_WEB_SESSION",
                           "CONFIG_CRUX_WEB_MANAGEMENT"):
                self.assertNotIn(symbol, options, f"{path.name}: {symbol}")

    def test_no_overlay_other_than_the_management_one_declares_the_ram_disk(self):
        for path in sorted((ROOT / "app").rglob("*.overlay")):
            if path.name != "management.overlay":
                self.assertNotIn("zephyr,ram-disk", path.read_text(), path.name)


class ManagementBuildFiles(unittest.TestCase):
    """The wiring of the step. The route sources are named by variable and put in the route table by
    Crux's own CMake functions, which hand their private include directories to those sources one by
    one. The product adds no include directory, in any build file."""

    APP_CMAKE = ROOT / "app" / "CMakeLists.txt"
    MANAGEMENT_CMAKE = ROOT / "framework" / "management" / "management.cmake"
    ENTROPY_CMAKE = ROOT / "framework" / "management" / "entropy.cmake"
    COMPOSE_CMAKE = ROOT / "framework" / "compose" / "CMakeLists.txt"
    FORBIDDEN = ("include_directories", "zephyr_include_directories", "target_include_directories",
                 "-include", "-I")

    def app_text(self):
        return "\n".join(code_lines(self.APP_CMAKE))

    def management_text(self):
        return "\n".join(code_lines(self.MANAGEMENT_CMAKE))

    def compose_text(self):
        return "\n".join(code_lines(self.COMPOSE_CMAKE))

    def block(self):
        match = re.search(r"if\(CONFIG_CRUX_CONTROLLER_MANAGEMENT\)(.*?)endif\(\)", self.app_text(), re.S)
        self.assertIsNotNone(match, "no if(CONFIG_CRUX_CONTROLLER_MANAGEMENT) block")
        return match.group(1)

    def test_the_management_block_is_inside_the_workload_switch_after_sntp(self):
        text = self.app_text()
        # The sntp sources are added by framework/configurations.cmake, which the workload block
        # includes before the management block.
        self.assertGreater(text.index("if(CONFIG_CRUX_CONTROLLER_MANAGEMENT)"),
                           text.index("framework/configurations.cmake"))
        self.assertGreater(text.index("if(CONFIG_CRUX_CONTROLLER_MANAGEMENT)"),
                           text.index("if(CONFIG_CRUX_CONTROLLER_WORKLOAD)"))
        self.assertLess(text.index("if(CONFIG_CRUX_CONTROLLER_MANAGEMENT)"), text.rindex("endif()"))

    def test_the_block_adds_the_policy_links_the_zone_and_includes_the_management_cmake(self):
        block = self.block()
        self.assertRegex(block, r"target_link_libraries\(app PRIVATE crux::web compose\)")
        self.assertIn('include("${CMAKE_CURRENT_LIST_DIR}/../framework/management/management.cmake")', block)
        configurations = "\n".join(code_lines(ROOT / "framework" / "configurations.cmake"))
        self.assertRegex(
            configurations,
            r'if\(CONFIG_CRUX_CONTROLLER_MANAGEMENT\)\s*target_sources\(app PRIVATE '
            r'"\$\{CMAKE_CURRENT_LIST_DIR\}/src/management_policy\.c"\)\s*endif\(\)',
        )

    def test_the_zone_is_added_once_for_either_step_that_uses_it(self):
        text = self.app_text()
        self.assertEqual(1, text.count("add_subdirectory(../framework/compose compose)"))
        self.assertRegex(
            text,
            r"if\(CONFIG_CRUX_CONTROLLER_FILE OR CONFIG_CRUX_CONTROLLER_MANAGEMENT\)\s*"
            r"add_subdirectory\(\.\./framework/compose compose\)\s*endif\(\)",
        )

    def test_no_build_file_of_the_step_adds_an_include_path(self):
        configurations = ROOT / "framework" / "configurations.cmake"
        for path in (self.APP_CMAKE, self.MANAGEMENT_CMAKE, self.ENTROPY_CMAKE, self.COMPOSE_CMAKE,
                     configurations):
            for line in code_lines(path):
                for word in self.FORBIDDEN:
                    self.assertNotIn(word, line, f"{path.name}: {line.strip()}")

    def test_the_build_files_of_the_step_name_no_private_crux_directory_or_target(self):
        for path in (self.APP_CMAKE, self.MANAGEMENT_CMAKE, self.COMPOSE_CMAKE):
            text = "\n".join(code_lines(path))
            # The module's own files are included by path, and that is all of components/ named.
            text = re.sub(r'include\("\$\{crux_root\}/[A-Za-z/]+\.cmake"\)', "", text)
            for private in ("crux_web_adapter", "crux_web_zephyr_resources", "crux_service_priority",
                            "components/", "/session", "/adapter", "web/src", "crux_access_adapter",
                            "crux_web_api", "crux_system_zephyr", "crux_interrupt"):
                self.assertNotIn(private, text, f"{path.name}: {private}")

    def test_the_route_sources_are_the_only_sources_the_management_cmake_adds(self):
        lines = [line for line in code_lines(self.MANAGEMENT_CMAKE) if "target_sources" in line]
        self.assertEqual(1, len(lines), lines)
        self.assertRegex(lines[0], r"target_sources\(app PRIVATE \$\{route_sources\}\)")

    def test_the_management_cmake_names_the_session_and_management_routes_and_no_other(self):
        text = self.management_text()
        self.assertRegex(
            text,
            r"set\(route_sources \$\{CRUX_WEB_SESSION_ROUTES\} \$\{CRUX_WEB_MANAGEMENT_ROUTES\}\)",
        )
        for left_out in ("CRUX_WEB_MANAGEMENT_NETWORK_ROUTES", "CRUX_WEB_MANAGEMENT_REBOOT_ROUTES",
                         "NETWORK_SOURCES", "SESSION_SOURCES", "MANAGEMENT_SOURCES", "PSA_PORT"):
            self.assertNotIn(left_out, text, left_out)

    def test_the_management_cmake_takes_the_crux_files_from_the_module_directory(self):
        text = self.management_text()
        self.assertIn('set(crux_root "${ZEPHYR_CRUX_MODULE_DIR}")', text)
        self.assertRegex(text, r"if\(NOT crux_root\)\s*message\(FATAL_ERROR")
        # The error text names the variable that is missing.
        self.assertRegex(text, r'message\(FATAL_ERROR "[^"]*ZEPHYR_CRUX_MODULE_DIR is not set"\)')
        for needed in ("cmake/CruxWebAssets.cmake", "cmake/CruxWebRoutes.cmake",
                       "components/web/session/sources.cmake",
                       "components/web/management/sources.cmake"):
            self.assertIn(f'include("${{crux_root}}/{needed}")', text, needed)

    def test_the_assets_come_before_the_routes_as_crux_requires(self):
        text = self.management_text()
        assets = re.search(r"crux_web_assets\(app FOLDER \"\$\{CMAKE_CURRENT_LIST_DIR\}/site\" STYLE strict\)", text)
        routes = re.search(
            r"crux_web_routes\(app SOURCES \$\{route_sources\} ZEPHYR_RESOURCES REVIEWED "
            r"\"\$\{CMAKE_CURRENT_LIST_DIR\}/reviewed-routes\.txt\"\)",
            text,
        )
        self.assertIsNotNone(assets)
        self.assertIsNotNone(routes)
        self.assertLess(assets.start(), routes.start())
        self.assertLess(text.index("target_sources(app PRIVATE ${route_sources})"), routes.start())

    def test_the_entropy_rules_are_in_their_own_file_that_only_the_image_includes(self):
        entropy = "\n".join(code_lines(ROOT / "framework" / "management" / "entropy.cmake"))
        self.assertIn('include("${ZEPHYR_CRUX_MODULE_DIR}/cmake/CruxMbedtlsEntropy.cmake")', entropy)
        self.assertLess(entropy.index("cmake/CruxMbedtlsEntropy.cmake"),
                        entropy.index("crux_mbedtls_fail_closed_entropy()"))
        self.assertRegex(entropy, r"if\(CONFIG_TEST_RANDOM_GENERATOR OR CONFIG_FAKE_ENTROPY_NATIVE_SIM\)\s*message\(FATAL_ERROR")
        self.assertRegex(entropy, r"CONFIG_ENTROPY_MCUX_TRNG")
        self.assertRegex(entropy, r"CONFIG_MBEDTLS_PSA_DRIVER_GET_ENTROPY")
        block = self.block()
        self.assertLess(block.index("management/entropy.cmake"), block.index("management/management.cmake"))
        # The management file, which the scenario includes too, holds none of it.
        self.assertNotIn("Entropy", self.management_text())
        self.assertNotIn("TEST_RANDOM", self.management_text())
        self.assertNotIn("fail_closed", self.management_text())

    def test_the_build_files_use_only_the_fixed_module_name_of_crux(self):
        # Crux names its Zephyr module `crux` (name: in zephyr/module.yml), so Zephyr sets
        # ZEPHYR_CRUX_MODULE_DIR whatever the checkout folder is called.
        for path in (self.MANAGEMENT_CMAKE, self.ENTROPY_CMAKE):
            text = path.read_text()
            self.assertIn("${ZEPHYR_CRUX_MODULE_DIR}", text, path.name)

    def test_the_management_cmake_refuses_a_missing_kernel_version(self):
        self.assertRegex(self.management_text(), r"if\(NOT KERNEL_VERSION_STRING\)")

    def test_the_versions_are_compile_definitions_of_the_application(self):
        text = self.management_text()
        self.assertRegex(text, r'MANAGEMENT_PLATFORM_VERSION="zephyr-\$\{KERNEL_VERSION_STRING\}"')
        self.assertRegex(text, r'MANAGEMENT_PROJECT_VERSION="crux-controller-management"')
        self.assertRegex(text, r"target_compile_definitions\(app PRIVATE")

    def test_only_the_zone_library_links_the_web_composition_interface_and_system(self):
        for path in sorted(ROOT.glob("app/**/CMakeLists.txt")) + [self.MANAGEMENT_CMAKE]:
            if path.parent.name == "compose":
                continue
            text = "\n".join(code_lines(path))
            self.assertNotIn("crux::web_zephyr", text, str(path))
        self.assertEqual(1, self.app_text().count("crux::system"))
        self.assertIn("crux::web_zephyr", self.compose_text())
        self.assertIn("crux::system", self.compose_text())

    def test_the_zone_gets_the_management_source_only_when_the_web_management_symbol_is_on(self):
        text = self.compose_text()
        self.assertRegex(
            text,
            r"if\(CONFIG_CRUX_WEB_MANAGEMENT\)\s*target_sources\(compose PRIVATE management_start\.c\)",
        )
        self.assertNotIn("CONFIG_CRUX_CONTROLLER_MANAGEMENT", text)
        # The first line still builds the storage source for every step that has a zone.
        self.assertRegex(text, r"add_library\(compose STATIC storage_mount\.c\)")

    def test_the_zone_links_the_public_service_targets_and_nothing_private(self):
        text = self.compose_text()
        links = re.findall(r"target_link_libraries\(compose PRIVATE([^)]*)\)", text)
        names = set(" ".join(links).split())
        expected = {"zephyr_interface", "crux::file_zephyr", "crux::web_zephyr", "crux::web_session",
                    "crux::web_management", "crux::access", "crux::credential_store",
                    "crux::security_event", "crux::config_service", "crux::mgmt_status",
                    "crux::tls_certificate", "crux::system", "crux::time", "crux::logging",
                    # The serial command line of the base image, under its own symbol.
                    "crux::cli_zephyr", "crux::cli"}
        self.assertEqual(expected, names)

    def test_the_zone_keeps_the_application_warnings_on_the_management_source(self):
        self.assertRegex(self.compose_text(), r"target_compile_options\(compose PRIVATE -Wall -Wextra -Werror\)")

    def test_no_build_file_names_a_reboot_network_or_file_service_symbol_or_route(self):
        for path in (self.APP_CMAKE, self.MANAGEMENT_CMAKE, self.COMPOSE_CMAKE):
            text = "\n".join(code_lines(path))
            for word in ("reboot", "REBOOT", "network_settings", "NETWORK_SETTINGS", "file_service",
                         "FILE_SERVICE", "crux::reboot", "crux::network_settings"):
                self.assertNotIn(word, text, f"{path.name}: {word}")

    def test_the_site_folder_is_the_route_set_and_the_reviewed_list_lies_beside_it(self):
        site = ROOT / "framework" / "management" / "site"
        self.assertEqual(["index.html", "page.css", "page.js"], sorted(p.name for p in site.iterdir()))
        self.assertTrue((ROOT / "framework" / "management" / "reviewed-routes.txt").is_file())


class ManagementRoutes(unittest.TestCase):
    """The list that the route generator checks the table against. A public or session-only route
    that is not listed fails the build, so this list is the review of what the image serves."""

    LIST = ROOT / "framework" / "management" / "reviewed-routes.txt"
    EXPECTED = [
        "public POST /api/v1/session",
        "session DELETE /api/v1/session",
        "public GET /api/v1/session/attempt/{id}",
        "session GET /api/v1/session/me",
        "session POST /api/v1/session/me/password",
        "session GET /api/v1/status",
        "session GET /api/v1/config",
        "session GET /api/v1/config/{name}",
        "session PUT /api/v1/config/{name}",
        "public GET @assets",
    ]

    def entries(self):
        return [line.strip() for line in self.LIST.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")]

    def test_the_list_is_the_nine_component_routes_and_the_packaged_folder(self):
        self.assertEqual(self.EXPECTED, self.entries())

    def test_the_list_names_no_reboot_network_or_file_route(self):
        text = "\n".join(self.entries())
        for word in ("reboot", "network", "/files", "/system"):
            self.assertNotIn(word, text, word)

    def test_the_list_says_why_the_save_route_is_not_on_it(self):
        text = " ".join(self.LIST.read_text().split())
        self.assertIn("config.save", text)
        self.assertIn("permission as their access class", text)


class ManagementPage(unittest.TestCase):
    """The packaged page: no framework, no external URL, no inline script or style. Only its bytes
    are tested here and by the scenario; no browser has loaded it."""

    SITE = ROOT / "framework" / "management" / "site"

    def read(self, name):
        return (self.SITE / name).read_text()

    def test_the_page_names_its_own_script_and_style_by_relative_path(self):
        html = self.read("index.html")
        self.assertRegex(html, r'<link rel="stylesheet" href="page\.css">')
        self.assertRegex(html, r'<script src="page\.js"></script>')

    def test_the_page_has_no_external_url_inline_script_inline_style_or_event_attribute(self):
        for name in ("index.html", "page.css", "page.js"):
            text = self.read(name)
            self.assertNotRegex(text, r"https?://|(?<![A-Za-z0-9])//[A-Za-z]|url\(", name)
        html = self.read("index.html")
        self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)[^>]*>")
        self.assertNotRegex(html, r"<script[^>]*src=[^>]*>\s*(?!</script>)\S", "no script body")
        self.assertNotRegex(html, r"<style\b|\sstyle=")
        self.assertNotRegex(html, r"\son[a-z]+=")
        self.assertNotRegex(html, r"javascript:")

    def test_the_page_has_the_two_login_fields_and_the_status_and_logout_parts(self):
        html = self.read("index.html")
        self.assertRegex(html, r'<input[^>]*\bname="user"[^>]*autocomplete="username"')
        self.assertRegex(html, r'<input[^>]*type="password"[^>]*\bname="password"[^>]*autocomplete="current-password"')
        for needle in ('id="login"', 'id="status"', 'id="logout"', 'id="message"', 'lang="en"'):
            self.assertIn(needle, html, needle)

    def test_the_script_talks_to_the_session_and_status_routes_with_the_two_forgery_headers(self):
        js = self.read("page.js")
        for needle in ('"/api/v1/session"', '"/attempt/"', '"/api/v1/status"',
                       "X-Crux-Request", "X-XSRF-TOKEN", "XSRF-TOKEN", "application/json",
                       "credentials", "same-origin"):
            self.assertIn(needle, js, needle)

    def test_the_script_writes_server_text_as_text_only(self):
        js = self.read("page.js")
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
                       "new Function", "setTimeout(\"", "localStorage", "sessionStorage"):
            self.assertNotIn(banned, js, banned)
        self.assertIn("textContent", js)

    def test_the_script_keeps_the_password_out_of_the_page_after_the_attempt(self):
        js = self.read("page.js")
        self.assertRegex(js, r'password\.value = ""')

    def test_the_script_sends_the_password_in_a_json_body_and_never_in_a_url(self):
        js = self.read("page.js")
        self.assertIn("JSON.stringify", js)
        self.assertNotRegex(js, r"\?.*password|password.*\+.*\"\?")

    def test_the_files_fit_what_the_packager_serves(self):
        total = 0
        for path in self.SITE.iterdir():
            self.assertRegex(path.name, r"^[A-Za-z0-9._~-]+$")
            self.assertIn(path.suffix, (".html", ".css", ".js"))
            self.assertGreater(path.stat().st_size, 0)
            total += path.stat().st_size
        # The packager's declared default budget is 393,216 bytes in all and 32 files.
        self.assertLess(total, 32 * 1024)
        text = "".join(p.read_text() for p in self.SITE.iterdir())
        self.assertNotRegex(text, r"-----BEGIN|\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")

    def test_the_page_says_what_it_does_not_do_and_names_no_private_wording(self):
        html = self.read("index.html")
        self.assertIn("certificate", html.lower())
        self.assertNotRegex("".join(p.read_text() for p in self.SITE.iterdir()),
                            r"(?i)\b(claude|assistant|llm)\b|work package|/Users/")


class ManagementStorage(unittest.TestCase):
    """The storage port gains the two roots of the credential store. The port stays ISO C."""

    HEADER = FRAMEWORK_SRC / "storage_port.h"
    SOURCE = ROOT / "framework" / "compose" / "storage_mount.c"

    def test_the_port_declares_the_store_binding_and_the_two_root_numbers(self):
        code = c_code(self.HEADER)
        self.assertRegex(code, r"#define STORAGE_PORT_STORE_ROOT_A 1\b")
        self.assertRegex(code, r"#define STORAGE_PORT_STORE_ROOT_B 2\b")
        self.assertRegex(code, r"storage_port_status_t storage_port_bind_store\(void\);")

    def test_the_port_header_still_includes_nothing(self):
        self.assertEqual([], includes(self.HEADER))

    def test_the_zone_creates_the_two_directories_and_binds_the_two_roots(self):
        code = c_code(self.SOURCE)
        for needle in ('"secure-a"', '"secure-b"', "fs_mkdir(", "crux_file_zephyr_bind_root(",
                       "STORAGE_PORT_STORE_ROOT_A", "STORAGE_PORT_STORE_ROOT_B"):
            self.assertIn(needle, code, needle)

    def test_the_store_binding_is_compiled_only_with_the_web_management_symbol_so_other_steps_are_unchanged(self):
        # The file image compiles this file too. Everything that management added to it is behind the Crux
        # symbol that the management fragment sets, and the helper that the file code uses is the one it had.
        code = c_code(self.SOURCE)
        guarded = code[code.index("#ifdef CONFIG_CRUX_WEB_MANAGEMENT"):]
        self.assertIn("storage_port_bind_store(void)", guarded)
        self.assertIn("directory_path(", guarded)
        before = code[: code.index("#ifdef CONFIG_CRUX_WEB_MANAGEMENT")]
        self.assertNotIn("directory_path", before)
        self.assertNotIn("storage_port_bind_store", before)
        self.assertNotIn("STORE_DIRECTORY", before)
        self.assertRegex(before, r"snprintf\(path, capacity, \"%s/%s\", volume\(\)->mnt_point, FILES_DIRECTORY\)")
        self.assertTrue(guarded.rstrip().endswith("#endif"))

    def test_the_roots_are_distinct_and_do_not_overlap_the_files_directory(self):
        code = c_code(self.SOURCE)
        self.assertRegex(code, r'#define FILES_DIRECTORY "files"')
        self.assertNotIn('"secure-a/', code)

    def test_the_header_says_that_root_a_can_stay_bound_and_that_an_unusable_store_is_fatal(self):
        text = " ".join(self.HEADER.read_text().replace("*", " ").split())
        self.assertIn("root A stays bound when root B fails", text)
        self.assertIn("there is no unbind", text)

    def test_the_composition_documents_that_an_unusable_credential_store_ends_the_start(self):
        text = " ".join((ROOT / "framework" / "compose" / "management_start.c").read_text().replace("*", " ").split())
        self.assertIn("CRUX_CREDENTIAL_ERR_UNUSABLE", text)
        self.assertIn("fine on a RAM disk", text)
        self.assertIn("revisited for a persistent medium", text)

    def test_the_header_comment_lists_the_third_call_and_its_order(self):
        text = " ".join(self.HEADER.read_text().replace("*", " ").split())
        self.assertIn("storage_port_bind_store()", text)
        self.assertIn("after storage_port_mount()", text)


class ManagementSources(unittest.TestCase):
    """The composition source of the zone. It runs the start sequence of management_port.h with the
    public Crux headers, the two composition interfaces the zone may name, and one Zephyr header on
    the zone's list. The checks read text; nothing here compiles or runs it."""

    SOURCE = ROOT / "framework" / "compose" / "management_start.c"
    ALLOWED = {
        '"../src/management_port.h"', '"../src/storage_port.h"', "<crux/access.h>",
        "<crux/config_service.h>", "<crux/credential_store.h>", "<crux/logging.h>",
        "<crux/management_status.h>", "<crux/security_event.h>", "<crux/status.h>",
        "<crux/system.h>", "<crux/time.h>", "<crux/tls_certificate_start.h>", "<crux/web.h>",
        "<crux/web_management.h>", "<crux/web_session.h>", "<crux/web_zephyr.h>",
        "<stdbool.h>", "<stddef.h>", "<stdint.h>", "<stdio.h>", "<string.h>",
        "<zephyr/net/tls_credentials.h>",
    }

    def code(self):
        return c_code(self.SOURCE)

    def test_the_source_includes_only_what_the_zone_may(self):
        for include in includes(self.SOURCE):
            self.assertIn(include, self.ALLOWED, include)
        for needed in ("<crux/web_zephyr.h>", "<zephyr/net/tls_credentials.h>",
                       '"../src/management_port.h"'):
            self.assertIn(needed, includes(self.SOURCE), needed)

    def test_the_source_includes_no_private_or_frozen_header(self):
        for include in includes(self.SOURCE):
            for banned in ("adapter", "session_internal", "web_session.h\"", "crux/thread.h",
                           "crux/sync.h", "crux/queue.h", "crux/serial.h", "psa/", "mbedtls",
                           "zephyr/kernel.h", "zephyr/sys/printk.h"):
                self.assertNotIn(banned, include, include)

    def test_the_source_implements_the_port_and_is_gated_on_the_crux_symbol_by_its_build_file(self):
        code = self.code()
        self.assertRegex(code, r"management_port_status_t management_port_start\(const management_port_config_t \*config\)")
        self.assertNotIn("CONFIG_CRUX_CONTROLLER", code)

    def body(self):
        code = self.code()
        return code[code.index("management_port_status_t management_port_start("):]

    def positions(self, needles):
        body = self.body()
        found = []
        for needle in needles:
            self.assertIn(needle, body, needle)
            found.append(body.index(needle))
        return found

    def test_the_calls_run_in_the_order_of_the_port_header(self):
        found = self.positions((
            "crux_security_event_init(", "crux_realtime_init(", "storage_port_mount(",
            "storage_port_bind_store(", "crux_credential_start(", "crux_access_init(",
            "crux_config_service_start(", "crux_mgmt_status_start(", "crux_security_event_start(",
            "crux_tls_certificate_start(", "tls_credentials_register()", "crux_web_session_init(",
            "crux_web_session_start_worker(", "crux_web_management_init(",
            "crux_web_management_start_worker(", "crux_web_start(",
        ))
        self.assertEqual(sorted(found), found)

    def test_the_credential_registration_takes_the_material_before_it_adds_it(self):
        code = self.code()
        helper = code[code.index("static int tls_credentials_register"):code.index("management_port_status_t management_port_start(")]
        self.assertLess(helper.index("crux_tls_certificate_material_take("), helper.index("tls_credential_add("))

    def test_the_web_start_is_the_last_call_of_the_sequence(self):
        body = self.body()
        calls = re.findall(r"\b(crux_[a-z_]+|storage_port_[a-z_]+|tls_credential_add)\(", body)
        self.assertEqual("crux_web_start", [c for c in calls if c != "crux_log_write"][-1])

    def test_both_tls_credential_registrations_are_checked_before_the_listener_starts(self):
        code = self.code()
        self.assertEqual(2, code.count("tls_credential_add("))
        self.assertIn("TLS_CREDENTIAL_PUBLIC_CERTIFICATE", code)
        self.assertIn("TLS_CREDENTIAL_PRIVATE_KEY", code)
        self.assertRegex(code, r"int result = tls_credential_add\([^;]*PUBLIC_CERTIFICATE[^;]*;\s*"
                               r"if \(result == 0\) \{\s*result = tls_credential_add\([^;]*PRIVATE_KEY")
        self.assertRegex(code, r"tls_credentials_register\(\) != 0")
        self.assertLess(code.index("tls_credentials_register() != 0"), code.index("crux_web_start("))

    def test_the_key_material_is_neither_copied_nor_logged_nor_released(self):
        code = self.code()
        self.assertNotIn("crux_tls_certificate_material_release", code)
        # The material is named inside its one helper and nowhere else, so no other code copies it.
        start = code.index("static int tls_credentials_register")
        end = code.index("static void set_certificate_options")
        self.assertNotRegex(code[:start] + code[end:], r"\bmaterial\b")
        for match in re.finditer(r"private_key", code):
            statement = code[code.rfind(";", 0, match.start()) + 1 : code.index(";", match.end())]
            self.assertIn("tls_credential_add(", statement, statement.strip())
        self.assertEqual(1, code.count("static crux_tls_certificate_material_t material;"))

    def test_the_certificate_names_the_bind_address_that_the_parser_gave(self):
        code = self.code()
        self.assertIn("management_address_parse(CONFIG_CRUX_WEB_BIND_ADDRESS", code)
        self.assertLess(code.index("management_address_parse("), code.index("crux_tls_certificate_start("))
        self.assertIn("CRUX_TLS_CERTIFICATE_DEFAULT_NOT_BEFORE_S", code)
        self.assertRegex(code, r"\.validity_days = 0u")

    def test_the_bind_address_text_must_not_be_empty_at_build_time(self):
        self.assertRegex(self.code(), r"_Static_assert\(sizeof\(CONFIG_CRUX_WEB_BIND_ADDRESS\) > 1u")

    def test_the_policy_and_the_versions_are_checked_before_anything_starts(self):
        code = self.code()
        start = code.index("management_port_status_t management_port_start(")
        for needle in ("management_policy_valid(", "management_version_valid("):
            self.assertIn(needle, code, needle)
            self.assertLess(code.index(needle, start), code.index("crux_security_event_init(", start))

    def test_the_permission_names_are_compared_with_the_crux_macros_and_a_difference_refuses_the_start(self):
        # Changed with the review: the comparison is a plain-C function of the policy
        # (management_permission_names_match), so that a host test can run the mismatch path. The
        # composition passes it the three Crux macros and refuses the start on a false answer.
        code = " ".join(self.code().split())
        self.assertRegex(code, r"management_permission_names_match\( ?CRUX_ACCESS_PERMISSION_MANAGE, "
                               r"CRUX_MGMT_STATUS_PERMISSION_READ, CRUX_CONFIG_SERVICE_PERMISSION_SAVE\)")
        self.assertNotIn("strcmp(", code)
        self.assertRegex(code, r"permission_names_agree\(\)")
        start = code.index("management_port_status_t management_port_start(")
        self.assertLess(code.index("permission_names_agree()", start), code.index("crux_security_event_init(", start))

    def test_the_policy_is_copied_member_by_member_into_the_crux_type(self):
        code = self.code()
        for member in (".name =", ".permissions =", ".permission_count =", ".roles =", ".role_count =",
                       ".session_idle_limit_s =", ".session_absolute_limit_s =",
                       ".password_acceptable = NULL"):
            self.assertIn(member, code, member)
        self.assertIn("management_role_count_fits", code)

    def test_the_reset_cause_is_read_once_and_before_the_initialiser_that_uses_it(self):
        code = self.code()
        self.assertEqual(1, code.count("crux_system_reset_cause_get("))
        self.assertEqual(0, code.count("crux_system_reset_cause_clear"))
        self.assertRegex(code, r"const crux_status_t cause_status = crux_system_reset_cause_get\(&cause\);")
        self.assertLess(code.index("crux_system_reset_cause_get("), code.index(".boot_reset_cause_status"))

    def test_the_session_module_is_told_https_and_no_origin_list(self):
        self.assertRegex(self.code(), r'crux_web_session_config_t sessions = \{"https", NULL, 0u\}')

    def test_the_listener_gets_the_session_authentication_and_the_kconfig_request_deadline(self):
        code = self.code()
        self.assertIn(".authenticate = crux_web_session_authenticate", code)
        self.assertIn(".request_deadline_ms = CONFIG_CRUX_WEB_REQUEST_DEADLINE_MS", code)
        self.assertIn(".authenticate_context = NULL", code)

    def test_the_start_is_one_shot_and_a_second_call_changes_nothing(self):
        code = self.code()
        self.assertIn("MANAGEMENT_PORT_ERR_ALREADY_STARTED", code)
        self.assertRegex(code, r"static bool started;")
        self.assertLess(code.index("MANAGEMENT_PORT_ERR_INVALID_ARGUMENT"), code.index("started = true;"))

    def test_the_header_comment_no_longer_says_that_nothing_in_the_file_has_run(self):
        text = " ".join(self.SOURCE.read_text().replace("*", " ").split())
        self.assertNotIn("Nothing in this file has run", text)
        self.assertIn("built in CI for the board and run on native_sim; never run on a board", text)

    def test_the_fragment_names_the_file_that_applies_the_entropy_correction(self):
        text = (ROOT / "app" / "conf" / "management.conf").read_text()
        self.assertIn("applied in framework/management/entropy.cmake", " ".join(text.replace("#", " ").split()))
        self.assertNotIn("applied in framework/management/management.cmake", " ".join(text.replace("#", " ").split()))

    def test_the_source_reports_through_crux_logging_and_never_logs_a_secret(self):
        code = self.code()
        self.assertIn("crux_log_write(", code)
        self.assertNotRegex(code, r"\bprintk\b|\bprintf\(")
        for word in ("password", "private_key"):
            for line in code.splitlines():
                if "crux_log_write" in line or "snprintf" in line:
                    self.assertNotIn(word, line, line)

    def test_the_source_calls_no_reboot_network_file_service_or_first_account_function(self):
        code = self.code()
        for word in ("crux_reboot", "crux_network_settings", "crux_file_service",
                     "crux_access_provision", "crux_cli", "crux_ssh"):
            self.assertNotIn(word, code, word)

    def test_the_zone_with_this_source_passes_the_boundary_check_against_the_published_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            crux = fake_crux.publish(directory)
            self.assertEqual([], check_boundary.check(ROOT, crux))
        self.assertEqual([], check_boundary.check(ROOT))

    def test_the_boundary_allow_lists_are_unchanged_by_this_step(self):
        # The composition list later grew by crux/cli_zephyr.h, for the serial command line of the
        # base image, in its own reviewed boundary change. This pin follows it.
        self.assertEqual(frozenset({"crux/file_zephyr.h", "crux/web_zephyr.h", "crux/cli_zephyr.h"}),
                         check_boundary.COMPOSITION_CRUX_HEADERS)
        self.assertEqual(
            frozenset({"zephyr/fs/fs.h", "zephyr/devicetree.h", "zephyr/net/tls_credentials.h"}),
            check_boundary.COMPOSITION_ZEPHYR_HEADERS)
        self.assertEqual(frozenset({"zephyr/kernel.h", "zephyr/net/sntp.h"}),
                         check_boundary.OS_ADAPTER_ZEPHYR_HEADERS)


class ManagementComposition(unittest.TestCase):
    """The start of the step in composition.c, after sntp and before the workload threads."""

    SOURCE = APP_SRC / "composition.c"

    def code(self):
        return c_code(self.SOURCE)

    def test_the_composition_includes_the_port_and_logging_under_the_product_symbol(self):
        text = self.SOURCE.read_text()
        self.assertRegex(
            text,
            r'#ifdef CONFIG_CRUX_CONTROLLER_MANAGEMENT\s*#include <crux/logging.h>\s*'
            r'#include "\.\./\.\./framework/src/management_port.h"',
        )

    def test_the_composition_starts_management_after_sntp_and_before_the_workload_threads(self):
        code = self.code()
        sntp = code.index("time_sync_start()")
        management = code.index("start_management();", code.index("static void start_management"))
        run = code.index("return workload_thread_start(&config)")
        self.assertLess(sntp, management)
        self.assertLess(management, run)

    def test_the_composition_keys_on_the_product_symbol_and_no_provider_symbol(self):
        code = self.code()
        self.assertGreaterEqual(code.count("CONFIG_CRUX_CONTROLLER_MANAGEMENT"), 2)
        self.assertNotRegex(code, r"CONFIG_CRUX_(?:THREAD|SYNC|QUEUE)")
        self.assertNotRegex(code, r"CONFIG_CRUX_(?:ACCESS|WEB)")

    def test_the_versions_come_from_the_build_and_a_missing_one_stops_the_build(self):
        text = self.SOURCE.read_text()
        self.assertRegex(text, r"#ifndef MANAGEMENT_PLATFORM_VERSION\s*#error")
        self.assertRegex(text, r"#ifndef MANAGEMENT_PROJECT_VERSION\s*#error")
        self.assertIn(".platform_version = MANAGEMENT_PLATFORM_VERSION", self.code())
        self.assertIn(".project_version = MANAGEMENT_PROJECT_VERSION", self.code())

    def test_a_failed_start_is_logged_and_the_workload_still_starts(self):
        code = self.code()
        self.assertRegex(code, r'if \(management_port_start\(&config\) != MANAGEMENT_PORT_OK\) \{\s*\(void\)crux_log_write\(CRUX_LOG_ERROR, "mgmt"')


class ManagementScenario(unittest.TestCase):
    """The native_sim scenario of the management capability. It lives beside tests/native_sim, not in it: the workload job
    runs every scenario under tests/native_sim in a workspace that has no Mbed TLS modules, so a
    scenario that needs them would fail to configure there. The management job names this directory."""

    DIRECTORY = ROOT / "tests" / "native_sim_mbed" / "management"
    CASES = ("start_sequence", "certificate_registered", "tls13_handshake_verifies",
             "tls12_only_refused", "plain_http_not_answered", "page_bytes",
             "status_needs_a_session", "login_attempt_accepted", "poll_reports_rejected",
             "csrf_rejected_without_header")

    def text(self, name):
        return (self.DIRECTORY / name).read_text()

    def cmake(self):
        return "\n".join(code_lines(self.DIRECTORY / "CMakeLists.txt"))

    def test_the_scenario_is_a_sibling_of_the_native_sim_directory_not_inside_it(self):
        self.assertTrue(self.DIRECTORY.is_dir())
        self.assertFalse((ROOT / "tests" / "native_sim" / "management").exists())
        self.assertEqual(
            ["CMakeLists.txt", "app.overlay", "prj.conf", "src", "testcase.yaml"],
            sorted(p.name for p in self.DIRECTORY.iterdir()),
        )

    def test_one_scenario_one_image_on_the_64_bit_simulator(self):
        data = yaml.safe_load(self.text("testcase.yaml"))
        self.assertEqual(["controller.management.native_sim.https_management"], sorted(data["tests"]))
        scenario = data["tests"]["controller.management.native_sim.https_management"]
        self.assertEqual(["native_sim/native/64"], data["common"]["platform_allow"])
        self.assertEqual({"controller", "management"}, set(data["common"]["tags"]))
        self.assertEqual(180, scenario["timeout"])
        # A missing module is a failure, not a skip: the key `modules` would turn it into one.
        self.assertNotIn("modules", scenario)
        self.assertNotIn("modules", data["common"])
        self.assertNotIn("extra_args", scenario)

    def test_the_scenario_builds_the_real_route_wiring_the_real_zone_and_the_real_policy(self):
        cmake = self.cmake()
        self.assertIn("${controller_root}/framework/management/management.cmake", cmake)
        self.assertRegex(cmake, r"add_subdirectory\(\$\{controller_root\}/framework/compose compose\)")
        self.assertIn("${controller_root}/framework/src/management_policy.c", cmake)
        self.assertRegex(cmake, r"target_link_libraries\(app PRIVATE[^)]*\bcompose\b")
        self.assertNotIn("management_start", cmake)
        self.assertNotIn("entropy.cmake", cmake)
        self.assertNotIn("route_sources", cmake)

    def test_the_scenario_adds_no_include_path_beyond_the_application_sources(self):
        cmake = self.cmake()
        for line in cmake.splitlines():
            for word in ("-include", "-I"):
                self.assertNotIn(word, line, line.strip())
        for line in cmake.splitlines():
            if "include_directories" in line:
                self.assertRegex(line, r"target_include_directories\(app PRIVATE \$\{controller_root\}/framework/src\)")
        for private in ("components/", "crux_web_adapter", "/session", "psa_threading"):
            self.assertNotIn(private, cmake, private)

    def test_the_scenario_refuses_to_build_outside_the_simulator_whose_entropy_is_a_test_source(self):
        cmake = self.cmake()
        self.assertRegex(cmake, r"if\(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM\)\s*message\(FATAL_ERROR")

    def test_the_scenario_names_no_thread_sync_or_queue_symbol(self):
        for name in ("CMakeLists.txt", "prj.conf"):
            self.assertNotRegex(self.text(name), r"CRUX_(?:THREAD|SYNC|QUEUE)(?:_\w+)?\b", name)

    def prj(self):
        return conf_options(self.DIRECTORY / "prj.conf")

    def test_the_scenario_picks_picolibc_because_the_target_does_and_says_so(self):
        text = self.text("prj.conf")
        self.assertEqual("y", self.prj().get("CONFIG_PICOLIBC"))
        self.assertNotIn("CONFIG_MINIMAL_LIBC=y", text)
        self.assertNotIn("CONFIG_EXTERNAL_LIBC=y", text)
        self.assertIn("minimal libc", " ".join(text.split()))

    def test_the_scenario_has_the_services_the_loopback_listener_and_the_fake_entropy(self):
        options = self.prj()
        for name in ("CONFIG_CRUX_PSA_THREADING", "CONFIG_CRUX_ACCESS", "CONFIG_CRUX_CONFIG_SERVICE",
                     "CONFIG_CRUX_MGMT_STATUS", "CONFIG_CRUX_TLS_CERTIFICATE", "CONFIG_CRUX_WEB",
                     "CONFIG_CRUX_WEB_SESSION", "CONFIG_CRUX_WEB_MANAGEMENT", "CONFIG_CRUX_SYSTEM",
                     "CONFIG_CRUX_NETIF", "CONFIG_CRUX_LOGGING", "CONFIG_NET_LOOPBACK",
                     "CONFIG_NET_SOCKETS_SOCKOPT_TLS", "CONFIG_TLS_CREDENTIALS",
                     "CONFIG_ENTROPY_GENERATOR", "CONFIG_CRUX_FILE_FATFS_SIMULATOR",
                     "CONFIG_FILE_SYSTEM_MKFS", "CONFIG_MBEDTLS", "CONFIG_PSA_CRYPTO_PROVIDER_MBEDTLS"):
            self.assertEqual("y", options.get(name), name)
        self.assertEqual('"127.0.0.1"', options.get("CONFIG_CRUX_WEB_BIND_ADDRESS"))
        self.assertEqual("443", options.get("CONFIG_CRUX_WEB_PORT"))
        for name in ("CONFIG_CRUX_WEB_SESSION_WORKER_PRIORITY", "CONFIG_CRUX_WEB_MANAGEMENT_WORKER_PRIORITY",
                     "CONFIG_CRUX_SECURITY_EVENT_DRAIN_PRIORITY"):
            self.assertEqual("11", options.get(name), name)
        self.assertEqual("n", options.get("CONFIG_FS_FATFS_MOUNT_MKFS"))

    def test_the_scenario_has_no_symbol_of_the_product_or_of_what_the_step_leaves_off(self):
        options = self.prj()
        self.assertFalse([n for n in options if n.startswith("CONFIG_CRUX_CONTROLLER")])
        for name in ("CONFIG_CRUX_REBOOT", "CONFIG_CRUX_NETWORK_SETTINGS", "CONFIG_CRUX_FILE_SERVICE",
                     "CONFIG_CRUX_SSH", "CONFIG_CRUX_CLI", "CONFIG_CRUX_WEB_PLAIN_HTTP_FOR_TESTS",
                     "CONFIG_SHELL"):
            self.assertNotEqual("y", options.get(name), name)
        self.assertFalse([n for n in options if n.startswith("CONFIG_WOLF")])

    def test_the_mbed_profile_is_the_one_of_the_fragment_except_for_the_larger_heap(self):
        fragment = conf_options(ROOT / "app" / "conf" / "management.conf")
        options = self.prj()
        shared = [name for name in fragment
                  if name.startswith(("CONFIG_MBEDTLS", "CONFIG_PSA_WANT", "CONFIG_PSA_CRYPTO"))]
        self.assertGreater(len(shared), 20)
        for name in shared:
            if name == "CONFIG_MBEDTLS_HEAP_SIZE":
                self.assertEqual("180000", options.get(name))
                continue
            self.assertEqual(fragment[name], options.get(name), name)

    def test_the_heap_is_larger_than_the_products_because_the_client_shares_the_process(self):
        text = " ".join(self.text("prj.conf").split())
        self.assertIn("client", text)
        self.assertIn("120,000", text)

    def test_the_scenario_declares_the_kernel_stacks_the_handshake_needs(self):
        options = self.prj()
        self.assertEqual("32768", options.get("CONFIG_MAIN_STACK_SIZE"))
        self.assertEqual("32768", options.get("CONFIG_ZTEST_STACK_SIZE"))

    def test_the_overlay_has_the_emulated_log_uart_the_ram_disk_and_the_storage_entry(self):
        text = self.text("app.overlay")
        for needle in ('compatible = "zephyr,uart-emul"', "logging_test:", 'compatible = "zephyr,ram-disk"',
                       "controller_storage:", 'mount-point = "/RAM:"', "zephyr,log-uart"):
            self.assertIn(needle, text, needle)

    def source(self):
        return self.text("src/test_management.c")

    def test_the_source_has_the_ten_cases_in_order(self):
        code = c_code(self.DIRECTORY / "src" / "test_management.c")
        found = re.findall(r"ZTEST\(management, test_(\d\d)_([a-z0-9_]+)\)", code)
        self.assertEqual([(f"{n + 1:02d}", name) for n, name in enumerate(self.CASES)], found)

    def test_the_source_starts_management_once_through_the_products_port(self):
        code = c_code(self.DIRECTORY / "src" / "test_management.c")
        self.assertIn('#include "management_port.h"', code)
        self.assertEqual(1, code.count("status = management_port_start(&config);"))
        self.assertIn("MANAGEMENT_PORT_ERR_ALREADY_STARTED", code)
        self.assertIn("MANAGEMENT_PORT_ERR_INVALID_ARGUMENT", code)

    def test_the_client_verifies_the_server_with_the_certificate_the_product_registered(self):
        code = " ".join(c_code(self.DIRECTORY / "src" / "test_management.c").split())
        for needle in ("ZSOCK_TLS_PEER_VERIFY_REQUIRED", "TLS_CREDENTIAL_CA_CERTIFICATE",
                       "tls_credential_get(CONFIG_CRUX_WEB_TLS_SEC_TAG, TLS_CREDENTIAL_PUBLIC_CERTIFICATE",
                       "NET_IPPROTO_TLS_1_3", "ZSOCK_TLS_SEC_TAG_LIST", "ZSOCK_TLS_HOSTNAME"):
            self.assertIn(needle, code, needle)

    def test_the_key_is_asked_for_its_length_only_and_never_read_or_printed(self):
        code = " ".join(c_code(self.DIRECTORY / "src" / "test_management.c").split())
        self.assertRegex(code, r"tls_credential_get\( ?CONFIG_CRUX_WEB_TLS_SEC_TAG, TLS_CREDENTIAL_PRIVATE_KEY, &probe, &key_length\)")
        self.assertIn("-EFBIG", code)
        self.assertEqual(1, code.count("TLS_CREDENTIAL_PRIVATE_KEY"))

    def test_the_tls12_case_has_a_positive_control_and_does_not_pass_on_any_failed_connect(self):
        code = " ".join(c_code(self.DIRECTORY / "src" / "test_management.c").split())
        case = code[code.index("ZTEST(management, test_04_tls12_only_refused)"):code.index("ZTEST(management, test_05_")]
        # The control: the same client set-up with a TLS 1.3 suite must connect, so the refusal below
        # is about the suite and not about the set-up, the listener or the socket options.
        self.assertIn("connect_tls(NET_IPPROTO_TLS_1_2, SUITE_TLS13_AES_128_GCM_SHA256, CONNECT_ATTEMPTS)", case)
        self.assertIn("connect_tls(NET_IPPROTO_TLS_1_2, SUITE_TLS12_ECDHE_ECDSA_AES_128_GCM_SHA256, 1)", case)
        self.assertLess(case.index("SUITE_TLS13_AES_128_GCM_SHA256"), case.index("SUITE_TLS12_ECDHE"))
        # The refusal is not a refused connection or a timeout, and the errno is logged.
        self.assertIn("last_connect_errno", case)
        self.assertIn("ECONNREFUSED", case)
        self.assertIn("ETIMEDOUT", case)
        self.assertIn("TC_PRINT", case)

    def test_connect_tls_saves_errno_before_anything_can_overwrite_it(self):
        code = " ".join(c_code(self.DIRECTORY / "src" / "test_management.c").split())
        helper = code[code.index("static int connect_tls("):code.index("static size_t read_until_quiet")]
        self.assertRegex(helper, r"zsock_connect\([^;]*\) == 0\) \{ return sock; \} last_connect_errno = errno; \(void\)zsock_close\(sock\);")

    def test_the_source_says_that_a_client_side_refusal_is_not_fully_excluded_in_process(self):
        text = " ".join(self.source().replace("*", " ").split())
        self.assertIn("a refusal on the client side cannot be fully excluded in one process", text)
        self.assertIn("docs/https-composition.md", text)

    def test_the_client_waits_with_poll_and_retries_the_connect_because_the_listener_opens_late(self):
        code = c_code(self.DIRECTORY / "src" / "test_management.c")
        self.assertIn("zsock_poll(", code)
        self.assertIn("CONNECT_ATTEMPTS", code)
        self.assertIn("k_msleep(", code)

    def test_the_source_names_the_limit_of_the_simulator_run(self):
        text = " ".join(self.source().replace("*", " ").split())
        for needle in ("fake entropy", "handshake time", "stack use", "heap peaks", "no browser",
                       "a successful login", "192.168.77.2", "the first account", "the libc"):
            self.assertIn(needle, text, needle)

    def test_the_source_uses_no_private_wording_and_logs_no_secret(self):
        text = self.source()
        self.assertNotRegex(text, r"(?i)\b(claude|assistant|llm)\b|work package|/Users/")
        code = c_code(self.DIRECTORY / "src" / "test_management.c")
        for line in code.splitlines():
            if "TC_PRINT" in line or "printk" in line:
                self.assertNotRegex(line, r"password|private|der\b|key", line)

    def test_the_scenario_files_carry_no_machine_path_or_secret(self):
        for path in self.DIRECTORY.rglob("*"):
            if path.is_file():
                text = path.read_text()
                self.assertNotRegex(text, r"/Users/|/home/|/private/|-----BEGIN", str(path))


@ci_map.needs_tomllib
class ManagementWorkflows(unittest.TestCase):
    """The management job and the budget row. They are the only places that switch the Mbed TLS group on, in
    their own runner and after the project list was checked, never in west.yml.

    The management job of ci.yml prepares its workspace with scripts/ci/prepare-job.sh and runs the
    checks of the job management of scripts/ci/checks.toml; STEPS names each step's check."""

    BOARD = "mimxrt1060_evk@B//qspi"
    GROUP_ON = "west config --local manifest.group-filter -- +crux-secure-management"
    STEPS = {
        "Mbed-only check, default workspace": "management-mbed-default",
        "Mbed-only check, group on": "management-mbed-group-on",
        "Fetch the Mbed TLS modules and nothing else": "management-mbed-fetch",
        "Install the Zephyr SDK": "management-sdk",
        "Run the management scenario on native_sim": "management-native-sim",
        "Check that the scenario ran and was not skipped": "management-native-sim-report",
        "Cross-build management with the baseline gate required": "management-build",
        "Check the outputs exist": "management-outputs",
        "Check the resolved management configuration and devicetree": "management-config",
        "Check what the image links": "management-symbols",
    }

    def ci(self):
        return yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())

    def budget(self):
        return yaml.safe_load((ROOT / ".github" / "workflows" / "budget.yml").read_text())

    def job(self):
        return self.ci()["jobs"]["management"]

    def step_names(self):
        """The workspace fetch of scripts/ci/prepare-job.sh, then the checks, in run order."""
        names = {check_id: name for name, check_id in self.STEPS.items()}
        return ["Fetch the default workspace"] + [names[i] for i in ci_map.ids("management")]

    def step(self, name):
        if name == "Fetch the default workspace":
            return {"name": name, "run": ci_map.prepare_branch("management")}
        return {"name": name, "run": ci_map.run(self.STEPS[name])}

    def commands(self):
        return ci_map.prepare_branch("management") + "\n" + ci_map.commands("management")

    def test_ci_has_a_management_job_named_for_the_step_build_jobs_and_asking_for_no_permission(self):
        job = self.job()
        self.assertRegex(job["name"], r"^management build \(")
        self.assertEqual(self.BOARD, ci_map.job_env("management")["BOARD"])
        self.assertEqual("ubuntu-24.04", job["runs-on"])
        self.assertNotIn("permissions", job)
        self.assertEqual({"contents": "read"}, self.ci()["permissions"])

    def test_the_job_has_the_same_shape_as_the_workload_job_where_both_fetch_and_install(self):
        jobs = self.ci()["jobs"]
        for key in ("runs-on",):
            self.assertEqual(jobs["workload"][key], jobs["management"][key])
        self.assertEqual(jobs["workload"]["env"], jobs["management"]["env"])
        host_packages = next(s for s in jobs["management"]["steps"] if s.get("name") == "Install host packages")
        workload_packages = next(s for s in jobs["workload"]["steps"] if s.get("name") == "Install host packages")
        self.assertEqual(workload_packages["run"], host_packages["run"])

    def test_the_steps_run_in_the_order_that_keeps_the_group_off_until_it_was_checked(self):
        names = self.step_names()
        order = [
            "Fetch the default workspace",
            "Mbed-only check, default workspace",
            "Mbed-only check, group on",
            "Fetch the Mbed TLS modules and nothing else",
            "Install the Zephyr SDK",
            "Run the management scenario on native_sim",
            "Check that the scenario ran and was not skipped",
            "Cross-build management with the baseline gate required",
            "Check the outputs exist",
            "Check the resolved management configuration and devicetree",
            "Check what the image links",
        ]
        positions = [names.index(name) for name in order]
        self.assertEqual(sorted(positions), positions)
        # The runner restores the SDK cache and prepares the workspace before the checks run.
        steps = [step.get("name", step.get("uses", "")) for step in self.job()["steps"]]
        self.assertLess(steps.index("Restore the Zephyr SDK"), steps.index("Prepare the workspace"))
        self.assertLess(steps.index("Prepare the workspace"), steps.index("Run the checks of this tier"))

    def test_the_default_update_comes_first_and_the_group_is_switched_on_after_the_project_list_check(self):
        default = self.step("Fetch the default workspace")["run"]
        self.assertIn("west init -l crux-controller", default)
        self.assertEqual(1, default.count("west update"))
        self.assertNotIn("group-filter", default)
        listing = self.step("Mbed-only check, group on")["run"]
        self.assertIn(self.GROUP_ON, listing)
        self.assertIn("check_mbed_only.py --mode mbed --baseline list-default.txt < list-mbed.txt", listing)
        self.assertNotIn("west update", listing)
        fetch = self.step("Fetch the Mbed TLS modules and nothing else")["run"]
        self.assertIn("west update", fetch)
        self.assertNotIn("group-filter", fetch)

    def test_the_fetch_asserts_that_no_wolf_project_and_both_mbed_projects_are_there(self):
        fetch = self.step("Fetch the Mbed TLS modules and nothing else")["run"]
        for name in ("wolfssl", "wolfssh", "wolfpsa"):
            self.assertIn(name, fetch)
        self.assertRegex(fetch, r'test ! -e "modules/crypto/\$name"')
        for name in ("mbedtls", "tf-psa-crypto"):
            self.assertIn(name, fetch)
        self.assertRegex(fetch, r'test -d "modules/crypto/\$name"')
        for requirements in ("requirements-base.txt", "requirements-build-test.txt",
                             "requirements-run-test.txt"):
            self.assertIn(requirements, fetch)

    def test_the_group_is_switched_on_in_exactly_the_pins_job_the_management_job_and_the_budget_step(self):
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            self.assertNotIn("+crux-secure-management", path.read_text(), path.name)
        self.assertNotIn("+crux-secure-management", ci_map.PREPARE.read_text())
        self.assertNotIn("+crux-secure-management", ci_map.BUDGET.read_text())
        for name in ci_map.data()["jobs"]:
            text = ci_map.commands(name)
            self.assertEqual(name in ("pins", "management", "budget-management", "base", "budget-base"),
                             "+crux-secure-management" in text, name)
        manifest = (ROOT / "west.yml").read_text()
        self.assertNotIn("group-filter", manifest)

    def test_the_scenario_runs_from_the_sibling_directory_and_the_workload_job_is_unchanged(self):
        run = self.step("Run the management scenario on native_sim")["run"]
        self.assertIn("west twister -p native_sim/native/64 -T crux-controller/tests/native_sim_mbed", run)
        self.assertIn("-O twister-out-management", run)
        workload = ci_map.commands("workload")
        self.assertIn("-T crux-controller/tests/native_sim \\\n", workload)
        self.assertNotIn("native_sim_mbed", workload)

    def test_a_skipped_or_missing_case_fails_the_job(self):
        run = self.step("Check that the scenario ran and was not skipped")["run"]
        self.assertIn("twister-out-management/twister.json", run)
        self.assertIn("assert statuses and all(status == \"passed\"", run)
        # The scenario has ten cases, and a report with another count is a different scenario.
        self.assertIn("assert len(statuses) == 10, statuses", run)
        self.assertIn("controller.management.native_sim.https_management", run)

    def test_the_board_image_is_built_with_the_gate_the_management_fragments_and_both_overlays(self):
        build = self.step("Cross-build management with the baseline gate required")["run"]
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", build)
        self.assertIn("conf/workload.conf;conf/net.conf;conf/management.conf", build)
        self.assertIn("boards/net.overlay;boards/management.overlay", build)
        self.assertIn("build/management", build)
        self.assertIn('-p always -b "$BOARD"', build)

    def test_the_job_checks_the_options_that_must_be_on_in_what_the_build_resolved(self):
        run = self.step("Check the resolved management configuration and devicetree")["run"]
        for option in (
            "CONFIG_CRUX_CONTROLLER_MANAGEMENT=y", "CONFIG_CRUX_CONTROLLER_NET=y", "CONFIG_CRUX_CONTROLLER_WORKLOAD=y",
            "CONFIG_CRUX_PSA_THREADING=y", "CONFIG_PSA_CRYPTO_PROVIDER_MBEDTLS=y", "CONFIG_MBEDTLS=y",
            "CONFIG_CRUX_ACCESS=y", "CONFIG_CRUX_CONFIG_SERVICE=y", "CONFIG_CRUX_MGMT_STATUS=y",
            "CONFIG_CRUX_TLS_CERTIFICATE=y", "CONFIG_CRUX_WEB=y", "CONFIG_CRUX_WEB_SESSION=y",
            "CONFIG_CRUX_WEB_MANAGEMENT=y", "CONFIG_CRUX_SYSTEM=y", "CONFIG_CRUX_NETIF=y",
            "CONFIG_CRUX_FILE_FATFS_RT1060_RAM_DISK=y", "CONFIG_DISK_DRIVER_RAM=y",
            "CONFIG_FILE_SYSTEM_MKFS=y", "CONFIG_ENTROPY_MCUX_TRNG=y",
            "CONFIG_MBEDTLS_PSA_DRIVER_GET_ENTROPY=y", "CONFIG_CRUX_WEB_PORT=443",
            'CONFIG_CRUX_WEB_BIND_ADDRESS="192.168.77.2"',
            "CONFIG_CRUX_WEB_SESSION_WORKER_PRIORITY=11",
            "CONFIG_CRUX_WEB_MANAGEMENT_WORKER_PRIORITY=11",
            "CONFIG_CRUX_SECURITY_EVENT_DRAIN_PRIORITY=11", "CONFIG_HTTP_SERVER_MAX_CLIENTS=3",
            "CONFIG_MBEDTLS_HEAP_SIZE=120000", "CONFIG_CRUX_THREAD=y", "CONFIG_CRUX_SYNC=y",
        ):
            self.assertIn(option, run, option)

    def test_the_job_checks_the_options_that_must_be_off_in_what_the_build_resolved(self):
        run = self.step("Check the resolved management configuration and devicetree")["run"]
        for option in (
            "CONFIG_CRUX_REBOOT=y", "CONFIG_CRUX_NETWORK_SETTINGS=y", "CONFIG_CRUX_FILE_SERVICE=y",
            "CONFIG_CRUX_SSH=y", "CONFIG_CRUX_CLI=y", "CONFIG_CRUX_CLI_CONSOLE=y",
            "CONFIG_CRUX_WEB_PLAIN_HTTP_FOR_TESTS=y", "CONFIG_CRUX_DEVELOPMENT_IMAGE=y",
            "CONFIG_CRUX_CONTROLLER_FILE=y", "CONFIG_CRUX_CONTROLLER_SYSTEM=y",
            "CONFIG_CRUX_SERIAL=y", "CONFIG_SHELL=y", "CONFIG_DISK_DRIVER_SDMMC=y", "CONFIG_IMX_USDHC=y",
            "CONFIG_FS_FATFS_MOUNT_MKFS=y", "CONFIG_TEST_RANDOM_GENERATOR=y",
            "CONFIG_FAKE_ENTROPY_NATIVE_SIM=y", "CONFIG_CRUX_CONFIGURATION_SETTINGS_FILE=y",
            "CONFIG_TASK_WDT_HW_FALLBACK=y", "CONFIG_WDT_SHELL=y", "CONFIG_HWINFO_SHELL=y",
        ):
            self.assertIn(option, run, option)
        self.assertIn("'^CONFIG_WOLF'", run)
        # Crux no longer has a Queue provider, so the job does not name its symbol.
        self.assertNotIn("CONFIG_CRUX_QUEUE", run)
        # The sentence that explains why Thread and Sync are on and nothing of the product names them.
        self.assertIn("The product's sources include neither", " ".join(run.replace("#", " ").split()))

    def test_the_job_checks_the_devicetree_for_the_watchdog_alias_the_ram_disk_and_the_entry(self):
        run = self.step("Check the resolved management configuration and devicetree")["run"]
        for needle in ("crux-watchdog0 = &?wdog0", "zephyr,ram-disk", "controller_storage", "zephyr.dts"):
            self.assertIn(needle, run, needle)

    def test_the_job_checks_what_the_image_links_and_what_it_does_not(self):
        run = self.step("Check what the image links")["run"]
        for symbol in ("management_port_start", "management_address_parse", "storage_port_bind_store",
                       "crux_web_start", "crux_tls_certificate_start",
                       "crux_tls_certificate_material_take", "tls_credential_add",
                       "crux_access_init", "crux_credential_start", "crux_security_event_start",
                       "crux_config_service_start", "crux_mgmt_status_start", "crux_web_session_init",
                       "crux_web_management_init", "crux_file_zephyr_bind_root",
                       "crux_system_reset_cause_get"):
            self.assertIn(symbol, run, symbol)
        for symbol in ("crux_reboot_start", "crux_network_settings_start", "crux_file_service_start"):
            self.assertIn(symbol, run, symbol)
        self.assertRegex(run, r"! grep -qE \" \[Tt\] \$\{symbol\}\$\" symbols\.txt")
        self.assertIn("arm-zephyr-eabi-nm", run)

    def test_the_job_runs_no_hardware_command_uploads_nothing_and_says_nothing_ran_on_a_board(self):
        commands = self.commands()
        for word in ("west flash", "west debug", "JLink", "pyocd", "openocd", "upload-artifact"):
            self.assertNotIn(word, commands, word)
        for step in self.job()["steps"]:
            self.assertNotIn("upload-artifact", step.get("uses", ""))
        self.assertIn("No flash, reset or hardware command was run.", commands)

    def test_every_west_build_of_the_job_carries_the_gate(self):
        for step in [*self.job()["steps"], *ci_map.checks("management")]:
            run = step.get("run", "")
            if "west build" in run:
                self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", run)

    def test_the_pins_job_comment_no_longer_says_that_no_job_fetches_with_the_group_on(self):
        self.assertNotIn("no job fetches or builds with", (ROOT / ".github" / "workflows" / "ci.yml").read_text())
        # The comment sits above the Mbed-only checks of the pins job in the CI map file.
        text = ci_map.MAP.read_text()
        self.assertNotIn("no job fetches or builds with", text)
        words = " ".join(text.replace("#", " ").split())
        self.assertIn("This job fetches nothing with the group on. The management job does, after the same check.", words)

    ROWS = {
        "minimal": {"config": "minimal", "conf": "", "overlay": "", "require": ""},
        "workload": {"config": "workload", "conf": "conf/workload.conf", "overlay": "", "require": ""},
        "net": {"config": "net", "conf": "conf/workload.conf;conf/net.conf", "overlay": "boards/net.overlay",
               "require": ""},
        "file": {"config": "file", "conf": "conf/workload.conf;conf/file.conf", "overlay": "boards/file.overlay",
               "require": "CONFIG_CRUX_CONTROLLER_FILE=y CONFIG_CRUX_FILE_FATFS_RT1060=y"},
        "system": {"config": "system", "conf": "conf/workload.conf;conf/system.conf", "overlay": "boards/system.overlay",
               "require": "CONFIG_CRUX_CONTROLLER_SYSTEM=y CONFIG_CRUX_SYSTEM=y"},
        "sntp": {"config": "sntp", "conf": "conf/workload.conf;conf/net.conf;conf/sntp.conf",
               "overlay": "boards/net.overlay",
               "require": "CONFIG_CRUX_CONTROLLER_SNTP=y CONFIG_CRUX_CONTROLLER_NET=y CONFIG_SNTP=y"},
    }

    def rows(self):
        return ci_map.budget_rows()

    def test_the_budget_rows_of_base_to_sntp_are_byte_identical_to_the_rows_before_the_step(self):
        rows = self.rows()
        self.assertEqual(["minimal", "workload", "net", "file", "system", "sntp", "management", "base"], list(rows))
        self.assertEqual(list(rows), self.budget()["jobs"]["budget"]["strategy"]["matrix"]["config"])
        for step, expected in self.ROWS.items():
            self.assertEqual(expected, rows[step], step)

    def test_the_management_row_is_built_on_the_network_with_the_group_and_requires_the_step(self):
        row = self.rows()["management"]
        self.assertEqual("conf/workload.conf;conf/net.conf;conf/management.conf", row["conf"])
        self.assertEqual("boards/net.overlay;boards/management.overlay", row["overlay"])
        self.assertEqual("mbed", row["group"])
        for option in ("CONFIG_CRUX_CONTROLLER_MANAGEMENT=y", "CONFIG_CRUX_ACCESS=y",
                       "CONFIG_CRUX_PSA_THREADING=y", "CONFIG_CRUX_WEB_MANAGEMENT=y"):
            self.assertIn(option, row["require"].split(), option)

    def test_only_the_management_row_names_a_group(self):
        # The base image runs web management on the same Mbed TLS profile.
        for step, row in self.rows().items():
            self.assertEqual(step in ("management", "base"), "group" in row, step)

    def test_the_budget_step_for_the_group_runs_only_for_the_rows_that_ask_and_before_the_sdk(self):
        # Only the job budget-management has the check, after scripts/ci/prepare-job.sh fetched the
        # workspace (fetch_workspace) and before the check that installs the SDK.
        names = ci_map.ids("budget-management")
        name = "budget-management-mbed"
        self.assertEqual(0, names.index(name))
        self.assertIn("fetch_workspace", ci_map.prepare_branch("budget-management"))
        self.assertLess(names.index(name), names.index("budget-management-sdk"))
        run = ci_map.run(name)
        self.assertLess(run.index("check_mbed_only.py --mode mbed --baseline list-default.txt"),
                        run.index("west update"))
        self.assertLess(run.index("--mode default"), run.index(self.GROUP_ON))
        self.assertLess(run.index(self.GROUP_ON), run.index("--mode mbed"))
        for wolf in ("wolfssl", "wolfssh", "wolfpsa"):
            self.assertIn(wolf, run)
        # The Budget row of the base image has the same check, in the same place.
        names = ci_map.ids("budget-base")
        self.assertEqual(0, names.index("budget-base-mbed"))
        self.assertIn("fetch_workspace", ci_map.prepare_branch("budget-base"))
        self.assertLess(names.index("budget-base-mbed"), names.index("budget-base-sdk"))
        self.assertEqual(run, ci_map.run("budget-base-mbed"))
        for job in ci_map.data()["jobs"]:
            if job.startswith("budget-") and job not in ("budget-management", "budget-base"):
                self.assertNotIn("+crux-secure-management", ci_map.commands(job), job)

    def test_the_budget_workflow_only_gained_lines(self):
        text = (ROOT / ".github" / "workflows" / "budget.yml").read_text()
        # The Budget script reads the same row values, which the management job env supplies.
        script = ci_map.BUDGET.read_text()
        for key in ("$CONF", "$OVERLAY", "$REQUIRE", "$CONFIG"):
            self.assertIn(key, script, key)
        for key in ("CONFIG", "CONF", "OVERLAY", "REQUIRE"):
            self.assertIn(key, ci_map.job_env("budget-management"), key)
        self.assertIn("matrix.config", text)
        self.assertNotIn("upload-artifact", text)
        self.assertNotIn("permissions: write", text)
        self.assertEqual({"contents": "read"}, self.budget()["permissions"])


class ManagementContributing(unittest.TestCase):
    """The contribution guide says what CI does for the management capability, and no more."""

    def text(self):
        return " ".join((ROOT / "CONTRIBUTING.md").read_text().split())

    def test_the_role_section_lists_the_steps_built_in_ci_up_to_management_and_still_claims_no_board_run(self):
        text = self.text()
        self.assertIn("`file`, `system`, `sntp`, `management` and `base` are built in CI.", text)
        self.assertIn("Only the `net` image has run on a board (twice, on one bench;", text)
        self.assertIn("and a change must not claim otherwise", text)

    def test_the_job_list_names_the_management_build_and_what_it_fetches(self):
        text = self.text()
        self.assertIn("`management build` (Twister on `native_sim` for the scenario in `tests/native_sim_mbed`, then the RT1060-EVKB build; it fetches the Mbed TLS modules, with the group switched on in its own runner)", text)
        self.assertIn("`Budget` for `minimal` to `base`: static resource use against `budgets/limits.json` (the `management` and `base` rows fetch the Mbed TLS modules in their own runners)", text)

    def test_the_optional_group_sentence_names_the_two_places_that_switch_it_on_and_the_check(self):
        text = self.text()
        self.assertIn("The optional groups of the Crux manifest stay off in `west.yml` and in every job except `management build`, `base build` and the `Budget` rows of `management` and `base`.", text)
        self.assertIn("only after `scripts/check_mbed_only.py` has checked the resolved project list", text)
        self.assertIn("The other projects of that group are not under the Apache-2.0 terms of this repository, and the narrowed import in `west.yml` keeps them out.", text)
        self.assertNotIn("The optional groups of the Crux manifest stay off, `crux-secure-management` among them", text)

    def test_the_boundary_sentence_names_the_two_files_of_the_management_directory(self):
        text = self.text()
        self.assertIn("`app/CMakeLists.txt`, `framework/management/management.cmake` and `framework/management/entropy.cmake` are checked for that", text)

    def test_the_guide_claims_no_login_and_no_board_run_for_management(self):
        text = self.text()
        self.assertNotRegex(text, r"management[^.]*(?:ran on a board|log in works|login works)")


class ManagementStepNote(unittest.TestCase):
    """The note of the step itself. It claims no CI result and says which results are open."""

    NOTE = ROOT / "docs" / "findings" / "s6-https-management.md"
    # The note records its results at the pin it was written at; the manifest has moved on since.
    NOTE_PIN = "8e3737d25d048b14a00c01da00494f58a62958c6"
    PIN = "05a50475653becf7e4867686f4f88747173e1c21"

    def text(self):
        return self.NOTE.read_text()

    def words(self):
        return " ".join(self.text().split())

    def test_the_note_exists_and_uses_its_labels(self):
        for label in ("**Verified**", "**Inferred**", "**Open**", "**Recorded**"):
            self.assertIn(label, self.text())

    # Approved behaviour change: CI ran at bb3ffefd and the results were read from the job logs, so the
    # sentence that nothing in the note is a CI result is replaced by the recorded results. The
    # board claim stays.
    def test_the_note_records_the_ci_results_at_the_reviewed_head_and_who_read_them(self):
        text = self.words()
        self.assertIn("bb3ffefd", text)
        self.assertIn("read from the GitHub job logs at that revision", text)
        self.assertIn("all 21 checks passed", text)
        self.assertIn("10 of 10 cases", text)
        self.assertIn("288872", text)
        self.assertIn("1265012", text)
        self.assertIn("S0 to S5 are identical to main", text)
        self.assertIn("the baseline gate", text)

    # Approved behaviour change: the sentence about who ran or read CI described how the work was
    # organised and meant nothing to a reader. The note keeps what it showed: the results are read from
    # the job logs, Zephyr builds happen in CI only, and nothing has run on a board.
    def test_the_note_claims_no_board_run_and_says_where_zephyr_builds_happen(self):
        text = self.words()
        self.assertIn(self.NOTE_PIN, text)
        self.assertIn("Nothing has run on a board", text)
        self.assertNotIn("the author of this change", text)
        self.assertIn("Zephyr builds and Twister runs happen in CI only", text)
        self.assertIn("the first build of this chain from outside `crux-pilot`", text)

    def test_the_note_records_that_the_revised_case_4_ran_in_ci_and_no_longer_calls_it_unrun(self):
        text = self.words()
        self.assertIn("The revised case ran at `fa11293` and passed", text)
        self.assertNotIn("the revised case 4, which has not run", text)
        self.assertNotIn("the case itself runs in the next CI run", text)

    def test_the_note_says_that_a_client_side_refusal_cannot_be_fully_excluded_in_process(self):
        text = self.words()
        self.assertIn("a refusal on the client side cannot be fully excluded in one process", text)
        self.assertIn("docs/https-composition.md", text)
        self.assertIn("openssl s_client", text)
        self.assertIn("positive control", text)

    def test_the_note_says_the_permission_check_became_a_start_time_refusal(self):
        text = self.words()
        self.assertIn("start-time refusal", text)
        self.assertIn("host test", text)

    def test_the_note_says_that_no_zephyr_build_ran_while_the_step_was_written(self):
        text = self.words()
        self.assertIn("no Zephyr build ran while the step was written", text)
        self.assertIn("syntax-only compile", text)
        self.assertIn("that is not a Zephyr build", text)

    def test_every_open_question_and_every_recorded_result_names_the_job(self):
        cells = lambda line: [c.strip() for c in line.split("|")]
        rows = [line for line in self.text().splitlines() if line.startswith("|")
                and len(cells(line)) > 3 and cells(line)[2].startswith(("**Open**", "**Recorded**"))]
        # The table of CI results has eight rows since the results were recorded; it had ten open ones.
        self.assertGreaterEqual(len(rows), 8)
        for row in rows:
            self.assertRegex(row, r"`(?:S6 build|Budget S[0-6]?[^`]*)`", row)
        self.assertGreaterEqual(sum(1 for r in rows if cells(r)[2].startswith("**Recorded**")), 6)

    def test_every_verified_row_of_the_work_table_names_a_file(self):
        rows = [line for line in self.text().splitlines()
                if line.startswith("|") and "**Verified**" in line and "8e3737d2" in line]
        self.assertGreaterEqual(len(rows), 6)
        for row in rows:
            source = [cell for cell in row.split("|") if cell.strip()][-1]
            self.assertRegex(source, r"`[A-Za-z0-9_./-]*[/.][A-Za-z0-9_./-]*`", row)

    def test_the_note_names_each_decision_test_and_the_test_exists(self):
        text = self.text()
        # The note names the classes by their step id (S6...); the class names carry the build
        # configuration name instead, as the mapping in docs/findings/README.md says.
        names = set(re.findall(r"`(S6[A-Za-z]+)(?:\.(test_[a-z0-9_]+))?`", text))
        self.assertGreaterEqual(len(names), 5)
        module = (ROOT / "tests" / "tooling" / "test_management.py").read_text()
        for old, method in names:
            cls = "Management" + old[len("S6"):]
            self.assertIn(f"class {cls}(", module, cls)
            if method:
                self.assertIn(f"def {method}(", module, method)

    def test_the_note_records_the_gaps_the_limit_and_the_wording_it_changed(self):
        text = self.words()
        for needle in ("tests/zephyr/entropy_boot", "no private include workaround", "<crux/cli_zephyr.h>",
                       "2,000 ms", "select them for themselves", "no request has been filed",
                       "docs/architecture.md"):
            self.assertIn(needle.lower(), text.lower(), needle)

    def test_the_note_lists_what_the_scenario_cannot_show_and_what_is_not_verified(self):
        text = self.words()
        for needle in ("a successful login", "handshake time", "stack use", "heap peaks", "the strength of any key",
                       "the page in a browser", "Ethernet", "anything on a board", "the first account",
                       "Timing:", "Entropy:", "Every Open row"):
            self.assertIn(needle, text, needle)

    def test_the_note_uses_no_shorthand_or_private_wording_and_qualifies_issue_references(self):
        text = self.text()
        self.assertNotRegex(text, r"\b[OB][1-9]\b")
        self.assertNotRegex(text, r"(?i)\b(claude|assistant|chatgpt|llm|agent)\b")
        self.assertNotRegex(text, r"(?i)work package|skeleton plan|\b(?:OD|WD)[0-9]+\b")
        self.assertNotRegex(text, r"/Users/|/home/|/private/|/tmp/|[A-Z]:\\")
        for number, line in enumerate(text.splitlines(), 1):
            for match in re.finditer(r"#[0-9]+", line):
                self.assertRegex(line[: match.start()], r"wonny-labs/crux-(?:pilot|controller)$",
                                 f"{number}: {line.strip()}")

    def test_the_readme_the_changelog_and_the_roadmap_point_at_the_note(self):
        # Approved behaviour change: the README links the findings index, which lists the note.
        for name in ("docs/findings/README.md", "CHANGELOG.md", "docs/roadmap.md"):
            self.assertIn("s6-https-management.md", (ROOT / name).read_text(), name)
        self.assertIn("docs/README.md", (ROOT / "README.md").read_text())
        changelog = " ".join((ROOT / "CHANGELOG.md").read_text().split())
        self.assertIn("No firmware image of S0 to S5 changes.", changelog)
        self.assertIn("built and never run on a board", changelog)

    def test_the_documents_that_listed_the_steps_list_management(self):
        for name in ("README.md", "docs/glossary.md", "docs/architecture.md", "docs/roadmap.md"):
            text = (ROOT / name).read_text()
            self.assertRegex(text, r"`management`", name)
        glossary = " ".join((ROOT / "docs" / "glossary.md").read_text().split())
        self.assertIn("builds one image, `minimal` to `base`", glossary)
        roadmap = " ".join((ROOT / "docs" / "roadmap.md").read_text().split())
        self.assertIn("Eight build configurations, `minimal` to `base`, are on `main`", roadmap)
        self.assertNotIn("Six", roadmap)
        self.assertNotIn("Seven", roadmap)

    def test_the_documents_no_longer_say_that_no_step_selects_thread_and_sync_or_that_no_web_source_exists(self):
        zone = " ".join((ROOT / "docs" / "composition-zone.md").read_text().split())
        self.assertNotIn("no source there does so yet", zone)
        self.assertNotIn("A composition source that uses them is a separate change", zone)
        architecture = " ".join((ROOT / "docs" / "architecture.md").read_text().split())
        self.assertNotIn("Thread, Sync, Queue and Serial are not used.", architecture)
        self.assertIn("select them for themselves", architecture)

    def test_the_manifest_comment_says_who_switches_the_group_on_and_the_group_stays_off(self):
        manifest = (ROOT / "west.yml").read_text()
        words = " ".join(manifest.replace("#", " ").split())
        self.assertIn("only the management build job and the Budget row of management switch the group on", words)
        self.assertNotIn("no job enables the group or fetches with it on", words)
        self.assertNotIn("group-filter", "\n".join(l for l in manifest.splitlines() if not l.strip().startswith("#")))

    def test_west_yml_changed_in_comments_only(self):
        data = yaml.safe_load((ROOT / "west.yml").read_text())["manifest"]
        crux = next(p for p in data["projects"] if p["name"] == "crux-pilot")
        self.assertEqual(self.PIN, crux["revision"])
        self.assertEqual({"name-blocklist": ["wolfssl", "wolfssh", "wolfpsa"]}, crux["import"])
        self.assertEqual(["crux-pilot", "picolibc"], [p["name"] for p in data["projects"]])


class ManagementFindings(unittest.TestCase):
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
        # The note names the class by its step id; the class carries the configuration name.
        self.assertIn("S6NotBuilt", text)
        self.assertIn("class ManagementNotBuilt(", (ROOT / "tests" / "tooling" / "test_management.py").read_text())
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

    # Approved behaviour change: management exists, so the README has its row and the roadmap its board
    # column. The groundwork note is kept as recorded and still says that S6 was not a step when it was
    # written.
    def test_the_readme_presents_management_and_the_groundwork_note_keeps_its_record(self):
        readme = (ROOT / "README.md").read_text()
        self.assertRegex(readme, r"(?m)^\|[^|\n]*HTTPS[^|\n]*\|\s*`management`\s*\|")
        roadmap = (ROOT / "docs" / "roadmap.md").read_text()
        row = re.search(r"^\|\s*`management`\s*\|.*$", roadmap, re.M)
        self.assertIsNotNone(row)
        self.assertTrue(row.group(0).rstrip().endswith("| not run |"), row.group(0))
        self.assertIn("not a step", self.words())

    def test_the_changelog_records_the_groundwork_and_that_no_image_changes(self):
        text = " ".join((ROOT / "CHANGELOG.md").read_text().split())
        self.assertIn("S6", text)
        self.assertIn("s6-https-management-gaps.md", text)
        self.assertIn("no firmware image", text)


if __name__ == "__main__":
    unittest.main()
