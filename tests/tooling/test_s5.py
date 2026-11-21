# SPDX-License-Identifier: Apache-2.0
"""Checks of step S5 (time synchronisation over SNTP): its limits, policy, configuration, build
files, sources, adapter, CI jobs, scenario and findings. Written test first, one slice at a time."""

import json
import pathlib
import re
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "budgets"))
sys.path.insert(0, str(ROOT / "scripts"))

import check  # noqa: E402
import check_boundary  # noqa: E402
import fake_crux  # noqa: E402

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
        # Step S6 later added its own row, which test_s6.py pins.
        self.assertEqual(["S0", "S1", "S2", "S3", "S4", "S5", "S6"], sorted(rows))
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


class S5Configuration(unittest.TestCase):
    CONF = ROOT / "app" / "conf" / "s5.conf"
    SYMBOLS = {
        # symbol: (type, default, range)
        "CRUX_CONTROLLER_TIME_SERVER": ("string", '"192.168.77.1"', None),
        "CRUX_CONTROLLER_TIME_INTERVAL_S": ("int", "600", (16, 86400)),
        "CRUX_CONTROLLER_TIME_TIMEOUT_MS": ("int", "3000", (100, 30000)),
        "CRUX_CONTROLLER_TIME_STALE_AGE_S": ("int", "1800", (60, 604800)),
        "CRUX_CONTROLLER_TIME_THRESHOLD_MS": ("int", "100", (1, 10000)),
        "CRUX_CONTROLLER_TIME_MAX_STEP_MS": ("int", "1000", (1, 3600000)),
        "CRUX_CONTROLLER_TIME_STACK": ("int", "8192", (2048, 65536)),
    }

    def test_the_fragment_selects_the_step_and_the_sntp_library(self):
        options = conf_options(self.CONF)
        self.assertEqual("y", options.get("CONFIG_CRUX_CONTROLLER_S5"))
        self.assertEqual("y", options.get("CONFIG_SNTP"))

    def test_the_fragment_adds_no_network_the_step_two_fragment_does_not_have_and_no_crux_symbol(self):
        for name in conf_options(self.CONF):
            for forbidden in ("CRUX_THREAD", "CRUX_SYNC", "CRUX_QUEUE", "CRUX_SERIAL", "SECURE",
                              "RELIANCE", "CRUX_MGMT", "CRUX_WEB", "SSH", "TLS", "CRUX_FILE",
                              "DNS_RESOLVER", "CRUX_TIME_RTC", "RTC"):
                self.assertNotIn(forbidden, name.upper(), name)
        self.assertNotIn("CONFIG_CRUX_SOCKETS", conf_options(self.CONF))

    def test_the_fragment_does_not_set_the_values_of_the_options_it_leaves_at_their_default(self):
        for name in conf_options(self.CONF):
            self.assertFalse(name.startswith("CONFIG_CRUX_CONTROLLER_TIME_"), name)

    def test_the_step_option_builds_on_the_network_step_and_crux_time(self):
        block = kconfig_block("CRUX_CONTROLLER_S5")
        self.assertIn("bool", block)
        self.assertRegex(block, r"depends on CRUX_CONTROLLER_S2 && CRUX_TIME && SNTP\b")
        for native in ("NET_UDP", "NET_IPV4"):
            self.assertRegex(block, rf"&& {native}\b", native)

    def test_the_step_option_selects_nothing(self):
        self.assertNotRegex(kconfig_block("CRUX_CONTROLLER_S5"), r"^\s*select\b")

    def test_each_setting_has_its_documented_type_default_and_range(self):
        for name, (kind, default, bounds) in self.SYMBOLS.items():
            block = kconfig_block(name)
            self.assertRegex(block, rf"^\s*{kind}\b", name)
            self.assertRegex(block, rf"(?m)^\s*default {re.escape(default)}$", name)
            self.assertRegex(block, r"depends on CRUX_CONTROLLER_S5\b", name)
            if bounds:
                self.assertRegex(block, rf"range {bounds[0]} {bounds[1]}\b", name)
            else:
                self.assertNotIn("range", block, name)

    def test_the_help_of_the_step_option_states_the_limits_in_words(self):
        text = " ".join(kconfig_block("CRUX_CONTROLLER_S5").split())
        for needle in ("unauthenticated", "IPv4", "not persisted", "step"):
            self.assertIn(needle, text, needle)

    def test_every_setting_says_what_it_is_in_a_help_text(self):
        for name in self.SYMBOLS:
            self.assertIn("help", kconfig_block(name), name)

    def test_the_stack_setting_is_a_starting_value_that_was_not_measured(self):
        text = " ".join(kconfig_block("CRUX_CONTROLLER_TIME_STACK").split())
        self.assertIn("starting value", text)
        self.assertIn("not measured", text)

    def test_the_fragment_leaves_the_network_to_the_step_two_fragment(self):
        text = self.CONF.read_text()
        self.assertIn("conf/s1.conf;conf/s2.conf;conf/s5.conf", " ".join(text.split()))


