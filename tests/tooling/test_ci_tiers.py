# SPDX-License-Identifier: Apache-2.0
"""Check the CI tiers: the map file scripts/ci/checks.toml, the selector scripts/ci/tiers.py (a copy
of the Crux selector) and the thin CI files that call scripts/ci/run-tier.sh.

The rules held here:

- the full tier runs exactly the recorded checks under the path filters of their workflows, and
  removing one fails this test;
- a fast run falls back to the full tier whenever the selector is unsure: an unknown path, a CI,
  build, script or shared configuration file, too many components, an unknown or empty change;
- a documentation-only change runs only the documentation readers in the fast tier;
- a fast run is never larger than the full run of the same change, and within a job it runs a
  prefix of the full run, so that a check never runs without the checks before it;
- the tier and the comparison base come from plain environment values of GitHub or Jenkins;
- the runner stops at the first failing check and writes JUnit;
- every job has a GitHub job and a Jenkins stage that only call the repository scripts.

The selector needs Python 3.11 or later (tomllib); on an older Python this module skips.
"""

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET

import yaml

import ci_map

REPO = Path(__file__).resolve().parents[2]
TIERS_PATH = REPO / "scripts/ci/tiers.py"
MANIFEST = REPO / "scripts/ci/checks.toml"
WORKFLOWS = REPO / ".github/workflows"


