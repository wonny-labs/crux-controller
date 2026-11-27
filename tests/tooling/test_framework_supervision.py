# SPDX-License-Identifier: Apache-2.0
"""Build-level checks of the framework's health supervision (specification criterion 19): the task
watchdog runs without a hardware fallback, every task watchdog channel has a callback, and the base
image's build test refuses the options that a product build must not have."""

import pathlib
import re
import unittest

import ci_map

ROOT = pathlib.Path(__file__).resolve().parents[2]


def c_code(path):
    """A C file without its comments."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(), flags=re.S)


def sources():
    return sorted(p for tree in ("framework", "app") for p in (ROOT / tree).rglob("*.c"))


class TaskWatchdogChannels(unittest.TestCase):
    def test_every_channel_has_a_callback_that_does_not_reset(self):
        calls = []
        for path in sources():
            code = c_code(path)
            for match in re.finditer(r"\btask_wdt_add\(\s*([^,]+),\s*([^,]+),", code):
                callback = match.group(2).strip()
                calls.append((path.name, callback))
                self.assertNotIn(callback, ("NULL", "0", "(void *)0"), path.name)
                self.assertRegex(callback, r"^[A-Za-z_]\w*$", path.name)
                body = code[code.index(f"static void {callback}("):]
                body = body[:body.index("\n}\n")]
                for word in ("sys_reboot", "crux_system_reset", "k_fatal_halt"):
                    self.assertNotIn(word, body, f"{path.name}: {callback}")
        # The one place that activates channels is the supervisor's port.
        self.assertEqual([("supervisor_zephyr.c", "channel_expired")], calls)

    def test_the_task_watchdog_has_no_hardware_behind_it(self):
        code = c_code(ROOT / "framework" / "os" / "supervisor_zephyr.c")
        self.assertIn("task_wdt_init(NULL)", code)
        self.assertIn("!IS_ENABLED(CONFIG_TASK_WDT_HW_FALLBACK)", code)
        kconfig = (ROOT / "zephyr" / "Kconfig").read_text()
        self.assertIn("depends on CRUX_SYSTEM && TASK_WDT && !TASK_WDT_HW_FALLBACK", kconfig)

    @ci_map.needs_tomllib
    def test_the_base_build_refuses_the_development_options_of_supervision(self):
        run = ci_map.run("base-config")
        for option in ("CONFIG_TASK_WDT_HW_FALLBACK=y", "CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG=y",
                       "CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION=y",
                       "CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG=y"):
            self.assertIn(option, run)
        self.assertIn("CONFIG_CRUX_CONTROLLER_WATCHDOG_TIMEOUT_MS", run)
        self.assertIn("timeout % 500", run)

    def test_fault_injection_cannot_reach_a_board_image(self):
        kconfig = (ROOT / "zephyr" / "Kconfig").read_text()
        block = kconfig[kconfig.index("config CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION"):]
        block = block[:block.index("\nconfig ") if "\nconfig " in block else len(block)]
        self.assertIn("depends on BOARD_NATIVE_SIM", block)
        cmake = (ROOT / "zephyr" / "CMakeLists.txt").read_text()
        self.assertIn("fault injection is for the native_sim scenarios only", cmake)


if __name__ == "__main__":
    unittest.main()
