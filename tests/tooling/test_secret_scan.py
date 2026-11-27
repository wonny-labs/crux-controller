# SPDX-License-Identifier: Apache-2.0
"""Check the ignore file of the secret scan (scripts/ci/secret-scan.sh).

Gitleaks skips a finding whose fingerprint (file:rule:line for a scan of a folder) is in
.gitleaksignore at the repository root (Gitleaks README, section .gitleaksignore). The file is a
reviewed allowlist: it holds only the entries listed here, and each entry must still point at the
line it was written for, so that a moved line fails this test instead of hiding another finding.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IGNORE = ROOT / ".gitleaksignore"

# Fingerprint -> text that the named line must contain. crux.boardKey is the name that Crux's VS Code
# tasks read, so it cannot be renamed, and its value is the board's build folder, not a secret.
ALLOWED = {
    ".vscode/settings.json:generic-api-key:3": '"crux.boardKey": "',
}


def entries():
    lines = (line.strip() for line in IGNORE.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


class GitleaksIgnore(unittest.TestCase):
    def test_the_ignore_file_holds_only_the_reviewed_entries(self):
        self.assertEqual(sorted(ALLOWED), sorted(entries()))

    def test_each_entry_still_points_at_its_line(self):
        for fingerprint, text in ALLOWED.items():
            with self.subTest(fingerprint):
                path, _rule, line = fingerprint.rsplit(":", 2)
                lines = (ROOT / path).read_text().splitlines()
                self.assertIn(text, lines[int(line) - 1])

    def test_the_scan_script_names_the_ignore_file(self):
        self.assertIn(".gitleaksignore", (ROOT / "scripts/ci/secret-scan.sh").read_text())


if __name__ == "__main__":
    unittest.main()