def load_tiers():
    if sys.version_info < (3, 11):
        return None
    spec = importlib.util.spec_from_file_location("ci_tiers", TIERS_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ci_tiers"] = module
    spec.loader.exec_module(module)
    return module


tiers = load_tiers()
needs_selector = unittest.skipIf(tiers is None, "scripts/ci/tiers.py needs Python 3.11 or later")

# The checks of the full tier, by job, in run order. Remove an id only with an approved change that
# removes the check, and say so in the pull request.
BUDGET = {f"budget-{c}": [f"budget-{c}"] for c in ("minimal", "workload", "net", "file", "system", "sntp")}
EXPECTED_FULL = {
    "tooling": ["tooling-tests", "secret-scan", "spdx"],
    "pins": ["pins-contract", "pins-mbed-default", "pins-mbed-group-on", "pins-negative-unnarrowed-import",
             "pins-negative-pin-without-reason"],
    "host-OFF": ["host-tests-sanitize-off", "host-coverage"],
    "host-ON": ["host-tests-sanitize-on"],
    "workload": ["workload-native-sim", "workload-build", "workload-outputs", "workload-config"],
    "net": ["net-build", "net-outputs", "net-config"],
    "file": ["file-build", "file-outputs", "file-config", "file-symbols"],
    "system": ["system-build", "system-outputs", "system-config", "system-symbols"],
    "sntp": ["sntp-build", "sntp-outputs", "sntp-config", "sntp-symbols"],
    "management": ["management-mbed-default", "management-mbed-group-on", "management-mbed-fetch",
                   "management-sdk", "management-native-sim", "management-native-sim-report", "management-build",
                   "management-outputs", "management-config", "management-symbols"],
    "boundary": ["boundary-check", "product-include-check", "kit-include-check", "template-check"],
    "patch-style": ["patch-style-fetch-zephyr", "patch-style"],
    "minimal": ["minimal-build", "minimal-outputs"],
    "base": ["base-mbed-default", "base-mbed-group-on", "base-mbed-fetch", "base-sdk", "base-native-sim",
             "base-native-sim-report", "base-native-sim-interactive-report", "static-analysis-zephyr",
             "base-prerequisite-refused", "base-build", "base-outputs",
             "base-config", "base-symbols", "base-sbom"],
    "static": ["format", "static-analysis"],
    **BUDGET,
    "budget-management": ["budget-management-mbed", "budget-management-sdk", "budget-management"],
    "budget-base": ["budget-base-mbed", "budget-base-sdk", "budget-base"],
    "devcontainer": ["devcontainer-image", "devcontainer-tooling-tests", "devcontainer-format",
                     "devcontainer-static-analysis", "devcontainer-host-tests", "devcontainer-boundary-check",
                     "devcontainer-product-include-check", "devcontainer-native-sim",
                     "devcontainer-workload-build", "devcontainer-workload-outputs",
                     "devcontainer-workload-config"],
    "rebuild": ["rebuild-first-workspace", "rebuild-sdk", "rebuild-first-build", "rebuild-second-build",
                "rebuild-compare", "rebuild-not-done"],
    "release": ["release-tool-tests", "release-pins", "release-freeze", "release-fresh-workspace",
                "release-sdk", "release-build", "release-parse-spdx", "release-assemble",
                "release-check-bundle", "release-print-manifest", "release-sbom-scan", "release-not-done"],
}
EXPECTED_NIGHTLY_ONLY = {
    "scheduled-main": ["scheduled-pin-main", "scheduled-fetch", "scheduled-pins", "scheduled-sdk",
                       "scheduled-build", "scheduled-outputs", "scheduled-config"],
    "product-integration": ["product-integration-workspace", "product-integration-build",
                            "product-integration-run", "product-integration-sbom",
                            "product-integration-vulnerabilities"],
    "template": ["template-workspace", "template-build", "template-run", "template-test", "template-joining-steps"],
}
# Checks of the nightly tier only, in a job that the full tier runs too, by job, in run order after
# the checks of the full tier.
EXPECTED_NIGHTLY_EXTRA = {
    "base": ["base-vulnerabilities", "template-board-workspace", "template-board-build"],
}
# The jobs of ci.yml and budget.yml run for every change, documentation-only changes included. The
# other three workflows run only for the paths of their filter.
PATH_FILTERED = {"devcontainer", "rebuild", "release"}
EVERY_CHANGE = {job for job in EXPECTED_FULL if job not in PATH_FILTERED}
# Which workflow runs which jobs of the map file.
WORKFLOW_JOBS = {
    "ci.yml": ["tooling", "pins", "host-OFF", "host-ON", "workload", "net", "file", "system", "sntp",
               "management", "boundary", "patch-style", "minimal", "base", "static"],
    "budget.yml": [f"budget-{c}" for c in ("minimal", "workload", "net", "file", "system", "sntp", "management",
                                          "base")],
    "devcontainer.yml": ["devcontainer"],
    "rebuild.yml": ["rebuild"],
    "release.yml": ["release"],
    "scheduled-main.yml": ["scheduled-main", "product-integration", "template"],
}
# The checks that every fast run selects: the tooling tests, the secret scan and the SPDX headers.
DOCS_READERS = {"tooling-tests", "secret-scan", "spdx"}
C_CHECKS = {"format", "static-analysis", "patch-style-fetch-zephyr", "patch-style"}


def ids_of(checks):
    return [c.id for c in checks]


def by_job(checks):
    result = {}
    for check in checks:
        result.setdefault(check.job, []).append(check.id)
    return result


def flat(jobs):
    return {i for ids in jobs.values() for i in ids}


def nightly_expected():
    """The checks of the nightly tier, by job: the full tier, the nightly-only jobs, and the nightly
    checks of jobs that the full tier runs too."""
    jobs = {job: list(ids) for job, ids in {**EXPECTED_FULL, **EXPECTED_NIGHTLY_ONLY}.items()}
    for job, ids in EXPECTED_NIGHTLY_EXTRA.items():
        jobs[job] = jobs[job] + ids
    return jobs


def workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


def triggers(data):
    # PyYAML reads the key `on` as the boolean True.
    return data.get("on", data.get(True))


@needs_selector
class ManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = tiers.load_manifest(MANIFEST)

    def plan(self, tier, changed):
        return tiers.plan(self.manifest, tier, changed).checks

    def test_the_full_tier_runs_every_recorded_check_in_order(self):
        self.assertEqual(EXPECTED_FULL, by_job(self.plan("full", None)))

    def test_the_nightly_tier_adds_only_the_nightly_jobs(self):
        self.assertEqual(nightly_expected(), by_job(self.plan("nightly", None)))

    def test_the_nightly_tier_ignores_the_change(self):
        self.assertEqual(self.plan("nightly", None), self.plan("nightly", ["docs/a.md"]))

    def test_every_job_has_checks_and_every_check_runs_in_full_or_nightly(self):
        self.assertEqual(set(self.manifest.jobs), set(EXPECTED_FULL) | set(EXPECTED_NIGHTLY_ONLY))
        everything = flat(nightly_expected())
        self.assertEqual(everything, {c.id for c in self.manifest.checks})

    def test_every_fast_component_exists(self):
        for check in self.manifest.checks:
            if isinstance(check.fast, list):
                with self.subTest(check=check.id):
                    self.assertLessEqual(set(check.fast), set(self.manifest.components))

    def test_no_check_is_advisory_and_none_hides_a_failure(self):
        for check in self.manifest.checks:
            with self.subTest(check=check.id):
                self.assertFalse(check.advisory)
                self.assertNotIn("continue-on-error", check.run)

    def test_no_check_names_a_github_value_that_another_ci_system_lacks(self):
        # A check may write the GitHub job summary when it exists, and must work without it.
        for check in self.manifest.checks:
            with self.subTest(check=check.id):
                self.assertNotIn("${{", check.run)
                self.assertNotIn("GITHUB_WORKSPACE", check.run)
                self.assertNotIn("GITHUB_EVENT", check.run)
                for summary in re.findall(r"\$\{GITHUB_STEP_SUMMARY[^}]*\}|\$GITHUB_STEP_SUMMARY\b", check.run):
                    self.assertEqual("${GITHUB_STEP_SUMMARY:-/dev/stdout}", summary)
                for temp in re.findall(r"\$\{RUNNER_TEMP[^}]*\}|\$RUNNER_TEMP\b", check.run):
                    self.assertEqual("${RUNNER_TEMP:-/tmp}", temp)

    def test_every_check_that_uses_the_workspace_moves_there_first(self):
        for check in self.manifest.checks:
            if "crux-controller/" in check.run and check.job != "devcontainer":
                with self.subTest(check=check.id):
                    first = [line for line in check.run.splitlines() if line and not line.startswith("#")]
                    moves = [line for line in first if line.startswith("cd ")]
                    self.assertTrue(moves, "a check that names crux-controller/ runs from the workspace")

    def test_every_board_build_requires_the_verified_zephyr_gate(self):
        for check in self.manifest.checks:
            if "west build -p always" in check.run:
                with self.subTest(check=check.id):
                    self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", check.run)
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", ci_map.BUDGET.read_text())


@needs_selector
class FullTierScopeTest(unittest.TestCase):
    """The full tier keeps the path filters of the workflows."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = tiers.load_manifest(MANIFEST)

    def jobs(self, changed):
        return set(by_job(tiers.plan(self.manifest, "full", changed).checks))

    def test_a_documentation_change_runs_what_ci_yml_and_budget_yml_ran_for_it(self):
        self.assertEqual(EVERY_CHANGE, self.jobs(["docs/glossary.md", "README.md"]))

    def test_a_source_change_runs_ci_and_budget_but_not_the_path_filtered_jobs(self):
        self.assertEqual(EVERY_CHANGE, self.jobs(["app/src/policy.c"]))

    def test_a_release_change_also_runs_the_rebuild_and_the_release_dry_run(self):
        self.assertEqual(EVERY_CHANGE | {"rebuild", "release"}, self.jobs(["release/assemble_bundle.py"]))

    def test_a_manifest_change_runs_the_dev_container_and_the_release_dry_run(self):
        self.assertEqual(EVERY_CHANGE | {"devcontainer", "release"}, self.jobs(["west.yml"]))

    def test_a_dev_container_change_runs_the_dev_container_job(self):
        for path in (".devcontainer/Dockerfile", "scripts/dev-shell.sh", "scripts/bootstrap.sh",
                     ".vscode/tasks.json", ".github/workflows/devcontainer.yml"):
            with self.subTest(path=path):
                self.assertEqual(EVERY_CHANGE | {"devcontainer"}, self.jobs([path]))

    def test_a_change_of_the_checks_runs_every_path_filtered_job(self):
        self.assertEqual(set(EXPECTED_FULL), self.jobs(["scripts/ci/checks.toml"]))

    def test_an_unknown_change_runs_every_full_check(self):
        self.assertEqual(flat(EXPECTED_FULL), {c.id for c in tiers.plan(self.manifest, "full", None).checks})

    def test_each_scope_is_the_path_filter_of_its_workflow_and_the_checks_folder(self):
        for job in sorted(PATH_FILTERED):
            with self.subTest(job=job):
                on = triggers(workflow(f"{job}.yml"))
                self.assertEqual(sorted(on["pull_request"]["paths"]), sorted(self.manifest.scopes[job]))
                self.assertIn("scripts/ci/**", self.manifest.scopes[job])


@needs_selector
class FastTierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = tiers.load_manifest(MANIFEST)

    def fast(self, changed):
        return tiers.plan(self.manifest, "fast", changed)

    def full(self, changed):
        return tiers.plan(self.manifest, "full", changed)

    def ids(self, changed):
        result = self.fast(changed)
        self.assertFalse(result.fallback, result.reason)
        return set(ids_of(result.checks))

    def assert_falls_back(self, changed):
        result = self.fast(changed)
        self.assertTrue(result.fallback, f"{changed} must fall back to the full tier")
        self.assertEqual(self.full(changed).checks, result.checks)

    def test_unsure_changes_fall_back_to_the_full_tier(self):
        cases = [
            ["new_area/source.c"],
            ["CODEOWNERS"],
            [".github/workflows/ci.yml"],
            ["Jenkinsfile"],
            ["scripts/ci/checks.toml"],
            ["scripts/ci/tiers.py"],
            ["scripts/check_boundary.py"],
            ["scripts/include-check-pins.json"],
            ["scripts/build-board.sh"],
            ["west.yml"],
            ["app/CMakeLists.txt"],
            ["app/Kconfig"],
            ["app/prj.conf"],
            ["app/conf/net.conf"],
            ["app/boards/net.overlay"],
            ["app/boards/mimxrt1060_evk_mimxrt1062_qspi_B.conf"],
            ["framework/compose/CMakeLists.txt"],
            ["framework/management/management.cmake"],
            ["tests/native_sim/workload/prj.conf"],
            ["tests/native_sim/workload/CMakeLists.txt"],
            ["tests/host/CMakeLists.txt"],
            ["budgets/limits.json"],
            ["budgets/collect.py"],
            [".devcontainer/Dockerfile"],
            [".vscode/settings.json"],
            [".clang-format"],
            [".clang-tidy"],
            ["app/src/policy.c", "new_area/b.c"],
        ]
        for changed in cases:
            with self.subTest(changed=changed):
                self.assert_falls_back(changed)

    def test_a_change_touching_many_components_falls_back(self):
        self.assert_falls_back(["app/src/a.c", "tests/host/test_a.c", "tests/native_sim/workload/src/a.c",
                                "tests/tooling/test_x.py"])

    def test_an_unknown_or_empty_change_falls_back(self):
        self.assert_falls_back(None)
        self.assert_falls_back([])

    def test_a_documentation_change_runs_only_the_documentation_readers(self):
        self.assertEqual(DOCS_READERS, self.ids(["docs/glossary.md", "README.md", "docs/findings/README.md"]))

    def test_a_tooling_test_or_release_change_runs_only_the_tooling_tests(self):
        self.assertEqual(DOCS_READERS, self.ids(["tests/tooling/test_docs.py"]))
        self.assertEqual(DOCS_READERS, self.ids(["release/assemble_bundle.py"]))

    def test_a_product_source_change_runs_the_quick_checks_and_one_board_build(self):
        ids = self.ids(["app/src/policy.c", "docs/architecture.md"])
        expected = (DOCS_READERS | C_CHECKS
                    | {"host-tests-sanitize-off", "host-coverage", "host-tests-sanitize-on"}
                    | set(EXPECTED_FULL["boundary"]) | set(EXPECTED_FULL["workload"])
                    | set(EXPECTED_FULL["management"][:6]))
        self.assertEqual(expected, ids)
        builds = [i for i in ids if i.endswith("-build")]
        self.assertEqual(["workload-build"], builds)

    def test_a_scenario_change_runs_twister_and_no_board_build(self):
        ids = self.ids(["tests/native_sim/workload/src/test_workload.c"])
        self.assertEqual(DOCS_READERS | C_CHECKS | {"workload-native-sim"}, ids)

    def test_a_host_test_change_runs_the_host_tests(self):
        ids = self.ids(["tests/host/test_policy.c"])
        self.assertEqual(
            DOCS_READERS | C_CHECKS | {"host-tests-sanitize-off", "host-coverage", "host-tests-sanitize-on"},
            ids)

    def test_a_management_change_runs_its_scenario_and_no_board_build(self):
        ids = self.ids(["framework/management/management_page.c"])
        expected = (DOCS_READERS | C_CHECKS | set(EXPECTED_FULL["boundary"])
                    | set(EXPECTED_FULL["management"][:6]))
        self.assertEqual(expected, ids)

    def test_a_fast_run_is_never_larger_than_the_full_run_and_keeps_its_order(self):
        for name, patterns in self.manifest.components.items():
            changed = [patterns[0].replace("**", "x/y.c")]
            with self.subTest(component=name):
                fast = self.fast(changed).checks
                full = self.full(changed).checks
                self.assertLessEqual(set(fast), set(full))
                order = ids_of(full)
                self.assertEqual(sorted(order.index(c.id) for c in fast), [order.index(c.id) for c in fast])

    def test_within_a_job_a_fast_run_runs_a_prefix_of_the_full_run(self):
        # A check may rely on what the checks before it in its job did (a fetch, a build), so a fast
        # run never skips a check and runs a later one of the same job.
        for name, patterns in self.manifest.components.items():
            changed = [patterns[0].replace("**", "x/y.c")]
            fast = by_job(self.fast(changed).checks)
            full = by_job(self.full(changed).checks)
            for job, ids in fast.items():
                with self.subTest(component=name, job=job):
                    self.assertEqual(full[job][: len(ids)], ids)

    def test_every_fast_component_selects_less_than_the_full_tier(self):
        for name, patterns in self.manifest.components.items():
            changed = [patterns[0].replace("**", "x/y.c")]
            with self.subTest(component=name):
                self.assertLess(len(self.fast(changed).checks), len(self.full(changed).checks))

    def test_the_fallback_names_its_reason(self):
        self.assertIn("scripts/check_boundary.py", self.fast(["scripts/check_boundary.py"]).reason)
        self.assertIn("new_area/source.c", self.fast(["new_area/source.c"]).reason)


@needs_selector
class PatternTest(unittest.TestCase):
    def test_patterns_follow_the_workflow_path_filter_rules(self):
        self.assertTrue(tiers.matches("README.md", ["**.md"]))
        self.assertTrue(tiers.matches("docs/a/b.md", ["**.md"]))
        self.assertTrue(tiers.matches("docs/a/b.png", ["docs/**"]))
        self.assertFalse(tiers.matches("docsx/a", ["docs/**"]))
        self.assertTrue(tiers.matches("app/Kconfig", ["**/Kconfig*"]))
        self.assertTrue(tiers.matches("Kconfig", ["**/Kconfig*"]))
        self.assertTrue(tiers.matches("app/conf/net.conf", ["**/*.conf"]))
        self.assertFalse(tiers.matches("app/src/a.c", ["app/*.c"]))

    def test_a_later_negation_removes_earlier_matches(self):
        patterns = ["**", "!docs/**", "!**.md", "docs/keep-*.md"]
        self.assertTrue(tiers.matches("app/src/a.c", patterns))
        self.assertFalse(tiers.matches("docs/glossary.md", patterns))
        self.assertFalse(tiers.matches("README.md", patterns))
        self.assertTrue(tiers.matches("docs/keep-this.md", patterns))


@needs_selector
class ManifestValidationTest(unittest.TestCase):
    BASE = textwrap.dedent("""\
        version = 1
        [selection]
        docs = ["docs/**"]
        escalate = []
        max_components = 3
        [components]
        a = ["a/**"]
        [jobs.one]
        description = "one"
        """)

    def load(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checks.toml"
            path.write_text(self.BASE + text)
            return tiers.load_manifest(path)

    def test_a_valid_manifest_loads(self):
        manifest = self.load('[[check]]\nid = "x"\njob = "one"\nrun = "true"\nfast = ["a"]\n')
        self.assertEqual(["x"], [c.id for c in manifest.checks])

    def test_mistakes_are_rejected(self):
        cases = [
            ('[[check]]\nid = "x"\njob = "two"\nrun = "true"\n', "unknown job"),
            ('[[check]]\nid = "x"\njob = "one"\nrun = "true"\nfast = ["b"]\n', "unknown component"),
            ('[[check]]\nid = "x"\njob = "one"\nrun = "true"\n[[check]]\nid = "x"\njob = "one"\nrun = "true"\n',
             "duplicate"),
            ('[[check]]\nid = "x"\njob = "one"\nrun = "true"\nfsat = "always"\n', "unknown key"),
            ('[[check]]\nid = "x"\njob = "one"\nrun = "true"\nscope = "nowhere"\n', "unknown scope"),
            ('[[check]]\nid = "x"\njob = "one"\nrun = "true"\ntiers = ["fast"]\n', "tiers"),
            ('[[check]]\nid = "x"\njob = "one"\nrun = "true"\nfast = "sometimes"\n', "fast"),
            ('[[check]]\nid = "x"\njob = "one"\nrun = "true"\ntiers = ["nightly"]\nfast = "always"\n', "fast"),
            ('[jobs.two]\ndescription = "two"\n[[check]]\nid = "x"\njob = "one"\nrun = "true"\n', "no checks"),
        ]
        for text, words in cases:
            with self.subTest(words=words):
                with self.assertRaises(tiers.ManifestError) as caught:
                    self.load(text)
                self.assertIn(words, str(caught.exception))


def git(directory, *arguments):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *arguments],
                          cwd=directory, check=True, capture_output=True, text=True).stdout.strip()


def commit(directory, files):
    for name, text in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(directory, "add", "-A")
    git(directory, "commit", "-q", "--allow-empty", "-m", "change")
    return git(directory, "rev-parse", "HEAD")


@needs_selector
class ChangedFilesTest(unittest.TestCase):
    """The change comes from plain git: the files since the merge base with the comparison base."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ci-tiers-test-")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        origin = root / "origin"
        origin.mkdir()
        git(origin, "init", "-q")
        commit(origin, {"README.md": "a\n", "src/a.c": "int a;\n" * 20})
        self.clone = root / "clone"
        git(root, "clone", "-q", str(origin), str(self.clone))
        git(self.clone, "checkout", "-q", "-b", "topic")
        self.origin = origin
        self.root = root

    def changed(self, base="origin/main", clone=None):
        return tiers.changed_files(clone or self.clone, base)

    def docs_only(self):
        files = self.changed().files
        return files is not None and tiers.is_docs_only(files, ["docs/**", "**.md"])

    def test_a_documentation_change_is_documentation_only(self):
        commit(self.clone, {"docs/data.txt": "d\n", "tests/README.md": "t\n"})
        self.assertTrue(self.docs_only())

    def test_a_source_change_is_not(self):
        commit(self.clone, {"src/b.c": "int b;\n"})
        self.assertFalse(self.docs_only())

    def test_a_source_file_moved_into_the_documentation_is_not(self):
        (self.clone / "docs").mkdir()
        git(self.clone, "mv", "src/a.c", "docs/a.md")
        commit(self.clone, {})
        self.assertEqual(["docs/a.md", "src/a.c"], self.changed().files)
        self.assertFalse(self.docs_only())

    def test_an_empty_change_is_not(self):
        commit(self.clone, {})
        self.assertEqual([], self.changed().files)
        self.assertFalse(self.docs_only())

    def test_changes_made_only_on_the_target_branch_are_not_counted(self):
        commit(self.origin, {"src/main-only.c": "int m;\n"})
        git(self.clone, "fetch", "-q", "origin")
        mine = commit(self.clone, {"docs/mine.md": "m\n"})
        change = self.changed()
        self.assertEqual(["docs/mine.md"], change.files)
        self.assertEqual(git(self.clone, "rev-parse", f"{mine}^"), change.diff_base)

    def test_a_previous_commit_that_a_shallow_clone_lacks_is_fetched(self):
        # The post-merge comparison base is the commit before the push; a clone without it fetches it.
        before = commit(self.origin, {"src/b.c": "int BAD;\n"})
        commit(self.origin, {"src/c.c": "int c;\n"})
        commit(self.origin, {"src/d.c": "int d;\n"})
        shallow = self.root / "shallow"
        git(self.root, "clone", "-q", "--depth", "1", f"file://{self.origin}", str(shallow))
        lacks = subprocess.run(["git", "-C", str(shallow), "cat-file", "-e", before + "^{commit}"],
                               capture_output=True)
        self.assertNotEqual(0, lacks.returncode, "the clone must lack the previous commit")
        self.assertEqual(["src/c.c", "src/d.c"], self.changed(before, shallow).files)

    def test_an_unknown_base_gives_no_change(self):
        self.assertIsNone(self.changed(base="origin/no-such-branch").files)
        self.assertIsNone(self.changed(base="0" * 40).files)
        self.assertIsNone(self.changed(base=None).files)


