# SPDX-License-Identifier: Apache-2.0
"""Checks of the format and static-analysis setup: the criteria files, the two scripts and the CI
job that runs them. The criteria are the ones that the Crux repository applies to its own code."""

import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import analyze_host  # noqa: E402
import ci_map  # noqa: E402

CLANG_FORMAT_VERSION = "18.1.8"
CLANG_TIDY_PACKAGE = "clang-tidy-18=1:18.1.3-1ubuntu1"


def read(name):
    return (ROOT / name).read_text()


def mapping(name):
    """Top-level `key: value` pairs of a flat YAML file such as .clang-format."""
    pairs = {}
    for line in read(name).splitlines():
        match = re.match(r"^([A-Za-z]+):\s*(.*?)\s*$", line)
        if match and not line.startswith("#"):
            pairs[match.group(1)] = match.group(2)
    return pairs


class FormatCriteria(unittest.TestCase):
    def test_the_format_style_is_the_crux_style(self):
        self.assertEqual(
            {
                "BasedOnStyle": "LLVM",
                "BreakBeforeBraces": "Linux",
                "IndentWidth": "4",
                "ColumnLimit": "100",
                "SortIncludes": "CaseSensitive",
                "AllowShortFunctionsOnASingleLine": "None",
                "AllowShortBlocksOnASingleLine": "Never",
                "IndentExternBlock": "NoIndent",
            },
            mapping(".clang-format"),
        )


class TidyCriteria(unittest.TestCase):
    def setUp(self):
        self.text = read(".clang-tidy")

    def checks(self):
        block = re.search(r"^Checks:\s*>-\n((?:  .*\n)+)", self.text, re.MULTILINE)
        self.assertIsNotNone(block, "no Checks block")
        return [item.strip() for item in block.group(1).replace("\n", " ").split(",") if item.strip()]

    def test_the_checks_are_the_crux_checks(self):
        self.assertEqual(
            [
                "-*",
                "bugprone-*",
                "clang-analyzer-*",
                "-clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling",
                "performance-*",
                "-performance-enum-size",
                "portability-*",
                "readability-identifier-naming",
            ],
            self.checks(),
        )

    def test_every_finding_is_an_error(self):
        self.assertRegex(self.text, r"(?m)^WarningsAsErrors: '\*'$")

    def test_the_format_style_is_read_from_the_format_file(self):
        self.assertRegex(self.text, r"(?m)^FormatStyle: file$")

    def test_the_header_filter_covers_only_the_directories_of_this_repository(self):
        match = re.search(r"(?m)^HeaderFilterRegex: '(.*)'$", self.text)
        self.assertIsNotNone(match, "no HeaderFilterRegex")
        pattern = re.compile(match.group(1))
        self.assertEqual(r".*/(workload|app|tests)/.*", match.group(1))
        for path in ("/w/repo/workload/include/workload.h", "/w/repo/app/src/net_client.h",
                     "/w/repo/tests/host/test_workload.c"):
            self.assertTrue(pattern.fullmatch(path), path)
        for path in ("/w/crux/components/time/include/crux/time.h", "/w/myapp/include/x.h",
                     "/w/contests/include/x.h",
                     "/w/zephyr/include/zephyr/kernel.h", "/usr/include/stdio.h"):
            self.assertFalse(pattern.fullmatch(path), path)

    def test_the_header_filter_says_why_it_is_narrow(self):
        lines = self.text.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("HeaderFilterRegex"))
        self.assertTrue(lines[index - 1].startswith("#"), "no comment above HeaderFilterRegex")


