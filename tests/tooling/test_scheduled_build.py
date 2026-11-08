"""Checks the scheduled build against crux-pilot main: it is read-only, publishes nothing and
keeps the pinned tool versions and the gate of ci.yml."""

import pathlib
import re
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
        self.assertIn("crux-pilot", self.commands)
        self.assertIn("main", self.commands)
        self.assertIn("west.yml", self.commands)
        for step in self.job["steps"]:
            self.assertNotIn("git commit", step.get("run", ""))
            self.assertNotIn("git push", step.get("run", ""))

    def test_fetches_reports_pins_and_builds_s2_with_the_gate_required(self):
        commands = self.commands
        self.assertLess(commands.index("west update"), commands.index("west crux-pins"))
        self.assertLess(commands.index("west crux-pins"), commands.index("west build"))
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", commands)
        self.assertIn("conf/s2.conf", commands)
        self.assertIn("boards/s2.overlay", commands)

    def test_a_pin_mismatch_is_reported_in_the_summary_not_hidden(self):
        self.assertIn("GITHUB_STEP_SUMMARY", self.commands)
        self.assertIn("MISMATCH", self.commands)

    def test_failure_writes_a_summary(self):
        summary_steps = [s for s in self.job["steps"] if "GITHUB_STEP_SUMMARY" in s.get("run", "")]
        self.assertTrue(any(s.get("if") == "always()" for s in summary_steps))

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
