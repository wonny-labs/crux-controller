# SPDX-License-Identifier: Apache-2.0
"""Checks that CI runs the three checks of the style work (SPDX headers, checkpatch, the style-kit
include check) in a way that can fail. These tests read the workflow only and use no network."""

import os
import pathlib
import shutil
import subprocess
import tempfile
import re
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def jobs():
    return yaml.safe_load(CI.read_text())["jobs"]


def steps_of(job):
    return jobs()[job]["steps"]


def only_step(job, fragment):
    found = [s for s in steps_of(job) if fragment in s.get("name", "")]
    assert len(found) == 1, f"{job}: need exactly one step named like {fragment!r}, got {found}"
    return found[0]


class CannotBeSilenced(unittest.TestCase):
    """Shared rule: a step of these checks never hides its own failure."""

    def assert_can_fail(self, job, step):
        self.assertNotIn("continue-on-error", step)
        self.assertNotIn("continue-on-error", jobs()[job])
        self.assertNotIn("if", step, "the step runs conditionally")
        run = step.get("run", "")
        self.assertNotRegex(run, r"\|\|\s*(true|:)\b")
        self.assertNotRegex(run, r"(^|\n)\s*set \+e")


class SpdxStep(CannotBeSilenced):
    def test_the_tooling_job_runs_the_spdx_check_after_checkout(self):
        step = only_step("tooling", "SPDX")
        names = [s.get("uses", s.get("name", "")) for s in steps_of("tooling")]
        self.assertTrue(names[0].startswith("actions/checkout@"))
        self.assertEqual("python scripts/check_spdx.py", step["run"].strip())
        self.assert_can_fail("tooling", step)

    def test_the_script_and_its_tests_exist(self):
        self.assertTrue((ROOT / "scripts" / "check_spdx.py").is_file())
        self.assertTrue((ROOT / "tests" / "tooling" / "test_check_spdx.py").is_file())

    def test_the_existing_tooling_steps_are_unchanged(self):
        runs = [s.get("run") for s in steps_of("tooling")]
        self.assertIn("python -m pip install pyyaml", runs)
        self.assertIn("python -m unittest discover -s tests/tooling -v", runs)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


STAND_IN = r"""#!/usr/bin/perl
my $bad = 0;
while (my $line = <STDIN>) { $bad = 1 if $line =~ /^\+.*BAD_BRACES/; }
print "stand-in checkpatch: ", ($bad ? "error" : "clean"), "\n";
exit($bad ? 1 : 0);
"""


