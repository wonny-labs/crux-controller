"""Checks of the option A west manifest (Stage 1, Task 1) and of its Mbed-only import."""

import copy
import pathlib
import re
import subprocess
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_mbed_only  # noqa: E402


def load_manifest():
    return yaml.safe_load((ROOT / "west.yml").read_text())["manifest"]


class ManifestIsOptionA(unittest.TestCase):
    def test_projects_are_crux_pilot_and_the_test_only_libc(self):
        projects = load_manifest()["projects"]
        self.assertEqual([p["name"] for p in projects], ["crux-pilot", "picolibc"])
        # The Crux import is narrowed: the three GPL stacks are blocked by name, so enabling the
        # Mbed TLS group fetches Mbed TLS and TF-PSA-Crypto and none of them.
        self.assertEqual(
            projects[0]["import"], {"name-blocklist": ["wolfssl", "wolfssh", "wolfpsa"]}
        )
        picolibc = projects[1]
        self.assertNotIn("import", picolibc)
        self.assertEqual(picolibc["remote"], "zephyrproject-rtos")
        self.assertEqual(picolibc["path"], "modules/lib/picolibc")
        # The revision in Zephyr's own manifest at the Zephyr release that Crux pins.
        self.assertEqual(picolibc["revision"], "01254932e8e81085817ed61fd858648584ffe37c")

    def test_crux_pilot_is_pinned_by_a_full_commit_hash(self):
        revision = load_manifest()["projects"][0]["revision"]
        self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_crux_pilot_is_pinned_to_the_approved_commit(self):
        # Moving the pin is a reviewed change of this test and of west.yml together.
        # The owner approved this commit on 8 November 2026: it publishes the
        # composition interface <crux/file_zephyr.h> (crux-pilot PR 346).
        revision = load_manifest()["projects"][0]["revision"]
        self.assertEqual(revision, "37c92b18b44b7dfb95c2109f036f23d00f05cb4c")

    def test_manifest_has_no_tag_pin(self):
        revision = str(load_manifest()["projects"][0]["revision"])
        self.assertIsNone(re.fullmatch(r"v?\d+(\.\d+)+(-[0-9A-Za-z.]+)?", revision))

    def test_no_optional_group_is_enabled(self):
        self.assertNotIn("group-filter", load_manifest())

    def test_self_path_is_the_repository_name(self):
        self.assertEqual(load_manifest()["self"]["path"], "crux-controller")


# Output of `west list --all -f '{name} {active}'` in a resolved workspace (west 1.4.0 prints
# `active` or `inactive`). The Crux
# manifest filters both optional groups out, so `all` lists their projects as inactive.
BASE = [
    ("manifest", True), ("crux-pilot", True), ("zephyr", True), ("cmsis", True),
    ("cmsis_6", True), ("hal_nxp", True), ("littlefs", True), ("fatfs", True),
    ("picolibc", True), ("reliance-edge", False),
]
WOLF = ["wolfssl", "wolfssh", "wolfpsa"]


def listing(mbed_active, wolf_active=None):
    """A listing; wolf_active None means the wolf projects are not in the resolved manifest."""
    rows = list(BASE)
    rows += [("mbedtls", mbed_active), ("tf-psa-crypto", mbed_active)]
    if wolf_active is not None:
        rows += [(name, wolf_active) for name in WOLF]
    return "".join(f"{name} {'active' if active else 'inactive'}\n" for name, active in rows)


def run_check(mode, text):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_mbed_only.py"), "--mode", mode],
        input=text, capture_output=True, text=True,
    )


