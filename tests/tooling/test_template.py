# SPDX-License-Identifier: Apache-2.0
"""Checks of the application template folder (specification section 7.5, criteria 47 to 49).

The rules held here:

- the folder has the shape of Crux's templates/product: a west manifest repository with app/, its
  CMake file, prj.conf, main(), the board files of native_sim and of the reference board, and a
  first test;
- the manifest names the framework, imports its manifest (so Crux comes at the framework's pin),
  follows main until the joining steps pin it, and holds the record of the template revision;
- main() passes a descriptor with the four mandatory entries to the start function, and the first
  test and the CI run look for the log lines that main() writes;
- prj.conf holds no board value, no symbol is set in prj.conf and again in a board file, and the
  reference board files give the values of the base image on that board;
- the README documents the joining steps that the joining test runs.
"""

import pathlib
import re
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "template"
APP = TEMPLATE / "app"
BOARDS = APP / "boards"
REFERENCE = "mimxrt1060_evk_mimxrt1062_qspi"


def assignments(path):
    """{symbol: value} of a Kconfig fragment."""
    found = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("CONFIG_"):
            symbol, value = line.split("=", 1)
            found[symbol] = value
    return found


def code(path):
    """The text of a C file without its comments."""
    text = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def readme_block(heading):
    """The first ```sh block under a heading of template/README.md, as a list of lines."""
    text = (TEMPLATE / "README.md").read_text()
    section = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    block = re.search(r"```sh\n(.*?)\n```", section, re.DOTALL)
    return block.group(1).splitlines()


class Layout(unittest.TestCase):
    def test_the_folder_has_the_files_of_a_product_repository(self):
        for name in ("README.md", "west.yml", ".gitignore", "app/CMakeLists.txt", "app/prj.conf",
                     "app/src/main.c", "app/testcase.yaml", "app/boards/native_sim.conf",
                     "app/boards/native_sim.overlay", f"app/boards/{REFERENCE}.conf",
                     f"app/boards/{REFERENCE}.overlay"):
            with self.subTest(name=name):
                self.assertTrue((TEMPLATE / name).is_file(), name)

    def test_the_build_folders_are_ignored(self):
        self.assertIn("/build/", (TEMPLATE / ".gitignore").read_text().splitlines())


class Manifest(unittest.TestCase):
    def setUp(self):
        self.manifest = yaml.safe_load((TEMPLATE / "west.yml").read_text())["manifest"]

    def test_the_framework_is_the_one_project_and_imports_its_manifest(self):
        projects = {p["name"]: p for p in self.manifest["projects"]}
        self.assertEqual(["crux-controller"], list(projects))
        self.assertIs(True, projects["crux-controller"]["import"])
        self.assertEqual("product", self.manifest["self"]["path"])

    def test_the_remote_is_the_one_of_this_repository(self):
        own = yaml.safe_load((ROOT / "west.yml").read_text())["manifest"]
        crux_base = next(r["url-base"] for r in own["remotes"] if r["name"] == "crux")
        remotes = {r["name"]: r["url-base"] for r in self.manifest["remotes"]}
        self.assertEqual(crux_base, remotes[self.manifest["projects"][0]["remote"]])

    def test_the_template_follows_main_until_the_joining_steps_pin_it(self):
        self.assertEqual("main", self.manifest["projects"][0]["revision"])
        self.assertEqual("none", self.manifest["self"]["userdata"]["template-revision"])

    def test_the_mbed_group_is_on_and_no_other_optional_group(self):
        self.assertEqual(["+crux-secure-management"], self.manifest["group-filter"])


class Application(unittest.TestCase):
    def test_main_passes_a_descriptor_with_the_four_entries(self):
        text = code(APP / "src" / "main.c")
        for entry in ("init", "start", "stop", "safe_state"):
            with self.subTest(entry=entry):
                self.assertRegex(text, rf"\.{entry}\s*=\s*product_{entry},")
        self.assertRegex(text, r"controller_framework_start\(&product_app\)")
        self.assertRegex(text, r"static const controller_app_t product_app")

    def test_main_names_no_board_and_no_path_of_the_framework(self):
        for path in (APP / "src" / "main.c", APP / "CMakeLists.txt"):
            text = path.read_text().lower()
            for word in ("mimxrt", "rt1060", "evkb", "native_sim", "crux-controller", "../", "framework/src"):
                with self.subTest(path=path.name, word=word):
                    self.assertNotIn(word, text)

    def test_the_cmake_file_links_the_interface_and_calls_the_image_function(self):
        text = (APP / "CMakeLists.txt").read_text()
        self.assertIn("target_link_libraries(app PRIVATE controller::framework)", text)
        self.assertIn("controller_framework_image()", text)
        self.assertIn("target_sources(app PRIVATE src/main.c)", text)

    def test_the_first_test_looks_for_the_lines_that_main_writes_in_order(self):
        test = yaml.safe_load((APP / "testcase.yaml").read_text())
        config = test["common"]["harness_config"]
        self.assertEqual("console", test["common"]["harness"])
        self.assertIs(True, config["ordered"])
        tag = re.search(r'#define PRODUCT_LOG_TAG "([^"]+)"', (APP / "src" / "main.c").read_text()).group(1)
        self.assertEqual([f"{tag}: init", f"{tag}: start"], config["regex"])
        source = code(APP / "src" / "main.c")
        self.assertIn('product_log("init")', source)
        self.assertIn('product_log("start")', source)
        # Crux Logging on Zephyr writes "<tag>: <text>" after the module name.
        line = f"[00:00:01.000,000] <inf> crux_logging: {tag}: init"
        self.assertRegex(line, config["regex"][0])


