# SPDX-License-Identifier: Apache-2.0
"""Checks of the interactive native_sim configuration of the base image.

tests/framework/interactive builds the controller framework with no application for native_sim, as
the base scenario does, and makes it reachable from the host for a person: HTTPS management on the
host's loopback address through native_sim's offloaded sockets, Crux Logging on the program's
standard output, and the Crux serial console on a pseudo-terminal through a bridge to the emulated
UART that Crux Serial accepts on native_sim. scripts/run-native-sim.sh builds and runs it, and
docs/native-sim-interactive.md is the how-to page. The configuration is for development only: it
builds for native_sim alone, with the simulator's test entropy source.
"""

import pathlib
import re
import stat
import subprocess
import unittest

import ci_map

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCENARIO = "tests/framework/interactive"
SCRIPT = "scripts/run-native-sim.sh"
PAGE = "docs/native-sim-interactive.md"
PORT = "8443"
OFFLOAD_FIX = f"{SCENARIO}/nsos_rdhup.cmake"
# Zephyr v4.5.0 drivers/net/nsos_adapt.c, the file that the interim copy edits.
NSOS_V450_SHA256 = "75dabbeb67eccfded419b4e1a105e1d9838c431c985035459bf94af071bb70c0"


def read(path):
    return (ROOT / path).read_text()


