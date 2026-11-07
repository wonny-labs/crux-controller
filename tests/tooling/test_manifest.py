"""Checks of the option A west manifest (Stage 1, Task 1)."""

import pathlib
import re
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load_manifest():
    return yaml.safe_load((ROOT / "west.yml").read_text())["manifest"]


class ManifestIsOptionA(unittest.TestCase):
    def test_crux_pilot_is_the_only_project_and_is_imported(self):
        projects = load_manifest()["projects"]
        self.assertEqual([p["name"] for p in projects], ["crux-pilot"])
        self.assertIs(projects[0]["import"], True)

    def test_crux_pilot_is_pinned_by_a_full_commit_hash(self):
        revision = load_manifest()["projects"][0]["revision"]
        self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_manifest_has_no_tag_pin(self):
        revision = str(load_manifest()["projects"][0]["revision"])
        self.assertIsNone(re.match(r"^v?\d+(\.\d+)*", revision))

    def test_no_optional_group_is_enabled(self):
        self.assertNotIn("group-filter", load_manifest())

    def test_self_path_is_the_repository_name(self):
        self.assertEqual(load_manifest()["self"]["path"], "crux-controller")


if __name__ == "__main__":
    unittest.main()