class MbedOnlyManifest(unittest.TestCase):
    def test_the_real_manifest_passes_the_static_check(self):
        self.assertEqual([], check_mbed_only.check_manifest(load_manifest()))

    def test_a_manifest_without_the_blocklist_fails_the_static_check(self):
        manifest = copy.deepcopy(load_manifest())
        manifest["projects"][0]["import"] = True
        problems = check_mbed_only.check_manifest(manifest)
        self.assertTrue(problems)
        self.assertIn("not narrowed", problems[0])

    def test_a_blocklist_that_misses_one_wolf_project_fails_the_static_check(self):
        for missing in WOLF:
            manifest = copy.deepcopy(load_manifest())
            manifest["projects"][0]["import"] = {
                "name-blocklist": [name for name in WOLF if name != missing]
            }
            problems = check_mbed_only.check_manifest(manifest)
            self.assertEqual(1, len(problems), problems)
            self.assertIn(missing, problems[0])

    def test_an_import_that_only_filters_by_path_fails_the_static_check(self):
        manifest = copy.deepcopy(load_manifest())
        manifest["projects"][0]["import"] = {"path-blocklist": ["manifest"]}
        self.assertTrue(check_mbed_only.check_manifest(manifest))

    def test_an_allowlist_without_the_wolf_projects_passes_the_static_check(self):
        manifest = copy.deepcopy(load_manifest())
        manifest["projects"][0]["import"] = {"name-allowlist": ["zephyr", "mbedtls"]}
        self.assertEqual([], check_mbed_only.check_manifest(manifest))
        manifest["projects"][0]["import"] = {"name-allowlist": ["zephyr", "wolfssl"]}
        self.assertTrue(check_mbed_only.check_manifest(manifest))

    def test_an_enabled_optional_group_fails_the_static_check(self):
        for group in ("crux-secure-management", "crux-reliance"):
            manifest = copy.deepcopy(load_manifest())
            manifest["group-filter"] = [f"+{group}"]
            problems = check_mbed_only.check_manifest(manifest)
            self.assertTrue(problems, group)
            self.assertIn(group, problems[0])

    def test_a_manifest_without_crux_pilot_fails_the_static_check(self):
        manifest = copy.deepcopy(load_manifest())
        manifest["projects"] = manifest["projects"][1:]
        self.assertTrue(check_mbed_only.check_manifest(manifest))


class MbedOnlyListing(unittest.TestCase):
    def test_default_workspace_keeps_the_wolf_projects_out_and_the_mbed_pair_inactive(self):
        self.assertEqual([], check_mbed_only.check_listing(listing(False), "default"))

    def test_group_enabled_workspace_has_the_mbed_pair_active_and_no_wolf_project(self):
        self.assertEqual([], check_mbed_only.check_listing(listing(True), "mbed"))

    def test_negative_control_unnarrowed_manifest_with_the_group_on_fails(self):
        for mode in ("default", "mbed"):
            problems = check_mbed_only.check_listing(listing(True, wolf_active=True), mode)
            for name in WOLF:
                self.assertTrue(any(name in problem for problem in problems), (mode, name))

    def test_negative_control_unnarrowed_manifest_with_the_group_off_fails(self):
        # The wolf projects are inactive but listed: the next group change would fetch them.
        problems = check_mbed_only.check_listing(listing(False, wolf_active=False), "default")
        self.assertEqual(3, len(problems), problems)

    def test_an_inactive_mbed_pair_fails_in_mbed_mode(self):
        problems = check_mbed_only.check_listing(listing(False), "mbed")
        self.assertEqual(2, len(problems), problems)

    def test_an_active_mbed_pair_fails_in_default_mode(self):
        problems = check_mbed_only.check_listing(listing(True), "default")
        self.assertEqual(2, len(problems), problems)

    def test_an_active_reliance_edge_fails_in_both_modes(self):
        for mode, mbed in (("default", False), ("mbed", True)):
            text = listing(mbed).replace("reliance-edge inactive", "reliance-edge active")
            problems = check_mbed_only.check_listing(text, mode)
            self.assertEqual(1, len(problems), (mode, problems))
            self.assertIn("reliance-edge", problems[0])

    def test_an_empty_or_unresolved_listing_does_not_pass(self):
        for text in ("", "manifest active\n", "manifest active\ncrux-pilot active\n"):
            for mode in ("default", "mbed"):
                self.assertTrue(check_mbed_only.check_listing(text, mode), (text, mode))

    def test_a_line_that_is_not_name_and_state_is_rejected(self):
        with self.assertRaises(ValueError):
            check_mbed_only.parse_listing("crux-pilot\n")
        with self.assertRaises(ValueError):
            check_mbed_only.parse_listing("crux-pilot maybe\n")
        # `west list` prints the word active or inactive, not a Python boolean.
        with self.assertRaises(ValueError):
            check_mbed_only.parse_listing("crux-pilot True\n")

    def test_an_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            check_mbed_only.check_listing(listing(False), "wolf")

    def test_command_line_exit_codes(self):
        ok = run_check("mbed", listing(True))
        self.assertEqual(0, ok.returncode, ok.stderr)
        self.assertIn("Mbed-only check passed (mbed)", ok.stdout)
        bad = run_check("mbed", listing(True, wolf_active=True))
        self.assertEqual(1, bad.returncode)
        self.assertIn("wolfssl", bad.stdout + bad.stderr)
        garbled = run_check("mbed", "not a listing\n")
        self.assertEqual(2, garbled.returncode)

    def test_command_line_reads_a_listing_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "list.txt"
            path.write_text(listing(False))
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "check_mbed_only.py"),
                 "--mode", "default", "--listing", str(path)],
                capture_output=True, text=True,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Mbed-only check passed (default)", result.stdout)


class PinsJobChecksTheResolvedWorkspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]
        cls.steps = jobs["pins"]["steps"]
        cls.names = [step.get("name", "") for step in cls.steps]

    def index(self, fragment):
        matches = [i for i, name in enumerate(self.names) if fragment in name]
        self.assertEqual(1, len(matches), f"{fragment!r}: {self.names}")
        return matches[0]

    def run_text(self, fragment):
        return self.steps[self.index(fragment)]["run"]

    def test_the_two_checks_and_the_negative_control_exist_after_the_fetch(self):
        fetch = self.index("Fetch the workspace")
        for fragment in ("Mbed-only check, default", "Mbed-only check, group on",
                         "Negative control, an unnarrowed import"):
            self.assertGreater(self.index(fragment), fetch, fragment)

    def test_they_run_before_the_existing_negative_control_edits_west_yml(self):
        existing = self.index("Negative control, a pin without a reason")
        for fragment in ("Mbed-only check, default", "Mbed-only check, group on",
                         "Negative control, an unnarrowed import"):
            self.assertLess(self.index(fragment), existing, fragment)

    def test_the_checks_read_the_resolved_workspace_with_west_list(self):
        for fragment, mode in (("Mbed-only check, default", "default"),
                               ("Mbed-only check, group on", "mbed")):
            text = self.run_text(fragment)
            self.assertIn("west list --all -f '{name} {active}'", text)
            self.assertIn(f"check_mbed_only.py --mode {mode}", text)

    def test_the_group_is_enabled_only_in_the_runner_and_switched_off_again(self):
        for fragment in ("Mbed-only check, group on", "Negative control, an unnarrowed import"):
            text = self.run_text(fragment)
            self.assertIn("west config --local manifest.group-filter -- +crux-secure-management", text)
            self.assertIn("west config --local -d manifest.group-filter", text)
        self.assertNotIn("west config", self.run_text("Mbed-only check, default"))
        self.assertNotIn("west config", self.run_text("Fetch the workspace"))

    def test_the_negative_control_must_fail_with_a_problem_and_restores_west_yml(self):
        text = self.run_text("Negative control, an unnarrowed import")
        self.assertIn('project["import"] = True', text)
        self.assertIn("--mode mbed", text)
        self.assertIn('test "$status" -eq 1', text)
        self.assertIn("grep -q 'wolfssl'", text)
        self.assertIn("git -C crux-controller checkout -- west.yml", text)

    def test_the_fetch_step_is_unchanged_and_no_group_is_enabled_there(self):
        text = self.run_text("Fetch the workspace")
        self.assertEqual("west init -l crux-controller\nwest update\n", text)


if __name__ == "__main__":
    unittest.main()