class S5BuildFiles(unittest.TestCase):
    def text(self):
        return "\n".join(code_lines(ROOT / "app" / "CMakeLists.txt"))

    def block(self):
        match = re.search(r"if\(CONFIG_CRUX_CONTROLLER_S5\)(.*?)endif\(\)", self.text(), re.S)
        self.assertIsNotNone(match, "no if(CONFIG_CRUX_CONTROLLER_S5) block")
        return match.group(1)

    def test_the_s5_block_is_inside_the_workload_switch_after_s4(self):
        text = self.text()
        self.assertGreater(text.index("if(CONFIG_CRUX_CONTROLLER_S5)"),
                           text.index("if(CONFIG_CRUX_CONTROLLER_S4)"))
        self.assertGreater(text.index("if(CONFIG_CRUX_CONTROLLER_S5)"),
                           text.index("if(CONFIG_CRUX_CONTROLLER_S1)"))

    def test_the_block_adds_the_glue_and_the_policy_and_no_new_target_link(self):
        block = self.block()
        self.assertIn("src/time_sync.c", block)
        self.assertIn("src/time_sync_policy.c", block)
        # Crux Time and Logging are linked for every step already; the authority header is in the
        # include directory of crux::time.
        self.assertNotIn("target_link_libraries", block)

    def test_the_block_adds_no_include_path_and_no_zone_and_no_library(self):
        block = self.block()
        for word in ("include_directories", "-include", "-I", "add_subdirectory", "add_library"):
            self.assertNotIn(word, block, word)

    def test_the_application_links_time_for_every_step(self):
        self.assertRegex(self.text(), r"target_link_libraries\(app PRIVATE crux::time\)")

    def test_no_build_file_names_the_adapter_source_outside_the_zone(self):
        self.assertNotIn("time_sync_zephyr", self.text())

    def test_the_zone_adds_the_sntp_adapter_only_for_step_s5_with_the_application_warnings(self):
        text = "\n".join(code_lines(APP_OS / "CMakeLists.txt"))
        match = re.search(r"if\(CONFIG_CRUX_CONTROLLER_S5\)(.*?)endif\(\)", text, re.S)
        self.assertIsNotNone(match)
        block = match.group(1)
        self.assertRegex(
            block, r"target_sources\(app PRIVATE \$\{CMAKE_CURRENT_LIST_DIR\}/time_sync_zephyr\.c\)"
        )
        self.assertRegex(
            block,
            r"set_source_files_properties\(\$\{CMAKE_CURRENT_LIST_DIR\}/time_sync_zephyr\.c\s+"
            r"TARGET_DIRECTORY app\s+PROPERTIES COMPILE_OPTIONS \"-Wall;-Wextra;-Werror\"\)",
        )
        for word in ("include_directories", "add_library", "target_link_libraries", "crux"):
            self.assertNotIn(word, text, word)

    def test_the_zone_has_exactly_the_two_sources_and_one_build_file(self):
        names = sorted(p.name for p in APP_OS.iterdir())
        self.assertEqual(["CMakeLists.txt", "time_sync_zephyr.c", "workload_os_zephyr.c"], names)

    def test_the_workload_adapter_is_still_added_for_every_step_unconditionally(self):
        text = "\n".join(code_lines(APP_OS / "CMakeLists.txt"))
        before = text[: text.index("if(CONFIG_CRUX_CONTROLLER_S5)")]
        self.assertIn("workload_os_zephyr.c", before)


class S5Port(unittest.TestCase):
    PORT = APP_SRC / "time_sync_port.h"

    def test_the_port_includes_iso_c_and_the_policy_header_only(self):
        for name in includes(self.PORT):
            self.assertIn(name, ("<stdint.h>", "<stddef.h>", "<stdbool.h>", '"time_sync_policy.h"'), name)

    def test_the_port_declares_the_query_the_sleep_and_the_thread_start(self):
        text = c_code(self.PORT)
        for needle in (
            "time_sync_port_query(", "time_sync_port_sleep_ms(", "time_sync_port_start(",
            "TIME_SYNC_PORT_OK", "TIME_SYNC_PORT_ERROR",
        ):
            self.assertIn(needle, text, needle)

    def test_the_port_names_no_zephyr_or_sntp_or_crux_symbol(self):
        self.assertNotRegex(c_code(self.PORT), r"\bk_|\bsntp_|\bcrux_|\bCRUX_|\bCONFIG_|zephyr")


