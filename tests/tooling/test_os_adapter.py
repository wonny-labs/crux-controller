"""Checks of the OS adapter zone app/os: its build files, its link to the application, the
provider constants and assertions in its source, and the port header that joins it to app/src."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "app"
ZONE = APP / "os"
ADAPTER = ZONE / "workload_os_zephyr.c"
PORT = APP / "src" / "workload_os.h"
DOMAIN = APP / "src" / "workload_thread.c"


def code(path):
    """The file without CMake comments, one string."""
    return "\n".join(line.split("#", 1)[0] for line in pathlib.Path(path).read_text().splitlines())


def c_code(path):
    """A C file without its comments."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", pathlib.Path(path).read_text(), flags=re.S)


def includes(path):
    return re.findall(r"^\s*#\s*include\s*([<\"][^>\"]+[>\"])", pathlib.Path(path).read_text(), re.M)


class ZoneBuildFiles(unittest.TestCase):
    """The adapter is one source of the application target, not a library of its own.

    A static library of its own is linked after the kernel archive, which left the msgq objects of
    the kernel out of the link. A source of the application target is the shape that applications
    use for kernel calls.
    """

    def text(self):
        return code(ZONE / "CMakeLists.txt")

    def test_the_zone_adds_its_source_to_the_application_target(self):
        self.assertRegex(
            self.text(),
            r"target_sources\(app PRIVATE \$\{CMAKE_CURRENT_LIST_DIR\}/workload_os_zephyr\.c\)",
        )

    def test_the_zone_is_not_a_library(self):
        text = self.text()
        self.assertNotIn("add_library", text)
        self.assertNotIn("target_link_libraries", text)

    def test_the_zone_links_no_crux_target(self):
        self.assertNotIn("crux", self.text())

    def test_the_zone_adds_no_include_path(self):
        for line in self.text().splitlines():
            for word in ("include_directories", "-include", "-I"):
                self.assertNotIn(word, line, line.strip())

    def test_the_zone_takes_sources_from_its_own_directory_only(self):
        for line in self.text().splitlines():
            if "target_sources" in line:
                self.assertNotIn("..", line, line.strip())

    def test_the_zone_keeps_the_application_warning_level_for_its_source(self):
        # The property is directory scoped, so the zone names the directory of the application
        # target. The test scenario builds this file too and has no other flags for it.
        self.assertRegex(
            self.text(),
            r"set_source_files_properties\(\$\{CMAKE_CURRENT_LIST_DIR\}/workload_os_zephyr\.c\s+"
            r"TARGET_DIRECTORY app\s+PROPERTIES COMPILE_OPTIONS \"-Wall;-Wextra;-Werror\"\)",
        )

    def test_the_zone_has_exactly_one_source_and_one_build_file(self):
        names = sorted(p.name for p in ZONE.iterdir())
        self.assertEqual(["CMakeLists.txt", "workload_os_zephyr.c"], names)


class ApplicationBuildFiles(unittest.TestCase):
    def text(self):
        return code(APP / "CMakeLists.txt")

    def test_the_application_adds_the_zone_next_to_the_workload(self):
        text = self.text()
        self.assertRegex(text, r"add_subdirectory\(os\)")
        self.assertLess(text.index("add_subdirectory(../workload"), text.index("add_subdirectory(os)"))

    def test_the_application_links_no_zone_library(self):
        for links in re.findall(r"target_link_libraries\(([^)]*)\)", self.text()):
            self.assertNotIn("os", links.split(), links)

    def test_the_application_still_links_the_workload(self):
        self.assertRegex(self.text(), r"target_link_libraries\(app PRIVATE[^)]*\bworkload\b")

    def test_the_application_no_longer_links_crux_thread_or_queue(self):
        text = self.text()
        self.assertNotIn("crux::thread", text)
        self.assertNotIn("crux::queue", text)

    def test_the_application_keeps_time_and_logging(self):
        text = self.text()
        self.assertIn("crux::time", text)
        self.assertIn("crux::logging", text)

    def test_no_build_file_of_the_application_links_thread_or_queue(self):
        for path in sorted(APP.rglob("CMakeLists.txt")):
            for target in ("crux::thread", "crux::queue", "crux::sync", "crux::serial"):
                self.assertNotIn(target, code(path), f"{path.relative_to(ROOT)}: {target}")

    def test_the_application_names_the_zone_source_only_in_the_zone(self):
        self.assertNotIn("workload_os_zephyr", self.text())


class Scenario(unittest.TestCase):
    """The native_sim scenario builds the real adapter and the real domain source."""

    TEXT = code(ROOT / "tests" / "native_sim" / "s1" / "CMakeLists.txt")

    def test_it_builds_the_zone_of_the_application(self):
        self.assertRegex(self.TEXT, r"add_subdirectory\(\$\{controller_root\}/app/os os\)")

    def test_it_links_no_zone_library_and_no_thread_or_queue_library(self):
        for links in re.findall(r"target_link_libraries\(([^)]*)\)", self.TEXT):
            self.assertNotIn("os", links.split(), links)
        self.assertNotIn("crux::thread", self.TEXT)
        self.assertNotIn("crux::queue", self.TEXT)

    def test_it_still_builds_the_application_domain_source(self):
        self.assertIn("${controller_root}/app/src/workload_thread.c", self.TEXT)

    def test_it_does_not_copy_the_adapter(self):
        self.assertNotIn("workload_os_zephyr.c", self.TEXT)


class AdapterSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.SOURCE = ADAPTER.read_text()

    def test_it_names_the_four_constants(self):
        for name in (
            "WORKLOAD_OS_THREAD_PRIORITY",
            "WORKLOAD_OS_STACK_BYTES",
            "WORKLOAD_OS_QUEUE_DEPTH",
            "WORKLOAD_OS_ITEM_BYTES",
        ):
            self.assertRegex(self.SOURCE, rf"#define {name}\b", name)

    def test_it_cites_the_provider_files_at_the_pinned_revision(self):
        self.assertIn("37c92b18", self.SOURCE)
        self.assertIn("components/thread/ports/zephyr/thread_native.c", self.SOURCE)
        self.assertIn("components/queue/ports/zephyr/queue_port.c", self.SOURCE)
        self.assertRegex(self.SOURCE, r"thread_native\.c:\d+")
        self.assertRegex(self.SOURCE, r"queue_port\.c:\d+")

    def test_it_asserts_the_provider_numbers_at_build_time(self):
        self.assertGreaterEqual(len(re.findall(r"BUILD_ASSERT\(", self.SOURCE)), 5)
        self.assertRegex(self.SOURCE, r"BUILD_ASSERT\(CONFIG_NUM_PREEMPT_PRIORITIES > 6")
        self.assertRegex(self.SOURCE, r"BUILD_ASSERT\(WORKLOAD_OS_THREAD_PRIORITY == 5\b")
        self.assertRegex(self.SOURCE, r"BUILD_ASSERT\(WORKLOAD_OS_QUEUE_DEPTH == 8\b")
        self.assertRegex(self.SOURCE, r"BUILD_ASSERT\(WORKLOAD_OS_ITEM_BYTES == 8\b")

    def test_it_uses_the_provider_deadline_not_k_msec(self):
        self.assertIn("K_TIMEOUT_ABS_TICKS", self.SOURCE)
        self.assertIn("k_ms_to_ticks_ceil64", self.SOURCE)
        self.assertIn("k_uptime_ticks", self.SOURCE)
        # Comments may explain the difference, so only the code is read here.
        stripped = c_code(ADAPTER)
        self.assertNotIn("K_MSEC", stripped)
        self.assertNotIn("k_msleep", stripped)

    def test_it_uses_the_zephyr_calls_the_port_needs(self):
        for call in ("k_thread_create", "k_thread_join", "k_msgq_put", "k_msgq_get", "k_sleep"):
            self.assertIn(call, self.SOURCE, call)
        self.assertIn("K_THREAD_STACK_DEFINE", self.SOURCE)

    def test_it_includes_the_kernel_header_and_the_port_by_a_relative_path(self):
        found = includes(ADAPTER)
        self.assertIn("<zephyr/kernel.h>", found)
        self.assertIn('"../src/workload_os.h"', found)

    def test_it_includes_no_frozen_crux_header(self):
        # Its comments cite the provider, so the check reads include directives only.
        found = includes(ADAPTER)
        for name in ("crux/thread.h", "crux/queue.h", "crux/sync.h", "crux/serial.h"):
            self.assertNotIn(f"<{name}>", found, name)


class PortHeader(unittest.TestCase):
    def test_it_includes_only_iso_c_and_the_workload_header(self):
        for name in includes(PORT):
            self.assertIn(name, ("<stdint.h>", "<stddef.h>", "<stdbool.h>", '"workload.h"'), name)

    def test_it_declares_the_result_enum_and_the_calls(self):
        text = PORT.read_text()
        for name in (
            "WORKLOAD_OS_OK",
            "WORKLOAD_OS_TIMEOUT",
            "WORKLOAD_OS_FULL",
            "WORKLOAD_OS_ERROR",
            "workload_os_start",
            "workload_os_queue_send",
            "workload_os_queue_receive",
            "workload_os_sleep_ms",
            "workload_os_join_producer",
            "workload_os_join_consumer",
            "workload_os_release",
        ):
            self.assertIn(name, text, name)


class DomainSource(unittest.TestCase):
    def test_the_workload_thread_source_has_no_thread_queue_or_zephyr_header(self):
        found = includes(DOMAIN)
        for name in ("<crux/thread.h>", "<crux/queue.h>"):
            self.assertNotIn(name, found, name)
        self.assertFalse([n for n in found if "zephyr" in n], found)

    def test_the_workload_thread_source_calls_no_thread_or_queue_function(self):
        text = DOMAIN.read_text()
        self.assertNotRegex(text, r"\bcrux_(thread|queue)_\w+")
        self.assertNotRegex(text, r"\bk_[a-z_]+\(")

    def test_the_workload_thread_source_calls_the_port(self):
        self.assertIn('#include "workload_os.h"', DOMAIN.read_text())

    def test_no_file_under_app_src_includes_a_zephyr_header(self):
        for path in sorted((APP / "src").iterdir()):
            for name in includes(path):
                self.assertNotIn("zephyr", name, f"{path.name}: {name}")

    def test_no_file_under_app_src_includes_a_frozen_crux_header(self):
        for path in sorted((APP / "src").iterdir()):
            for name in includes(path):
                self.assertNotIn(
                    name.strip("<>"),
                    ("crux/thread.h", "crux/sync.h", "crux/queue.h", "crux/serial.h"),
                    f"{path.name}: {name}",
                )


if __name__ == "__main__":
    unittest.main()