@needs_selector
class ContextTest(unittest.TestCase):
    """The tier and base of `auto` come from either CI system's environment."""

    def context(self, env, event=None):
        with tempfile.TemporaryDirectory() as directory:
            if event is not None:
                path = Path(directory) / "event.json"
                path.write_text(json.dumps(event))
                env = {**env, "GITHUB_EVENT_PATH": str(path)}
            return tiers.ci_context(env)

    def github(self, name, event, **extra):
        return self.context({"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": name, **extra}, event)

    def test_github_events(self):
        draft = self.github("pull_request", {"pull_request": {"draft": True}}, GITHUB_BASE_REF="main")
        ready = self.github("pull_request", {"pull_request": {"draft": False}}, GITHUB_BASE_REF="main")
        self.assertEqual(("fast", "origin/main", "change-request"), draft)
        self.assertEqual(("full", "origin/main", "change-request"), ready)
        repository = {"default_branch": "main"}
        merged = self.github("push", {"before": "a" * 40, "repository": repository}, GITHUB_REF="refs/heads/main")
        self.assertEqual(("full", "a" * 40, "post-merge"), merged)
        self.assertEqual(("nightly", None, "scheduled"), self.github("schedule", {}))
        self.assertEqual(("full", None, "manual"), self.github("workflow_dispatch", {}))

    def test_jenkins_builds(self):
        jenkins = {"JENKINS_URL": "https://ci.example.invalid/"}
        change = self.context({**jenkins, "CHANGE_ID": "12", "CHANGE_TARGET": "main", "BRANCH_NAME": "PR-12"})
        self.assertEqual(("full", "origin/main", "change-request"), change)
        merged = self.context({**jenkins, "BRANCH_NAME": "main", "GIT_PREVIOUS_SUCCESSFUL_COMMIT": "c" * 40})
        self.assertEqual(("full", "c" * 40, "post-merge"), merged)
        self.assertEqual(("full", None, "first-build"), self.context({**jenkins, "BRANCH_NAME": "main"}))
        self.assertEqual(("fast", "origin/main", "branch"), self.context({**jenkins, "BRANCH_NAME": "feature/x"}))
        timer = self.context({**jenkins, "BRANCH_NAME": "main", "CRUX_CI_TRIGGER": "timer"})
        self.assertEqual(("nightly", None, "scheduled"), timer)

    def test_a_local_run_is_fast_against_main(self):
        self.assertEqual(("fast", "origin/main", "local"), self.context({}))


