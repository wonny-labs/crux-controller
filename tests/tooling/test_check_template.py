# SPDX-License-Identifier: Apache-2.0
"""Tests of scripts/check_template.py, the checks of the application template folder.

The rules held here:

- criterion 48: a build file of the template (CMakeLists.txt or *.cmake) adds no source, subdirectory,
  included file or module from outside the template folder, and adds no include path;
- criterion 49: no file of a copy holds an absolute path or a relative path that leaves the copy;
- the template folder of this repository passes both checks.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_template.py"
sys.path.insert(0, str(ROOT / "scripts"))

import check_template  # noqa: E402

CMAKE_HEAD = ("cmake_minimum_required(VERSION 3.20.0)\n"
              "find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})\n"
              "project(product LANGUAGES C)\n")


class Folder:
    """A throwaway template folder with files written from a dict."""

    def __init__(self, files):
        self._dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._dir.name) / "template"
        self.root.mkdir()
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def close(self):
        self._dir.cleanup()


def build_problems(files):
    folder = Folder(files)
    try:
        return check_template.build_file_problems(folder.root)
    finally:
        folder.close()


def path_problems(files):
    folder = Folder(files)
    try:
        return check_template.path_problems(folder.root)
    finally:
        folder.close()


def cmake(body):
    return {"app/CMakeLists.txt": CMAKE_HEAD + body, "app/src/main.c": ""}


class BuildFiles(unittest.TestCase):
    def test_sources_of_the_folder_pass(self):
        body = ("target_sources(app PRIVATE src/main.c ${CMAKE_CURRENT_SOURCE_DIR}/src/other.c)\n"
                "target_link_libraries(app PRIVATE controller::framework)\n"
                "controller_framework_image()\n")
        self.assertEqual([], build_problems(cmake(body)))

    def test_a_source_outside_the_folder_fails(self):
        for argument in ("../../framework/src/framework.c", "/opt/sources/x.c", "../../../x.c",
                         "${ZEPHYR_BASE}/samples/x.c", "$ENV{HOME}/x.c",
                         "${ZEPHYR_CRUX_CONTROLLER_MODULE_DIR}/framework/src/startup.c",
                         "${CMAKE_CURRENT_SOURCE_DIR}/../../x.c", "$<TARGET_PROPERTY:x,SOURCES>"):
            with self.subTest(argument=argument):
                problems = build_problems(cmake(f"target_sources(app PRIVATE {argument})\n"))
                self.assertEqual(1, len(problems), problems)
                self.assertIn(argument, problems[0])

    def test_a_relative_source_that_stays_in_the_folder_passes(self):
        files = {**cmake("target_sources(app PRIVATE ../common/shared.c)\n"), "common/shared.c": ""}
        self.assertEqual([], build_problems(files))

    def test_every_command_that_adds_sources_or_files_is_read(self):
        for command in ("zephyr_library_sources(../../x.c)", "zephyr_sources(../../x.c)",
                        "zephyr_library_sources_ifdef(CONFIG_X ../../x.c)", "add_subdirectory(../../framework fw)",
                        "include(../../framework/management/management.cmake)", "add_library(lib STATIC ../../x.c)",
                        "add_executable(tool ../../x.c)", "configure_file(../../x.in out.h)",
                        "file(GLOB extra ../../*.c)", "aux_source_directory(../../framework/src extra)"):
            with self.subTest(command=command):
                self.assertEqual(1, len(build_problems(cmake(command + "\n"))), command)

    def test_a_quoted_or_multi_line_argument_is_read(self):
        body = 'target_sources(app\n    PRIVATE\n    "../../framework/src/framework.c"\n)\n'
        self.assertEqual(1, len(build_problems(cmake(body))))

    def test_a_comment_is_not_read(self):
        body = "# target_sources(app PRIVATE ../../x.c)\ntarget_sources(app PRIVATE src/main.c) # ../../y.c\n"
        self.assertEqual([], build_problems(cmake(body)))

    def test_an_include_path_fails(self):
        for command in ("include_directories(src)", "target_include_directories(app PRIVATE src)",
                        "zephyr_include_directories(src)", "zephyr_library_include_directories(src)",
                        "target_compile_options(app PRIVATE -Isrc)",
                        "target_compile_options(app PRIVATE -include ../../x.h)"):
            with self.subTest(command=command):
                self.assertEqual(1, len(build_problems(cmake(command + "\n"))), command)

    def test_a_module_from_outside_the_folder_fails(self):
        for command in ("set(EXTRA_ZEPHYR_MODULES /opt/module)", "list(APPEND ZEPHYR_EXTRA_MODULES ../../x)"):
            with self.subTest(command=command):
                self.assertEqual(1, len(build_problems(cmake(command + "\n"))), command)

    def test_a_cmake_file_anywhere_in_the_folder_is_read(self):
        files = {"app/cmake/extra.cmake": "target_sources(app PRIVATE ../../../x.c)\n"}
        problems = build_problems(files)
        self.assertEqual(1, len(problems))
        self.assertIn("app/cmake/extra.cmake:1", problems[0])

    def test_find_package_of_zephyr_is_allowed(self):
        self.assertEqual([], build_problems(cmake("")))


class Paths(unittest.TestCase):
    def test_a_clean_copy_passes(self):
        files = {"west.yml": "manifest:\n  remotes:\n    - name: wonny-labs\n      url-base: https://github.com/wonny-labs\n",
                 "app/boards/native_sim_native_64.overlay": "/delete-node/ &storage_partition;\n/ {\n  chosen { };\n};\n"
                                                  "mount-point = \"/RAM:\";\n",
                 "app/src/main.c": "/* A comment. */\n// Another.\n#include <crux/logging.h>\n",
                 "app/CMakeLists.txt": CMAKE_HEAD + "target_sources(app PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src/main.c)\n",
                 "README.md": "Run `cp -R crux-controller/template product-workspace/product`.\n"
                              "See [the guide](https://github.com/wonny-labs/crux-controller/blob/main/docs/x.md).\n"}
        self.assertEqual([], path_problems(files))

    def test_an_absolute_path_fails(self):
        for text in ("path: /home/user/product\n", "cache: /tmp/x/y\n", "C:\\work\\product\n", "C:/work/x\n",
                     "~/zephyrproject/zephyr\n", "url-base: file:///srv/git\n", '"/opt/zephyr-sdk/bin"\n'):
            with self.subTest(text=text):
                problems = path_problems({"west.yml": text})
                self.assertEqual(1, len(problems), problems)
                self.assertIn("west.yml:1", problems[0])

    def test_a_relative_path_that_leaves_the_copy_fails(self):
        problems = path_problems({"app/src/main.c": '#include "../../../framework/src/x.h"\n'})
        self.assertEqual(1, len(problems), problems)
        problems = path_problems({"README.md": "See [the page](../docs/x.md).\n"})
        self.assertEqual(1, len(problems), problems)

    def test_a_relative_path_inside_the_copy_passes(self):
        self.assertEqual([], path_problems({"app/src/main.c": '#include "../common/x.h"\n', "app/common/x.h": ""}))

    def test_the_git_folder_and_a_build_folder_are_not_read(self):
        files = {".git/config": "url = /srv/git/product\n", "build/CMakeCache.txt": "/home/user/x/y\n",
                 "app/build/zephyr/x.txt": "/home/user/x/y\n"}
        self.assertEqual([], path_problems(files))

    def test_a_binary_file_is_skipped(self):
        folder = Folder({})
        try:
            (folder.root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe/home/user/x")
            self.assertEqual([], check_template.path_problems(folder.root))
        finally:
            folder.close()


class CommandLine(unittest.TestCase):
    def invoke(self, files, *extra):
        folder = Folder(files)
        self.addCleanup(folder.close)
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(folder.root), *extra],
                              capture_output=True, text=True)

    def test_exit_zero_when_clean(self):
        result = self.invoke(cmake("target_sources(app PRIVATE src/main.c)\n"))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_exit_one_and_report_when_violated(self):
        result = self.invoke(cmake("target_sources(app PRIVATE ../../x.c)\n"))
        self.assertEqual(1, result.returncode)
        self.assertIn("app/CMakeLists.txt:4", result.stdout)

    def test_each_check_runs_alone(self):
        files = {**cmake("target_sources(app PRIVATE src/main.c)\n"), "west.yml": "path: /home/user/x\n"}
        self.assertEqual(0, self.invoke(files, "--check", "build").returncode)
        self.assertEqual(1, self.invoke(files, "--check", "paths").returncode)

    def test_exit_two_for_a_missing_folder(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", "/nonexistent-template"],
                                capture_output=True, text=True)
        self.assertEqual(2, result.returncode)


class ThisRepository(unittest.TestCase):
    def test_the_template_folder_passes_both_checks(self):
        template = ROOT / "template"
        self.assertTrue(template.is_dir())
        self.assertEqual([], check_template.build_file_problems(template))
        self.assertEqual([], check_template.path_problems(template))


if __name__ == "__main__":
    unittest.main()
