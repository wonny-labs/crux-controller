# SPDX-License-Identifier: Apache-2.0
"""Checks that CI runs the three checks of the style work (SPDX headers, checkpatch, the style-kit
include check) in a way that can fail. A job of ci.yml runs the checks of the job of the same name
in scripts/ci/checks.toml; these tests read both and use no network."""

import hashlib
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import re
import unittest

import yaml

import ci_map

ROOT = pathlib.Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def jobs():
    return yaml.safe_load(CI.read_text())["jobs"]


def steps_of(job):
    return jobs()[job]["steps"]


def only_step(job, check_id):
    """The check of a job of the CI map file, as a step: its id, its commands, the job env of ci.yml."""
    assert check_id in ci_map.ids(job), f"{job}: no check {check_id}"
    return {"name": check_id, "run": ci_map.run(check_id), "env": jobs()[job].get("env", {}),
            **{k: v for k, v in ci_map.check(check_id).items() if k in ("advisory",)}}


class CannotBeSilenced(unittest.TestCase):
    """Shared rule: a step of these checks never hides its own failure."""

    def assert_can_fail(self, job, step):
        self.assertNotIn("continue-on-error", step)
        self.assertNotIn("continue-on-error", jobs()[job])
        self.assertNotIn("advisory", step, "an advisory check cannot fail its job")
        self.assertNotIn("if", step, "the step runs conditionally")
        # The workflow runs the checks of the job in one step that waits only for the plan.
        tier = next(s for s in steps_of(job) if s.get("name") == "Run the checks of this tier")
        self.assertNotIn("continue-on-error", tier)
        self.assertEqual("steps.plan.outputs.checks != '0'", tier["if"])
        run = step.get("run", "")
        self.assertNotRegex(run, r"\|\|\s*(true|:)\b")
        self.assertNotRegex(run, r"(^|\n)\s*set \+e")


@ci_map.needs_tomllib
class SpdxStep(CannotBeSilenced):
    def test_the_tooling_job_runs_the_spdx_check_after_checkout(self):
        step = only_step("tooling", "spdx")
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
        self.assertEqual("python -m unittest discover -s tests/tooling -v", ci_map.run("tooling-tests").strip())
        self.assertEqual(["tooling-tests", "spdx"], ci_map.ids("tooling"))


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


