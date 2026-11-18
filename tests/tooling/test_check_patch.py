# SPDX-License-Identifier: Apache-2.0
"""Tests of scripts/check-patch.sh, the checkpatch wrapper adopted from the Crux Pilot style kit.

Most tests run it against a stand-in for Zephyr's checkpatch.pl, so that the wiring (which lines
are handed over, the rule set, the exit status, the refusals) is checked on every machine and
without Zephyr. The tests of the real tool run only when ZEPHYR_BASE names a Zephyr checkout.
"""

import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-patch.sh"

# Records its arguments and what it reads, and fails when the diff contains the marker.
STAND_IN = r"""#!/usr/bin/perl
use strict;
open(my $log, '>', $ENV{CP_LOG}) or die;
print $log "ARGS: @ARGV\n";
my $bad = 0;
while (my $line = <STDIN>) {
    print $log $line;
    $bad = 1 if $line =~ /^\+.*BAD_BRACES/;
}
close($log);
print "stand-in checkpatch: ", ($bad ? "error" : "clean"), "\n";
exit($bad ? 1 : 0);
"""


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True, capture_output=True, text=True,
    )


class Fixture:
    """A throwaway repository with a base commit and a fake Zephyr checkout."""

    def __init__(self):
        self.directory = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.directory.name)
        self.repo = base / "repo"
        self.zephyr = base / "zephyr"
        self.home = base / "home"
        self.log = base / "checkpatch.log"
        for path in (self.repo, self.home, self.zephyr / "scripts"):
            path.mkdir(parents=True)
        (self.zephyr / "scripts" / "checkpatch.pl").write_text(STAND_IN)
        git(self.repo, "init", "-q", "-b", "main")
        self.write("src/a.c", "int a(void)\n{\n    return 1;\n}\n")
        self.write("README.md", "# readme\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message="change"):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message)

    def run(self, *args, zephyr=True, **env):
        environment = {
            "PATH": os.environ["PATH"], "HOME": str(self.home), "CP_LOG": str(self.log),
        }
        if zephyr:
            environment["ZEPHYR_BASE"] = str(self.zephyr)
        environment.update(env)
        return subprocess.run(
            ["bash", str(SCRIPT), *args], cwd=self.repo, env=environment,
            capture_output=True, text=True,
        )

    def close(self):
        self.directory.cleanup()


class WithFixture(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.close)


class Refusals(WithFixture):
    def test_a_missing_zephyr_base_is_an_error_not_a_pass(self):
        self.fx.write("src/a.c", "int b;\n")
        self.fx.commit()
        result = self.fx.run("HEAD^", "HEAD", zephyr=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("ZEPHYR_BASE", result.stderr)

    def test_a_zephyr_base_without_checkpatch_is_an_error(self):
        result = self.fx.run("HEAD", "HEAD", ZEPHYR_BASE=str(self.fx.home))
        self.assertEqual(2, result.returncode)
        self.assertIn("checkpatch.pl", result.stderr)

    def test_a_missing_revision_is_an_error(self):
        result = self.fx.run("0" * 40, "HEAD")
        self.assertEqual(2, result.returncode)
        self.assertIn("Missing Git commit", result.stderr)

    def test_more_than_two_arguments_are_refused(self):
        self.assertEqual(2, self.fx.run("a", "b", "c").returncode)

    def test_help_exits_zero(self):
        result = self.fx.run("--help", zephyr=False)
        self.assertEqual(0, result.returncode)
        self.assertIn("CHECKPATCH_TYPES", result.stdout)


class Wiring(WithFixture):
    def test_a_range_without_c_changes_passes_without_running_checkpatch(self):
        self.fx.write("README.md", "# changed\n")
        self.fx.commit()
        result = self.fx.run("HEAD^", "HEAD")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("No changed C source or header files", result.stdout)
        self.assertFalse(self.fx.log.exists())

    def test_changed_c_lines_are_handed_to_checkpatch_with_the_braces_rule(self):
        self.fx.write("src/a.c", "int a(void)\n{\n    return 2;\n}\n")
        self.fx.write("README.md", "# changed\n")
        self.fx.commit()
        result = self.fx.run("HEAD^", "HEAD")
        self.assertEqual(0, result.returncode, result.stderr)
        log = self.fx.log.read_text()
        self.assertIn("ARGS: --no-tree --no-signoff --types BRACES -", log)
        self.assertIn("+    return 2;", log)
        self.assertIn("src/a.c", log)
        self.assertNotIn("README.md", log)

    def test_the_rule_set_can_be_widened(self):
        self.fx.write("src/a.c", "int c;\n")
        self.fx.commit()
        self.fx.run("HEAD^", "HEAD", CHECKPATCH_TYPES="BRACES,CODE_INDENT")
        self.assertIn("--types BRACES,CODE_INDENT", self.fx.log.read_text())

    def test_the_default_range_is_the_last_commit(self):
        self.fx.write("src/a.c", "int d;\n")
        self.fx.commit()
        self.fx.write("README.md", "# docs only\n")
        self.fx.commit()
        result = self.fx.run()
        self.assertIn("No changed C source or header files", result.stdout)

    def test_a_finding_of_checkpatch_fails_the_check(self):
        self.fx.write("src/a.c", "int a(void)\n{\n    BAD_BRACES;\n}\n")
        self.fx.commit()
        result = self.fx.run("HEAD^", "HEAD")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("stand-in checkpatch: error", result.stdout)

    def test_a_header_change_is_checked_too(self):
        self.fx.write("src/a.h", "int BAD_BRACES;\n")
        self.fx.commit()
        self.assertEqual(1, self.fx.run("HEAD^", "HEAD").returncode)

    def test_lines_outside_the_range_are_not_checked(self):
        self.fx.write("src/a.c", "int BAD_BRACES;\n")
        self.fx.commit()
        self.fx.write("src/a.c", "int fine;\n")
        self.fx.commit()
        self.assertEqual(0, self.fx.run("HEAD^", "HEAD").returncode)


ZEPHYR = os.environ.get("ZEPHYR_BASE", "")
HAVE_CHECKPATCH = bool(ZEPHYR) and (pathlib.Path(ZEPHYR) / "scripts" / "checkpatch.pl").is_file()


@unittest.skipUnless(HAVE_CHECKPATCH, "ZEPHYR_BASE does not name a Zephyr checkout")
class RealCheckpatch(WithFixture):
    def run_real(self, *args):
        return self.fx.run(*args, ZEPHYR_BASE=ZEPHYR)

    def test_a_clean_change_passes(self):
        self.fx.write("src/a.c", "int a(int x)\n{\n    if (x) {\n        x = 2;\n        return x;\n    }\n"
                                 "    return 1;\n}\n")
        self.fx.commit()
        result = self.run_real("HEAD^", "HEAD")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_an_if_without_braces_fails(self):
        self.fx.write("src/a.c", "int a(int x)\n{\n    if (x)\n        return 2;\n"
                                 "    return 1;\n}\n")
        self.fx.commit()
        result = self.run_real("HEAD^", "HEAD")
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("braces {} are required", result.stdout + result.stderr)

    def test_a_brace_on_the_wrong_line_fails(self):
        self.fx.write("src/a.c", "int a(int x)\n{\n    if (x)\n    {\n        return 2;\n    }\n"
                                 "    return 1;\n}\n")
        self.fx.commit()
        self.assertNotEqual(0, self.run_real("HEAD^", "HEAD").returncode)


if __name__ == "__main__":
    unittest.main()