def code_of(text):
    """C, devicetree or CMake text without its comments."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", " ", text)
    return re.sub(r"(?m)^\s*#[^\n]*", " ", text)


def conf_values(path):
    values = {}
    for line in read(path).splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


class Configuration(unittest.TestCase):
    def setUp(self):
        self.values = conf_values(f"{SCENARIO}/prj.conf")

    def test_it_is_the_base_image_with_its_three_services(self):
        for key in ("CONFIG_CRUX_CONTROLLER_FRAMEWORK", "CONFIG_CRUX_WEB_MANAGEMENT", "CONFIG_CRUX_CLI_CONSOLE",
                    "CONFIG_SNTP"):
            self.assertEqual("y", self.values.get(key), key)

    def test_it_supervises_the_controller_as_the_base_image_does(self):
        # An unmet Kconfig dependency only turns supervision off, so name what it needs.
        for key in ("CONFIG_TASK_WDT", "CONFIG_CRUX_SYSTEM", "CONFIG_CRUX_REBOOT", "CONFIG_REBOOT"):
            self.assertEqual("y", self.values.get(key), key)
        self.assertEqual("n", self.values.get("CONFIG_TASK_WDT_HW_FALLBACK"))
        # The start function runs below the supervisor's priority (<controller/framework.h>).
        self.assertEqual("8", self.values.get("CONFIG_MAIN_THREAD_PRIORITY"))
        self.assertNotEqual("y", self.values.get("CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION"))
        self.assertIn("startup done phases=7 failed=0", read(f"{SCENARIO}/pytest/test_interactive.py"))
        self.assertIn("startup done phases=7 failed=0", read(PAGE))

    def test_a_restart_request_restarts_the_program(self):
        # Without it a restart request ends the program in place of starting it again.
        self.assertEqual("y", self.values.get("CONFIG_NATIVE_SIM_REBOOT"))

    def test_the_network_is_the_hosts_through_offloaded_sockets(self):
        for key in ("CONFIG_NET_SOCKETS_OFFLOAD", "CONFIG_NET_NATIVE_OFFLOADED_SOCKETS", "CONFIG_NET_SOCKETS_SOCKOPT_TLS"):
            self.assertEqual("y", self.values.get(key), key)
        self.assertNotEqual("y", self.values.get("CONFIG_NET_LOOPBACK"))
        self.assertEqual("n", self.values.get("CONFIG_ETH_NATIVE_TAP"))

    def test_management_listens_on_the_loopback_address_and_an_unprivileged_port(self):
        self.assertEqual('"127.0.0.1"', self.values.get("CONFIG_CRUX_WEB_BIND_ADDRESS"))
        self.assertEqual(PORT, self.values.get("CONFIG_CRUX_WEB_PORT"))

    def test_the_time_server_is_the_loopback_address_so_nothing_leaves_the_host(self):
        self.assertEqual('"127.0.0.1"', self.values.get("CONFIG_CRUX_CONTROLLER_TIME_SERVER"))

    def test_the_log_goes_to_standard_output_through_the_console_uart(self):
        for key in ("CONFIG_UART_NATIVE_PTY_0_ON_STDINOUT", "CONFIG_LOG_BACKEND_UART", "CONFIG_UART_CONSOLE"):
            self.assertEqual("y", self.values.get(key), key)
        for key in ("CONFIG_LOG_BACKEND_NATIVE_POSIX", "CONFIG_STDOUT_CONSOLE", "CONFIG_SHELL"):
            self.assertEqual("n", self.values.get(key), key)

    def test_the_store_is_a_flash_disk_that_a_host_file_keeps(self):
        for key in ("CONFIG_DISK_DRIVER_FLASH", "CONFIG_CRUX_FILE_FATFS_SIMULATOR"):
            self.assertEqual("y", self.values.get(key), key)
        self.assertNotEqual("y", self.values.get("CONFIG_DISK_DRIVER_RAM"))

    def test_it_is_no_test_image(self):
        self.assertNotEqual("y", self.values.get("CONFIG_ZTEST"))


class Devicetree(unittest.TestCase):
    def setUp(self):
        self.text = code_of(read(f"{SCENARIO}/app.overlay"))

    def test_crux_serial_keeps_an_emulated_uart(self):
        self.assertRegex(self.text, r"crux-serial0\s*=\s*&console_emul\s*;")
        self.assertRegex(self.text, r"console_emul:\s*[\w-]+\s*\{[^}]*\"zephyr,uart-emul\"")

    def test_the_pseudo_terminal_of_the_console_is_the_second_pty_uart(self):
        self.assertRegex(self.text, r"&uart1\s*\{[^}]*status\s*=\s*\"okay\"")

    def test_the_log_uart_is_the_first_pty_uart(self):
        self.assertRegex(self.text, r"uarts\s*=\s*<&uart0>")
        self.assertRegex(self.text, r"&uart0\s*\{[^}]*current-speed\s*=\s*<115200>")

    def test_the_store_is_on_the_flash_simulator(self):
        self.assertIn('"zephyr,flash-disk"', self.text)
        self.assertRegex(self.text, r"controller_storage:\s*controller-storage\s*\{[^}]*\"zephyr,fstab,fatfs\"")


class Build(unittest.TestCase):
    def setUp(self):
        self.text = code_of(read(f"{SCENARIO}/CMakeLists.txt"))

    def test_it_refuses_every_board_but_native_sim_with_its_test_entropy(self):
        self.assertRegex(self.text, r"if\(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM\)\s*"
                                    r"message\(FATAL_ERROR")

    def test_it_refuses_a_listener_off_the_loopback_address(self):
        self.assertRegex(self.text, r'if\(NOT CONFIG_CRUX_WEB_BIND_ADDRESS STREQUAL "127\.0\.0\.1"\)\s*'
                                    r"message\(FATAL_ERROR")

    def test_it_builds_the_image_as_a_product_does(self):
        self.assertIn("target_link_libraries(app PRIVATE controller::framework)", self.text)
        self.assertIn("controller_framework_image()", self.text)

    def test_the_bridge_moves_bytes_between_the_pty_and_the_emulated_uart(self):
        code = code_of(read(f"{SCENARIO}/src/interactive.c"))
        for call in ("controller_framework_start(NULL)", "uart_poll_in(", "uart_poll_out(", "uart_emul_put_rx_data(",
                     "uart_emul_get_tx_data("):
            self.assertIn(call, code)

    def test_the_product_application_does_not_use_it(self):
        for path in (ROOT / "app").rglob("*"):
            if path.is_file():
                text = path.read_text(errors="replace")
                self.assertNotIn("NET_NATIVE_OFFLOADED_SOCKETS", text, path)
                self.assertNotIn("framework/interactive", text, path)


class OffloadFix(unittest.TestCase):
    """The interim copy of native_sim's offload driver is for the interactive configuration only."""

    def setUp(self):
        self.text = read(OFFLOAD_FIX)
        self.code = code_of(self.text)

    def test_only_the_interactive_configuration_includes_it(self):
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True,
                                 text=True).stdout.split()
        users = [path for path in tracked
                 if (path.endswith((".cmake", "CMakeLists.txt", ".conf", ".yml", ".yaml", ".toml", ".sh"))
                     and path != OFFLOAD_FIX and "nsos_rdhup" in read(path))]
        self.assertEqual([f"{SCENARIO}/CMakeLists.txt"], users)

    def test_no_product_build_file_names_the_driver_or_the_copy(self):
        for tree in ("app", "framework", "zephyr", "include", "release"):
            self.assertTrue((ROOT / tree).is_dir(), tree)
            for path in (ROOT / tree).rglob("*"):
                if path.is_file():
                    text = path.read_text(errors="replace")
                    self.assertNotIn("nsos_rdhup", text, path)
                    self.assertNotIn("nsos_adapt", text, path)

    def test_it_is_included_after_the_native_sim_guard(self):
        scenario = code_of(read(f"{SCENARIO}/CMakeLists.txt"))
        guard = scenario.index("if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)")
        self.assertLess(guard, scenario.index("include(${CMAKE_CURRENT_LIST_DIR}/nsos_rdhup.cmake)"))

    def test_it_refuses_every_build_but_native_sim_with_offloaded_sockets(self):
        self.assertRegex(self.code, r"if\(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_NET_NATIVE_OFFLOADED_SOCKETS\)\s*"
                                    r"message\(FATAL_ERROR")

    def test_the_build_fails_when_zephyr_changes_the_driver(self):
        self.assertIn(f"set(nsos_sha256 {NSOS_V450_SHA256})", self.code)
        self.assertRegex(self.code, r'file\(SHA256 "\$\{nsos_source\}" nsos_actual\)\s*'
                                    r"if\(NOT nsos_actual STREQUAL nsos_sha256\)\s*message\(FATAL_ERROR")
        self.assertIn('set(nsos_source "${ZEPHYR_BASE}/drivers/net/nsos_adapt.c")', self.code)

    def test_the_copy_keeps_the_licence_notice_and_goes_to_the_build_folder(self):
        self.assertIn('"SPDX-License-Identifier: Apache-2.0"', self.code)
        self.assertIn("Changed copy of Zephyr v4.5.0 drivers/net/nsos_adapt.c", self.text)
        self.assertIn('set(nsos_copy "${CMAKE_CURRENT_BINARY_DIR}/nsos_adapt_rdhup.c")', self.code)

    def test_it_states_its_label_provenance_and_removal(self):
        self.assertTrue(self.text.startswith("# SPDX-License-Identifier: Apache-2.0\n"))
        for words in ("project-specific workaround", "tests/native/web_https/nsos_rdhup.cmake at 1330195487c3",
                      "Removal:"):
            self.assertIn(words, self.text)
        self.assertIn("1330195487c34c8df6046d41ae030d3cdf8a5138", read("west.yml"))