@ci_map.needs_tomllib
class PatchStyleJob(CannotBeSilenced):
    STEP = "patch-style"

    def test_the_job_is_named_and_fetches_two_commits_and_zephyr(self):
        job = jobs()["patch-style"]
        self.assertEqual("Patch style", job["name"])
        checkout = job["steps"][0]
        self.assertTrue(checkout["uses"].startswith("actions/checkout@"))
        self.assertEqual("crux-controller", checkout["with"]["path"])
        # The whole history, not two commits: scripts/ci/run-tier.sh compares the change with the
        # merge base of its target, and the patch style check uses that same base.
        self.assertEqual(0, checkout["with"]["fetch-depth"])
        runs = "\n".join(s.get("run", "") for s in job["steps"]) + "\n" + ci_map.commands("patch-style")
        self.assertIn("west init -l crux-controller", runs)
        # west refuses to update a project that comes through an import, so Zephyr is not
        # updated by name: west updates crux, and the job fetches only the commit that the
        # Crux manifest names for Zephyr.
        self.assertNotRegex(runs, r"west update zephyr\b")
        self.assertRegex(runs, r"west update crux(?![-\w])")
        self.assertIn("west==1.4.0", runs)

    def fetch_step(self):
        return only_step("patch-style", "patch-style-fetch-zephyr")

    def test_the_fetch_step_resolves_the_pinned_zephyr_commit_and_fetches_only_it(self):
        run = self.fetch_step()["run"]
        self.assertTrue(run.lstrip().startswith("set -euo pipefail"))
        self.assertIn("west init -l crux-controller", run)
        self.assertIn("west list -f '{revision}' zephyr", run)
        self.assertIn("west list -f '{abspath}' zephyr", run)
        self.assertIn("--depth=1 https://github.com/zephyrproject-rtos/zephyr", run)
        self.assertRegex(run, r"\^\[0-9a-f\]\{40\}\$")
        self.assertNotRegex(run, r"west update zephyr\b")
        self.assertNotIn("continue-on-error", self.fetch_step())

    def test_the_step_runs_the_script_from_the_repository_with_zephyr_base(self):
        # The check starts in the repository root, sets ZEPHYR_BASE to the Zephyr of the workspace
        # folder, and runs scripts/check-patch.sh through scripts/ci/check-patch-range.sh.
        step = only_step("patch-style", self.STEP)
        self.assertNotRegex(step["run"], r"(^|\n)\s*cd ")
        self.assertIn('export ZEPHYR_BASE="$(cd .. && pwd)/zephyr"', step["run"])
        self.assertIn("scripts/ci/check-patch-range.sh", step["run"])
        self.assertIn('exec scripts/check-patch.sh "$base" HEAD', (ROOT / "scripts/ci/check-patch-range.sh").read_text())
        self.assert_can_fail("patch-style", step)

    def test_the_job_has_no_other_check_step_that_could_hide_the_result(self):
        for step in steps_of("patch-style"):
            self.assertNotIn("continue-on-error", step)
        self.assertEqual(["patch-style-fetch-zephyr", "patch-style"], ci_map.ids("patch-style"))
        for check in ci_map.checks("patch-style"):
            self.assertNotIn("advisory", check)

    # The check text is run for real, with a stand-in for checkpatch.pl, in a workspace folder built
    # to look like what CI checks out: the clone crux-controller beside zephyr.
    def make_repo(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = pathlib.Path(directory.name).resolve()
        repo = base / "crux-controller"
        zephyr = base / "zephyr"
        (zephyr / "scripts").mkdir(parents=True)
        (zephyr / "scripts" / "checkpatch.pl").write_text(STAND_IN)
        (repo / "scripts" / "ci").mkdir(parents=True)
        shutil.copy2(ROOT / "scripts" / "check-patch.sh", repo / "scripts" / "check-patch.sh")
        shutil.copy2(ROOT / "scripts" / "ci" / "check-patch-range.sh", repo / "scripts" / "ci" / "check-patch-range.sh")
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
        """Run the check as scripts/ci/run-tier.sh does: the event, and the commit it compared the
        change with (none when it has none). A missing zephyr folder is moved away first."""
        step = only_step("patch-style", self.STEP)
        env = {"PATH": os.environ["PATH"], "HOME": str(repo.parent), "CRUX_CI_EVENT": event}
        if before:
            env["CRUX_CI_DIFF_BASE"] = before
        workspace_zephyr = repo.parent / "zephyr"
        if zephyr != workspace_zephyr and workspace_zephyr.exists():
            workspace_zephyr.rename(repo.parent / "zephyr-moved-away")
        # run-tier.sh runs a check as: bash -eo pipefail -c <run>, from the repository root.
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
            cwd=repo, env=env, capture_output=True, text=True,
        )

    # The fetch step runs for real with a stub for west, a local repository in place of the
    # Zephyr remote (git rewrites the URL), and the real git.
    def run_fetch(self, west_list_fails_before_update=False, cloned=False, revision=None,
                  path_name="zephyr", wrong_remote_commit=False):
        step = self.fetch_step()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = pathlib.Path(directory.name).resolve()
        remote = base / "remote"
        (remote / "scripts").mkdir(parents=True)
        (remote / "scripts" / "checkpatch.pl").write_text("#!/usr/bin/perl\n")
        subprocess.run(["git", "init", "-q", "-b", "main", str(remote)], check=True)
        git(remote, "add", "-A")
        git(remote, "commit", "-q", "-m", "zephyr")
        commit = git(remote, "rev-parse", "HEAD")
        if wrong_remote_commit:
            commit = "1" * 40
        (base / "crux-controller").mkdir()
        (base / "bin").mkdir()
        zephyr = base / path_name
        if cloned:
            (zephyr / "scripts").mkdir(parents=True)
            (zephyr / "scripts" / "checkpatch.pl").write_text("#!/usr/bin/perl\n")
        west = base / "bin" / "west"
        # `west list` fails in the stub until a plain `west update` has run, when the scenario
        # says the import does not resolve before that.
        west.write_text(
            "#!/usr/bin/env bash\n"
            "echo \"west $*\" >> \"$WEST_LOG\"\n"
            "case \"$1\" in\n"
            "  init) exit 0;;\n"
            "  update) [[ \"$*\" == update ]] && touch \"$WEST_STATE\"; exit 0;;\n"
            "  list)\n"
            "    if [[ \"$WEST_FAIL_FIRST\" == 1 && ! -f \"$WEST_STATE\" ]]; then exit 1; fi\n"
            "    case \"$*\" in\n"
            "      *revision*) echo \"$ZEPHYR_REVISION\";;\n"
            "      *abspath*) echo \"$ZEPHYR_PATH\";;\n"
            "    esac;;\n"
            "esac\n"
        )
        west.chmod(0o755)
        env = {
            "PATH": f"{base / 'bin'}:{os.environ['PATH']}", "HOME": str(base),
            "WEST_LOG": str(base / "west.log"),
            "WEST_STATE": str(base / "west.state"),
            "WEST_FAIL_FIRST": "1" if west_list_fails_before_update else "0",
            "ZEPHYR_REVISION": revision or commit, "ZEPHYR_PATH": str(zephyr),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.file://{remote}.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/zephyrproject-rtos/zephyr",
        }
        # The check starts in the repository root and moves to the workspace folder itself.
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
            cwd=base / "crux-controller", env=env, capture_output=True, text=True,
        )
        log = (base / "west.log").read_text() if (base / "west.log").exists() else ""
        return result, zephyr, log

    def test_the_fetch_step_gets_exactly_the_named_commit_with_checkpatch(self):
        result, zephyr, log = self.run_fetch()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue((zephyr / "scripts" / "checkpatch.pl").is_file())
        self.assertRegex(log, r"west update crux(?![-\w])")
        self.assertNotIn("west update zephyr", log)
        self.assertNotRegex(log, r"(?m)^west update$")

    def test_a_zephyr_that_the_import_already_cloned_is_not_fetched_again(self):
        result, zephyr, log = self.run_fetch(cloned=True, wrong_remote_commit=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_a_revision_that_is_not_a_full_hash_fails(self):
        result, _, _ = self.run_fetch(revision="v4.4.2")
        self.assertNotEqual(0, result.returncode)

    def test_a_zephyr_outside_the_workspace_folder_fails(self):
        result, _, _ = self.run_fetch(path_name="elsewhere")
        self.assertNotEqual(0, result.returncode)

    def test_a_commit_that_cannot_be_fetched_fails_the_step(self):
        result, zephyr, _ = self.run_fetch(revision="1" * 40)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse((zephyr / "scripts" / "checkpatch.pl").exists())

    def test_when_the_import_does_not_resolve_before_a_full_update_plain_west_update_runs(self):
        result, zephyr, log = self.run_fetch(west_list_fails_before_update=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertRegex(log, r"(?m)^west update$")

    def test_a_pull_request_with_a_bad_change_fails(self):
        _, repo, zephyr = self.make_repo()
        target = git(repo, "rev-parse", "HEAD")
        self.commit(repo, "int BAD_BRACES;\n")
        result = self.run_step(repo, zephyr, "change-request", target)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("stand-in checkpatch: error", result.stdout)

    def test_a_pull_request_with_a_clean_change_passes(self):
        _, repo, zephyr = self.make_repo()
        target = git(repo, "rev-parse", "HEAD")
        self.commit(repo, "int fine;\n")
        result = self.run_step(repo, zephyr, "change-request", target)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_a_push_checks_everything_since_the_previous_push(self):
        _, repo, zephyr = self.make_repo()
        before = git(repo, "rev-parse", "HEAD")
        self.commit_file(repo, "b.c", "int BAD_BRACES;\n")
        self.commit(repo, "int fine;\n")
        # The last commit alone is clean, so only the whole range shows the problem.
        result = self.run_step(repo, zephyr, "post-merge", before)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertEqual(0, self.run_step(repo, zephyr, "change-request", git(repo, "rev-parse", "HEAD^")).returncode)

    def test_a_push_without_a_previous_sha_is_an_error(self):
        # scripts/ci/run-tier.sh passes no comparison base for a missing or all-zero previous SHA.
        _, repo, zephyr = self.make_repo()
        result = self.run_step(repo, zephyr, "post-merge", "")
        self.assertEqual(2, result.returncode)
        self.assertIn("previous push SHA", result.stderr)

    def test_a_manual_or_nightly_run_without_a_base_checks_the_latest_commit(self):
        # A run with no change to compare with (by hand, nightly) checks the latest commit, as the
        # patch style check of Crux does.
        _, repo, zephyr = self.make_repo()
        self.commit(repo, "int BAD_BRACES;\n")
        for event in ("manual", "scheduled"):
            self.assertEqual(1, self.run_step(repo, zephyr, event).returncode, event)
        self.commit(repo, "int fine;\n")
        self.assertEqual(0, self.run_step(repo, zephyr, "manual").returncode)

    def test_a_missing_zephyr_fails_instead_of_passing(self):
        _, repo, zephyr = self.make_repo()
        target = git(repo, "rev-parse", "HEAD")
        self.commit(repo, "int BAD_BRACES;\n")
        result = self.run_step(repo, zephyr.parent / "nowhere", "change-request", target)
        self.assertEqual(2, result.returncode)

    @unittest.skipIf(sys.version_info < (3, 11), "scripts/ci/tiers.py needs Python 3.11 or later")
    def test_a_push_fetches_a_previous_commit_that_the_clone_lacks(self):
        # The selector fetches the comparison base that a shallow clone lacks, and the check then
        # covers every commit since it.
        spec = importlib.util.spec_from_file_location("ci_tiers_for_patch_style", ROOT / "scripts/ci/tiers.py")
        tiers = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = tiers  # the dataclasses of the module look themselves up here
        spec.loader.exec_module(tiers)
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
        change = tiers.changed_files(clone, before)
        self.assertEqual(["a.c", "b.c"], change.files)
        (clone / "scripts" / "ci").mkdir(parents=True, exist_ok=True)
        (base / "clone" / "zephyr").symlink_to(zephyr, target_is_directory=True)
        result = self.run_step(clone, base / "clone" / "zephyr", "post-merge", change.diff_base)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)


@ci_map.needs_tomllib
class KitIncludeStep(CannotBeSilenced):
    """The include check as the Crux style kit wraps it, from an immutable commit."""

    NAME = "kit-include-check"

    def step(self):
        return only_step("boundary", self.NAME)

    def test_the_commit_is_a_full_hash_and_both_urls_name_it(self):
        step = self.step()
        self.assertRegex(step["env"]["KIT_COMMIT"], r"^[0-9a-f]{40}$")
        run = step["run"]
        self.assertIn(
            "https://raw.githubusercontent.com/wonny-labs/crux/${KIT_COMMIT}/templates/product",
            run,
        )
        self.assertIn("/check_domain_includes.py", run)
        self.assertIn("/style/check-includes.sh", run)

    def test_both_files_have_a_committed_sha256(self):
        env = self.step()["env"]
        for name in ("CHECKER_SHA256", "WRAPPER_SHA256"):
            self.assertRegex(env[name], r"^[0-9a-f]{64}$", name)
        self.assertNotEqual(env["CHECKER_SHA256"], env["WRAPPER_SHA256"])

    def test_the_checker_hash_is_the_one_of_the_existing_step(self):
        existing = only_step("boundary", "product-include-check")
        self.assertEqual(existing["env"]["CHECK_SHA256"], self.step()["env"]["CHECKER_SHA256"])

    def test_downloads_fail_on_http_errors_and_are_verified_before_the_run(self):
        run = self.step()["run"]
        self.assertEqual(2, len(re.findall(r"curl\b[^\n]*--fail", run)))
        self.assertEqual(2, run.count("sha256sum --check --strict"))
        last_download = run.rindex("curl")
        first_verify = run.index("sha256sum")
        execution = run.index('bash "$kit/style/check-includes.sh"')
        self.assertLess(last_download, first_verify)
        self.assertLess(first_verify, execution)

    def test_the_wrapper_runs_inside_the_checkout_and_the_step_cannot_pass_on_failure(self):
        # scripts/ci/run-tier.sh starts every check in the repository root, and this one stays there.
        step = self.step()
        self.assertNotRegex(step["run"], r"(^|\n)\s*cd ")
        self.assertTrue(step["run"].lstrip().startswith("set -euo pipefail"))
        self.assert_can_fail("boundary", step)

    def test_the_existing_boundary_steps_are_still_there(self):
        runs = ci_map.commands("boundary")
        self.assertRegex(runs, r"check_boundary\.py --repo crux-controller --crux-root crux(?![-\w])")
        self.assertIn('python3 "$script" --product .', runs)

    # The step text runs for real with a curl that serves local stand-ins.
    def run_step(self, wrapper_text, tamper=False):
        step = self.step()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = pathlib.Path(directory.name).resolve()
        served = base / "served"
        (served / "style").mkdir(parents=True)
        (base / "bin").mkdir()
        (base / "crux-controller").mkdir()
        checker = "print('checker')\n"
        (served / "check_domain_includes.py").write_text(checker)
        shim = base / "bin" / "curl"
        shim.write_text(
            "#!/usr/bin/env bash\n"
            "while [[ $# -gt 0 ]]; do\n"
            "  case \"$1\" in --output) out=\"$2\"; shift 2;; -*) shift;; *) url=\"$1\"; shift;; esac\n"
            "done\n"
            "cp \"$SERVED/${url#*/templates/product/}\" \"$out\"\n"
        )
        shim.chmod(0o755)
        served_wrapper = "#!/usr/bin/env bash\necho tampered\n" if tamper else wrapper_text
        (served / "style" / "check-includes.sh").write_text(served_wrapper)
        env = {
            "PATH": f"{base / 'bin'}:{os.environ['PATH']}", "HOME": str(base),
            "TMPDIR": str(base / "tmp"), "SERVED": str(served),
            "KIT_COMMIT": "0" * 40, "CHECKER_SHA256": hashlib.sha256(checker.encode()).hexdigest(),
            "WRAPPER_SHA256": hashlib.sha256(wrapper_text.encode()).hexdigest(),
        }
        (base / "tmp").mkdir()
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
            cwd=base / "crux-controller", env=env, capture_output=True, text=True,
        )

    def test_a_passing_wrapper_passes_the_step(self):
        result = self.run_step("#!/usr/bin/env bash\necho wrapper ran\nexit 0\n")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("wrapper ran", result.stdout)

    def test_a_failing_wrapper_fails_the_step(self):
        result = self.run_step("#!/usr/bin/env bash\necho include violation >&2\nexit 1\n")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("include violation", result.stderr)

    def test_a_download_that_does_not_match_its_hash_never_runs(self):
        result = self.run_step("#!/usr/bin/env bash\necho wrapper ran\nexit 0\n", tamper=True)
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("tampered", result.stdout)
        self.assertNotIn("wrapper ran", result.stdout)


if __name__ == "__main__":
    unittest.main()