class Configuration(unittest.TestCase):
    BOARD_WORDS = ("NATIVE", "MCUX", "RT1060", "IMX", "NXP", "FAKE_ENTROPY", "PICOLIBC", "EMUL",
                   "START_WITHOUT_WATCHDOG", "NET_CONFIG_MY", "BIND_ADDRESS", "TIME_SERVER", "LOOPBACK",
                   "RETENTION", "RETAINED_MEM", "MAIN_STACK_SIZE", "_COUNT", "HW_STACK_PROTECTION")

    def test_prj_conf_turns_the_framework_on_and_holds_no_board_value(self):
        common = assignments(APP / "prj.conf")
        self.assertEqual("y", common["CONFIG_CRUX_CONTROLLER_FRAMEWORK"])
        for symbol in common:
            for word in self.BOARD_WORDS:
                with self.subTest(symbol=symbol, word=word):
                    self.assertNotIn(word, symbol)

    def test_no_symbol_is_set_in_prj_conf_and_again_in_a_board_file(self):
        common = set(assignments(APP / "prj.conf"))
        for path in sorted(BOARDS.glob("*.conf")):
            with self.subTest(board=path.name):
                self.assertEqual(set(), common & set(assignments(path)))

    def test_the_reference_board_has_the_values_of_the_base_image(self):
        # The base image builds for this board in CI (app/prj.conf with app/conf/base.conf).
        merged = {**assignments(APP / "prj.conf"), **assignments(BOARDS / f"{REFERENCE}.conf")}
        base = {**assignments(ROOT / "app" / "prj.conf"), **assignments(ROOT / "app" / "conf" / "base.conf")}
        self.assertEqual(base, merged)

    def test_the_reference_board_overlay_has_the_roles_of_the_base_image(self):
        text = (BOARDS / f"{REFERENCE}.overlay").read_text()
        for role in ("crux-serial0 = &lpuart3;", "crux-watchdog0 = &wdog0;", "zephyr,log-uart = &logging_uarts;",
                     "controller_storage: controller-storage", "controller_retained: retention@0",
                     "local-mac-address", "reg = <0x20200000 0x7ff00>;"):
            with self.subTest(role=role):
                self.assertIn(role, text)

    def test_only_native_sim_starts_without_a_watchdog_and_uses_the_test_entropy(self):
        native = assignments(BOARDS / "native_sim.conf")
        reference = assignments(BOARDS / f"{REFERENCE}.conf")
        self.assertEqual("y", native["CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG"])
        self.assertNotIn("CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG", reference)
        for symbol in ("CONFIG_FAKE_ENTROPY_NATIVE_SIM", "CONFIG_TEST_RANDOM_GENERATOR", "CONFIG_SHELL",
                       "CONFIG_CRUX_DEVELOPMENT_IMAGE", "CONFIG_CRUX_WEB_PLAIN_HTTP_FOR_TESTS"):
            with self.subTest(symbol=symbol):
                self.assertNotEqual("y", reference.get(symbol, assignments(APP / "prj.conf").get(symbol)))
        self.assertEqual("y", reference["CONFIG_STACK_CANARIES"])
        self.assertEqual("y", reference["CONFIG_HW_STACK_PROTECTION"])
        self.assertEqual("n", assignments(APP / "prj.conf")["CONFIG_TASK_WDT_HW_FALLBACK"])

    def test_the_native_sim_overlay_has_the_roles_that_the_framework_looks_up(self):
        text = (BOARDS / "native_sim.overlay").read_text()
        for role in ("crux-serial0 = &console_emul;", "zephyr,log-uart = &logging_uarts;",
                     "controller_storage: controller-storage", "zephyr,uart-emul"):
            with self.subTest(role=role):
                self.assertIn(role, text)


class Readme(unittest.TestCase):
    def test_the_joining_steps_copy_pin_commit_and_update(self):
        steps = readme_block("Start a product")
        self.assertEqual("cp -R crux-controller/template product-workspace/product", steps[1])
        self.assertIn("crux-controller/scripts/pin_framework.py --framework crux-controller", steps[2])
        self.assertEqual(["west init -l product", "west update"], steps[-2:])
        for step in steps:
            with self.subTest(step=step):
                self.assertNotRegex(step, r"<[^>]+>")  # no placeholder: the joining test runs the steps

    def test_the_readme_states_the_decisions_of_the_template(self):
        text = (TEMPLATE / "README.md").read_text()
        for phrase in ("full commit SHA", "template-revision", "never reach a copy", "criteria 19 and 38",
                       "through the framework's manifest import", "CONFIG_FAKE_ENTROPY_NATIVE_SIM",
                       "CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG", "-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON",
                       "*Standard*", "*Project-specific workaround*", "*documented but optional*"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_build_commands_name_both_boards(self):
        steps = readme_block("Start a product")
        text = (TEMPLATE / "README.md").read_text()
        self.assertIn("west build -b native_sim/native/64", text)
        self.assertIn("west build -b mimxrt1060_evk@B/mimxrt1062/qspi", text)
        self.assertNotIn("west build", "\n".join(steps))


if __name__ == "__main__":
    unittest.main()
