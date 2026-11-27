# SPDX-License-Identifier: Apache-2.0
"""Checks of the system capability (Crux System): its limits, policy, configuration, build files, sources, CI
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
import ci_map  # noqa: E402
import fake_crux  # noqa: E402

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


class SystemLimits(unittest.TestCase):
    """The row is declared before the first measurement, with the margins of base to file."""

    def limits(self):
        return json.loads((ROOT / "budgets" / "limits.json").read_text())

    def test_limits_declare_system_with_the_same_placeholder_margins(self):
        data = self.limits()
        self.assertEqual(REGIONS, set(data["min_free_percent"]["system"]))
        self.assertTrue(all(v == 25 for v in data["min_free_percent"]["system"].values()))
        self.assertIn("placeholder", data["_comment"].lower())

    def test_the_system_row_equals_the_file_row_and_no_other_row_changed(self):
        rows = self.limits()["min_free_percent"]
        # Steps sntp and management later added their own rows, which test_sntp.py and test_management.py pin.
        self.assertEqual(["minimal", "workload", "net", "file", "system", "sntp", "management", "base"], list(rows))
        for step in ("minimal", "workload", "net", "file"):
            self.assertEqual(rows["file"], rows[step], step)
        self.assertEqual(rows["file"], rows["system"])

    def test_the_checker_accepts_a_measurement_of_system_inside_the_margin(self):
        regions = {name: {"used": 0, "size": 1000} for name in REGIONS}
        regions["FLASH"] = {"used": 750, "size": 1000}
        self.assertEqual([], check.check({"config": "system", "regions": regions}, self.limits()))

    def test_the_checker_fails_a_measurement_of_system_beyond_the_margin(self):
        regions = {name: {"used": 0, "size": 1000} for name in REGIONS}
        regions["FLASH"] = {"used": 751, "size": 1000}
        messages = check.check({"config": "system", "regions": regions}, self.limits())
        self.assertEqual(1, len(messages))
        self.assertIn("system FLASH", messages[0])


class SystemPolicy(unittest.TestCase):
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


class SystemConfiguration(unittest.TestCase):
    CONF = ROOT / "app" / "conf" / "system.conf"

    def test_the_fragment_selects_the_step_and_the_native_facilities_that_system_requires(self):
        options = conf_options(self.CONF)
        for name in ("CONFIG_CRUX_CONTROLLER_SYSTEM", "CONFIG_CRUX_SYSTEM", "CONFIG_WATCHDOG",
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
        block = kconfig_block("CRUX_CONTROLLER_SYSTEM")
        self.assertIn("bool", block)
        self.assertRegex(block, r"depends on CRUX_CONTROLLER_WORKLOAD && CRUX_SYSTEM\b")
        for native in ("WATCHDOG", "HWINFO", "REBOOT"):
            self.assertRegex(block, rf"\bdepends on [^\n]*\b{native}\b|&& {native}\b", native)

    def test_the_step_option_selects_nothing(self):
        # No Crux symbol is selected for the product: Crux System asks for the native facilities
        # itself, and the product states them in its fragment.
        self.assertNotRegex(kconfig_block("CRUX_CONTROLLER_SYSTEM"), r"^\s*select\b", )

    def test_the_overlay_selects_the_watchdog_that_crux_system_asks_for_by_alias(self):
        text = (ROOT / "app" / "boards" / "system.overlay").read_text()
        self.assertRegex(text, r"aliases\s*\{\s*crux-watchdog0\s*=\s*&wdog0;\s*\};")
        self.assertRegex(text, r"&wdog0\s*\{\s*status\s*=\s*\"okay\";\s*\};")
        self.assertNotIn("wdog1", text)
        self.assertNotIn("rtwdog", text)


class SystemBuildFiles(unittest.TestCase):
    def text(self):
        return "\n".join(code_lines(ROOT / "app" / "CMakeLists.txt"))

    def block(self):
        text = self.text()
        match = re.search(r"if\(CONFIG_CRUX_CONTROLLER_SYSTEM\)(.*?)endif\(\)", text, re.S)
        self.assertIsNotNone(match, "no if(CONFIG_CRUX_CONTROLLER_SYSTEM) block")
        return match.group(1)

    def test_the_system_block_is_inside_the_workload_switch(self):
        text = self.text()
        self.assertGreater(text.index("if(CONFIG_CRUX_CONTROLLER_SYSTEM)"),
                           text.index("if(CONFIG_CRUX_CONTROLLER_WORKLOAD)"))

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
        before = text[: text.index("if(CONFIG_CRUX_CONTROLLER_SYSTEM)")]
        self.assertNotIn("crux::system", before)


class SystemSources(unittest.TestCase):
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
        # The headers come from tests/tooling/fake_crux.py, which also lists the Access and web headers
        # that the composition zone of the management capability includes, so this fixture publishes them too.
        with tempfile.TemporaryDirectory() as directory:
            crux = fake_crux.publish(directory)
            self.assertEqual([], check_boundary.check(ROOT, crux))

    def test_the_policy_flag_values_are_asserted_against_crux_at_build_time(self):
        source = c_code(self.GLUE)
        for name in self.NAMES:
            # Both sides are cast: GCC fails the build (-Werror=enum-compare) on a comparison of
            # constants of two different anonymous enums, which is what these two are.
            self.assertRegex(
                source,
                rf"_Static_assert\(\s*\(uint32_t\)HEALTH_CAUSE_{name}\s*==\s*"
                rf"\(uint32_t\)CRUX_RESET_CAUSE_{name}\b",
                name,
            )

    def test_every_comparison_of_a_policy_flag_in_the_glue_casts_both_sides(self):
        # -Werror=enum-compare: the policy's flags and Crux's are constants of different enums.
        source = c_code(self.GLUE)
        found = re.findall(r"HEALTH_CAUSE_\w+\s*==", source)
        self.assertEqual(len(self.NAMES), len(found))
        for statement in re.findall(r"_Static_assert\([^;]*;", source):
            self.assertRegex(statement, r"\(uint32_t\)HEALTH_CAUSE_\w+\s*==\s*\(uint32_t\)CRUX_RESET_CAUSE_\w+")

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

    def test_the_composition_starts_system_between_the_storage_and_the_workload(self):
        source = c_code(APP_SRC / "composition.c")
        self.assertIn("#ifdef CONFIG_CRUX_CONTROLLER_SYSTEM", source)
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
            for tree in ("app/src", "app/os", "app/compose", "workload", "framework/src",
                         "framework/compose", "framework/os", "include"):
                with tempfile.TemporaryDirectory() as directory:
                    path = pathlib.Path(directory) / tree / "x.c"
                    path.parent.mkdir(parents=True)
                    path.write_text(f"#include <{header}>\n")
                    found = check_boundary.check(directory)
                    self.assertEqual([header], [v.include for v in found], f"{tree}: {header}")

    def test_the_zone_allow_lists_are_unchanged_by_this_step(self):
        # The system capability left every zone list as it was. The adapter zone list later grew by
        # zephyr/net/sntp.h in its own reviewed boundary change, and the composition zone's
        # lists grew by crux/web_zephyr.h and zephyr/net/tls_credentials.h in another, and by
        # crux/cli_zephyr.h in a third. This pin follows all three.
        self.assertEqual(
            frozenset({"zephyr/fs/fs.h", "zephyr/devicetree.h", "zephyr/net/tls_credentials.h"}),
            check_boundary.COMPOSITION_ZEPHYR_HEADERS)
        self.assertEqual(frozenset({"zephyr/kernel.h", "zephyr/net/sntp.h"}),
                         check_boundary.OS_ADAPTER_ZEPHYR_HEADERS)
        self.assertEqual(frozenset({"crux/file_zephyr.h", "crux/web_zephyr.h", "crux/cli_zephyr.h"}),
                         check_boundary.COMPOSITION_CRUX_HEADERS)
        self.assertEqual(
            frozenset({"crux/thread.h", "crux/sync.h", "crux/serial.h"}),
            check_boundary.FROZEN_CRUX_HEADERS,
        )
        self.assertEqual(["app/src", "workload", "app/compose", "app/os", "include", "framework/src", "framework/compose", "framework/os",
                          # Added with the fixture application (delivery stage 3); the zone
                          # allow-lists above stay as they were.
                          "tests/framework/fixture"],
                         [rule.directory for rule in check_boundary.RULES])

    def test_a_private_system_header_fails_in_every_tree(self):
        for name in ("crux/system_zephyr.h", "crux/system_port.h", "system_port.h"):
            for tree in ("app/src", "app/os", "app/compose", "framework/src", "framework/compose",
                         "framework/os"):
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


class SystemScenario(unittest.TestCase):
    DIRECTORY = ROOT / "tests" / "native_sim" / "system"
    CASES = ("reset_cause", "watchdog_unsupported", "period_out_of_range")

    def scenarios(self):
        return yaml.safe_load((self.DIRECTORY / "testcase.yaml").read_text())

    def test_one_scenario_per_case_on_the_64_bit_simulator(self):
        data = self.scenarios()
        self.assertEqual(
            {f"controller.system.native_sim.{case}" for case in self.CASES}, set(data["tests"])
        )
        for name, test in data["tests"].items():
            case = name.rsplit(".", 1)[1]
            self.assertEqual(f"SYSTEM_CASE={case}", test["extra_args"], name)
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
        source = (self.DIRECTORY / "src" / "test_system.c").read_text()
        for case in self.CASES:
            self.assertIn(f"SYSTEM_CASE_{case}", source, case)
        self.assertIn("CRUX_WATCHDOG_UNAVAILABLE", source)
        self.assertIn("a feed cycle and a missed feed cannot be shown here", " ".join(source.split()))

    def test_the_scenario_reads_the_log_from_an_emulated_uart(self):
        text = (self.DIRECTORY / "app.overlay").read_text()
        self.assertIn('compatible = "zephyr,uart-emul"', text)
        self.assertIn("logging_test:", text)

    def test_the_workload_scenario_checks_the_cycle_hook_that_the_feed_hangs_on(self):
        source = (ROOT / "tests" / "native_sim" / "workload" / "src" / "test_workload.c").read_text()
        self.assertIn("workload_thread_set_cycle_hook(count_hook)", source)
        self.assertIn("test_the_cycle_hook_runs_about_once_per_cycle", source)
        self.assertIn("test_the_workload_logs_one_line_per_message", source)


@ci_map.needs_tomllib
class SystemWorkflows(unittest.TestCase):
    """A job of a workflow runs the checks of the job of the same name in scripts/ci/checks.toml."""

    def ci(self):
        return yaml.safe_load((WORKFLOWS / "ci.yml").read_text())

    def commands(self, job):
        return ci_map.commands(job)

    def budget_rows(self):
        return ci_map.budget_rows()

    def test_ci_has_a_system_job_that_builds_the_board_image_with_the_gate_required(self):
        self.assertIn("system", self.ci()["jobs"])
        job = self.ci()["jobs"]["system"]
        self.assertEqual(BOARD, ci_map.job_env("system")["BOARD"])
        commands = self.commands("system")
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", commands)
        self.assertIn("conf/workload.conf;conf/system.conf", commands)
        self.assertIn("boards/system.overlay", commands)
        self.assertIn("build/system", commands)

    def test_the_system_job_follows_the_file_job_step_for_step_where_it_builds(self):
        jobs = self.ci()["jobs"]
        names = [step.get("name", step.get("uses", "")) for step in jobs["system"]["steps"]]
        file = [step.get("name", step.get("uses", "")) for step in jobs["file"]["steps"]]
        self.assertEqual(
            [name.replace("file", "system") for name in file][:-1], names[: len(file) - 1],
        )
        self.assertEqual(jobs["file"]["runs-on"], jobs["system"]["runs-on"])
        self.assertEqual(jobs["file"]["env"]["SDK_VERSION"], jobs["system"]["env"]["SDK_VERSION"])
        # The checks of the two jobs in scripts/ci/checks.toml follow each other the same way.
        self.assertEqual([i.replace("file", "system") for i in ci_map.ids("file")], ci_map.ids("system"))

    def test_the_system_job_checks_what_the_build_resolved(self):
        commands = self.commands("system")
        for needle in (
            "CONFIG_CRUX_CONTROLLER_SYSTEM=y", "CONFIG_CRUX_SYSTEM=y", "CONFIG_WATCHDOG=y",
            "CONFIG_HWINFO=y", "CONFIG_REBOOT=y", "crux-watchdog0", "wdog0", "zephyr.bin",
        ):
            self.assertIn(needle, commands, needle)

    def test_the_system_job_checks_that_no_other_owner_and_no_crux_thread_provider_is_on(self):
        commands = self.commands("system")
        for needle in (
            "CONFIG_TASK_WDT=y", "CONFIG_WDT_SHELL=y", "CONFIG_HWINFO_SHELL=y",
            "CONFIG_CRUX_CONTROLLER_M3=y", "CONFIG_CRUX_THREAD=y", "CONFIG_CRUX_SYNC=y",
        ):
            self.assertIn(needle, commands, needle)
        # Crux no longer has a Queue provider, so the job does not name its symbol.
        self.assertNotIn("CONFIG_CRUX_QUEUE", commands)

    def test_the_system_job_checks_what_the_image_links(self):
        commands = self.commands("system")
        for symbol in ("health_report_reset_cause", "health_watchdog_start", "health_cycle",
                       "health_feed_result", "crux_watchdog_start", "crux_watchdog_feed",
                       "crux_system_reset_cause_get", "crux_system_reset_cause_clear"):
            self.assertIn(symbol, commands, symbol)
        self.assertIn("arm-zephyr-eabi-nm", commands)

    def test_the_system_job_runs_no_hardware_command_and_says_nothing_ran_on_a_board(self):
        commands = self.commands("system")
        for word in ("west flash", "west debug", "JLink", "pyocd", "openocd"):
            self.assertNotIn(word, commands, word)
        self.assertIn("No flash, reset or hardware command was run.", commands)

    def test_the_native_sim_scenarios_of_system_run_in_ci_with_the_others(self):
        self.assertIn("tests/native_sim", self.commands("workload"))
        self.assertIn("native_sim/native/64", self.commands("workload"))

    def test_the_budget_matrix_has_a_system_row_on_the_workload_base(self):
        rows = self.budget_rows()
        self.assertIn("system", rows)
        self.assertEqual("conf/workload.conf;conf/system.conf", rows["system"]["conf"])
        self.assertEqual("boards/system.overlay", rows["system"]["overlay"])

    def test_the_budget_row_requires_the_step_and_the_provider_to_be_built(self):
        require = self.budget_rows()["system"]["require"].split()
        self.assertIn("CONFIG_CRUX_CONTROLLER_SYSTEM=y", require)
        self.assertIn("CONFIG_CRUX_SYSTEM=y", require)

    def test_the_budget_rows_of_the_other_steps_are_unchanged(self):
        rows = self.budget_rows()
        # Steps sntp and management later added their own rows, which test_sntp.py and test_management.py pin.
        self.assertEqual(["minimal", "workload", "net", "file", "system", "sntp", "management", "base"], list(rows))
        self.assertEqual(("", "", ""), (rows["minimal"]["conf"], rows["minimal"]["overlay"], rows["minimal"]["require"]))
        self.assertEqual("conf/workload.conf", rows["workload"]["conf"])
        self.assertEqual("conf/workload.conf;conf/net.conf", rows["net"]["conf"])
        self.assertEqual("boards/net.overlay", rows["net"]["overlay"])
        self.assertEqual("conf/workload.conf;conf/file.conf", rows["file"]["conf"])
        self.assertEqual("boards/file.overlay", rows["file"]["overlay"])
        self.assertEqual("CONFIG_CRUX_CONTROLLER_FILE=y CONFIG_CRUX_FILE_FATFS_RT1060=y",
                         rows["file"]["require"])

    def test_no_workflow_uploads_an_artifact_and_the_new_job_asks_for_no_write_permission(self):
        for path in sorted(WORKFLOWS.glob("*.yml")):
            text = path.read_text()
            self.assertNotIn("upload-artifact", text, path.name)
        self.assertEqual({"contents": "read"}, self.ci()["permissions"])
        self.assertNotIn("permissions", self.ci()["jobs"]["system"])


class SystemFindings(unittest.TestCase):
    NOTE = ROOT / "docs" / "findings" / "s4-system-composition.md"

    def test_the_findings_note_exists_and_uses_the_three_labels(self):
        text = self.NOTE.read_text()
        for label in ("Measured", "Inferred", "Open"):
            self.assertIn(label, text)

    def test_the_note_says_nothing_ran_on_a_board_and_names_the_pinned_revision(self):
        text = " ".join(self.NOTE.read_text().split())
        self.assertIn("Nothing ran on a board", text)
        self.assertIn("37c92b18b44b7dfb95c2109f036f23d00f05cb4c", text)

    def test_the_note_records_that_the_simulator_cannot_show_a_feed_cycle(self):
        text = " ".join(self.NOTE.read_text().split())
        self.assertIn("a feed cycle", text)
        self.assertIn("system_binding.c", text)

    # Approved behaviour change: CI ran at the merge commit of system and its results were read from the job
    # logs, so the rows that said "not yet known" now record them, with the revision and the source. The
    # claim about the board stays.
    def test_the_note_records_the_ci_results_with_their_revision_and_source(self):
        text = self.NOTE.read_text()
        words = " ".join(text.split())
        self.assertIn("**Recorded**", text)
        self.assertIn("9a906b1", words)
        self.assertIn("read from the GitHub job logs", words)
        self.assertNotIn("not yet known", text)
        for claim in ("CI job \"S4 build", "CI job \"Budget S4", "CI job \"S1 (native_sim"):
            line = next(line for line in text.splitlines() if claim in line)
            self.assertIn("Recorded", line)
        budget = next(line for line in text.splitlines() if "CI job \"Budget S4" in line)
        self.assertIn("45236", budget)
        self.assertIn("22720", budget)
        scenarios = next(line for line in text.splitlines() if "CI job \"S1 (native_sim" in line)
        self.assertIn("24 of 24", scenarios)

    def test_the_note_keeps_its_board_row_open(self):
        line = next(line for line in self.NOTE.read_text().splitlines() if "on a board" in line and line.startswith("|"))
        self.assertIn("not run", line)
        self.assertIn("Open", line)

    # Approved behaviour change: the board column left the README for the status page, the roadmap, and the
    # findings links for the findings index; the README keeps one row per capability.
    def test_the_roadmap_lists_system_as_built_and_never_run_on_a_board(self):
        readme = (ROOT / "README.md").read_text()
        self.assertRegex(readme, r"(?m)^\|[^|\n]*Crux System[^|\n]*\|\s*`system`\s*\|")
        roadmap = (ROOT / "docs" / "roadmap.md").read_text()
        row = re.search(r"^\|\s*`system`\s*\|.*$", roadmap, re.M)
        self.assertIsNotNone(row)
        self.assertIn("not run", row.group(0))
        self.assertIn("s4-system-composition.md", (ROOT / "docs" / "findings" / "README.md").read_text())

    def test_the_changelog_names_system(self):
        self.assertIn("`system`", (ROOT / "CHANGELOG.md").read_text())

    def test_the_manifest_pins_the_approved_commit(self):
        manifest = (ROOT / "west.yml").read_text()
        self.assertIn("revision: 1330195487c34c8df6046d41ae030d3cdf8a5138", manifest)


class SystemStartFailureWording(unittest.TestCase):
    """A failed start does not always mean that no watchdog runs. Crux can fail after the native
    start was attempted, with the outcome unknown, and then WDOG1 may run unfed."""

    def words(self, path):
        return " ".join(pathlib.Path(path).read_text().split())

    def test_the_glue_says_the_state_is_unknown_for_a_status_that_may_follow_an_attempt(self):
        source = c_code(APP_SRC / "health.c")
        self.assertIn("watchdog start failed", source)
        self.assertIn("may be running", source)
        self.assertIn("is not fed", source)
        self.assertIn("may reset", source)
        # Only these statuses mean that no watchdog was started: no device, or a refused timeout.
        self.assertRegex(
            source,
            r"started == CRUX_ERR_NOT_SUPPORTED \|\| started == CRUX_ERR_OUT_OF_RANGE",
        )

    def test_the_not_started_wording_stays_for_the_cases_that_are_certain(self):
        source = c_code(APP_SRC / "health.c")
        self.assertEqual(3, source.count("watchdog not started"))  # allowed, policy, Crux

    def test_the_three_places_name_the_three_certain_cases_and_the_unknown_one(self):
        places = {
            "health.h": self.words(APP_SRC / "health.h"),
            "composition.c": self.words(APP_SRC / "composition.c"),
            "findings": self.words(ROOT / "docs" / "findings" / "s4-system-composition.md"),
        }
        for name, text in places.items():
            self.assertIn("state is unknown", text, name)
            self.assertIn("may still reset", text, name)
            self.assertNotRegex(text, r"workload runs without a watchdog\.? *$", name)

    def test_the_findings_row_for_a_failed_start_no_longer_says_it_always_means_no_watchdog(self):
        text = self.words(ROOT / "docs" / "findings" / "s4-system-composition.md")
        row = re.search(r"\| A start that fails \|[^|]*\|", text)
        self.assertIsNotNone(row)
        self.assertNotIn("the workload runs without a watchdog", row.group(0))
        self.assertIn("CRUX_ERR_OUT_OF_RANGE", row.group(0))
        self.assertIn("CRUX_ERR_NOT_SUPPORTED", row.group(0))

    def test_the_note_records_the_possible_reset_loop_and_the_supervision_it_needs(self):
        text = self.words(ROOT / "docs" / "findings" / "s4-system-composition.md")
        self.assertIn("keep resetting", text)
        self.assertIn("supervised and time-limited", text)
        self.assertIn("armed before workload_thread_start", text)


class SystemWordingFixes(unittest.TestCase):
    def test_the_feed_is_once_per_pass_with_due_cycles_everywhere_it_is_described(self):
        for path in (ROOT / "app" / "Kconfig", ROOT / "CHANGELOG.md", ROOT / "README.md"):
            text = " ".join(path.read_text().split())
            self.assertNotRegex(text, r"once (for each|per) (workload )?cycle", path.name)
        self.assertIn("once for each pass that has cycles due",
                      " ".join(kconfig_block("CRUX_CONTROLLER_SYSTEM").split()))

    def test_the_findings_note_carries_no_line_counts_that_a_later_edit_makes_wrong(self):
        text = (ROOT / "docs" / "findings" / "s4-system-composition.md").read_text()
        self.assertNotIn("| Lines |", text)
        self.assertNotIn("wc -l", text)

    def test_the_findings_note_carries_no_line_counts_of_the_overlay_and_the_fragment(self):
        text = " ".join((ROOT / "docs" / "findings" / "s4-system-composition.md").read_text().split())
        self.assertNotRegex(text, r"\d+ lines each")
        self.assertIn("The composition proper is the fragment and the overlay.", text)

    def test_the_third_place_that_sets_the_alias_is_named_with_its_file_and_line(self):
        lines = (ROOT / "app" / "boards" / "system.overlay").read_text().splitlines()
        overlay = " ".join(" ".join(line.strip().lstrip("/*").strip() for line in lines).split())
        note = " ".join((ROOT / "docs" / "findings" / "s4-system-composition.md").read_text().split())
        for name, text in (("overlay", overlay), ("findings", note)):
            self.assertIn("tests/zephyr/management_rt1060_compile", text, name)
            self.assertIn("target.overlay:3", text, name)
            self.assertNotIn("not checked at the pin", text, name)
            self.assertNotIn("may be a third place", text, name)
            self.assertNotIn("may set the alias too", text, name)

    def test_the_header_names_the_refused_start_of_the_reset_cause_policy(self):
        lines = (APP_SRC / "health.h").read_text().splitlines()
        header = " ".join(line.strip().lstrip("/*").strip() for line in lines)
        header = " ".join(header.split())
        self.assertIn("CRUX_ERR_INVALID_STATE", header)
        self.assertIn("start_watchdog is always true", header)

    def test_the_findings_say_which_refused_feeds_fault_and_which_do_not(self):
        text = " ".join((ROOT / "docs" / "findings" / "s4-system-composition.md").read_text().split())
        self.assertIn("without moving the lifecycle to faulted", text)

    def test_the_overlay_comment_names_only_what_was_read_at_the_pin(self):
        text = (ROOT / "app" / "boards" / "system.overlay").read_text()
        self.assertNotIn("controller sample", text)
        self.assertIn("tests/system_consumer", text)
        self.assertIn("37c92b18", text)


if __name__ == "__main__":
    unittest.main()