@needs_selector
class RunnerTest(unittest.TestCase):
    """Run a small map file end to end through scripts/ci/run-tier.sh."""

    MANIFEST = textwrap.dedent("""\
        version = 1
        [selection]
        docs = ["docs/**"]
        escalate = []
        max_components = 3
        [components]
        a = ["a/**"]
        [jobs.one]
        description = "one"
        env = { CI_TEST_JOB_VALUE = "job" }
        [jobs.two]
        description = "two"
        [[check]]
        id = "first"
        job = "one"
        run = "echo first-ran $CI_TEST_JOB_VALUE $CRUX_CI_TIER"
        [[check]]
        id = "fails"
        job = "one"
        run = "echo about-to-fail; exit 3"
        [[check]]
        id = "after"
        job = "one"
        run = "echo after-ran"
        [[check]]
        id = "other"
        job = "two"
        run = "echo other-ran"
        """)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ci-runner-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        git(self.root, "init", "-q")
        (self.root / "checks.toml").write_text(self.MANIFEST)
        commit(self.root, {"a/x.c": "x\n"})

    def run_tier(self, *arguments):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("GITHUB_", "CHANGE_", "JENKINS_", "CRUX_CI_"))}
        env["CRUX_CI_PYTHON"] = sys.executable
        command = [str(REPO / "scripts/ci/run-tier.sh"), *arguments, "--manifest", str(self.root / "checks.toml"),
                   "--root", str(self.root)]
        return subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True, check=False)

    def test_the_first_failure_stops_the_job_and_names_the_rerun(self):
        result = self.run_tier("full", "--job", "one")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("first-ran job full", result.stdout)
        self.assertIn("about-to-fail", result.stdout)
        self.assertNotIn("after-ran", result.stdout)
        self.assertNotIn("other-ran", result.stdout)
        self.assertIn("scripts/ci/run-tier.sh full --job one --check fails", result.stderr)
        self.assertIn("CONTRIBUTING.md#ci-tiers", result.stderr)

    def test_junit_and_logs_are_written(self):
        self.run_tier("full", "--job", "one")
        suite = ET.parse(self.root / "build/ci/one.junit.xml").getroot().find("testsuite")
        cases = {case.get("name"): case for case in suite.iter("testcase")}
        self.assertEqual({"first", "fails", "after"}, set(cases))
        self.assertIsNotNone(cases["fails"].find("failure"))
        self.assertIsNotNone(cases["after"].find("skipped"))
        self.assertIn("about-to-fail", (self.root / "build/ci/logs/one/fails.log").read_text())

    def test_plan_and_count_run_nothing(self):
        plan = self.run_tier("full", "--job", "two", "--plan")
        self.assertEqual(0, plan.returncode, plan.stderr)
        self.assertIn("two: other", plan.stdout)
        self.assertNotIn("other-ran", plan.stdout)
        self.assertEqual("3", self.run_tier("full", "--job", "one", "--count").stdout.strip())

    def test_usage_errors_exit_2(self):
        self.assertEqual(2, self.run_tier("sometimes").returncode)
        self.assertEqual(2, self.run_tier("full", "--job", "three").returncode)
        self.assertEqual(2, self.run_tier("full", "--check", "missing").returncode)

    def test_the_real_map_file_plans_without_running_anything(self):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("GITHUB_", "CHANGE_", "JENKINS_", "CRUX_CI_"))}
        env["CRUX_CI_PYTHON"] = sys.executable
        result = subprocess.run([str(REPO / "scripts/ci/run-tier.sh"), "nightly", "--plan"], cwd=REPO, env=env,
                                capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(len(flat(nightly_expected())),
                         len([line for line in result.stdout.splitlines() if ": " in line and not line.startswith("Tier")]))


# --- the CI files ---------------------------------------------------------------------------------

PLAN = "Plan the checks of this tier"
RUN = "Run the checks of this tier"
PLANNED = "steps.plan.outputs.checks != '0'"
# The steps of a workflow job that are not checks: the runner's set-up and the job summary.
SETUP_STEPS = {"Install PyYAML", "Install host packages", "Install pinned build tools", "Install the pinned tools",
               "Restore the Zephyr SDK", "Prepare the workspace", "Write the result summary", PLAN, RUN}


def job_id_of(step_run):
    match = re.search(r'--job (?:"([^"]+)"|(\S+))', step_run)
    return (match.group(1) or match.group(2)) if match else None


class WorkflowTest(unittest.TestCase):
    """A workflow job only sets up its runner and calls the repository scripts."""

    def jobs(self):
        for name, job_ids in WORKFLOW_JOBS.items():
            for job_id, job in workflow(name)["jobs"].items():
                yield name, job_id, job

    def matrix_jobs(self, job):
        """The jobs of the map file that a workflow job runs, with its matrix expanded."""
        run = next(s["run"] for s in job["steps"] if s.get("name") == RUN)
        target = job_id_of(run)
        matrix = job.get("strategy", {}).get("matrix", {})
        for key, values in matrix.items():
            token = "${{ matrix.%s }}" % key
            if token in target:
                return [target.replace(token, str(value)) for value in values]
        return [target]

    def test_every_map_job_runs_in_exactly_one_workflow_job(self):
        seen = {}
        for name, job_id, job in self.jobs():
            for target in self.matrix_jobs(job):
                seen.setdefault(target, []).append(f"{name}:{job_id}")
        expected = {job for jobs in WORKFLOW_JOBS.values() for job in jobs}
        self.assertEqual(expected, set(seen))
        for target, where in seen.items():
            self.assertEqual(1, len(where), (target, where))
        for name, jobs in WORKFLOW_JOBS.items():
            with self.subTest(workflow=name):
                found = [t for _, job in workflow(name)["jobs"].items() for t in self.matrix_jobs(job)]
                self.assertEqual(sorted(jobs), sorted(found))

    def test_every_step_is_set_up_or_the_tier(self):
        for name, job_id, job in self.jobs():
            for step in job["steps"]:
                with self.subTest(workflow=name, job=job_id, step=step.get("name", step.get("uses"))):
                    if "uses" in step:
                        self.assertRegex(step["uses"], r"^actions/(checkout|setup-python|cache)@v\d$")
                    else:
                        self.assertIn(step["name"], SETUP_STEPS)

    def test_the_plan_runs_first_and_every_later_step_waits_for_it(self):
        for name, job_id, job in self.jobs():
            with self.subTest(workflow=name, job=job_id):
                names = [s.get("name", s.get("uses")) for s in job["steps"]]
                plan = names.index(PLAN)
                self.assertTrue(all(s.get("uses", "").startswith(("actions/checkout", "actions/setup-python"))
                                    for s in job["steps"][:plan]))
                for step in job["steps"][plan + 1:]:
                    if step.get("name") == "Write the result summary":
                        continue
                    self.assertEqual(PLANNED, step.get("if"), step.get("name", step.get("uses")))

    def test_the_tier_and_the_preparation_call_only_the_repository_scripts(self):
        target = r'(?P<q>"?)(?P<job>[\w${}. -]+)(?P=q)'
        for name, job_id, job in self.jobs():
            steps = {s.get("name"): s for s in job["steps"]}
            with self.subTest(workflow=name, job=job_id):
                run = re.fullmatch(r'scripts/ci/run-tier\.sh "\$TIER" --job ' + target, steps[RUN]["run"].strip())
                self.assertIsNotNone(run, steps[RUN]["run"])
                self.assertEqual("crux-controller", steps[RUN]["working-directory"])
                plan = steps[PLAN]["run"]
                self.assertIn(f'scripts/ci/run-tier.sh "$TIER" --job {run.group(0).split("--job ")[1]} --plan', plan)
                self.assertIn(f'scripts/ci/run-tier.sh "$TIER" --job {run.group(0).split("--job ")[1]} --count', plan)
                if "Prepare the workspace" in steps:
                    prepare = steps["Prepare the workspace"]
                    self.assertEqual(f'scripts/ci/prepare-job.sh {run.group(0).split("--job ")[1]}',
                                     prepare["run"].strip())
                    self.assertEqual("crux-controller", prepare["working-directory"])

    def test_every_job_checks_out_the_history_into_the_workspace_folder(self):
        for name, job_id, job in self.jobs():
            with self.subTest(workflow=name, job=job_id):
                checkout = job["steps"][0]
                self.assertTrue(checkout["uses"].startswith("actions/checkout@"))
                self.assertEqual("crux-controller", checkout["with"]["path"])
                # The selector compares the change with the merge base, so it needs the history.
                self.assertEqual(0, checkout["with"]["fetch-depth"])

    def test_the_tier_comes_from_the_event_or_the_manual_input(self):
        for name in WORKFLOW_JOBS:
            data = workflow(name)
            on = triggers(data)
            with self.subTest(workflow=name):
                self.assertIn("schedule", on)
                self.assertEqual("choice", on["workflow_dispatch"]["inputs"]["tier"]["type"])
                self.assertEqual({"fast", "full", "nightly"}, set(on["workflow_dispatch"]["inputs"]["tier"]["options"]))
                if "pull_request" in on:
                    self.assertEqual(["opened", "synchronize", "reopened", "ready_for_review"],
                                     on["pull_request"]["types"])
                for job in data["jobs"].values():
                    self.assertEqual("${{ inputs.tier || 'auto' }}", job["env"]["TIER"])

    def test_only_older_runs_of_a_pull_request_are_cancelled(self):
        # The scheduled build has no pull request and never cancels a run.
        self.assertEqual(False, workflow("scheduled-main.yml")["concurrency"]["cancel-in-progress"])
        for name in set(WORKFLOW_JOBS) - {"scheduled-main.yml"}:
            data = workflow(name)
            with self.subTest(workflow=name):
                self.assertEqual("${{ github.event_name == 'pull_request' }}", data["concurrency"]["cancel-in-progress"])

    def test_no_workflow_uploads_an_artefact_or_asks_for_write_permission(self):
        for name in WORKFLOW_JOBS:
            text = (WORKFLOWS / name).read_text()
            with self.subTest(workflow=name):
                self.assertNotIn("upload-artifact", text)
                self.assertEqual({"contents": "read"}, workflow(name)["permissions"])

    def test_the_pinned_tools_of_the_workflows_are_those_of_the_dev_container(self):
        # The Jenkins jobs take their tools from the dev container's list, so the two must agree.
        pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==(\S+)$",
                               (REPO / ".devcontainer/requirements-tools.txt").read_text(), re.MULTILINE))
        for name in WORKFLOW_JOBS:
            for tool, version in re.findall(r"\b(cmake|ninja|west|clang-format|pyyaml)==([\d.]+)",
                                            (WORKFLOWS / name).read_text()):
                with self.subTest(workflow=name, tool=tool):
                    self.assertEqual(pins[tool], version)