# Git quotes a non-ASCII path in `ls-files` output unless it is given -z. These settings make the
# default explicit, so the tests do not depend on the core.quotePath of the machine that runs them.
QUOTED_PATHS = {
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "core.quotePath",
    "GIT_CONFIG_VALUE_0": "true",
}


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class Fixture:
    """A throwaway git repository, and a stand-in formatter that records what it is given."""

    def __init__(self, files, version=CLANG_FORMAT_VERSION, exit_status=0):
        self._dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._dir.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        git(self.root, "add", "-A")
        self.log = pathlib.Path(self._dir.name) / "arguments.txt"
        self.formatter = pathlib.Path(self._dir.name) / "fake-clang-format"
        self.formatter.write_text(
            "#!/bin/sh\n"
            f'if [ "$1" = "--version" ]; then echo "clang-format version {version}"; exit 0; fi\n'
            f'printf \'%s\\n\' "$@" > "{self.log}"\n'
            f"exit {exit_status}\n"
        )
        self.formatter.chmod(self.formatter.stat().st_mode | stat.S_IEXEC)

    def run(self, script):
        env = dict(os.environ, CLANG_FORMAT=str(self.formatter), **QUOTED_PATHS)
        return subprocess.run(
            ["bash", str(SCRIPTS / script)], cwd=self.root, env=env, capture_output=True, text=True
        )

    def arguments(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def close(self):
        self._dir.cleanup()


class FormatScript(unittest.TestCase):
    def setUp(self):
        self.assertTrue((SCRIPTS / "check-format.sh").is_file(), "scripts/check-format.sh is missing")
        self.text = read("scripts/check-format.sh")

    def fixture(self, files, **kwargs):
        fixture = Fixture(files, **kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def test_the_file_list_comes_from_git_and_not_from_a_hand_list(self):
        self.assertIn("git -C", self.text)
        self.assertIn("ls-files", self.text)
        self.assertNotRegex(self.text, r"\b(app|workload|tests)/", "a hand-written directory")

    def test_the_formatter_version_is_pinned(self):
        self.assertIn(CLANG_FORMAT_VERSION, self.text)

    def test_every_tracked_c_and_h_file_is_checked_in_every_directory(self):
        files = {
            "workload/src/a.c": "int a;\n",
            "workload/include/a.h": "int a;\n",
            "app/src/b.c": "int b;\n",
            "app/os/c.c": "int c;\n",
            "tests/native_sim/workload/src/d.c": "int d;\n",
            "docs/notes.md": "not code\n",
        }
        fixture = self.fixture(files)
        result = fixture.run("check-format.sh")
        self.assertEqual(0, result.returncode, result.stderr)
        checked = sorted(pathlib.Path(a).relative_to(fixture.root.resolve()).as_posix()
                         for a in fixture.arguments() if a.endswith((".c", ".h")))
        self.assertEqual(sorted(name for name in files if name.endswith((".c", ".h"))), checked)

    def test_a_file_with_a_non_ascii_name_is_checked(self):
        fixture = self.fixture({"app/src/a.c": "int a;\n", "app/src/\u00e4.c": "int b;\n"})
        result = fixture.run("check-format.sh")
        self.assertEqual(0, result.returncode, result.stderr)
        names = [pathlib.Path(a).name for a in fixture.arguments() if a.endswith(".c")]
        self.assertEqual(["a.c", "\u00e4.c"], sorted(names))

    def test_a_new_file_is_checked_without_a_change_to_the_script(self):
        fixture = self.fixture({"app/src/old.c": "int a;\n"})
        (fixture.root / "app/src/new.c").write_text("int b;\n")
        fixture.run("check-format.sh")
        self.assertTrue(any(a.endswith("app/src/new.c") for a in fixture.arguments()))

    def test_the_formatter_runs_as_a_check_that_fails_on_a_difference(self):
        fixture = self.fixture({"app/src/a.c": "int a;\n"})
        fixture.run("check-format.sh")
        self.assertIn("--dry-run", fixture.arguments())
        self.assertIn("--Werror", fixture.arguments())

    def test_a_formatting_difference_fails_the_script(self):
        fixture = self.fixture({"app/src/a.c": "int a;\n"}, exit_status=1)
        self.assertEqual(1, fixture.run("check-format.sh").returncode)

    def test_another_formatter_version_fails_with_a_clear_message(self):
        fixture = self.fixture({"app/src/a.c": "int a;\n"}, version="17.0.6")
        result = fixture.run("check-format.sh")
        self.assertNotEqual(0, result.returncode)
        self.assertIn(CLANG_FORMAT_VERSION, result.stderr)
        self.assertIn("17.0.6", result.stderr)
        self.assertEqual([], fixture.arguments(), "the formatter must not run on a wrong version")


class Tree:
    """A throwaway git repository with a compile database and a stand-in clang-tidy."""

    def __init__(self, tracked, analysed, tidy_version="18.1.3", tidy_status=0):
        self._dir = tempfile.TemporaryDirectory()
        base = pathlib.Path(self._dir.name).resolve()
        self.root = base / "repo"
        self.build = self.root / "build" / "analyze"
        self.build.mkdir(parents=True)
        git(self.root, "init", "-q")
        for name in tracked:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("int x;\n")
        git(self.root, "add", "-A")
        # An "@" in a database entry stands for the root of the repository, to write an absolute path.
        database = [
            {"directory": str(self.build), "command": "cc -c x", "file": name.replace("@", str(self.root))}
            for name in analysed
        ]
        self.database = self.build / "compile_commands.json"
        self.database.write_text(json.dumps(database))
        self.log = base / "tidy-arguments.txt"
        self.tidy = base / "fake-clang-tidy"
        self.tidy.write_text(
            "#!/bin/sh\n"
            f'if [ "$1" = "--version" ]; then echo "LLVM version {tidy_version}"; exit 0; fi\n'
            f'printf \'%s\\n\' "$@" > "{self.log}"\n'
            "echo 'tidy ran'\n"
            f"exit {tidy_status}\n"
        )
        self.tidy.chmod(self.tidy.stat().st_mode | stat.S_IEXEC)

    def run(self, *extra, env=None):
        env = dict(os.environ, CLANG_TIDY=str(self.tidy), **QUOTED_PATHS, **(env or {}))
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "analyze_host.py"), "--compile-commands",
             str(self.database), *extra],
            cwd=self.root, env=env, capture_output=True, text=True,
        )

    def tidy_files(self):
        arguments = self.log.read_text().splitlines() if self.log.exists() else []
        return sorted(pathlib.Path(a).relative_to(self.root).as_posix()
                      for a in arguments if a.endswith((".c", ".cpp")))

    def close(self):
        self._dir.cleanup()


