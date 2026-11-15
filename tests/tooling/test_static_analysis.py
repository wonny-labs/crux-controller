"""Checks of the format and static-analysis setup: the criteria files, the two scripts and the CI
job that runs them. The criteria are the ones that the Crux repository applies to its own code."""

import os
import pathlib
import re
import stat
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
CLANG_FORMAT_VERSION = "18.1.8"


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
        for path in ("/w/repo/workload/include/workload.h", "/w/repo/app/src/net_client.h",
                     "/w/repo/tests/host/test_workload.c"):
            self.assertTrue(pattern.fullmatch(path), path)
        for path in ("/w/crux/components/time/include/crux/time.h",
                     "/w/zephyr/include/zephyr/kernel.h", "/usr/include/stdio.h"):
            self.assertFalse(pattern.fullmatch(path), path)

    def test_the_header_filter_says_why_it_is_narrow(self):
        lines = self.text.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("HeaderFilterRegex"))
        self.assertTrue(lines[index - 1].startswith("#"), "no comment above HeaderFilterRegex")


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
        env = dict(os.environ, CLANG_FORMAT=str(self.formatter))
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
            "tests/native_sim/s1/src/d.c": "int d;\n",
            "docs/notes.md": "not code\n",
        }
        fixture = self.fixture(files)
        result = fixture.run("check-format.sh")
        self.assertEqual(0, result.returncode, result.stderr)
        checked = sorted(pathlib.Path(a).relative_to(fixture.root.resolve()).as_posix()
                         for a in fixture.arguments() if a.endswith((".c", ".h")))
        self.assertEqual(sorted(name for name in files if name.endswith((".c", ".h"))), checked)

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


if __name__ == "__main__":
    unittest.main()
