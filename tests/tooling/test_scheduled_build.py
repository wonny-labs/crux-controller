"""Checks the scheduled build against crux-pilot main: it is read-only, publishes nothing and
keeps the pinned tool versions and the gate of ci.yml."""

import pathlib
import re
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
PATH = WORKFLOWS / "scheduled-main.yml"


def load(path):
    return yaml.safe_load(path.read_text())


def triggers(data):
    # PyYAML reads the key `on` as the boolean True.
    return data.get("on", data.get(True))


def commands(job):
    return "\n".join(step.get("run", "") for step in job["steps"])


class ScheduledBuild(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PATH.is_file(), "scheduled-main.yml does not exist")
        self.data = load(PATH)
        self.job = self.data["jobs"]["build"]
        self.commands = commands(self.job)

    def test_runs_daily_and_on_manual_dispatch_only(self):
        on = triggers(self.data)
        self.assertEqual({"schedule", "workflow_dispatch"}, set(on))
        self.assertEqual(1, len(on["schedule"]))
        self.assertRegex(on["schedule"][0]["cron"], r"^\d+ \d+ \* \* \*$")

    def test_permissions_are_read_only_and_nothing_is_published(self):
        self.assertEqual({"contents": "read"}, self.data["permissions"])
        self.assertNotIn("permissions", self.job)
        for step in self.job["steps"]:
            uses = step.get("uses", "")
            self.assertNotIn("upload-artifact", uses)
            self.assertNotIn("gh-release", uses)
        text = PATH.read_text()
        for word in ("gh release", "git push", "git tag", "secrets."):
            self.assertNotIn(word, text)

    def test_the_only_token_is_the_automatic_one_for_the_sdk_install(self):
        text = PATH.read_text()
        self.assertEqual(1, len(re.findall(r"\$\{\{ *github\.token *\}\}", text)))
        self.assertIn("GH_TOKEN: ${{ github.token }}", text)

    def test_rewrites_the_crux_pilot_revision_to_main_in_the_runner_only(self):
        import os
        import subprocess
        import tempfile

        step = next(s["run"] for s in self.job["steps"] if "project[\"revision\"] = \"main\"" in s.get("run", ""))
        step = step.replace("python - <<", f"{sys.executable} - <<")
        manifest = (ROOT / "west.yml").read_text()
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            (work / "crux-controller").mkdir()
            (work / "crux-controller" / "west.yml").write_text(manifest)
            result = subprocess.run(["bash", "-e", "-c", step], cwd=directory, capture_output=True,
                                    text=True, env=dict(os.environ))
            self.assertEqual(0, result.returncode, result.stderr)
            rewritten = yaml.safe_load((work / "crux-controller" / "west.yml").read_text())
        projects = {p["name"]: p for p in rewritten["manifest"]["projects"]}
        self.assertEqual("main", projects["crux-pilot"]["revision"])
        original = {p["name"]: p for p in yaml.safe_load(manifest)["manifest"]["projects"]}
        self.assertEqual(original["picolibc"], projects["picolibc"])
        self.assertEqual(original["crux-pilot"].get("import"), projects["crux-pilot"].get("import"))
        for step in self.job["steps"]:
            self.assertNotIn("git commit", step.get("run", ""))
            self.assertNotIn("git push", step.get("run", ""))

    def test_the_job_runs_on_dispatch_and_only_on_this_repository_for_the_schedule(self):
        self.assertIn("github.event_name != 'schedule'", self.job["if"])
        self.assertIn("github.repository == 'wonny-labs/crux-controller'", self.job["if"])

    def test_fetches_reports_pins_and_builds_s2_with_the_gate_required(self):
        commands = self.commands
        self.assertLess(commands.index("west update"), commands.index("west crux-pins"))
        self.assertLess(commands.index("west crux-pins"), commands.index("west build"))
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", commands)
        self.assertIn("conf/s2.conf", commands)
        self.assertIn("boards/s2.overlay", commands)

    def pins_step(self):
        steps = [s for s in self.job["steps"] if "west crux-pins" in s.get("run", "")]
        self.assertEqual(1, len(steps))
        return steps[0]["run"]

    def run_pins_step(self, west_script):
        """Run the pins step under bash -e with a stub west, as the runner would."""
        import os
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            bin_dir = pathlib.Path(directory) / "bin"
            bin_dir.mkdir()
            west = bin_dir / "west"
            west.write_text("#!/bin/sh\n" + west_script)
            west.chmod(0o755)
            summary = pathlib.Path(directory) / "summary.md"
            summary.write_text("")
            env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                       GITHUB_STEP_SUMMARY=str(summary))
            result = subprocess.run(["bash", "-e", "-c", self.pins_step()], cwd=directory, env=env,
                                    capture_output=True, text=True)
            return result, summary.read_text()

    def test_a_pin_mismatch_is_reported_in_the_summary_and_does_not_stop_the_run(self):
        result, summary = self.run_pins_step(
            "echo 'CONTRACT crux-pilot a47c1590a252'\n"
            "echo 'MISMATCH littlefs 111111111111 (contract 8f5ca3478433)'\nexit 1\n"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("MISMATCH littlefs 111111111111", summary)
        self.assertIn("**MISMATCH reported.**", summary)
        self.assertIn("::warning::", result.stdout)

    def test_matching_pins_are_recorded_without_a_mismatch_note(self):
        result, summary = self.run_pins_step("echo 'CONTRACT crux-pilot a47c1590a252'\necho 'OK zephyr dccb09599635'\n")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK zephyr dccb09599635", summary)
        self.assertNotIn("MISMATCH", summary)

    def test_a_west_failure_without_a_contract_line_fails_the_step(self):
        result, _ = self.run_pins_step("echo 'west: error: something broke' >&2\nexit 1\n")
        self.assertNotEqual(0, result.returncode)

    def test_failure_writes_a_summary(self):
        summary_steps = [s for s in self.job["steps"] if "job.status" in s.get("run", "")]
        self.assertEqual(1, len(summary_steps))
        self.assertEqual("always()", summary_steps[0]["if"])
        self.assertIn("GITHUB_STEP_SUMMARY", summary_steps[0]["run"])
        self.assertIs(self.job["steps"][-1], summary_steps[0])

    def test_the_resolved_s2_configuration_is_checked_as_in_ci(self):
        ci = load(WORKFLOWS / "ci.yml")["jobs"]["s2"]
        wanted = next(s for s in ci["steps"] if s.get("name", "").startswith("Check the resolved S2"))
        own = [s for s in self.job["steps"] if s.get("name") == wanted["name"]]
        self.assertEqual([wanted["run"]], [s["run"] for s in own])

    def test_tool_versions_and_sdk_cache_key_match_ci(self):
        ci = load(WORKFLOWS / "ci.yml")["jobs"]["s2"]
        for key in ("SDK_VERSION", "BOARD"):
            self.assertEqual(ci["env"][key], self.job["env"][key])
        self.assertIn("cmake==3.28.4 ninja==1.11.1 west==1.4.0", self.commands)
        keys = [s["with"]["key"] for s in self.job["steps"] if "actions/cache" in s.get("uses", "")]
        ci_keys = [s["with"]["key"] for s in ci["steps"] if "actions/cache" in s.get("uses", "")]
        self.assertEqual(ci_keys, keys)
        self.assertEqual("ubuntu-24.04", self.job["runs-on"])


if __name__ == "__main__":
    unittest.main()
