# SPDX-License-Identifier: Apache-2.0
"""Tests of scripts/check_settings_sources.py: criterion 32 (gap C5)."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_settings_sources.py"
NAMES = ("settings_file.c", "settings_line.c", "settings_store.c")


def run(entries, crux="/ws/crux"):
    with tempfile.TemporaryDirectory() as directory:
        database = pathlib.Path(directory) / "compile_commands.json"
        database.write_text(json.dumps([{"directory": "/ws/build", "file": f, "command": "cc"}
                                        for f in entries]))
        return subprocess.run([sys.executable, str(SCRIPT), "--compile-commands", str(database),
                               "--crux-root", crux], capture_output=True, text=True, check=False)


class SettingsSources(unittest.TestCase):
    def test_the_staged_copies_in_the_build_directory_pass(self):
        result = run([f"/ws/build/settings-file-candidate/{name}" for name in NAMES] + ["/ws/app/main.c"])
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for name in NAMES:
            self.assertIn(name, result.stdout)

    def test_a_source_under_the_crux_tests_path_fails(self):
        entries = [f"/ws/build/settings-file-candidate/{name}" for name in NAMES[:2]]
        entries.append("/ws/crux/tests/native/configuration_settings_file/settings_store.c")
        result = run(entries)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("/ws/crux/tests/", result.stdout + result.stderr)

    def test_a_relative_entry_is_resolved_against_its_directory(self):
        entries = [f"/ws/build/settings-file-candidate/{name}" for name in NAMES[:2]]
        entries.append("../crux/tests/native/configuration_settings_file/settings_store.c")
        self.assertNotEqual(0, run(entries).returncode)

    def test_a_missing_settings_source_fails(self):
        result = run([f"/ws/build/settings-file-candidate/{name}" for name in NAMES[:2]])
        self.assertNotEqual(0, result.returncode)
        self.assertIn("settings_store.c", result.stdout + result.stderr)

    def test_a_build_with_no_settings_source_fails(self):
        self.assertNotEqual(0, run(["/ws/app/main.c"]).returncode)


if __name__ == "__main__":
    unittest.main()
