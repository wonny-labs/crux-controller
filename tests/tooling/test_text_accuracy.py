# SPDX-License-Identifier: Apache-2.0
"""Statements in the documents and comments that a file of this repository can disprove."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def scripts_row():
    for line in (ROOT / "docs" / "architecture.md").read_text().splitlines():
        if line.startswith("| `scripts/` |"):
            return line
    raise AssertionError("docs/architecture.md has no row for scripts/")


class ScriptsRow(unittest.TestCase):
    def test_the_row_names_every_file_in_scripts(self):
        row = scripts_row()
        files = sorted(p.name for p in (ROOT / "scripts").iterdir() if p.is_file())
        self.assertTrue(files, "scripts/ is empty")
        missing = [name for name in files if f"`{name}`" not in row]
        self.assertEqual([], missing, "docs/architecture.md does not name these scripts")

    def test_the_row_names_no_script_that_does_not_exist(self):
        named = re.findall(r"`([A-Za-z0-9_.-]+\.(?:py|sh))`", scripts_row())
        for name in named:
            self.assertTrue((ROOT / "scripts" / name).is_file(), f"{name} is not in scripts/")


class ModuleSwitchComment(unittest.TestCase):
    """app/conf/file.conf says why it does not repeat CONFIG_CRUX_MODULE."""

    def test_the_comment_does_not_claim_that_prj_conf_sets_it(self):
        text = (ROOT / "app" / "conf" / "file.conf").read_text()
        self.assertNotIn("prj.conf keeps it on", text)
        self.assertTrue((ROOT / "app" / "prj.conf").is_file())
        prj = (ROOT / "app" / "prj.conf").read_text()
        self.assertNotIn("CONFIG_CRUX_MODULE", prj)

    def test_the_comment_gives_the_real_reason(self):
        header = "\n".join(
            line for line in (ROOT / "app" / "conf" / "file.conf").read_text().splitlines()
            if line.startswith("#")
        )
        flat = " ".join(header.replace("# ", " ").split())
        self.assertRegex(flat, r"CONFIG_CRUX_MODULE is not repeated \(it defaults to y")

    def test_no_file_of_the_application_sets_it(self):
        # The comment says that no file of this repository sets the switch. Comments do not count.
        files = [p for pattern in ("*.conf", "*.overlay", "*.cmake", "CMakeLists.txt")
                 for p in (ROOT / "app").rglob(pattern)]
        files += [p for p in (ROOT / "tests").rglob("prj.conf")]
        setters = []
        for path in files:
            for line in path.read_text().splitlines():
                if line.lstrip().startswith("#"):
                    continue
                if re.search(r"\bCONFIG_CRUX_MODULE\b|\bCRUX_MODULE\b", line):
                    setters.append(f"{path.relative_to(ROOT)}: {line.strip()}")
        self.assertEqual([], setters)


if __name__ == "__main__":
    unittest.main()
