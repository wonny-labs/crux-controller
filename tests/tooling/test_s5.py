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

    def test_the_zone_allow_lists_are_unchanged_by_this_step(self):
        self.assertEqual(frozenset({"zephyr/kernel.h", "zephyr/net/sntp.h"}),
                         check_boundary.OS_ADAPTER_ZEPHYR_HEADERS)
        self.assertEqual(frozenset({"zephyr/fs/fs.h", "zephyr/devicetree.h"}),
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


if __name__ == "__main__":
    unittest.main()
