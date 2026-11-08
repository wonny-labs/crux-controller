"""Public files must not point at planning documents that readers cannot see."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PUBLIC = (".github", "app", "budgets", "docs", "scripts", "workload", "README.md")
PRIVATE_REFERENCE = re.compile(r"\b(?:OD|WD)[0-9]+\b|skeleton plan|work package", re.IGNORECASE)


class PublicText(unittest.TestCase):
    def test_no_reference_to_a_private_planning_document(self):
        offenders = []
        for name in PUBLIC:
            path = ROOT / name
            files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
            for file in files:
                for number, line in enumerate(file.read_text(errors="replace").splitlines(), 1):
                    if PRIVATE_REFERENCE.search(line):
                        offenders.append(f"{file.relative_to(ROOT)}:{number}: {line.strip()}")
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