def tree(case, tracked, analysed, **kwargs):
    fixture = Tree(tracked, analysed, **kwargs)
    case.addCleanup(fixture.close)
    return fixture


class CompileDatabase(unittest.TestCase):
    def test_the_files_come_from_the_database_resolved_against_their_directory(self):
        fixture = tree(self, ["app/src/a.c", "workload/src/b.c"],
                       ["../../app/src/a.c", "@/workload/src/b.c"])
        found = analyze_host.database_sources(fixture.database, fixture.root)
        self.assertEqual([fixture.root / "app/src/a.c", fixture.root / "workload/src/b.c"], found)

    def test_files_outside_the_repository_and_in_the_build_directory_are_dropped(self):
        fixture = tree(self, ["app/src/a.c"], ["../../app/src/a.c", "/usr/include/x.c",
                                                "generated.c", "../../build/analyze/gen.c"])
        found = analyze_host.database_sources(fixture.database, fixture.root)
        self.assertEqual([fixture.root / "app/src/a.c"], found)

    def test_a_file_listed_twice_is_listed_once(self):
        fixture = tree(self, ["app/src/a.c"], ["../../app/src/a.c", "../../app/src/a.c"])
        self.assertEqual([fixture.root / "app/src/a.c"],
                         analyze_host.database_sources(fixture.database, fixture.root))


class NotAnalysed(unittest.TestCase):
    def test_every_tracked_source_outside_the_database_is_listed(self):
        fixture = tree(
            self,
            ["app/src/a.c", "app/os/z.c", "tests/native_sim/workload/src/t.c", "app/src/a.h", "README.md"],
            ["../../app/src/a.c"],
        )
        tracked = analyze_host.tracked_sources(fixture.root)
        analysed = analyze_host.database_sources(fixture.database, fixture.root)
        self.assertEqual(
            ["app/os/z.c", "tests/native_sim/workload/src/t.c"],
            [p.relative_to(fixture.root).as_posix()
             for p in analyze_host.not_analysed(tracked, analysed)],
        )

    def test_nothing_is_left_when_every_source_is_in_the_database(self):
        fixture = tree(self, ["app/src/a.c"], ["../../app/src/a.c"])
        tracked = analyze_host.tracked_sources(fixture.root)
        analysed = analyze_host.database_sources(fixture.database, fixture.root)
        self.assertEqual([], analyze_host.not_analysed(tracked, analysed))

    def test_a_source_with_a_non_ascii_name_is_listed_by_its_real_path(self):
        fixture = tree(self, ["app/src/a.c", "app/src/\u00e4.c"], ["../../app/src/a.c"])
        result = fixture.run()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("  app/src/\u00e4.c", result.stdout.splitlines())

    def test_a_new_untracked_source_is_listed_too(self):
        fixture = tree(self, ["app/src/a.c"], ["../../app/src/a.c"])
        (fixture.root / "app/src/new.c").write_text("int n;\n")
        listed = analyze_host.tracked_sources(fixture.root)
        self.assertIn(fixture.root / "app/src/new.c", listed)