class S5Adapter(unittest.TestCase):
    ADAPTER = APP_OS / "time_sync_zephyr.c"

    def test_it_includes_the_two_zephyr_headers_of_the_zone_and_the_port_by_relative_paths(self):
        found = includes(self.ADAPTER)
        self.assertIn("<zephyr/kernel.h>", found)
        self.assertIn("<zephyr/net/sntp.h>", found)
        self.assertIn('"../src/time_sync_port.h"', found)
        self.assertIn('"../src/time_sync_policy.h"', found)

    def test_it_includes_no_socket_posix_or_crux_header(self):
        for name in includes(self.ADAPTER):
            self.assertNotIn("socket", name, name)
            self.assertNotIn("crux", name, name)
            self.assertFalse(name.startswith("<sys/") or name.startswith("<netinet") or
                             name.startswith("<arpa") or name == "<netdb.h>", name)
            self.assertTrue(
                name in ("<errno.h>", "<stdint.h>", "<stdbool.h>", "<stddef.h>", "<zephyr/kernel.h>",
                         "<zephyr/net/sntp.h>") or name.startswith('"../src/'),
                name,
            )

    def test_it_queries_through_sntp_simple_only(self):
        code = c_code(self.ADAPTER)
        self.assertEqual(1, len(re.findall(r"\bsntp_simple\(", code)))
        for forbidden in ("sntp_init", "sntp_query", "sntp_close", "sntp_recv_response",
                          "sntp_simple_addr", "sntp_init_async", "sockaddr", "zsock_"):
            self.assertNotIn(forbidden, code, forbidden)

    def test_it_maps_the_library_errors_to_the_four_results(self):
        code = c_code(self.ADAPTER)
        self.assertIn("-ETIMEDOUT", code)
        self.assertIn("-EBUSY", code)
        for name in ("TIME_SYNC_SAMPLE_OK", "TIME_SYNC_SAMPLE_TIMEOUT",
                     "TIME_SYNC_SAMPLE_KISS_OF_DEATH", "TIME_SYNC_SAMPLE_ERROR"):
            self.assertIn(name, code, name)

    def test_it_converts_the_answer_with_the_policys_function_and_never_writes_a_clock(self):
        code = c_code(self.ADAPTER)
        self.assertIn("time_sync_instant_from_sntp(", code)
        for forbidden in ("sys_clock_settime", "clock_settime", "settimeofday", "crux_realtime"):
            self.assertNotIn(forbidden, code, forbidden)

    def test_the_thread_is_low_priority_and_its_stack_comes_from_the_product_option(self):
        code = c_code(self.ADAPTER)
        self.assertRegex(code, r"#ifdef CONFIG_CRUX_CONTROLLER_TIME_STACK")
        self.assertRegex(code, r"#define TIME_SYNC_STACK_BYTES CONFIG_CRUX_CONTROLLER_TIME_STACK")
        self.assertRegex(code, r"#define TIME_SYNC_THREAD_PRIORITY 10\b")
        self.assertRegex(code, r"BUILD_ASSERT\(CONFIG_NUM_PREEMPT_PRIORITIES > TIME_SYNC_THREAD_PRIORITY")
        self.assertIn("k_thread_create", code)
        self.assertIn("K_THREAD_STACK_DEFINE", code)
        # The workload threads run at 5, so this one is later in the scheduler's order.
        self.assertIn("workload", self.ADAPTER.read_text().lower())

    def test_it_sleeps_with_the_kernel_not_with_a_busy_loop(self):
        code = c_code(self.ADAPTER)
        self.assertIn("k_sleep(", code)
        self.assertNotIn("k_busy_wait", code)

    def test_it_says_which_zephyr_revision_it_read_and_that_the_pinned_one_differs_only_in_async(self):
        text = " ".join(self.ADAPTER.read_text().split())
        self.assertIn("v4.4.0", text)
        self.assertIn("v4.4.2", text)
        self.assertIn("sntp_close_async", text)

    def test_the_adapter_zone_still_includes_nothing_outside_its_allow_list(self):
        violations = check_boundary.check(ROOT, None)
        self.assertEqual([], [v for v in violations if "time_sync" in str(v)])


