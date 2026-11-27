# SPDX-License-Identifier: Apache-2.0
"""scripts/analyze_zephyr.py: clang-tidy over this repository's sources of a native_sim build.

Criterion 41, delivery stage 3: clang-tidy also analyses the Zephyr sources from the native_sim compile
database. The script keeps the options that the analysis needs and drops the GCC options that clang
does not accept; the base job runs it on the application scenario's build (scripts/ci/checks.toml).
"""

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "tooling"))

import analyze_zephyr  # noqa: E402
import ci_map  # noqa: E402


class KeptArguments(unittest.TestCase):
    def test_defines_includes_forced_includes_and_the_standard_are_kept(self):
        command = ["/usr/bin/gcc", "-DFOO=1", "-D", "BAR", "-Iinc", "-isystem", "/sys", "-imacros",
                   "autoconf.h", "-include", "first.h", "-std=c17", "-m64", "-nostdinc", "-c", "a.c",
                   "-o", "a.o"]
        self.assertEqual(["-DFOO=1", "-D", "BAR", "-Iinc", "-isystem", "/sys", "-imacros", "autoconf.h",
                          "-include", "first.h", "-std=c17", "-m64", "-nostdlibinc"],
                         analyze_zephyr.kept_arguments(command))

    def test_gccs_own_header_folder_is_left_out(self):
        # clang refuses GCC's stdatomic.h; its built-in headers take the place of GCC's.
        command = ["gcc", "-isystem", "/usr/lib/gcc/x86_64-linux-gnu/13/include", "-isystem",
                   "/ws/modules/picolibc/include", "-I/usr/lib/gcc/x86_64-linux-gnu/13/include-fixed"]
        self.assertEqual(["-isystem", "/ws/modules/picolibc/include"],
                         analyze_zephyr.kept_arguments(command))

    def test_gcc_options_that_clang_refuses_are_dropped(self):
        command = ["gcc", "-fno-reorder-functions", "--param=min-pagesize=0", "-fno-defer-pop",
                   "-specs=picolibc.specs", "-mtp=soft", "-fno-printf-return-value", "-Wall", "-Werror",
                   "-O2", "-g", "-MD", "-MT", "x", "-MF", "x.d", "-o", "x.o", "-c", "x.c"]
        self.assertEqual([], analyze_zephyr.kept_arguments(command))

    def test_a_command_string_is_split_like_the_argument_list(self):
        entry = {"directory": "/b", "file": "a.c", "command": "gcc -DX='a b' -Iinc -c a.c"}
        self.assertEqual(["gcc", "-DX=a b", "-Iinc", "-c", "a.c"], analyze_zephyr.arguments_of(entry))


class Rewrite(unittest.TestCase):
    def test_only_the_given_sources_are_kept_with_clang_as_the_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            ours = pathlib.Path(directory) / "framework.c"
            ours.write_text("")
            entries = [
                {"directory": directory, "file": str(ours), "arguments": ["gcc", "-DA", "-fno-common",
                                                                          "-c", str(ours)]},
                {"directory": directory, "file": "/zephyr/kernel/sched.c",
                 "arguments": ["gcc", "-c", "/zephyr/kernel/sched.c"]},
            ]
            rewritten = analyze_zephyr.rewrite(entries, [ours.resolve()])
            self.assertEqual(1, len(rewritten))
            self.assertEqual(["clang", "-DA", "-c", str(ours.resolve())], rewritten[0]["arguments"])
            json.dumps(rewritten)

    def test_an_entry_with_a_relative_file_is_resolved_against_its_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            ours = pathlib.Path(directory) / "fixture.c"
            ours.write_text("")
            entries = [{"directory": directory, "file": "fixture.c", "command": "gcc -c fixture.c"}]
            rewritten = analyze_zephyr.rewrite(entries, [ours.resolve()])
            self.assertEqual(str(ours.resolve()), rewritten[0]["file"])


class CiCheck(unittest.TestCase):
    @ci_map.needs_tomllib
    def test_the_base_job_analyses_the_application_scenario_build(self):
        run = ci_map.run("static-analysis-zephyr")
        self.assertIn("controller.framework.native_sim.application", run)
        self.assertIn("compile_commands.json", run)
        self.assertIn("scripts/analyze_zephyr.py", run)

    def test_the_script_finds_its_repository_from_its_own_place(self):
        # CI starts the check in the workspace folder, which is no Git repository.
        script = (ROOT / "scripts" / "analyze_zephyr.py").read_text()
        self.assertIn("pathlib.Path(__file__).resolve().parents[1]", script)
        self.assertNotIn("analyze_host.repo_root()", script)


class PrerequisiteRefused(unittest.TestCase):
    """Criterion 27: a start prerequisite on a service that the build leaves out fails the build."""

    def test_the_module_refuses_it_with_a_clear_message(self):
        cmake = (ROOT / "zephyr" / "CMakeLists.txt").read_text()
        self.assertIn('"TIME:CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC:time synchronisation"', cmake)
        self.assertIn("which this build leaves out", cmake)
        kconfig = (ROOT / "zephyr" / "Kconfig").read_text()
        block = kconfig[kconfig.index("config CRUX_CONTROLLER_PREREQUISITE_TIME"):]
        block = block[:block.index("\nconfig ")]
        self.assertNotIn("depends on", block)

    @ci_map.needs_tomllib
    def test_the_base_job_checks_the_refusal(self):
        run = ci_map.run("base-prerequisite-refused")
        self.assertIn("-DCONFIG_CRUX_CONTROLLER_PREREQUISITE_TIME=y", run)
        self.assertIn("-DCONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC=n", run)
        self.assertIn("which this build leaves out", run)


if __name__ == "__main__":
    unittest.main()
