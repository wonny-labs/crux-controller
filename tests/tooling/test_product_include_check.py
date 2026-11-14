"""Checks that CI runs the Crux Pilot product include check from a verified, immutable download.

The revision of crux-pilot that west.yml pins predates check_domain_includes.py, so the
Boundary check job downloads the script from a commit URL and verifies its SHA-256 before it
runs. These tests read the workflow only. They do not use the network.
"""

import pathlib
import re
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
URL = re.compile(
    r"https://raw\.githubusercontent\.com/wonny-labs/crux-pilot/"
    r"(?P<commit>\$\{CHECK_COMMIT\}|[0-9a-f]{40})/templates/product/check_domain_includes\.py"
)


def boundary_job():
    return yaml.safe_load(CI.read_text())["jobs"]["boundary"]


def check_step():
    steps = [s for s in boundary_job()["steps"] if "product include check" in s.get("name", "").lower()]
    assert len(steps) == 1, "the Boundary check job needs exactly one product include check step"
    return steps[0]


class ProductIncludeCheckStep(unittest.TestCase):
    def setUp(self):
        self.step = check_step()
        self.run = self.step["run"]
        self.env = self.step.get("env", {})

    def test_the_step_is_in_the_boundary_job_and_uses_no_action(self):
        self.assertNotIn("uses", self.step)

    def test_the_commit_is_a_full_hash_and_the_url_names_it(self):
        match = URL.search(self.run)
        self.assertIsNotNone(match, "no raw.githubusercontent.com commit URL for the script")
        commit = match.group("commit")
        if commit == "${CHECK_COMMIT}":
            commit = self.env.get("CHECK_COMMIT", "")
        self.assertRegex(commit, r"^[0-9a-f]{40}$")

    def test_the_download_fails_on_http_errors(self):
        self.assertRegex(self.run, r"curl\b[^\n]*--fail")

    def test_the_expected_hash_is_a_committed_sha256(self):
        self.assertRegex(self.env.get("CHECK_SHA256", ""), r"^[0-9a-f]{64}$")

    def test_the_hash_is_verified_between_the_download_and_the_run(self):
        curl = self.run.index("curl")
        verify = self.run.index("sha256sum")
        python = self.run.index("python3")
        self.assertLess(curl, verify)
        self.assertLess(verify, python)
        verify_line = next(line for line in self.run.splitlines() if "sha256sum" in line)
        self.assertIn("CHECK_SHA256", verify_line)

    def test_the_verification_is_a_strict_check_that_cannot_be_ignored(self):
        verify_line = next(line for line in self.run.splitlines() if "sha256sum" in line)
        self.assertRegex(verify_line, r"sha256sum\s+--check\s+--strict\s+-\s*$")
        for swallow in ("|| true", "|| :", "||true"):
            self.assertNotIn(swallow, self.run)
        self.assertNotIn("continue-on-error", self.step)
        self.assertEqual(self.run.splitlines()[0].strip(), "set -euo pipefail")

    def test_the_script_is_downloaded_to_the_temporary_directory_before_it_is_checked(self):
        lines = [line.strip() for line in self.run.splitlines()]
        self.assertTrue(lines[1].startswith('script="$RUNNER_TEMP/'))
        curl = next(i for i, line in enumerate(lines) if line.startswith("curl"))
        download = " ".join(lines[curl : curl + 3])
        self.assertIn('--output "$script"', download)

    def test_a_failed_command_fails_the_step(self):
        self.assertIn("set -euo pipefail", self.run)

    def test_the_check_runs_in_product_mode_from_the_repository_root_without_exceptions(self):
        self.assertRegex(self.run, r"cd crux-controller\n")
        self.assertRegex(self.run, r'python3 "\$script" --product \.(\n|$)')
        for option in ("--domain", "--exclude"):
            self.assertNotIn(option, self.run)

    def test_the_script_is_not_stored_in_the_checked_out_repository(self):
        self.assertIn("$RUNNER_TEMP", self.run)

    def test_the_step_comment_says_why_the_script_is_downloaded(self):
        lines = CI.read_text().splitlines()
        start = next(i for i, line in enumerate(lines) if "Run the Crux Pilot product include check" in line)
        comment = "\n".join(lines[start - 3 : start]).lower()
        self.assertTrue(all(line.strip().startswith("#") for line in lines[start - 3 : start]))
        self.assertIn("pin", comment)
        self.assertIn("download", comment)


if __name__ == "__main__":
    unittest.main()