@ci_map.needs_tomllib
class PrepareJobTest(unittest.TestCase):
    """scripts/ci/prepare-job.sh knows every job and refuses another."""

    def test_every_job_of_the_map_file_has_a_branch(self):
        for job in ci_map.data()["jobs"]:
            with self.subTest(job=job):
                ci_map.prepare_branch(job)

    def test_an_unknown_job_and_a_wrong_folder_name_are_errors(self):
        result = subprocess.run(["bash", str(ci_map.PREPARE), "no-such-job"], capture_output=True, text=True)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "elsewhere" / "scripts" / "ci"
            copy.mkdir(parents=True)
            (copy / "prepare-job.sh").write_text(ci_map.PREPARE.read_text())
            result = subprocess.run(["bash", str(copy / "prepare-job.sh"), "tooling"], capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertIn("crux-controller", result.stderr)

    def test_the_build_jobs_fetch_the_workspace_and_install_the_sdk(self):
        for job in ("workload", "net", "file", "system", "sntp", "minimal", "budget-net"):
            with self.subTest(job=job):
                branch = ci_map.prepare_branch(job)
                self.assertIn("fetch_workspace", branch)
                self.assertIn("install_sdk", branch)

    def test_the_jobs_with_the_mbed_group_install_the_sdk_after_they_fetched_its_modules(self):
        for job, sdk in (("management", "management-sdk"), ("budget-management", "budget-management-sdk"),
                         ("base", "base-sdk"), ("budget-base", "budget-base-sdk")):
            with self.subTest(job=job):
                branch = ci_map.prepare_branch(job)
                self.assertNotIn("install_sdk", branch)
                self.assertNotIn("group-filter", branch)
                ids = ci_map.ids(job)
                switch = next(i for i in ids if "+crux-secure-management" in ci_map.run(i))
                self.assertLess(ids.index(switch), ids.index(sdk))
                self.assertIn("scripts/ci/install-sdk.sh zephyr", ci_map.run(sdk))


class InstallSdkTest(unittest.TestCase):
    SCRIPT = REPO / "scripts/ci/install-sdk.sh"

    def run_script(self, env, *arguments):
        return subprocess.run(["bash", str(self.SCRIPT), *arguments], capture_output=True, text=True,
                              env={"PATH": os.environ["PATH"], **env})

    def test_an_sdk_that_is_there_is_not_installed_again(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory) / "sdk" / "zephyr-sdk-1.0.1"
            sdk.mkdir(parents=True)
            result = self.run_script({"SDK_VERSION": "1.0.1", "ZEPHYR_SDK_INSTALL_DIR": str(sdk)}, directory)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_a_missing_sdk_is_installed_with_west_into_the_parent_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "bin").mkdir()
            (base / "zephyr").mkdir()
            west = base / "bin" / "west"
            west.write_text('#!/usr/bin/env bash\necho "$PWD $*" > "$WEST_LOG"\n')
            west.chmod(0o755)
            sdk = base / "sdk" / "zephyr-sdk-1.0.1"
            env = {"SDK_VERSION": "1.0.1", "ZEPHYR_SDK_INSTALL_DIR": str(sdk), "WEST_LOG": str(base / "log"),
                   "PATH": f"{base / 'bin'}:{os.environ['PATH']}", "GH_TOKEN": "token-value"}
            result = self.run_script(env, str(base / "zephyr"))
            self.assertEqual(0, result.returncode, result.stderr)
            log = (base / "log").read_text()
            self.assertIn("sdk install --version 1.0.1", log)
            self.assertIn(f"--install-base {base / 'sdk'}", log)
            self.assertIn("--gnu-toolchains arm-zephyr-eabi", log)
            self.assertIn("--personal-access-token token-value", log)
            self.assertTrue(log.startswith(str((base / "zephyr").resolve())) or log.startswith(str(base / "zephyr")))

    def test_missing_settings_are_errors(self):
        self.assertNotEqual(0, self.run_script({}, "zephyr").returncode)


