# SPDX-License-Identifier: Apache-2.0
"""Checks of the product integration check: a fixture product under tests/product_integration that
imports this repository into a west workspace of its own, builds on native_sim and runs.

The rules held here:

- the fixture is a product: its manifest lists crux-controller and imports its manifest, so Crux
  comes at the pin of this repository, and its CMake file names no path of crux-controller;
- tests/product_integration/manifest.py writes the commit under test into the copy of the manifest,
  and refuses anything else than a full commit and a manifest of that shape;
- tests/product_integration/run.sh makes a new workspace from the commit under test, refuses to
  reuse a folder that it did not make, checks the resolved project list before it fetches the Mbed
  TLS modules, and builds with the verified Zephyr gate;
- the check is the nightly job product-integration of scripts/ci/checks.toml, with a job of
  scheduled-main.yml and a Jenkins stage, and it runs no other tier.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

import yaml

import ci_map

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "product_integration"
MANIFEST_TOOL = FIXTURE / "manifest.py"
RUN = FIXTURE / "run.sh"
SHA = "0123456789abcdef0123456789abcdef01234567"


def fixture_manifest():
    return yaml.safe_load((FIXTURE / "west.yml").read_text())


def rewrite(text, revision):
    """Run manifest.py on a copy of text; return (exit status, rewritten text, stderr)."""
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "west.yml"
        path.write_text(text)
        result = subprocess.run([sys.executable, str(MANIFEST_TOOL), "--revision", revision, str(path)],
                                capture_output=True, text=True)
        return result.returncode, path.read_text(), result.stderr


class FixtureProduct(unittest.TestCase):
    def test_the_manifest_imports_this_repository_as_a_project(self):
        manifest = fixture_manifest()["manifest"]
        projects = {p["name"]: p for p in manifest["projects"]}
        self.assertEqual(["crux-controller"], list(projects))
        self.assertIs(True, projects["crux-controller"]["import"])
        self.assertEqual("product", manifest["self"]["path"])
        # Crux comes through the import, at the pin of this repository, with its narrowed import.
        self.assertNotIn("crux", projects)
        self.assertNotIn("group-filter", manifest)

    def test_the_remote_of_the_project_is_the_one_of_this_repository(self):
        manifest = fixture_manifest()["manifest"]
        remotes = {r["name"]: r["url-base"] for r in manifest["remotes"]}
        project = manifest["projects"][0]
        own = yaml.safe_load((ROOT / "west.yml").read_text())["manifest"]
        crux_base = next(r["url-base"] for r in own["remotes"] if r["name"] == "crux")
        self.assertEqual(crux_base, remotes[project["remote"]])

    def test_the_cmake_file_names_no_path_of_crux_controller(self):
        text = (FIXTURE / "CMakeLists.txt").read_text()
        code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
        for word in ("crux-controller", "ZEPHYR_EXTRA_MODULES", "EXTRA_ZEPHYR_MODULES", "include_directories",
                     "../", "framework/"):
            self.assertNotIn(word, code, word)
        self.assertIn("target_link_libraries(app PRIVATE controller::framework)", code)
        self.assertIn("controller_framework_image()", code)

    def test_the_sources_reach_the_framework_through_its_interface_header_only(self):
        for path in sorted((FIXTURE / "src").rglob("*.c")):
            includes = re.findall(r'#\s*include\s*[<"]([^>"]+)[>"]', path.read_text())
            for name in includes:
                with self.subTest(path=path.name, include=name):
                    self.assertFalse(name.startswith(("crux/", "../")), name)
                    if name.startswith("controller/"):
                        self.assertTrue((ROOT / "include" / name).is_file(), name)

    def test_the_product_turns_on_every_service_of_the_base_image(self):
        text = (FIXTURE / "prj.conf").read_text()
        for symbol in ("CONFIG_CRUX_CONTROLLER_FRAMEWORK=y", "CONFIG_CRUX_CLI_CONSOLE=y",
                       "CONFIG_CRUX_WEB_MANAGEMENT=y", "CONFIG_SNTP=y"):
            self.assertIn(symbol, text.splitlines())
        cmake = (FIXTURE / "CMakeLists.txt").read_text()
        for symbol in ("CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT", "CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL",
                       "CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC", "CONFIG_ZEPHYR_CRUX_CONTROLLER_MODULE"):
            self.assertIn(symbol, cmake)

    def test_the_product_writes_the_build_metadata_that_west_spdx_needs(self):
        # Zephyr deletes zephyr.meta when CONFIG_BUILD_OUTPUT_META is off, and west spdx then stops
        # with "cannot find a valid zephyr.meta" (Zephyr v4.5.0, doc/develop/west/zephyr-cmds.rst and
        # scripts/pylib/zspdx/walker.py).
        self.assertIn("CONFIG_BUILD_OUTPUT_META=y", (FIXTURE / "prj.conf").read_text().splitlines())
        # The build step checks it too, so a missing option fails before the SBOM step.
        self.assertIn("CONFIG_BUILD_OUTPUT_META=y", RUN.read_text())

    def test_no_twister_run_of_crux_controller_picks_up_the_fixture(self):
        # It builds only in its own workspace, so it has no testcase.yaml for the in-repository runs.
        self.assertFalse((FIXTURE / "testcase.yaml").exists())
        self.assertFalse((FIXTURE / "sample.yaml").exists())


class ManifestTool(unittest.TestCase):
    def test_the_commit_under_test_becomes_the_revision(self):
        status, text, error = rewrite((FIXTURE / "west.yml").read_text(), SHA)
        self.assertEqual(0, status, error)
        manifest = yaml.safe_load(text)["manifest"]
        project = manifest["projects"][0]
        self.assertEqual(SHA, project["revision"])
        self.assertIs(True, project["import"])
        self.assertEqual(fixture_manifest()["manifest"]["remotes"], manifest["remotes"])
        self.assertEqual("product", manifest["self"]["path"])

    def test_only_a_full_lowercase_commit_is_accepted(self):
        for revision in ("main", SHA[:12], SHA.upper(), SHA + "0", "", "v1.0.0"):
            with self.subTest(revision=revision):
                status, text, _ = rewrite((FIXTURE / "west.yml").read_text(), revision)
                self.assertEqual(2, status)
                self.assertEqual((FIXTURE / "west.yml").read_text(), text)

    def test_a_manifest_without_the_project_is_refused(self):
        text = "manifest:\n  projects:\n    - name: other\n      revision: main\n"
        status, rewritten, error = rewrite(text, SHA)
        self.assertEqual(1, status)
        self.assertIn("crux-controller", error)
        self.assertEqual(text, rewritten)

    def test_a_project_that_does_not_import_the_manifest_is_refused(self):
        text = "manifest:\n  projects:\n    - name: crux-controller\n      revision: main\n"
        status, _, error = rewrite(text, SHA)
        self.assertEqual(1, status)
        self.assertIn("import", error)


class RunScript(unittest.TestCase):
    def setUp(self):
        # The commands of the script, without its comment lines.
        self.text = "\n".join(line for line in RUN.read_text().splitlines()
                              if not line.lstrip().startswith("#") or line.startswith("#!"))

    def test_the_script_is_executable_and_strict(self):
        self.assertTrue(os.access(RUN, os.X_OK))
        self.assertTrue(self.text.startswith("#!/usr/bin/env bash\n"))
        self.assertIn("set -euo pipefail", self.text)

    def test_it_takes_the_commit_of_the_clone_it_belongs_to(self):
        self.assertIn('rev-parse HEAD', self.text)
        self.assertIn("manifest.py", self.text)
        # The clone of the commit under test is made before west update, so west does not fetch it.
        self.assertLess(self.text.index("git clone"), self.text.index("west update"))
        self.assertIn("checkout --quiet --detach", self.text)

    def test_it_never_reuses_a_folder_that_it_did_not_make(self):
        self.assertIn(".product-integration", self.text)
        with tempfile.TemporaryDirectory() as directory:
            folder = pathlib.Path(directory) / "workspace"
            folder.mkdir()
            (folder / "keep.txt").write_text("not ours")
            result = subprocess.run(["bash", str(RUN), "workspace", str(folder)], capture_output=True, text=True,
                                    env={**os.environ, "CRUX_PRODUCT_INTEGRATION_ANY_HOST": "1"})
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertTrue((folder / "keep.txt").is_file())

    def test_usage_errors_exit_2(self):
        for arguments in ([], ["unknown", "/tmp/x"], ["workspace"], ["workspace", ""], ["workspace", "/"],
                          ["build", "//"], ["run", "relative/folder"]):
            with self.subTest(arguments=arguments):
                result = subprocess.run(["bash", str(RUN), *arguments], capture_output=True, text=True,
                                        env={**os.environ, "CRUX_PRODUCT_INTEGRATION_ANY_HOST": "1"})
                self.assertEqual(2, result.returncode, result.stderr)

    def test_the_project_list_is_checked_before_the_mbed_modules_are_fetched(self):
        default = self.text.index("--mode default")
        group = self.text.index("+crux-secure-management")
        mbed = self.text.index("--mode mbed")
        second_update = self.text.rindex("west update")
        self.assertLess(default, group)
        self.assertLess(group, mbed)
        self.assertLess(mbed, second_update)
        for name in ("wolfssl", "wolfssh", "wolfpsa"):
            self.assertIn(name, self.text)

    def test_it_builds_for_native_sim_with_the_gate_and_runs_with_a_time_limit(self):
        self.assertIn("native_sim/native/64", self.text)
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", self.text)
        self.assertRegex(self.text, r"timeout [^\n]*zephyr\.exe")
        self.assertIn("PROJECT EXECUTION SUCCESSFUL", self.text)
        self.assertIn("flash", self.text.lower())  # it says that it flashes nothing

    def test_it_needs_linux_for_native_sim(self):
        self.assertIn('uname -s', self.text)


@ci_map.needs_tomllib
class NightlyCheck(unittest.TestCase):
    JOB = "product-integration"

    def test_the_job_runs_only_in_the_nightly_tier(self):
        checks = ci_map.checks(self.JOB)
        self.assertEqual(["product-integration-workspace", "product-integration-build", "product-integration-run",
                          "product-integration-sbom", "product-integration-vulnerabilities"],
                         [c["id"] for c in checks])
        for check in checks:
            with self.subTest(check=check["id"]):
                self.assertEqual(["nightly"], check.get("tiers"))
                self.assertIn("tests/product_integration/run.sh", check["run"])
                self.assertIn("${RUNNER_TEMP:-/tmp}/product-integration", check["run"])

    def test_the_job_prepares_nothing_outside_its_checks(self):
        self.assertEqual("", ci_map.prepare_branch(self.JOB).strip())

    def test_the_nightly_workflow_has_a_job_for_it(self):
        data = yaml.safe_load((ROOT / ".github/workflows/scheduled-main.yml").read_text())
        job = data["jobs"]["product-integration"]
        steps = {s.get("name"): s for s in job["steps"]}
        self.assertEqual(f'scripts/ci/run-tier.sh "$TIER" --job {self.JOB}',
                         steps["Run the checks of this tier"]["run"].strip())
        self.assertIn("github.repository == 'wonny-labs/crux-controller'", job["if"])

    def test_the_jenkinsfile_has_a_stage_for_it(self):
        self.assertIn(f"runJob('{self.JOB}')", (ROOT / "Jenkinsfile").read_text())


if __name__ == "__main__":
    unittest.main()
