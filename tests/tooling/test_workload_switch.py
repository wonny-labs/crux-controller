"""Checks that the workload's build switch belongs to the product, not to a Crux provider.

The workload runs on Zephyr threads and a message queue behind the adapter zone app/os, so the
build keys on the product's own Kconfig symbol CONFIG_CRUX_CONTROLLER_S1. No file of the product
selects, depends on or tests the Crux Thread, Sync or Queue providers, and the worker stack size of
every step is the number that it was before the switch moved.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "app"
KCONFIG = APP / "Kconfig"
CONF = APP / "conf"
PROVIDER_SYMBOLS = ("CRUX_THREAD", "CRUX_QUEUE", "CRUX_SYNC")


def without_hash_comments(path):
    return "\n".join(line.split("#", 1)[0] for line in pathlib.Path(path).read_text().splitlines())


def c_code(path):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", pathlib.Path(path).read_text(), flags=re.S)


def conf_options(path):
    options = {}
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            options[name.strip()] = value.strip()
    return options


def kconfig_block(name):
    text = without_hash_comments(KCONFIG)
    block = re.search(rf"^config {name}\n(.*?)(?=^config |^source |\Z)", text, re.S | re.M)
    assert block is not None, f"no config {name} in app/Kconfig"
    return block.group(1)


def kconfig_default(name):
    return int(re.search(r"^\s*default (\d+)\s*$", kconfig_block(name), re.M).group(1))


def resolved(*fragments):
    """The options that the confs set, later fragments winning, as the build applies them."""
    options = {}
    for fragment in fragments:
        options.update(conf_options(fragment))
    return options


def worker_stack(*fragments):
    """The stack bytes of each workload thread in an image built from these fragments, or None
    when the image has no workload."""
    options = resolved(*fragments)
    if options.get("CONFIG_CRUX_CONTROLLER_S1") != "y":
        return None
    return int(options.get("CONFIG_CRUX_CONTROLLER_WORKER_STACK", kconfig_default("CRUX_CONTROLLER_WORKER_STACK")))


class ProductSymbol(unittest.TestCase):
    def test_the_product_defines_the_workload_symbol(self):
        block = kconfig_block("CRUX_CONTROLLER_S1")
        self.assertIn("bool", block)
        self.assertIn("MULTITHREADING", block)

    def test_the_symbol_asks_for_the_64_bit_timeouts_that_the_providers_used_to_select(self):
        # The adapter builds absolute deadlines. Crux Thread and Crux Queue selected this option.
        self.assertRegex(kconfig_block("CRUX_CONTROLLER_S1"),
                         re.compile(r"^\s*select TIMEOUT_64BIT\s*$", re.M))

    def test_app_kconfig_names_no_provider_symbol(self):
        text = without_hash_comments(KCONFIG)
        for name in PROVIDER_SYMBOLS:
            self.assertIsNone(re.search(rf"\b{name}\b", text), name)

    def test_the_later_steps_and_the_stack_option_depend_on_the_workload_symbol(self):
        self.assertIn("depends on CRUX_CONTROLLER_S1 && CRUX_SOCKETS && CRUX_NETIF",
                      kconfig_block("CRUX_CONTROLLER_S2"))
        self.assertIn("depends on CRUX_CONTROLLER_S1 && CRUX_FILE_FATFS_RT1060",
                      kconfig_block("CRUX_CONTROLLER_S3"))
        self.assertIn("depends on CRUX_CONTROLLER_S1", kconfig_block("CRUX_CONTROLLER_WORKER_STACK"))

    def test_the_stack_option_keeps_the_range_that_the_provider_option_imposed(self):
        # The old BUILD_ASSERT kept this option equal to CRUX_THREAD_STACK_BYTES, whose range is
        # 1024 to 65536 in the provider at the pinned revision.
        self.assertRegex(kconfig_block("CRUX_CONTROLLER_WORKER_STACK"),
                         re.compile(r"^\s*range 1024 65536\s*$", re.M))

    def test_every_product_option_that_a_conf_sets_is_defined(self):
        defined = set(re.findall(r"^config (CRUX_CONTROLLER_\w+)", without_hash_comments(KCONFIG), re.M))
        for path in sorted(CONF.glob("*.conf")):
            for name in conf_options(path):
                if name.startswith("CONFIG_CRUX_CONTROLLER_"):
                    self.assertIn(name[len("CONFIG_"):], defined, f"{path.name}: {name}")


class BuildFiles(unittest.TestCase):
    def test_the_application_build_keys_on_the_product_symbol(self):
        text = without_hash_comments(APP / "CMakeLists.txt")
        self.assertRegex(text, re.compile(r"^if\(CONFIG_CRUX_CONTROLLER_S1\)", re.M))
        for name in PROVIDER_SYMBOLS:
            self.assertNotIn(f"CONFIG_{name}", text)

    def test_the_workload_blocks_of_the_application_stay_inside_the_switch(self):
        text = without_hash_comments(APP / "CMakeLists.txt")
        start = text.index("if(CONFIG_CRUX_CONTROLLER_S1)")
        for needle in ("add_subdirectory(../workload", "add_subdirectory(os)",
                       "src/workload_thread.c", "if(CONFIG_CRUX_CONTROLLER_S2)",
                       "if(CONFIG_CRUX_CONTROLLER_S3)"):
            self.assertGreater(text.index(needle), start, needle)

    def test_the_composition_keys_on_the_product_symbol(self):
        text = c_code(APP / "src" / "composition.c")
        self.assertEqual(2, len(re.findall(r"#ifdef CONFIG_CRUX_CONTROLLER_S1\b", text)))
        for name in PROVIDER_SYMBOLS:
            self.assertNotIn(f"CONFIG_{name}", text)

    def test_no_source_or_build_file_of_the_product_keys_on_a_provider_symbol(self):
        paths = [p for p in APP.rglob("*") if p.is_file() and p.suffix in {".c", ".h", ".txt", ".cmake"}]
        paths += [p for p in (ROOT / "workload").rglob("*") if p.is_file() and p.suffix in {".c", ".h", ".txt"}]
        paths += list((ROOT / "tests").rglob("CMakeLists.txt"))
        for path in paths:
            text = c_code(path) if path.suffix in {".c", ".h"} else without_hash_comments(path)
            for name in PROVIDER_SYMBOLS:
                self.assertIsNone(re.search(rf"\bCONFIG_{name}\b", text), f"{path.relative_to(ROOT)}: {name}")


class Confs(unittest.TestCase):
    def fragments(self):
        return sorted(CONF.glob("*.conf")) + [APP / "prj.conf"] + sorted(
            (ROOT / "tests" / "native_sim").glob("*/prj.conf")
        )

    def test_the_workload_conf_selects_the_product_symbol(self):
        self.assertEqual("y", conf_options(CONF / "s1.conf").get("CONFIG_CRUX_CONTROLLER_S1"))

    def test_no_conf_of_the_product_selects_a_provider_the_product_no_longer_uses(self):
        for path in self.fragments():
            for name in conf_options(path):
                for symbol in PROVIDER_SYMBOLS:
                    self.assertFalse(
                        name == f"CONFIG_{symbol}" or name.startswith(f"CONFIG_{symbol}_"),
                        f"{path.relative_to(ROOT)}: {name}",
                    )

    def test_the_skeleton_step_has_no_workload(self):
        self.assertNotIn("CONFIG_CRUX_CONTROLLER_S1", conf_options(APP / "prj.conf"))
        self.assertIsNone(worker_stack(APP / "prj.conf"))

    def test_the_scenario_asks_for_64_bit_timeouts_itself(self):
        # It builds the adapter without app/Kconfig, so the product symbol cannot select it.
        options = conf_options(ROOT / "tests" / "native_sim" / "s1" / "prj.conf")
        self.assertEqual("y", options.get("CONFIG_TIMEOUT_64BIT"))


class EffectiveWorkerStack(unittest.TestCase):
    """The stack bytes of each workload thread, per step, as they were before the switch moved:
    4096 where nothing sets the option (S1, S3, the scenario) and 8192 in S2."""

    PROJECT = APP / "prj.conf"

    def test_s1_builds_4096_byte_stacks(self):
        self.assertEqual(4096, worker_stack(self.PROJECT, CONF / "s1.conf"))

    def test_s2_builds_8192_byte_stacks(self):
        self.assertEqual(8192, worker_stack(self.PROJECT, CONF / "s1.conf", CONF / "s2.conf"))

    def test_s3_builds_4096_byte_stacks(self):
        self.assertEqual(4096, worker_stack(self.PROJECT, CONF / "s1.conf", CONF / "s3.conf"))

    def test_the_scenario_uses_the_adapter_default_and_it_equals_the_product_default(self):
        # No app/Kconfig in the scenario: the adapter's fallback applies.
        self.assertNotIn("CONFIG_CRUX_CONTROLLER_WORKER_STACK",
                         conf_options(ROOT / "tests" / "native_sim" / "s1" / "prj.conf"))
        adapter = c_code(APP / "os" / "workload_os_zephyr.c")
        fallback = int(re.search(r"#define WORKLOAD_OS_STACK_DEFAULT_BYTES (\d+)", adapter).group(1))
        self.assertEqual(4096, fallback)
        self.assertEqual(fallback, kconfig_default("CRUX_CONTROLLER_WORKER_STACK"))

    def test_the_default_is_4096_and_s2_is_the_only_override(self):
        self.assertEqual(4096, kconfig_default("CRUX_CONTROLLER_WORKER_STACK"))
        for path in sorted(CONF.glob("*.conf")):
            has = "CONFIG_CRUX_CONTROLLER_WORKER_STACK" in conf_options(path)
            self.assertEqual(path.name == "s2.conf", has, path.name)


if __name__ == "__main__":
    unittest.main()