@ci_map.needs_tomllib
class JenkinsTest(unittest.TestCase):
    """The Jenkins wrapper runs the same jobs, through the same scripts, as the GitHub workflows."""

    @classmethod
    def setUpClass(cls):
        cls.jenkinsfile = (REPO / "Jenkinsfile").read_text()
        cls.run_job = (REPO / "scripts/ci/jenkins/run-job.sh").read_text()
        cls.jobs = list(ci_map.data()["jobs"])

    def test_every_job_has_a_stage_that_runs_it(self):
        stages = re.findall(r"stage\('([\w-]+)'\) \{\n\s+agent .*\n\s+steps \{ script \{ runJob\('([\w-]+)'\) \} \}",
                            self.jenkinsfile)
        self.assertEqual(sorted((job, job) for job in self.jobs), sorted(stages))

    def test_the_stages_call_only_the_repository_scripts(self):
        self.assertEqual(["scripts/ci/jenkins/run-job.sh ${job}"], re.findall(r"\bsh \"([^\"]+)\"", self.jenkinsfile))
        self.assertIn('scripts/ci/prepare-job.sh "$job"', self.run_job)
        self.assertIn('exec scripts/ci/run-tier.sh "$tier" --job "$job"', self.run_job)

    def test_every_container_stage_builds_the_dev_container_image_without_j_link(self):
        agents = re.findall(r"agent \{ dockerfile \{([^}]*)\}", self.jenkinsfile)
        self.assertEqual(len(self.jobs) - 1, len(agents))
        for agent in agents:
            self.assertIn("filename 'Dockerfile'; dir '.devcontainer'", agent)
            self.assertIn("--build-arg CRUX_JLINK=0", agent)
        # The Dev container job builds the image itself, so it runs on an agent with Docker.
        self.assertRegex(self.jenkinsfile, r"stage\('devcontainer'\) \{\n\s+agent \{ node \{ label 'docker'")

    def test_the_jenkins_tools_and_pins_come_from_the_repository_files(self):
        self.assertIn(".devcontainer/requirements-tools.txt", self.run_job)
        self.assertIn("scripts/include-check-pins.json", self.run_job)

    def test_the_sdk_version_is_the_one_of_the_workflows_and_the_image(self):
        version = re.search(r"SDK_VERSION = '([\d.]+)'", self.jenkinsfile).group(1)
        self.assertIn(f"ENV ZEPHYR_SDK_VERSION={version}", (REPO / ".devcontainer/Dockerfile").read_text())
        for name in ("ci.yml", "budget.yml", "rebuild.yml", "release.yml", "scheduled-main.yml"):
            for job in workflow(name)["jobs"].values():
                if "SDK_VERSION" in job.get("env", {}):
                    self.assertEqual(version, job["env"]["SDK_VERSION"], name)

    def test_the_jenkins_files_archive_only_the_check_reports(self):
        # Hashes only: no image, ELF or map file leaves a build (CONTRIBUTING, Content rules).
        self.assertEqual(["build/ci/**"], re.findall(r"archiveArtifacts [^\n]*artifacts: '([^']+)'", self.jenkinsfile))

    def test_no_github_workflow_runs_the_jenkins_files(self):
        for path in WORKFLOWS.glob("*.yml"):
            with self.subTest(workflow=path.name):
                self.assertNotIn("Jenkinsfile", path.read_text())
                self.assertNotIn("scripts/ci/jenkins", path.read_text())


if __name__ == "__main__":
    unittest.main()
