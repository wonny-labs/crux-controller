# SPDX-License-Identifier: Apache-2.0
"""Checks of the serial command line of the controller framework and the base image.

The framework starts the Crux serial console, with its login and first-account setup, through the
composition interface <crux/cli_zephyr.h> in the composition zone (framework/compose/cli_start.c),
behind a port header of the portable core (framework/src/cli_port.h). The service is the Kconfig
symbol CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL of zephyr/Kconfig. The board file of the RT1060-EVKB
names the console's UART with the alias crux-serial0, and the native_sim scenario of the base
image types the first-account setup into an emulated UART.
"""

import pathlib
import re
import unittest

import ci_map

ROOT = pathlib.Path(__file__).resolve().parents[2]
SYMBOL = "CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL"


def read(path):
    return (ROOT / path).read_text()


def code_of(text):
    """C text without its comments."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", text)


def kconfig_entry(name):
    text = read("zephyr/Kconfig")
    match = re.search(rf"^config {name}\n(.*?)(?=^\S)", text, flags=re.DOTALL | re.MULTILINE)
    assert match, f"zephyr/Kconfig has no config {name}"
    return match.group(1)


def conf_values(path):
    values = {}
    for line in read(path).splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


class Kconfig(unittest.TestCase):
    def test_the_service_is_on_by_default_when_crux_offers_the_console(self):
        entry = kconfig_entry(SYMBOL)
        self.assertIn("bool ", entry)
        self.assertIn("default y", entry)
        self.assertRegex(entry, r"depends on .*CRUX_CLI_CONSOLE")
        # The console logs in against Access, which web management starts.
        self.assertRegex(entry, r"depends on .*CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT")

    def test_the_service_sits_inside_the_framework_menu(self):
        text = read("zephyr/Kconfig")
        start = text.index("if CRUX_CONTROLLER_FRAMEWORK\n")
        end = text.index("endif # CRUX_CONTROLLER_FRAMEWORK")
        self.assertIn(f"config {SYMBOL}\n", text[start:end])

    def test_no_service_excludes_another(self):
        code = "\n".join(line for line in read("zephyr/Kconfig").splitlines()
                         if not line.strip().startswith("#"))
        self.assertNotRegex(code, r"depends on [^\n]*!CRUX_CONTROLLER_FRAMEWORK")


class PortAndZone(unittest.TestCase):
    def test_the_port_header_is_plain_c(self):
        code = code_of(read("framework/src/cli_port.h"))
        includes = re.findall(r"#\s*include\s*[<\"]([^>\"]+)[>\"]", code)
        for name in includes:
            self.assertFalse(name.startswith(("zephyr/", "crux/")), name)
        self.assertIn("cli_port_start(", code)
        self.assertIn("setup_role", code)

    def test_the_zone_starts_the_registry_and_then_the_console(self):
        code = code_of(read("framework/compose/cli_start.c"))
        self.assertIn("#include <crux/cli_zephyr.h>", code)
        self.assertIn('#include "../src/cli_port.h"', code)
        self.assertLess(code.index("crux_cli_init("), code.index("crux_cli_serial_start("))
        self.assertNotIn("crux_access_provision", code)
        self.assertNotRegex(code, r"#\s*include\s*<zephyr/")

    def test_only_the_zone_links_the_console_composition_target(self):
        compose = read("framework/compose/CMakeLists.txt")
        block = re.search(rf"if\(CONFIG_{SYMBOL}\)(.*?)endif\(\)", compose, flags=re.DOTALL)
        self.assertIsNotNone(block, "framework/compose/CMakeLists.txt builds cli_start.c under the symbol")
        self.assertIn("cli_start.c", block.group(1))
        self.assertIn("crux::cli_zephyr", block.group(1))
        for path in sorted(ROOT.rglob("CMakeLists.txt")) + sorted(ROOT.rglob("*.cmake")):
            relative = path.relative_to(ROOT).as_posix()
            if relative.startswith(("build/", "framework/compose/")):
                continue
            with self.subTest(path=relative):
                self.assertNotIn("crux::cli_zephyr", path.read_text())

    def test_the_start_function_runs_the_command_line_after_web_management(self):
        code = code_of(read("framework/src/framework.c"))
        self.assertIn(f"#ifdef CONFIG_{SYMBOL}", code)
        self.assertIn('#include "cli_port.h"', code)
        table = code[code.index("static const startup_phase_t phases[]"):]
        table = table[:table.index("};")]
        names = re.findall(r'\{"([^"]+)",', table)
        self.assertEqual(["clock", "web management", "command line", "time synchronisation"], names)

    def test_the_first_account_gets_the_role_that_manages_accounts(self):
        code = code_of(read("framework/src/framework.c"))
        self.assertIn("MANAGEMENT_ROLE_ADMINISTRATOR", code)

    def test_the_command_line_needs_web_management_to_have_started(self):
        # Access is started by the web management phase; the console must not start without it.
        code = code_of(read("framework/src/framework.c"))
        phase = code[code.index("static int phase_command_line"):]
        phase = phase[:phase.index("\n}\n")]
        self.assertIn("management_started", phase)


class BaseImage(unittest.TestCase):
    def test_the_fragment_turns_on_the_console(self):
        values = conf_values("app/conf/base.conf")
        for key in ("CONFIG_CRUX_SERIAL", "CONFIG_CRUX_CLI", "CONFIG_CRUX_CLI_CONSOLE"):
            self.assertEqual("y", values.get(key), key)
        self.assertEqual("n", values.get("CONFIG_SHELL"))

    def test_the_console_runs_in_the_device_management_band(self):
        for path in ("app/conf/base.conf", "tests/framework/base/prj.conf"):
            with self.subTest(path=path):
                priority = int(conf_values(path)["CONFIG_CRUX_CLI_CONSOLE_PRIORITY"])
                self.assertTrue(11 <= priority <= 13, priority)

    def test_the_board_file_names_the_console_uart(self):
        text = code_of(read("app/boards/mimxrt1060_evk_mimxrt1062_qspi.overlay"))
        self.assertRegex(text, r"crux-serial0\s*=\s*&lpuart3\s*;")
        self.assertRegex(text, r"&lpuart3\s*\{[^}]*status\s*=\s*\"okay\"")
        # Logging keeps LPUART1, so the console and the log never share a UART.
        self.assertRegex(text, r"uarts\s*=\s*<&lpuart1>")
        self.assertNotRegex(text, r"crux-serial0\s*=\s*&lpuart1\b")

    def test_no_other_board_file_or_fragment_names_the_alias(self):
        for path in sorted((ROOT / "app").rglob("*")):
            if path.suffix not in (".overlay", ".conf") or path.name == "mimxrt1060_evk_mimxrt1062_qspi.overlay":
                continue
            code = "\n".join(line.split("#", 1)[0] if path.suffix == ".conf" else line
                             for line in path.read_text().splitlines())
            if path.suffix == ".overlay":
                code = code_of(code)
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertNotIn("crux-serial0", code)

    @ci_map.needs_tomllib
    def test_ci_checks_what_the_base_build_resolved(self):
        config = ci_map.run("base-config")
        for option in (f"CONFIG_{SYMBOL}=y", "CONFIG_CRUX_CLI_CONSOLE=y", "CONFIG_CRUX_SERIAL=y"):
            self.assertIn(option, config)
        self.assertIn("crux-serial0", config)
        symbols = ci_map.run("base-symbols")
        for symbol in ("cli_port_start", "crux_cli_serial_start", "crux_cli_init"):
            self.assertIn(symbol, symbols)
        self.assertIn(f"CONFIG_{SYMBOL}=y", ci_map.job_env("budget-base")["REQUIRE"])


class NativeSimScenario(unittest.TestCase):
    SCENARIO = "tests/framework/base"

    def test_the_scenario_turns_on_the_console(self):
        values = conf_values(f"{self.SCENARIO}/prj.conf")
        for key in ("CONFIG_CRUX_SERIAL", "CONFIG_CRUX_CLI", "CONFIG_CRUX_CLI_CONSOLE",
                    "CONFIG_UART_INTERRUPT_DRIVEN", "CONFIG_UART_USE_RUNTIME_CONFIGURE"):
            self.assertEqual("y", values.get(key), key)

    def test_the_console_has_its_own_emulated_uart(self):
        text = code_of(read(f"{self.SCENARIO}/app.overlay"))
        self.assertRegex(text, r"crux-serial0\s*=\s*&serial_test\s*;")
        self.assertRegex(text, r"serial_test:\s*serial-test\s*\{[^}]*zephyr,uart-emul")
        self.assertRegex(text, r"uarts\s*=\s*<&logging_test>")

    def test_the_scenario_types_the_first_account_setup(self):
        code = code_of(read(f"{self.SCENARIO}/src/test_base.c"))
        for text in ('"!setup"', '"account created"', '"setup not available"', '"login failed"',
                     '"logout"', "startup done phases=4 failed=0", "phase command line ok"):
            self.assertIn(text, code)

    @ci_map.needs_tomllib
    def test_ci_counts_every_case_of_the_scenario(self):
        code = code_of(read(f"{self.SCENARIO}/src/test_base.c"))
        cases = len(re.findall(r"^ZTEST\(base,", code, flags=re.MULTILINE))
        self.assertIn(f"assert len(statuses) == {cases}, statuses", ci_map.run("base-native-sim-report"))


if __name__ == "__main__":
    unittest.main()
