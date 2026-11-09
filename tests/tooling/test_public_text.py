"""Public files must not point at planning documents that readers cannot see."""

import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PUBLIC = (
    ".github", "app", "budgets", "docs", "release", "scripts", "workload",
    "README.md", "SECURITY.md", "RELEASE.md", "CHANGELOG.md", "CONTRIBUTING.md",
)
PRIVATE_REFERENCE = re.compile(r"\b(?:OD|WD)[0-9]+\b|skeleton plan|work package", re.IGNORECASE)


def scan(root, names):
    offenders = []
    for name in names:
        path = root / name
        files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for file in files:
            for number, line in enumerate(file.read_text(errors="replace").splitlines(), 1):
                if PRIVATE_REFERENCE.search(line):
                    offenders.append(f"{file.relative_to(root)}:{number}: {line.strip()}")
    return offenders


class PublicText(unittest.TestCase):
    def test_no_reference_to_a_private_planning_document(self):
        self.assertEqual([], scan(ROOT, PUBLIC))

    def test_the_contribution_guide_is_scanned_and_exists(self):
        self.assertIn("CONTRIBUTING.md", PUBLIC)
        self.assertTrue((ROOT / "CONTRIBUTING.md").is_file())

    def test_a_private_reference_in_the_contribution_guide_is_found(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "CONTRIBUTING.md").write_text("fine line\nsee the skeleton plan\n")
            found = scan(root, ("CONTRIBUTING.md",))
        self.assertEqual(["CONTRIBUTING.md:2: see the skeleton plan"], found)


if __name__ == "__main__":
    unittest.main()