class S5Sources(unittest.TestCase):
    GLUE = APP_SRC / "time_sync.c"
    HEADER = APP_SRC / "time_sync.h"
    AUTHORITY_CALLS = (
        "crux_realtime_set", "crux_realtime_set_synchronized", "crux_realtime_adopt",
        "crux_realtime_invalidate",
    )

    def test_the_glue_files_exist(self):
        self.assertTrue(self.GLUE.is_file())
        self.assertTrue(self.HEADER.is_file())

    def test_the_glue_includes_public_crux_headers_its_own_headers_and_iso_c_only(self):
        allowed = {
            "<stdbool.h>", "<stddef.h>", "<stdint.h>", "<stdio.h>", "<crux/logging.h>",
            "<crux/status.h>", "<crux/time.h>", "<crux/time_authority.h>", '"time_sync.h"',
            '"time_sync_policy.h"', '"time_sync_port.h"',
        }
        for path in (self.GLUE, self.HEADER):
            for include in includes(path):
                self.assertIn(include, allowed, f"{path.name}: {include}")
        for needed in ("<crux/time.h>", "<crux/time_authority.h>", "<crux/logging.h>"):
            self.assertIn(needed, includes(self.GLUE))

    def test_the_glue_header_declares_init_poll_and_start(self):
        header = c_code(self.HEADER)
        for needle in ("time_sync_init(void)", "time_sync_poll(void)", "time_sync_start(void)"):
            self.assertIn(needle, header, needle)

    def test_the_glue_header_includes_no_zephyr_header(self):
        self.assertFalse([n for n in includes(self.HEADER) if "zephyr" in n])

    def test_the_glue_is_the_only_caller_of_the_time_authority_in_the_image(self):
        callers = {name: [] for name in self.AUTHORITY_CALLS}
        for tree in ("app", "workload"):
            for path in sorted((ROOT / tree).rglob("*")):
                if path.suffix not in (".c", ".h"):
                    continue
                code = c_code(path)
                for name in self.AUTHORITY_CALLS:
                    if re.search(rf"\b{name}\s*\(", code):
                        callers[name].append(path.relative_to(ROOT).as_posix())
        self.assertEqual(["app/src/time_sync.c"], callers["crux_realtime_set"])
        self.assertEqual(["app/src/time_sync.c"], callers["crux_realtime_set_synchronized"])
        self.assertEqual([], callers["crux_realtime_adopt"])
        self.assertEqual([], callers["crux_realtime_invalidate"])

    def test_no_file_of_the_image_sets_the_native_clock(self):
        for tree in ("app", "workload"):
            for path in sorted((ROOT / tree).rglob("*")):
                if path.suffix not in (".c", ".h"):
                    continue
                code = c_code(path)
                for forbidden in ("sys_clock_settime", "clock_settime", "settimeofday", "stime"):
                    self.assertNotRegex(code, rf"\b{forbidden}\s*\(", f"{path.relative_to(ROOT)}: {forbidden}")

    def test_the_glue_sets_with_source_external_and_synchronised_in_one_call(self):
        code = c_code(self.GLUE)
        self.assertEqual(1, len(re.findall(r"\bcrux_realtime_set\s*\(", code)))
        self.assertRegex(code, r"crux_realtime_set\(&\w+,\s*CRUX_REALTIME_SOURCE_EXTERNAL,\s*true\)")
        self.assertEqual(1, len(re.findall(r"\bcrux_realtime_set_synchronized\s*\(\s*false\s*\)", code)))
        self.assertNotRegex(code, r"crux_realtime_set_synchronized\s*\(\s*true")
        for forbidden in ("crux_realtime_adopt", "crux_realtime_invalidate", "CRUX_REALTIME_SOURCE_MANUAL",
                          "CRUX_REALTIME_SOURCE_RTC", "CRUX_REALTIME_SOURCE_UNKNOWN"):
            self.assertNotIn(forbidden, code, forbidden)

    def test_the_glue_initialises_the_realtime_provider_once_before_it_reads_or_writes(self):
        code = c_code(self.GLUE)
        self.assertEqual(1, len(re.findall(r"\bcrux_realtime_init\s*\(", code)))
        self.assertLess(code.index("crux_realtime_init("), code.index("crux_realtime_get_snapshot("))
        self.assertLess(code.index("crux_realtime_init("), code.index("crux_realtime_set("))

    def test_the_glue_reads_one_snapshot_after_the_query_and_decides_with_the_policy(self):
        code = c_code(self.GLUE)
        poll = code[code.index("void time_sync_poll(void)"):]
        query = poll.index("time_sync_port_query(")
        snapshot = poll.index("crux_realtime_get_snapshot(")
        decide = poll.index("time_sync_decide(")
        write = poll.index("crux_realtime_set(")
        self.assertLess(query, snapshot)
        self.assertLess(snapshot, decide)
        self.assertLess(decide, write)
        self.assertEqual(1, poll.count("crux_realtime_get_snapshot("))
        self.assertNotRegex(code, r"\bcrux_realtime_now\s*\(")

    def test_the_glue_sets_only_on_the_apply_set_action(self):
        code = c_code(self.GLUE)
        poll = code[code.index("void time_sync_poll(void)"):]
        guard = poll.rindex("TIME_SYNC_APPLY_SET", 0, poll.index("crux_realtime_set("))
        self.assertLess(guard, poll.index("crux_realtime_set("))
        self.assertIn("decision.clear_synchronized", poll)

    def test_a_failed_native_write_is_reported_and_the_clock_is_left_invalid_for_a_retry(self):
        code = c_code(self.GLUE)
        for needle in ("time set failed", "time is not valid", "retry"):
            self.assertIn(needle, code, needle)
        text = " ".join((self.GLUE).read_text().split())
        self.assertIn("clears validity and synchronisation", text)

    def test_the_glue_logs_through_crux_logging_under_one_tag_with_one_writer(self):
        code = c_code(self.GLUE)
        self.assertNotRegex(code, r"\bprintk\b|\bprintf\(")
        self.assertEqual(1, len(re.findall(r"\bcrux_log_write\(", code)))
        self.assertEqual({'"time"'}, set(re.findall(r'"time"', code)))

    def test_the_policy_range_is_asserted_against_crux_time_at_build_time(self):
        code = c_code(self.GLUE)
        for pair in (
            ("TIME_SYNC_MIN_UNIX_SECONDS", "CRUX_TIME_MIN_UNIX_SECONDS"),
            ("TIME_SYNC_MAX_UNIX_SECONDS_EXCLUSIVE", "CRUX_TIME_MAX_UNIX_SECONDS_EXCLUSIVE"),
        ):
            self.assertRegex(code, rf"_Static_assert\(\s*{pair[0]}\s*==\s*{pair[1]}\b")

    def test_the_policy_result_codes_are_the_only_source_of_the_decision(self):
        code = c_code(self.GLUE)
        for needle in ("time_sync_decide(", "time_sync_decision_level(", "time_sync_action_name(",
                       "time_sync_reason_name("):
            self.assertIn(needle, code, needle)

    def test_the_glue_checks_the_settings_against_each_other_at_build_time(self):
        code = c_code(self.GLUE)
        self.assertRegex(code, r"_Static_assert\(CONFIG_CRUX_CONTROLLER_TIME_THRESHOLD_MS\s*<=\s*"
                               r"CONFIG_CRUX_CONTROLLER_TIME_MAX_STEP_MS")
        self.assertRegex(code, r"_Static_assert\(CONFIG_CRUX_CONTROLLER_TIME_STALE_AGE_S\s*>\s*"
                               r"CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S")
        self.assertRegex(code, r"_Static_assert\(\(?[^;]*CONFIG_CRUX_CONTROLLER_TIME_TIMEOUT_MS[^;]*"
                               r"CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S")

    def test_the_glue_uses_the_product_settings_and_no_literal_server(self):
        code = c_code(self.GLUE)
        for name in ("CONFIG_CRUX_CONTROLLER_TIME_SERVER", "CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S",
                     "CONFIG_CRUX_CONTROLLER_TIME_TIMEOUT_MS", "CONFIG_CRUX_CONTROLLER_TIME_STALE_AGE_S",
                     "CONFIG_CRUX_CONTROLLER_TIME_THRESHOLD_MS", "CONFIG_CRUX_CONTROLLER_TIME_MAX_STEP_MS"):
            self.assertIn(name, code, name)
        self.assertNotRegex(code, r"\d+\.\d+\.\d+\.\d+")

    def test_the_composition_starts_s5_last_before_the_workload(self):
        source = c_code(APP_SRC / "composition.c")
        self.assertIn("#ifdef CONFIG_CRUX_CONTROLLER_S5", source)
        self.assertIn('#include "time_sync.h"', source)
        start = source.index("time_sync_start()")
        run = source.index("return workload_thread_start(&config)")
        self.assertLess(source.index("workload_thread_set_sink(exchange_with_peer)"), start)
        self.assertLess(start, run)
        self.assertNotRegex(source, r"crux_realtime|sys_clock|clock_")

    def test_the_glue_and_its_header_pass_the_boundary_check_against_a_crux_that_publishes_time(self):
        # The headers come from tests/tooling/fake_crux.py, which also lists the Access and web headers
        # that the composition zone of step S6 includes, so this fixture publishes them too.
        with tempfile.TemporaryDirectory() as directory:
            crux = fake_crux.publish(directory)
            self.assertEqual([], check_boundary.check(ROOT, crux))

    def test_the_zone_allow_lists_are_unchanged_by_this_step(self):
        self.assertEqual(frozenset({"zephyr/kernel.h", "zephyr/net/sntp.h"}),
                         check_boundary.OS_ADAPTER_ZEPHYR_HEADERS)
        self.assertEqual(
            frozenset({"zephyr/fs/fs.h", "zephyr/devicetree.h", "zephyr/net/tls_credentials.h"}),
            check_boundary.COMPOSITION_ZEPHYR_HEADERS)
        self.assertEqual(["app/src", "workload", "app/compose", "app/os"],
                         [rule.directory for rule in check_boundary.RULES])

    def test_the_sntp_header_still_fails_outside_the_adapter_zone(self):
        for tree in ("app/src", "app/compose", "workload"):
            with tempfile.TemporaryDirectory() as directory:
                path = pathlib.Path(directory) / tree / "x.c"
                path.parent.mkdir(parents=True)
                path.write_text("#include <zephyr/net/sntp.h>\n")
                found = check_boundary.check(directory)
                self.assertEqual(["zephyr/net/sntp.h"], [v.include for v in found], tree)