class PatchStyleJob(CannotBeSilenced):
    STEP = "Check the patch style"

    def test_the_job_is_named_and_fetches_two_commits_and_zephyr(self):
        job = jobs()["patch-style"]
        self.assertEqual("Patch style", job["name"])
        checkout = job["steps"][0]
        self.assertTrue(checkout["uses"].startswith("actions/checkout@"))
        self.assertEqual("crux-controller", checkout["with"]["path"])
        self.assertEqual(2, checkout["with"]["fetch-depth"])
        runs = "\n".join(s.get("run", "") for s in job["steps"])
        self.assertIn("west init -l crux-controller", runs)
        self.assertRegex(runs, r"west update zephyr\b")
        self.assertIn("west==1.4.0", runs)

    def test_the_step_runs_the_script_from_the_repository_with_zephyr_base(self):
        step = only_step("patch-style", self.STEP)
        self.assertEqual("crux-controller", step["working-directory"])
        self.assertEqual("${{ github.workspace }}/zephyr", step["env"]["ZEPHYR_BASE"])
        self.assertIn("scripts/check-patch.sh", step["run"])
        self.assert_can_fail("patch-style", step)

    def test_the_job_has_no_other_check_step_that_could_hide_the_result(self):
        for step in steps_of("patch-style"):
            self.assertNotIn("continue-on-error", step)

    # The step text is run for real, with a stand-in for checkpatch.pl, in repositories built to
    # look like what GitHub checks out.
    def make_repo(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = pathlib.Path(directory.name)
        repo = base / "crux-controller"
        zephyr = base / "zephyr"
        (zephyr / "scripts").mkdir(parents=True)
        (zephyr / "scripts" / "checkpatch.pl").write_text(STAND_IN)
        (repo / "scripts").mkdir(parents=True)
        shutil.copy2(ROOT / "scripts" / "check-patch.sh", repo / "scripts" / "check-patch.sh")
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        (repo / "a.c").write_text("int a;\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        return base, repo, zephyr

    def commit(self, repo, text):
        (repo / "a.c").write_text(text)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "change")

    def commit_file(self, repo, name, text):
        (repo / name).write_text(text)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "change " + name)

    def run_step(self, repo, zephyr, event, before=""):
        step = only_step("patch-style", self.STEP)
        env = {
            "PATH": os.environ["PATH"], "HOME": str(repo.parent),
            "GITHUB_EVENT_NAME": event, "PUSH_BEFORE": before, "ZEPHYR_BASE": str(zephyr),
        }
        # GitHub runs a step as: bash --noprofile --norc -eo pipefail {0}
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
            cwd=repo, env=env, capture_output=True, text=True,
        )

    def test_a_pull_request_with_a_bad_change_fails(self):
        _, repo, zephyr = self.make_repo()
        self.commit(repo, "int BAD_BRACES;\n")
        result = self.run_step(repo, zephyr, "pull_request")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("stand-in checkpatch: error", result.stdout)

    def test_a_pull_request_with_a_clean_change_passes(self):
        _, repo, zephyr = self.make_repo()
        self.commit(repo, "int fine;\n")
        result = self.run_step(repo, zephyr, "pull_request")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_a_push_checks_everything_since_the_previous_push(self):
        _, repo, zephyr = self.make_repo()
        before = git(repo, "rev-parse", "HEAD")
        self.commit_file(repo, "b.c", "int BAD_BRACES;\n")
        self.commit(repo, "int fine;\n")
        # The last commit alone is clean, so only the whole range shows the problem.
        result = self.run_step(repo, zephyr, "push", before)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertEqual(0, self.run_step(repo, zephyr, "pull_request").returncode)

    def test_a_push_without_a_previous_sha_is_an_error(self):
        _, repo, zephyr = self.make_repo()
        for before in ("", "0" * 40):
            result = self.run_step(repo, zephyr, "push", before)
            self.assertEqual(2, result.returncode, before)
            self.assertIn("previous push SHA", result.stderr)

    def test_an_event_that_is_neither_push_nor_pull_request_is_an_error(self):
        _, repo, zephyr = self.make_repo()
        result = self.run_step(repo, zephyr, "workflow_dispatch")
        self.assertEqual(2, result.returncode)

    def test_a_missing_zephyr_fails_instead_of_passing(self):
        _, repo, zephyr = self.make_repo()
        self.commit(repo, "int BAD_BRACES;\n")
        result = self.run_step(repo, zephyr.parent / "nowhere", "pull_request")
        self.assertEqual(2, result.returncode)

    def test_a_push_fetches_a_previous_commit_that_the_clone_lacks(self):
        base, repo, zephyr = self.make_repo()
        before = git(repo, "rev-parse", "HEAD")
        self.commit_file(repo, "b.c", "int BAD_BRACES;\n")
        self.commit(repo, "int fine;\n")
        self.commit(repo, "int fine2;\n")
        clone = base / "clone" / "crux-controller"
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(clone)],
            check=True, capture_output=True,
        )
        self.assertFalse(
            subprocess.run(["git", "-C", str(clone), "cat-file", "-e", before + "^{commit}"],
                           capture_output=True).returncode == 0,
            "the clone must lack the previous commit",
        )
        result = self.run_step(clone, zephyr, "push", before)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
