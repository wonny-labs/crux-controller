# SPDX-License-Identifier: Apache-2.0
"""Checks of board support: the README table of supported boards, the Twister platforms and the one board-specific
dependency of app/Kconfig.

The board is an input of scripts/build-board.sh and of the VS Code tasks (test_vscode_board.py). This file checks
that the boards a reader is told about, the platforms Twister runs and the build agree, and that the Crux symbol
named after one SoC stays in one place until Crux offers a board-neutral one.
"""

import pathlib
import re
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOARD = "mimxrt1060_evk@B/mimxrt1062/qspi"
TESTCASES = sorted(ROOT.glob("tests/native_sim*/*/testcase.yaml"))
# A full board target as Twister and Zephyr's hardware model name it: board, then at least the SoC.
FULL_TARGET = re.compile(r"^[A-Za-z0-9_]+(@[A-Za-z0-9_.]+)?(/[A-Za-z0-9_]+)+$")


def platforms(data, key):
    """Each scenario name -> its list under key, from the scenario or from common."""
    common = (data.get("common") or {}).get(key)
    return {name: scenario.get(key, common) for name, scenario in data["tests"].items()}


class Twister(unittest.TestCase):
    def test_there_are_scenarios(self):
        self.assertTrue(TESTCASES)

    def test_every_scenario_names_full_board_targets_and_its_integration_platforms(self):
        for path in TESTCASES:
            data = yaml.safe_load(path.read_text())
            allowed = platforms(data, "platform_allow")
            integration = platforms(data, "integration_platforms")
            for name in data["tests"]:
                with self.subTest(scenario=name):
                    self.assertTrue(allowed[name], name)
                    for target in allowed[name]:
                        self.assertRegex(target, FULL_TARGET)
                    # Twister's integration mode (--integration) runs exactly the allowed platforms.
                    self.assertEqual(allowed[name], integration[name])


class Readme(unittest.TestCase):
    def test_the_readme_lists_the_supported_boards_in_one_table(self):
        text = (ROOT / "README.md").read_text()
        section = text.split("## Supported boards\n", 1)[1].split("\n## ", 1)[0]
        rows = [line for line in section.splitlines() if line.startswith("| ") and "---" not in line]
        self.assertEqual(2, len(rows), rows)  # the header and one board
        self.assertIn(f"`{BOARD}`", rows[1])
        self.assertIn("SEGGER J-Link", rows[1])
        self.assertIn("docs/board-bring-up.md", section)
        # The short spelling that CI uses is stated once, as the same board target.
        self.assertIn("`mimxrt1060_evk@B//qspi`", section)
        self.assertIn("docs/board-bring-up.md#other-boards", section)

    def test_the_readme_table_is_the_only_list_of_boards(self):
        for page in ("docs/tutorial.md", "docs/board-bring-up.md"):
            with self.subTest(page):
                text = (ROOT / page).read_text()
                self.assertNotIn("| Board |", text)
        self.assertIn("../README.md#supported-boards", (ROOT / "docs" / "tutorial.md").read_text())

    def test_the_board_page_says_what_a_second_board_needs_and_gives_no_steps(self):
        text = (ROOT / "docs" / "board-bring-up.md").read_text()
        self.assertNotIn("## Add a board", text)
        section = text.split("\n## Other boards\n", 1)[1].split("\n## ", 1)[0]
        for name in ("net", "sntp", "management", "system", "file"):
            self.assertIn(f"`{name}`", section, name)
        self.assertNotRegex(section, r"(?m)^\d+\. ")


class Kconfig(unittest.TestCase):
    def test_the_soc_named_file_provider_is_named_in_one_place_only(self):
        # Crux has no board-neutral symbol for its FatFs provider yet; the dependency stays in one line.
        text = (ROOT / "app" / "Kconfig").read_text()
        self.assertEqual(1, len(re.findall(r"\bCRUX_FILE_FATFS_RT1060\b", text)))
        self.assertNotRegex(text, r"\bSOC_[A-Z0-9_]+")
        self.assertNotRegex(text, r"\bBOARD_[A-Z0-9_]+")


if __name__ == "__main__":
    unittest.main()