class S5Scenario(unittest.TestCase):
    DIRECTORY = ROOT / "tests" / "native_sim" / "s5"
    CASES = (
        "first_sync", "kiss_of_death", "late_answer", "out_of_range",
        "step_refused_then_resync", "correction_and_threshold", "stale_after_silence",
    )

    def scenarios(self):
        return yaml.safe_load((self.DIRECTORY / "testcase.yaml").read_text())

    def source(self):
        return (self.DIRECTORY / "src" / "test_s5.c").read_text()

    def test_one_scenario_per_case_on_the_64_bit_simulator(self):
        data = self.scenarios()
        self.assertEqual({f"controller.s5.native_sim.{case}" for case in self.CASES}, set(data["tests"]))
        for name, test in data["tests"].items():
            case = name.rsplit(".", 1)[1]
            self.assertEqual(f"S5_CASE={case}", test["extra_args"], name)
        self.assertEqual(["native_sim/native/64"], data["common"]["platform_allow"])
        self.assertIn("s5", data["common"]["tags"])

    def test_the_scenario_builds_the_applications_own_sources_and_the_real_adapter(self):
        text = (self.DIRECTORY / "CMakeLists.txt").read_text()
        for needle in ("${controller_root}/app/src/time_sync.c",
                       "${controller_root}/app/src/time_sync_policy.c",
                       "${controller_root}/app/os/time_sync_zephyr.c", "crux::time", "crux::logging"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("add_subdirectory(${controller_root}/app/os", text)

    def test_the_scenario_gives_the_settings_it_needs_through_compile_definitions(self):
        text = " ".join((self.DIRECTORY / "CMakeLists.txt").read_text().split())
        for needle in (
            'CONFIG_CRUX_CONTROLLER_TIME_SERVER="127.0.0.1"', "CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S=1",
            "CONFIG_CRUX_CONTROLLER_TIME_TIMEOUT_MS=600", "CONFIG_CRUX_CONTROLLER_TIME_STALE_AGE_S=2",
            "CONFIG_CRUX_CONTROLLER_TIME_THRESHOLD_MS=100", "CONFIG_CRUX_CONTROLLER_TIME_MAX_STEP_MS=1000",
            "CONFIG_CRUX_CONTROLLER_TIME_STACK=8192", "S5_CASE_${S5_CASE}=1",
        ):
            self.assertIn(needle, text, needle)
        self.assertIn("FATAL_ERROR", text)

    def test_the_scenario_runs_the_real_sntp_library_over_loopback_with_crux_time_and_logging(self):
        options = conf_options(self.DIRECTORY / "prj.conf")
        for name in ("CONFIG_SNTP", "CONFIG_NET_LOOPBACK", "CONFIG_NET_UDP", "CONFIG_NET_SOCKETS",
                     "CONFIG_CRUX_TIME", "CONFIG_CRUX_LOGGING", "CONFIG_ZTEST"):
            self.assertEqual("y", options.get(name), name)
        for name in options:
            for forbidden in ("CRUX_THREAD", "CRUX_SYNC", "CRUX_QUEUE", "CRUX_TIME_TESTING",
                              "CRUX_TIME_RTC", "DNS_RESOLVER", "SNTP_UNCERTAINTY"):
                self.assertNotIn(forbidden, name, name)

    def test_the_scenario_reads_the_log_from_an_emulated_uart(self):
        text = (self.DIRECTORY / "app.overlay").read_text()
        self.assertIn('compatible = "zephyr,uart-emul"', text)
        self.assertIn("logging_test:", text)

    def test_every_case_has_a_source_section(self):
        source = self.source()
        for case in self.CASES:
            self.assertIn(f"S5_CASE_{case}", source, case)
        self.assertIn('#error "S5_CASE names no case of this test"', source)

    def test_the_responder_answers_on_port_123_of_the_loopback_address_with_a_real_packet(self):
        source = self.source()
        for needle in ("127.0.0.1", "htons(123)", "SOCK_DGRAM", "recvfrom", "sendto",
                       "2208988800", "request + 40", "reply + 24", "reply[1]"):
            self.assertIn(needle, source, needle)

    def test_the_cases_cover_every_answer_kind(self):
        source = self.source()
        for needle in ("kiss_of_death", "delay_ms", "946684799", "4102444800", "CRUX_REALTIME_SOURCE_EXTERNAL",
                       "is_synchronized", "is_valid", "crux_realtime_get_snapshot",
                       "action=apply-set reason=first-sync", "reason=kiss-of-death", "reason=timeout",
                       "action=refuse-range", "action=refuse-step", "reason=resync",
                       "reason=within-threshold", "reason=correction", "action=mark-stale"):
            self.assertIn(needle, source, needle)

    def test_the_scenario_never_sets_a_clock_itself(self):
        code = c_code(self.DIRECTORY / "src" / "test_s5.c")
        for forbidden in ("crux_realtime_set", "sys_clock_settime", "clock_settime", "crux_realtime_adopt"):
            self.assertNotIn(forbidden, code, forbidden)

    def test_the_source_names_the_limit_of_the_simulator_run(self):
        text = " ".join(re.sub(r"^\s*\*", " ", self.source(), flags=re.M).split())
        self.assertIn("a real server, a real network path and a board are not shown here", text)


class S5Workflows(unittest.TestCase):
    def ci(self):
        return yaml.safe_load((WORKFLOWS / "ci.yml").read_text())

    def commands(self, job):
        return "\n".join(step.get("run", "") for step in self.ci()["jobs"][job]["steps"])

    def budget_rows(self):
        budget = yaml.safe_load((WORKFLOWS / "budget.yml").read_text())
        return {row["step"]: row for row in budget["jobs"]["budget"]["strategy"]["matrix"]["include"]}

    def test_ci_has_an_s5_job_that_builds_the_board_image_with_the_gate_required(self):
        self.assertIn("s5", self.ci()["jobs"])
        job = self.ci()["jobs"]["s5"]
        self.assertEqual(BOARD, job["env"]["BOARD"])
        self.assertTrue(job["name"].startswith("S5 build "))
        commands = self.commands("s5")
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", commands)
        self.assertIn("conf/s1.conf;conf/s2.conf;conf/s5.conf", commands)
        self.assertIn("boards/s2.overlay", commands)
        self.assertIn("build/s5", commands)

    def test_the_s5_job_follows_the_s4_job_step_for_step_where_it_builds(self):
        jobs = self.ci()["jobs"]
        names = [step.get("name", step.get("uses", "")) for step in jobs["s5"]["steps"]]
        s4 = [step.get("name", step.get("uses", "")) for step in jobs["s4"]["steps"]]
        self.assertEqual([name.replace("S4", "S5") for name in s4][:5], names[:5])
        self.assertEqual(jobs["s4"]["runs-on"], jobs["s5"]["runs-on"])
        self.assertEqual(jobs["s4"]["env"]["SDK_VERSION"], jobs["s5"]["env"]["SDK_VERSION"])

    def test_the_s5_job_checks_what_the_build_resolved(self):
        commands = self.commands("s5")
        for needle in (
            "CONFIG_CRUX_CONTROLLER_S5=y", "CONFIG_CRUX_CONTROLLER_S2=y", "CONFIG_CRUX_CONTROLLER_S1=y",
            "CONFIG_SNTP=y", "CONFIG_CRUX_TIME=y", "CONFIG_NET_UDP=y", "CONFIG_NET_IPV4=y",
            "CONFIG_CRUX_CONTROLLER_TIME_SERVER=\"192.168.77.1\"", "CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S=600",
            "CONFIG_CRUX_CONTROLLER_TIME_TIMEOUT_MS=3000", "CONFIG_CRUX_CONTROLLER_TIME_STALE_AGE_S=1800",
            "CONFIG_CRUX_CONTROLLER_TIME_THRESHOLD_MS=100", "CONFIG_CRUX_CONTROLLER_TIME_MAX_STEP_MS=1000",
            "CONFIG_CRUX_CONTROLLER_TIME_STACK=8192", "zephyr.bin",
        ):
            self.assertIn(needle, commands, needle)

    def test_the_s5_job_checks_that_nothing_else_takes_the_clock_or_the_crux_providers(self):
        commands = self.commands("s5")
        for needle in (
            "CONFIG_CRUX_TIME_RTC=y", "CONFIG_CRUX_THREAD=y", "CONFIG_CRUX_SYNC=y",
            "CONFIG_CRUX_QUEUE=y", "CONFIG_CRUX_CONTROLLER_S3=y", "CONFIG_CRUX_CONTROLLER_S4=y",
            "CONFIG_SNTP_UNCERTAINTY=y",
            # Zephyr's own SNTP clock setters would give the clock a second writer.
            "CONFIG_NET_CONFIG_CLOCK_SNTP_INIT=y", "CONFIG_NET_CONFIG_SNTP_INIT_RESYNC=y",
        ):
            self.assertIn(needle, commands, needle)

    def test_the_s5_job_checks_what_the_image_links(self):
        commands = self.commands("s5")
        for symbol in ("time_sync_init", "time_sync_poll", "time_sync_start", "time_sync_decide",
                       "time_sync_port_query", "sntp_simple", "crux_realtime_init",
                       "crux_realtime_set", "crux_realtime_set_synchronized",
                       "crux_realtime_get_snapshot"):
            self.assertIn(symbol, commands, symbol)
        # The Crux Time and SNTP libraries define the other authority and query calls themselves, so
        # their symbols prove no caller: the job says so and leaves the callers to the source tests.
        self.assertIn("their symbols are not a sign of a caller", " ".join(commands.replace("#", " ").split()))
        self.assertIn("arm-zephyr-eabi-nm", commands)

    def test_the_s5_job_runs_no_hardware_command_and_says_nothing_ran_on_a_board(self):
        commands = self.commands("s5")
        for word in ("west flash", "west debug", "JLink", "pyocd", "openocd"):
            self.assertNotIn(word, commands, word)
        self.assertIn("No flash, reset or hardware command was run.", commands)

    def test_the_native_sim_scenarios_of_s5_run_in_ci_with_the_others(self):
        self.assertIn("tests/native_sim", self.commands("s1"))

    def test_the_budget_matrix_has_an_s5_row_on_the_network_base(self):
        rows = self.budget_rows()
        self.assertIn("S5", rows)
        self.assertEqual("conf/s1.conf;conf/s2.conf;conf/s5.conf", rows["S5"]["conf"])
        self.assertEqual("boards/s2.overlay", rows["S5"]["overlay"])

    def test_the_budget_row_requires_the_step_and_the_library_to_be_built(self):
        require = self.budget_rows()["S5"]["require"].split()
        for option in ("CONFIG_CRUX_CONTROLLER_S5=y", "CONFIG_SNTP=y", "CONFIG_CRUX_CONTROLLER_S2=y"):
            self.assertIn(option, require, option)

    def test_the_budget_rows_of_the_other_steps_are_unchanged(self):
        # Step S6 later added its own row, which test_s6.py pins, so the list ends at S6.
        rows = self.budget_rows()
        self.assertEqual(["S0", "S1", "S2", "S3", "S4", "S5", "S6"], sorted(rows))
        self.assertEqual(("", "", ""), (rows["S0"]["conf"], rows["S0"]["overlay"], rows["S0"]["require"]))
        self.assertEqual("conf/s1.conf", rows["S1"]["conf"])
        self.assertEqual("conf/s1.conf;conf/s2.conf", rows["S2"]["conf"])
        self.assertEqual("conf/s1.conf;conf/s3.conf", rows["S3"]["conf"])
        self.assertEqual("conf/s1.conf;conf/s4.conf", rows["S4"]["conf"])
        self.assertEqual("CONFIG_CRUX_CONTROLLER_S4=y CONFIG_CRUX_SYSTEM=y", rows["S4"]["require"])

    def test_no_workflow_uploads_an_artifact_and_the_new_job_asks_for_no_write_permission(self):
        for path in sorted(WORKFLOWS.glob("*.yml")):
            self.assertNotIn("upload-artifact", path.read_text(), path.name)
        self.assertEqual({"contents": "read"}, self.ci()["permissions"])
        self.assertNotIn("permissions", self.ci()["jobs"]["s5"])


class S5Findings(unittest.TestCase):
    NOTE = ROOT / "docs" / "findings" / "s5-time-synchronisation.md"

    def words(self, path=None):
        return " ".join((path or self.NOTE).read_text().split())

    def test_the_findings_note_exists_and_uses_the_three_labels(self):
        text = self.NOTE.read_text()
        for label in ("Measured", "Inferred", "Open"):
            self.assertIn(label, text)

    def test_the_note_says_nothing_ran_on_a_board_and_names_the_pinned_revision(self):
        text = self.words()
        self.assertIn("Nothing ran on a board", text)
        self.assertIn("37c92b18b44b7dfb95c2109f036f23d00f05cb4c", text)

    def test_the_note_states_each_rule_of_the_policy(self):
        text = self.words()
        for needle in (
            "outside 2000-01-01 to 2100-01-01", "never sets", "counts as a failure",
            "strictly", "marked not synchronised once", "any in-range answer",
            "below the correction threshold", "up to and including the maximum step",
            "refused", "synchronisation is lost", "the next in-range answer",
            "a failed query at boot sets nothing",
        ):
            self.assertIn(needle, text, needle)

    def test_the_note_lists_every_default_and_what_it_is(self):
        text = self.words()
        for needle in (
            "192.168.77.1", "600 s", "3000 ms", "1800 s", "100 ms", "1000 ms", "8192",
            "starting value", "not measured",
        ):
            self.assertIn(needle, text, needle)

    def test_the_note_records_the_limits_the_owner_has_to_know(self):
        text = self.words()
        for needle in (
            "unauthenticated", "a rogue server", "can move the clock", "accepted limitation",
            "step, not a slew", "nothing persists time", "no RTC", "not valid after a reset",
            "path delay is not compensated",
        ):
            self.assertIn(needle, text, needle)

    def test_the_note_states_the_event_wall_clock_consequence(self):
        text = self.words()
        for needle in ("monotonic time", "snapshot", "seq", "up", "before the first set",
                       "across a step", "shifted"):
            self.assertIn(needle, text, needle)

    # Approved behaviour change: the note no longer cites a private consult. It states the question
    # and the answer neutrally and points at the Crux Time contract that supports each duty.
    def test_the_note_states_the_four_duties_as_a_question_and_answer_and_where_each_is_met(self):
        text = self.words()
        self.assertNotIn("consult", text)
        self.assertNotIn("Crux Pilot was asked", text)
        self.assertIn("The question was whether a product thread may call `crux_realtime_set`", text)
        self.assertIn("not a Crux decision", text)
        self.assertIn("docs/time-contract.md", text)
        for needle in ("staleness is the product's", "write failure", "one writer of the native clock",
                       "events"):
            self.assertIn(needle, text, needle)

    def test_the_note_names_the_scenario_cases_and_what_they_cannot_show(self):
        text = self.words()
        for needle in ("failed native write", "first_sync", "kiss_of_death", "late_answer",
                       "out_of_range", "step_refused_then_resync", "correction_and_threshold",
                       "stale_after_silence", "v4.4.0", "v4.4.2"):
            self.assertIn(needle, text, needle)

    # Approved behaviour change: CI ran at the merge commit of S5 and its results were read from the job
    # logs, so the rows that said "not yet known" now record them, with the revision and the source. The
    # claim about the board and the real server stays open.
    def test_the_note_records_the_ci_results_with_their_revision_and_source(self):
        text = self.NOTE.read_text()
        words = " ".join(text.split())
        self.assertIn("**Recorded**", text)
        self.assertIn("29a2d8f", words)
        self.assertIn("read from the GitHub job logs", words)
        self.assertNotIn("not yet known", text)
        for claim in ("CI job \"S5 build", "CI job \"Budget S5", "CI job \"S1 (native_sim"):
            line = next(line for line in text.splitlines() if claim in line)
            self.assertIn("Recorded", line)
        budget = next(line for line in text.splitlines() if "CI job \"Budget S5" in line)
        self.assertIn("105908", budget)
        self.assertIn("80876", budget)
        scenarios = next(line for line in text.splitlines() if "CI job \"S1 (native_sim" in line)
        self.assertIn("31 of 31", scenarios)
        self.assertIn("seven", scenarios)

    def test_the_note_keeps_its_real_server_and_board_row_open(self):
        line = next(line for line in self.NOTE.read_text().splitlines() if "A query to a real server" in line)
        self.assertIn("not run", line)
        self.assertIn("Open", line)

    def test_the_note_has_no_line_counts_and_no_machine_paths(self):
        text = self.NOTE.read_text()
        self.assertNotIn("wc -l", text)
        self.assertNotRegex(text, r"/Users/|/home/")

    def test_the_readme_lists_s5_as_built_and_never_run_on_a_board(self):
        readme = (ROOT / "README.md").read_text()
        row = re.search(r"^\|\s*S5\s*\|.*$", readme, re.M)
        self.assertIsNotNone(row)
        self.assertIn("not run", row.group(0))
        self.assertIn("s5-time-synchronisation.md", readme)
        self.assertIn("step S5", " ".join(readme.split()))

    def test_the_changelog_names_s5_and_its_limits(self):
        text = " ".join((ROOT / "CHANGELOG.md").read_text().split())
        self.assertIn("S5", text)
        self.assertIn("SNTP", text)
        self.assertIn("unauthenticated", text)

    def test_the_contributing_guide_lists_s5_where_it_lists_the_steps_and_jobs(self):
        text = (ROOT / "CONTRIBUTING.md").read_text()
        self.assertIn("Steps S0 to S6 are built in CI", text)
        self.assertIn("`S5 build`", text)
        self.assertIn("`Budget` for S0 to S6:", text)

    def test_the_zone_note_no_longer_says_that_no_sntp_code_exists(self):
        zone = " ".join((ROOT / "docs" / "composition-zone.md").read_text().split())
        self.assertNotIn("no SNTP adapter exists yet", zone)
        self.assertNotIn("holds one source", zone)
        self.assertIn("time_sync_zephyr.c", zone)
        adapter = (APP_OS / "workload_os_zephyr.c").read_text()
        self.assertNotIn("which no source includes yet", adapter)

    def test_the_manifest_pins_the_approved_commit(self):
        manifest = (ROOT / "west.yml").read_text()
        self.assertIn("revision: 5fa998398b3557551cd7995ed44119f1c483cab9", manifest)


if __name__ == "__main__":
    unittest.main()
