"""Checks of step S4 (Crux System): its limits, policy, configuration, build files, sources, CI
jobs, scenario and findings. Written test first, one slice at a time."""

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


class S4Configuration(unittest.TestCase):
    CONF = ROOT / "app" / "conf" / "s4.conf"

    def test_the_fragment_selects_the_step_and_the_native_facilities_that_system_requires(self):
        options = conf_options(self.CONF)
        for name in ("CONFIG_CRUX_CONTROLLER_S4", "CONFIG_CRUX_SYSTEM", "CONFIG_WATCHDOG",
                     "CONFIG_HWINFO", "CONFIG_REBOOT"):
            self.assertEqual("y", options.get(name), name)

    def test_the_fragment_selects_none_of_the_owners_that_crux_system_refuses(self):
        # Crux System fails the build when another owner of the watchdog or of the reset cause is
        # on: the native watchdog and HWINFO shells, the task watchdog fallback and the M3 sample.
        options = conf_options(self.CONF)
        for name in ("CONFIG_WDT_SHELL", "CONFIG_HWINFO_SHELL", "CONFIG_TASK_WDT",
                     "CONFIG_TASK_WDT_HW_FALLBACK", "CONFIG_CRUX_CONTROLLER_M3"):
            self.assertNotEqual("y", options.get(name), name)

    def test_the_fragment_selects_no_thread_sync_or_queue_provider_and_no_other_group(self):
        for name in conf_options(self.CONF):
            for forbidden in ("CRUX_THREAD", "CRUX_SYNC", "CRUX_QUEUE", "CRUX_SERIAL", "SECURE",
                              "RELIANCE", "CRUX_MGMT", "CRUX_WEB", "SSH", "CRUX_FILE"):
                self.assertNotIn(forbidden, name.upper(), name)

    def test_the_step_option_needs_the_workload_step_and_crux_system(self):
        block = kconfig_block("CRUX_CONTROLLER_S4")
        self.assertIn("bool", block)
        self.assertRegex(block, r"depends on CRUX_CONTROLLER_S1 && CRUX_SYSTEM\b")
        for native in ("WATCHDOG", "HWINFO", "REBOOT"):
            self.assertRegex(block, rf"\bdepends on [^\n]*\b{native}\b|&& {native}\b", native)

    def test_the_step_option_selects_nothing(self):
        # No Crux symbol is selected for the product: Crux System asks for the native facilities
        # itself, and the product states them in its fragment.
        self.assertNotRegex(kconfig_block("CRUX_CONTROLLER_S4"), r"^\s*select\b", )

    def test_the_overlay_selects_the_watchdog_that_crux_system_asks_for_by_alias(self):
        text = (ROOT / "app" / "boards" / "s4.overlay").read_text()
        self.assertRegex(text, r"aliases\s*\{\s*crux-watchdog0\s*=\s*&wdog0;\s*\};")
        self.assertRegex(text, r"&wdog0\s*\{\s*status\s*=\s*\"okay\";\s*\};")
        self.assertNotIn("wdog1", text)
        self.assertNotIn("rtwdog", text)


class S4BuildFiles(unittest.TestCase):
    def text(self):
        return "\n".join(code_lines(ROOT / "app" / "CMakeLists.txt"))

    def block(self):
        text = self.text()
        match = re.search(r"if\(CONFIG_CRUX_CONTROLLER_S4\)(.*?)endif\(\)", text, re.S)
        self.assertIsNotNone(match, "no if(CONFIG_CRUX_CONTROLLER_S4) block")
        return match.group(1)

    def test_the_s4_block_is_inside_the_workload_switch(self):
        text = self.text()
        self.assertGreater(text.index("if(CONFIG_CRUX_CONTROLLER_S4)"),
                           text.index("if(CONFIG_CRUX_CONTROLLER_S1)"))

    def test_the_block_adds_the_two_sources_and_links_the_public_system_target(self):
        block = self.block()
        self.assertIn("src/health.c", block)
        self.assertIn("src/health_policy.c", block)
        self.assertRegex(block, r"target_link_libraries\(app PRIVATE[^)]*\bcrux::system\b")

    def test_the_block_adds_no_include_path_and_no_zone(self):
        block = self.block()
        for word in ("include_directories", "-include", "-I", "add_subdirectory", "add_library"):
            self.assertNotIn(word, block, word)

    def test_no_build_file_links_a_private_system_target(self):
        for path in sorted(ROOT.glob("app/**/CMakeLists.txt")):
            body = "\n".join(code_lines(path))
            for private in ("crux_system_zephyr", "crux_system_api", "crux_system_linux",
                            "crux_interrupt"):
                self.assertNotIn(private, body, f"{path.relative_to(ROOT)}: {private}")
        self.assertEqual(1, self.text().count("crux::system"))

    def test_the_application_links_system_only_inside_the_step(self):
        text = self.text()
        before = text[: text.index("if(CONFIG_CRUX_CONTROLLER_S4)")]
        self.assertNotIn("crux::system", before)


