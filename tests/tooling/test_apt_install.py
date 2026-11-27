# SPDX-License-Identifier: Apache-2.0
"""Checks scripts/ci/apt-install.sh, which installs the host packages of a GitHub-hosted Ubuntu
runner from the Ubuntu archive alone, and that every workflow installs its packages through it.
A third-party source of the runner image (for example packages.microsoft.com) then cannot fail a
job. The script runs against stand-ins for sudo and apt-get; no network is used."""

import os
import pathlib
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "apt-install.sh"
WORKFLOWS = ROOT / ".github" / "workflows"
CALL = "crux-controller/scripts/ci/apt-install.sh"
# The Ubuntu sources file of the ubuntu-24.04 runner image (actions/runner-images,
# images/ubuntu/scripts/build/configure-apt-sources.sh).
UBUNTU_SOURCES = "/etc/apt/sources.list.d/ubuntu.sources"


def workflow_steps():
    """(workflow file name, job id, step) for every step of every workflow."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job_id, job in yaml.safe_load(path.read_text())["jobs"].items():
            for step in job.get("steps", []):
                yield path.name, job_id, step


class AptInstallScript(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = pathlib.Path(self._tmp.name)
        self.bin = base / "bin"
        self.bin.mkdir()
        self.log = base / "calls.log"
        self.sources = base / "ubuntu.sources"
        self.sources.write_text("Types: deb\n")
        self.stub("sudo", 'exec "$@"')
        self.stub("apt-get", f'echo "apt-get $*" >> "{self.log}"\nexit "${{FAKE_APT_STATUS:-0}}"')

    def stub(self, name, body):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\n")
        path.chmod(0o755)

    def run_script(self, *args, **env):
        environment = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                       "CRUX_APT_SOURCES": str(self.sources), **env}
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True,
                              env=environment)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def options(self):
        return (f"-o Dir::Etc::sourcelist={self.sources} -o Dir::Etc::sourceparts=- "
                "-o APT::Get::List-Cleanup=0")

    def test_the_script_has_the_licence_line_and_is_executable(self):
        self.assertTrue(SCRIPT.is_file(), SCRIPT)
        self.assertEqual("# SPDX-License-Identifier: Apache-2.0", SCRIPT.read_text().splitlines()[1])
        self.assertTrue(os.access(SCRIPT, os.X_OK))

    def test_update_and_install_read_only_the_ubuntu_sources_file(self):
        result = self.run_script("--no-install-recommends", "gperf", "xz-utils")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([f"apt-get {self.options()} update",
                          f"apt-get {self.options()} install -y --no-install-recommends gperf xz-utils"],
                         self.calls())

    def test_a_pinned_package_version_is_passed_unchanged(self):
        result = self.run_script("clang-tidy-18=1:18.1.3-1ubuntu1")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(f"apt-get {self.options()} install -y clang-tidy-18=1:18.1.3-1ubuntu1",
                         self.calls()[-1])

    def test_the_default_sources_file_is_the_one_of_the_ubuntu_24_04_runner(self):
        self.assertIn(f"CRUX_APT_SOURCES:-{UBUNTU_SOURCES}", SCRIPT.read_text())

    def test_a_missing_sources_file_stops_before_apt_get(self):
        result = self.run_script("gperf", CRUX_APT_SOURCES=str(self.sources.parent / "missing.sources"))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("missing.sources", result.stderr)
        self.assertEqual([], self.calls())

    def test_no_package_is_a_usage_error(self):
        result = self.run_script()
        self.assertEqual(2, result.returncode)
        self.assertIn("Usage", result.stderr)
        self.assertEqual([], self.calls())

    def test_a_failed_update_fails_the_script_before_install(self):
        result = self.run_script("gperf", FAKE_APT_STATUS="100")
        self.assertEqual(100, result.returncode)
        self.assertEqual(1, len(self.calls()))
        self.assertTrue(self.calls()[0].endswith(" update"))


class WorkflowsUseTheScript(unittest.TestCase):
    def test_no_workflow_step_runs_apt_directly(self):
        for name, job_id, step in workflow_steps():
            run = step.get("run", "")
            for word in ("apt-get", "apt ", "apt-fast", "aptitude"):
                self.assertNotIn(word, run, f"{name} {job_id}: {step.get('name')}")

    def test_every_host_package_step_calls_the_script_once(self):
        found = []
        for name, job_id, step in workflow_steps():
            run = step.get("run", "")
            if "apt-install.sh" in run:
                self.assertEqual(1, run.count(CALL), f"{name} {job_id}")
                self.assertNotIn("sudo", run, f"{name} {job_id}: the script calls sudo itself")
                found.append((name, job_id, step["name"]))
        # The 14 steps that installed packages with apt-get before the script existed, the step of
        # the host job that installs clang-18 with libFuzzer for the nightly check
        # host-fuzz, and the step of the template job of scheduled-main.yml.
        self.assertEqual(16, len(found), found)
        self.assertEqual(10, sum(1 for name, _, _ in found if name == "ci.yml"), found)

    def test_jenkins_does_not_call_the_script(self):
        # Jenkins runs in the Dev Container image, which installs its packages in the Dockerfile.
        for path in (ROOT / "Jenkinsfile", ROOT / "scripts" / "ci" / "jenkins" / "run-job.sh",
                     ROOT / "scripts" / "ci" / "checks.toml"):
            self.assertNotIn("apt-install.sh", path.read_text(), path)


if __name__ == "__main__":
    unittest.main()