class AnalyzeScript(unittest.TestCase):
    def setUp(self):
        self.text = read("scripts/analyze_host.py")

    def test_the_configure_command_exports_the_compile_database_of_the_host_tests(self):
        for fragment in ("tests/host", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", "-DWORKLOAD_SANITIZE=OFF"):
            self.assertIn(fragment, self.text)

    def test_there_is_no_hand_written_list_of_sources(self):
        self.assertNotRegex(self.text, r"\b(app|workload)/(src|os|compose)\b")
        self.assertNotRegex(self.text, r"\b\w+\.c\b")

    def test_only_the_files_of_the_database_go_to_clang_tidy(self):
        fixture = tree(self, ["app/src/a.c", "workload/src/b.c", "app/os/z.c"],
                       ["../../app/src/a.c", "../../workload/src/b.c"])
        result = fixture.run()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(["app/src/a.c", "workload/src/b.c"], fixture.tidy_files())
        arguments = fixture.log.read_text().splitlines()
        self.assertEqual(str(fixture.build), arguments[arguments.index("-p") + 1])

    def test_the_not_analysed_list_is_printed_last_and_names_every_missing_source(self):
        fixture = tree(self, ["app/src/a.c", "app/os/z.c", "tests/native_sim/workload/src/t.c"],
                       ["../../app/src/a.c"])
        result = fixture.run()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        output = result.stdout
        self.assertLess(output.index("tidy ran"), output.index("Not analysed"))
        tail = output[output.index("Not analysed"):]
        self.assertIn("2 ", tail.splitlines()[0])
        self.assertIn("app/os/z.c", tail)
        self.assertIn("tests/native_sim/workload/src/t.c", tail)
        self.assertNotIn("app/src/a.c", tail)

    def test_a_finding_fails_the_script_and_the_list_is_still_printed(self):
        fixture = tree(self, ["app/src/a.c", "app/os/z.c"], ["../../app/src/a.c"], tidy_status=1)
        result = fixture.run()
        self.assertEqual(1, result.returncode)
        self.assertIn("app/os/z.c", result.stdout)

    def test_another_clang_tidy_major_version_fails_with_a_clear_message(self):
        fixture = tree(self, ["app/src/a.c"], ["../../app/src/a.c"], tidy_version="17.0.6")
        result = fixture.run()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("18", result.stderr)
        self.assertIn("17.0.6", result.stderr)
        self.assertEqual([], fixture.tidy_files())

    def test_an_empty_database_fails_instead_of_analysing_nothing(self):
        fixture = tree(self, ["app/src/a.c"], [])
        result = fixture.run()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("no source", result.stderr)
        self.assertIn("app/src/a.c", result.stdout, "the not-analysed list is still printed")

    def test_a_failed_configure_still_prints_the_list_and_fails(self):
        fixture = tree(self, ["app/src/a.c", "app/os/z.c"], ["../../app/src/a.c"])
        bin_dir = fixture.root.parent / "bin"
        bin_dir.mkdir()
        cmake = bin_dir / "cmake"
        cmake.write_text("#!/bin/sh\necho 'configure failed' >&2\nexit 1\n")
        cmake.chmod(cmake.stat().st_mode | stat.S_IEXEC)
        env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "analyze_host.py")], cwd=fixture.root,
            env=dict(os.environ, CLANG_TIDY=str(fixture.tidy), **QUOTED_PATHS, **env),
            capture_output=True, text=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("configure", result.stderr)
        self.assertIn("Not analysed (2 ", result.stdout)
        self.assertIn("app/os/z.c", result.stdout)
        self.assertEqual([], fixture.tidy_files())


@ci_map.needs_tomllib
class CiJob(unittest.TestCase):
    """The workflow runs both checks in one job, with pinned tools, and a finding fails it."""

    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load(read(".github/workflows/ci.yml"))
        cls.matches = [job for job in cls.workflow["jobs"].values()
                       if job.get("name") == "Static analysis"]

    def job(self):
        self.assertEqual(1, len(self.matches), "ci.yml must have one job named Static analysis")
        return self.matches[0]

    def commands(self):
        # The job installs the tools, then runs the checks of the job static of scripts/ci/checks.toml.
        steps = "\n".join(step.get("run", "") for step in self.job()["steps"])
        return steps + "\n" + ci_map.commands("static")

    def test_the_job_runs_on_the_runner_of_the_other_jobs(self):
        self.assertEqual("ubuntu-24.04", self.job()["runs-on"])

    def test_it_checks_out_with_the_pinned_actions_of_the_other_jobs(self):
        uses = [step.get("uses") for step in self.job()["steps"] if "uses" in step]
        self.assertEqual(["actions/checkout@v4", "actions/setup-python@v5"], uses)

    def test_the_format_tool_is_installed_at_the_pinned_version(self):
        self.assertIn(f"pip install clang-format=={CLANG_FORMAT_VERSION}", self.commands())

    def test_clang_tidy_is_installed_at_the_pinned_package_version(self):
        self.assertIn(f"apt-get install -y {CLANG_TIDY_PACKAGE}", self.commands())

    def test_both_scripts_run_in_the_job(self):
        commands = self.commands()
        self.assertIn("scripts/check-format.sh", commands)
        self.assertIn("scripts/analyze_host.py", commands)

    def test_a_finding_fails_the_job(self):
        job = self.job()
        self.assertNotIn("continue-on-error", job)
        for step in [*job["steps"], *ci_map.checks("static")]:
            self.assertNotIn("continue-on-error", step)
            self.assertNotIn("advisory", step)
            self.assertNotRegex(step.get("run", ""), r"\|\|\s*true")

    def test_the_job_does_not_add_permissions_or_upload_anything(self):
        job = self.job()
        self.assertNotIn("permissions", job)
        self.assertNotIn("actions/upload-artifact", read(".github/workflows/ci.yml"))


if __name__ == "__main__":
    unittest.main()