class S4Sources(unittest.TestCase):
    GLUE = APP_SRC / "health.c"
    HEADER = APP_SRC / "health.h"
    NAMES = ("POR", "PIN", "SOFTWARE", "WATCHDOG", "DEBUG", "CPU_LOCKUP", "HARDWARE", "SECURITY",
             "USER", "TEMPERATURE", "OTHER")

    def test_the_glue_includes_public_crux_headers_and_its_own_policy_only(self):
        allowed = {"<stdio.h>", "<stdbool.h>", "<stdint.h>", "<stddef.h>", "<crux/logging.h>",
                   "<crux/status.h>", "<crux/system.h>", '"health.h"', '"health_policy.h"'}
        for path in (self.GLUE, self.HEADER):
            for include in includes(path):
                self.assertIn(include, allowed, f"{path.name}: {include}")
        self.assertIn("<crux/system.h>", includes(self.GLUE))
        self.assertIn("<crux/logging.h>", includes(self.GLUE))

    def test_the_glue_and_its_header_pass_the_boundary_check_against_a_crux_that_publishes_system(self):
        with tempfile.TemporaryDirectory() as directory:
            crux = pathlib.Path(directory)
            for name in ("system.h", "logging.h", "status.h", "time.h", "file.h"):
                header = crux / "components" / "x" / "include" / "crux" / name
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text("")
            composition = crux / "components" / "file" / "ports" / "zephyr" / "include" / "crux"
            composition.mkdir(parents=True)
            (composition / "file_zephyr.h").write_text("")
            self.assertEqual([], check_boundary.check(ROOT, crux))

    def test_the_policy_flag_values_are_asserted_against_crux_at_build_time(self):
        source = c_code(self.GLUE)
        for name in self.NAMES:
            self.assertRegex(
                source,
                rf"_Static_assert\(\s*HEALTH_CAUSE_{name}\s*==\s*CRUX_RESET_CAUSE_{name}\b",
                name,
            )

    def test_the_glue_reads_logs_and_clears_the_cause_in_that_order(self):
        source = c_code(self.GLUE)
        start = source.index("health_report_reset_cause(void)")
        body = source[start:]
        read = body.index("crux_system_reset_cause_get(")
        log = body.index("say(decision.level, text)")
        clear = body.index("crux_system_reset_cause_clear(")
        self.assertLess(read, log)
        self.assertLess(log, clear)
        # The one writer of every line is say(), which goes through Crux Logging.
        self.assertEqual(1, len(re.findall(r"\bcrux_log_write\(", source)))

    def test_the_glue_never_resets_the_controller_and_starts_the_watchdog_once(self):
        source = c_code(self.GLUE)
        self.assertNotIn("crux_system_reset(", source)
        self.assertEqual(1, len(re.findall(r"\bcrux_watchdog_start\(", source)))
        self.assertEqual(1, len(re.findall(r"\bcrux_watchdog_feed\(", source)))
        self.assertEqual(1, len(re.findall(r"\bcrux_system_reset_cause_clear\(", source)))

    def test_the_glue_asks_the_policy_for_the_interval_and_for_every_feed(self):
        source = c_code(self.GLUE)
        self.assertIn("health_watchdog_timeout(", source)
        self.assertIn("health_feed_wanted(", source)
        self.assertIn("health_feed_result(", source)
        self.assertIn("health_boot_decide(", source)

    def test_the_glue_logs_through_crux_logging_under_one_tag(self):
        source = c_code(self.GLUE)
        self.assertNotRegex(source, r"\bprintk\b|\bprintf\(")
        self.assertEqual({'"system"'}, set(re.findall(r'"system"', source)))

    def test_the_header_declares_the_three_calls_and_the_hook_type(self):
        header = c_code(self.HEADER)
        for needle in ("health_report_reset_cause(void)", "health_watchdog_start(uint32_t period_ms)",
                       "health_cycle(void)"):
            self.assertIn(needle, header, needle)

    def test_the_workload_calls_a_hook_once_per_batch_of_due_cycles_and_names_no_system_symbol(self):
        header = c_code(APP_SRC / "workload_thread.h")
        self.assertIn("workload_thread_set_cycle_hook(", header)
        source = c_code(APP_SRC / "workload_thread.c")
        self.assertIn("state.cycle_hook", source)
        self.assertNotRegex(source, r"crux_watchdog|crux_system|health_")
        # The hook runs where the producer has counted due cycles, once per pass, not per cycle.
        loop = source[source.index("while (!atomic_load(&state.stop_producer))"):]
        self.assertEqual(1, loop.count("state.cycle_hook()"))
        self.assertLess(loop.index("if (due == 0)"), loop.index("state.cycle_hook()"))
        self.assertLess(loop.index("state.cycle_hook()"), loop.index("for (uint32_t i = 0; i < due"))

    def test_the_composition_starts_s4_between_the_storage_and_the_workload(self):
        source = c_code(APP_SRC / "composition.c")
        self.assertIn("#ifdef CONFIG_CRUX_CONTROLLER_S4", source)
        self.assertIn('#include "health.h"', source)
        report = source.index("health_report_reset_cause(")
        start = source.index("health_watchdog_start(config.period_ms)")
        hook = source.index("workload_thread_set_cycle_hook(health_cycle)")
        run = source.index("return workload_thread_start(&config)")
        storage = source.index("configure_from_storage(&config);")
        self.assertLess(storage, report)
        self.assertLess(report, start)
        self.assertLess(start, hook)
        self.assertLess(hook, run)

    def test_the_other_trees_still_refuse_every_zephyr_header_that_system_uses_natively(self):
        # System needs <zephyr/drivers/watchdog.h>, <zephyr/drivers/hwinfo.h> and
        # <zephyr/sys/reboot.h> inside Crux. A product never needs them, and no zone lists them.
        for header in ("zephyr/drivers/watchdog.h", "zephyr/drivers/hwinfo.h",
                       "zephyr/sys/reboot.h", "fsl_wdog.h"):
            for tree in ("app/src", "app/os", "app/compose", "workload"):
                with tempfile.TemporaryDirectory() as directory:
                    path = pathlib.Path(directory) / tree / "x.c"
                    path.parent.mkdir(parents=True)
                    path.write_text(f"#include <{header}>\n")
                    found = check_boundary.check(directory)
                    self.assertEqual([header], [v.include for v in found], f"{tree}: {header}")

    def test_the_zone_allow_lists_are_unchanged_by_this_step(self):
        self.assertEqual(frozenset({"zephyr/fs/fs.h", "zephyr/devicetree.h"}),
                         check_boundary.COMPOSITION_ZEPHYR_HEADERS)
        self.assertEqual(frozenset({"zephyr/kernel.h"}), check_boundary.OS_ADAPTER_ZEPHYR_HEADERS)
        self.assertEqual(frozenset({"crux/file_zephyr.h"}), check_boundary.COMPOSITION_CRUX_HEADERS)
        self.assertEqual(
            frozenset({"crux/thread.h", "crux/sync.h", "crux/queue.h", "crux/serial.h"}),
            check_boundary.FROZEN_CRUX_HEADERS,
        )
        self.assertEqual(["app/src", "workload", "app/compose", "app/os"],
                         [rule.directory for rule in check_boundary.RULES])

    def test_a_private_system_header_fails_in_every_tree(self):
        for name in ("crux/system_zephyr.h", "crux/system_port.h", "system_port.h"):
            for tree in ("app/src", "app/os", "app/compose"):
                with tempfile.TemporaryDirectory() as directory:
                    path = pathlib.Path(directory) / tree / "x.c"
                    path.parent.mkdir(parents=True)
                    angle = f"<{name}>" if name.startswith("crux/") else f'"{name}"'
                    path.write_text(f"#include {angle}\n")
                    crux = pathlib.Path(directory) / "crux"
                    header = crux / "components" / "system" / "include" / "crux" / "system.h"
                    header.parent.mkdir(parents=True)
                    header.write_text("")
                    found = check_boundary.check(directory, crux)
                    self.assertEqual(1, len(found), f"{tree}: {name}")