class NoSecrets(unittest.TestCase):
    def test_no_key_certificate_or_password_is_in_the_configuration(self):
        paths = [p for p in (ROOT / SCENARIO).rglob("*") if p.is_file()] + [ROOT / SCRIPT]
        for path in paths:
            text = path.read_text()
            self.assertNotIn("PRIVATE KEY", text, path)
            self.assertNotIn("BEGIN CERTIFICATE", text, path)
            self.assertNotRegex(text, r"(?i)password\s*=\s*[\"'][^\"']+[\"']", path)

    def test_the_scenario_makes_its_password_at_run_time(self):
        text = read(f"{SCENARIO}/pytest/test_interactive.py")
        self.assertIn("secrets.token_urlsafe(", text)


class Scenario(unittest.TestCase):
    def test_twister_runs_it_with_the_pytest_harness_on_native_sim(self):
        text = read(f"{SCENARIO}/testcase.yaml")
        self.assertIn("harness: pytest", text)
        self.assertIn("native_sim/native/64", text)
        self.assertIn("controller.framework.native_sim.interactive:", text)

    def test_the_scenario_checks_the_web_port_the_console_and_a_restart(self):
        text = read(f"{SCENARIO}/pytest/test_interactive.py")
        for word in (f"{PORT}", "ssl.", "connected to pseudotty", "!setup", "account created", "source == \"stored\""):
            self.assertIn(word, text)

    def test_the_scenario_closes_a_kept_alive_connection_abruptly_then_needs_answers(self):
        text = read(f"{SCENARIO}/pytest/test_interactive.py")
        body = text[text.index("def test_a_person_operates"):]
        closed = body.index("close_kept_alive_connection_abruptly()")
        self.assertLess(closed, body.index("next_answer()"))
        self.assertLess(closed, body.index('console.type("help")'))
        self.assertNotIn("Connection: close", text[text.index("def close_kept_alive"):text.index("def next_answer")])

    @ci_map.needs_tomllib
    def test_ci_requires_the_scenario_to_pass(self):
        run = ci_map.run("base-native-sim-interactive-report")
        self.assertIn("controller.framework.native_sim.interactive", run)
        self.assertIn('all(status == "passed" for status in statuses)', run)
        self.assertEqual("base", ci_map.check("base-native-sim-interactive-report")["job"])


class Script(unittest.TestCase):
    def setUp(self):
        self.text = read(SCRIPT)

    def test_it_is_an_executable_bash_script_with_the_spdx_line_second(self):
        lines = self.text.splitlines()
        self.assertEqual("#!/usr/bin/env bash", lines[0])
        self.assertEqual("# SPDX-License-Identifier: Apache-2.0", lines[1])
        self.assertTrue((ROOT / SCRIPT).stat().st_mode & stat.S_IXUSR)

    def test_it_builds_the_scenario_for_native_sim(self):
        self.assertIn("native_sim/native/64", self.text)
        self.assertIn(SCENARIO, self.text)

    def test_each_run_seeds_the_test_entropy_from_the_host(self):
        self.assertIn("--seed=", self.text)
        self.assertIn("/dev/urandom", self.text)

    def test_the_store_survives_a_restart_in_a_file_of_the_build_folder(self):
        self.assertIn("--flash=", self.text)

    def test_the_console_pty_gets_a_fixed_name(self):
        self.assertIn("--uart_1_attach_uart_cmd=", self.text)


class Page(unittest.TestCase):
    def test_the_how_to_page_gives_the_command_and_is_in_the_map(self):
        page = read(PAGE)
        self.assertIn("bash scripts/run-native-sim.sh", page)
        self.assertIn(f"https://127.0.0.1:{PORT}", page)
        self.assertIn("(native-sim-interactive.md)", read("docs/README.md"))

    def test_the_page_states_the_abrupt_close_limit_and_its_interim_fix(self):
        page = " ".join(read(PAGE).split())
        for words in ("only a restart of the image recovers it", OFFLOAD_FIX, "project-specific workaround",
                      "Replace it with the version that Crux publishes"):
            self.assertIn(words, page)


if __name__ == "__main__":
    unittest.main()