class S4Scenario(unittest.TestCase):
    DIRECTORY = ROOT / "tests" / "native_sim" / "s4"
    CASES = ("reset_cause", "watchdog_unsupported", "period_out_of_range")

    def scenarios(self):
        return yaml.safe_load((self.DIRECTORY / "testcase.yaml").read_text())

    def test_one_scenario_per_case_on_the_64_bit_simulator(self):
        data = self.scenarios()
        self.assertEqual(
            {f"controller.s4.native_sim.{case}" for case in self.CASES}, set(data["tests"])
        )
        for name, test in data["tests"].items():
            case = name.rsplit(".", 1)[1]
            self.assertEqual(f"S4_CASE={case}", test["extra_args"], name)
        self.assertEqual(["native_sim/native/64"], data["common"]["platform_allow"])

    def test_the_scenario_uses_the_real_system_provider_and_the_native_facilities(self):
        options = conf_options(self.DIRECTORY / "prj.conf")
        for name in ("CONFIG_CRUX_SYSTEM", "CONFIG_WATCHDOG", "CONFIG_HWINFO", "CONFIG_REBOOT",
                     "CONFIG_CRUX_LOGGING"):
            self.assertEqual("y", options.get(name), name)
        for name in options:
            for forbidden in ("CRUX_THREAD", "CRUX_SYNC", "CRUX_QUEUE", "WDT_SHELL", "TASK_WDT"):
                self.assertNotIn(forbidden, name, name)

    def test_the_scenario_builds_the_applications_own_sources_not_copies(self):
        text = (self.DIRECTORY / "CMakeLists.txt").read_text()
        self.assertIn("${controller_root}/app/src/health.c", text)
        self.assertIn("${controller_root}/app/src/health_policy.c", text)
        self.assertIn("crux::system", text)

    def test_every_case_has_a_source_section_and_the_source_names_the_limit_of_the_simulator(self):
        source = (self.DIRECTORY / "src" / "test_s4.c").read_text()
        for case in self.CASES:
            self.assertIn(f"S4_CASE_{case}", source, case)
        self.assertIn("CRUX_WATCHDOG_UNAVAILABLE", source)
        self.assertIn("a feed cycle and a missed feed cannot be shown here", " ".join(source.split()))

    def test_the_scenario_reads_the_log_from_an_emulated_uart(self):
        text = (self.DIRECTORY / "app.overlay").read_text()
        self.assertIn('compatible = "zephyr,uart-emul"', text)
        self.assertIn("logging_test:", text)

    def test_the_s1_scenario_checks_the_cycle_hook_that_the_feed_hangs_on(self):
        source = (ROOT / "tests" / "native_sim" / "s1" / "src" / "test_s1.c").read_text()
        self.assertIn("workload_thread_set_cycle_hook(count_hook)", source)
        self.assertIn("test_the_cycle_hook_runs_about_once_per_cycle", source)
        self.assertIn("test_the_workload_logs_one_line_per_message", source)


if __name__ == "__main__":
    unittest.main()
