# SPDX-License-Identifier: Apache-2.0
"""Checks that CONTRIBUTING.md states the coding and analysis position of the repository: the prefix
of the product's Kconfig symbols, and the section on static analysis and the coding standard with
the facts that were measured on main at merge e11e971.

The numbers in the section are pinned against the repository itself, so they cannot drift without a
failing test: the host-built sources are read from tests/host/CMakeLists.txt and the tracked sources
come from git."""

import pathlib
import re
import subprocess
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLATFORM_GUIDELINES = (
    "https://github.com/wonny-labs/crux-pilot/blob/"
    "751e04aead779ac08e438ec1e2640e57fc50e9fe/docs/coding-guidelines.md"
)
HEADING = "## Static analysis and coding standard"


def contributing():
    return (ROOT / "CONTRIBUTING.md").read_text()


def section():
    body = contributing()
    start = body.index(HEADING)
    match = re.search(r"^## ", body[start + len(HEADING):], re.MULTILINE)
    end = start + len(HEADING) + match.start() if match else len(body)
    return body[start:end]


def flat(text):
    return " ".join(text.split())


def host_built_sources():
    """The sources of this repository that tests/host builds, read from its CMake files."""
    sources = set()
    host = (ROOT / "tests/host/CMakeLists.txt").read_text()
    for name in re.findall(r"(?<![\w./-])([\w./-]+\.c)\b", host):
        sources.add((ROOT / "tests/host" / name).resolve())
    workload = (ROOT / "workload/CMakeLists.txt").read_text()
    for name in re.findall(r"(?<![\w./-])([\w./-]+\.c)\b", workload):
        sources.add((ROOT / "workload" / name).resolve())
    return sources


def tracked_c_sources():
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "*.c", "*.cpp"],
        check=True, capture_output=True,
    )
    return {(ROOT / n.decode()).resolve() for n in out.stdout.split(b"\0") if n}


class ProductKconfigPrefix(unittest.TestCase):
    def test_the_prefix_is_recorded_as_the_products_own(self):
        body = flat(contributing())
        self.assertIn("`CRUX_CONTROLLER_`", body)
        self.assertRegex(body, r"not Crux platform symbols")

    def test_the_platform_sample_and_the_refusal_are_stated(self):
        body = flat(contributing())
        self.assertIn("`CONFIG_CRUX_CONTROLLER_M3`", body)
        self.assertIn("refuses", body)
        self.assertIn("docs/findings/s4-system-composition.md", body)

    def test_the_product_defines_no_symbol_of_the_sample(self):
        self.assertNotIn("config CRUX_CONTROLLER_M3", (ROOT / "app/Kconfig").read_text())

    def test_every_product_symbol_has_the_prefix(self):
        for line in (ROOT / "app/Kconfig").read_text().splitlines():
            match = re.match(r"\s*(?:menu)?config (\w+)", line)
            if match:
                self.assertTrue(match.group(1).startswith("CRUX_CONTROLLER_"), line)


class StaticAnalysisSection(unittest.TestCase):
    def test_the_section_exists_once(self):
        self.assertEqual(1, contributing().count(HEADING))

    def test_the_section_is_short(self):
        self.assertLessEqual(len(section().splitlines()), 45)

    def test_the_measurement_is_dated_and_tied_to_the_merge(self):
        body = flat(section())
        self.assertIn("e11e971", body)
        self.assertIn("18 November 2026", body)

    def test_format_gate(self):
        body = flat(section())
        self.assertIn("clang-format 18.1.8", body)
        self.assertIn("every tracked C file", body)
        self.assertIn("`scripts/check-format.sh`", body)

    def test_tidy_scope_and_the_not_analysed_list_match_the_repository(self):
        body = flat(section())
        analysed = host_built_sources()
        missing = tracked_c_sources() - analysed
        self.assertEqual(12, len(analysed))
        self.assertEqual(16, len(missing))
        self.assertIn("clang-tidy 18", body)
        for family in ("bugprone", "clang-analyzer", "performance", "portability"):
            self.assertIn(f"`{family}`", body)
        self.assertIn("warnings are errors", body)
        self.assertIn("the 12 sources", body)
        self.assertIn("`scripts/analyze_host.py`", body)
        self.assertIn("16 today", body)
        self.assertIn("they need Zephyr headers", body)
        self.assertIn("without failing", body)

    def test_zephyr_side_files_get_compiler_warnings_only(self):
        body = flat(section())
        self.assertIn("`-Wall -Wextra -Werror`", body)
        self.assertIn("native_sim", body)
        cmake = (ROOT / "app/CMakeLists.txt").read_text()
        self.assertIn("-Wall -Wextra -Werror", cmake)

    def test_other_checks_are_named_with_where_they_run(self):
        body = flat(section())
        self.assertIn("`scripts/check_boundary.py`", body)
        self.assertIn("`Boundary check`", body)
        self.assertIn("`.github/workflows/budget.yml`", body)
        self.assertIn("`Static analysis`", body)

    def test_what_is_not_measured_or_linted_is_stated_and_true(self):
        body = flat(section())
        self.assertIn("no coverage measurement", body)
        self.assertIn("Python, shell, YAML and CMake", body)
        workflows = " ".join(
            p.read_text().lower() for p in (ROOT / ".github/workflows").glob("*.yml")
        )
        for tool in ("gcov", "lcov", "ruff", "flake8", "pylint", "shellcheck", "yamllint"):
            self.assertNotIn(tool, workflows)

    def test_compliance_statement_is_negative_and_links_the_platform_text(self):
        body = flat(section())
        self.assertIn(
            "not a claim of MISRA C, CERT C, security or functional-safety compliance", body
        )
        self.assertIn(PLATFORM_GUIDELINES, section())
        self.assertNotRegex(body.lower(), r"advisory subset")

    def test_gaps_are_labelled_and_no_future_work_is_promised(self):
        body = flat(section())
        self.assertIn("known gaps, not scheduled", body.lower())
        self.assertNotRegex(body.lower(), r"\b(will be|we will|planned|roadmap|soon|later)\b")


def ci_row():
    for line in contributing().splitlines():
        if line.startswith("| `ci.yml` |"):
            return flat(line)
    raise AssertionError("the ci.yml row of the workflow table is missing")


class CiJobTable(unittest.TestCase):
    def setUp(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        self.jobs = workflow["jobs"]

    def test_the_row_names_every_job_of_ci_yml(self):
        row = ci_row()
        for job_id, job in self.jobs.items():
            # The row shortens a name to its first words: "S1 (native_sim and ...)" is `S1`.
            short = job["name"].split(" (")[0]
            self.assertIn(f"`{short}`", row, job_id)

    def test_the_patch_style_job_and_its_rule_are_in_the_row(self):
        row = ci_row()
        self.assertIn("`Patch style`", row)
        self.assertIn("checkpatch", row)
        self.assertIn("BRACES", row)
        self.assertIn("`scripts/check-patch.sh`", row)

    def test_the_spdx_step_is_in_the_tooling_job(self):
        steps = [s.get("name") for s in self.jobs["tooling"]["steps"]]
        self.assertIn("Check SPDX headers", steps)
        row = ci_row()
        self.assertIn("`Check SPDX headers`", row)
        self.assertIn("`scripts/check_spdx.py`", row)

    def test_the_kit_step_is_in_the_boundary_job(self):
        steps = [s.get("name") for s in self.jobs["boundary"]["steps"]]
        self.assertIn("Run the style kit include check script", steps)
        self.assertIn("style kit", ci_row())


class SpdxAndPatchStyleFacts(unittest.TestCase):
    def test_the_section_states_the_spdx_check_as_the_script_defines_it(self):
        body = flat(section())
        self.assertIn("`scripts/check_spdx.py`", body)
        self.assertIn("first-party C, CMake, Kconfig, Python and shell files", body)
        script = (ROOT / "scripts/check_spdx.py").read_text()
        for suffix in ('".c"', '".h"', '".py"', '".sh"', '".cmake"', '"CMakeLists.txt"', '"Kconfig"'):
            self.assertIn(suffix, script)

    def test_the_section_states_the_checkpatch_gate_as_the_script_defines_it(self):
        body = flat(section())
        self.assertIn("`scripts/check-patch.sh`", body)
        self.assertIn("BRACES", body)
        self.assertIn("changed C lines", body)
        script = (ROOT / "scripts/check-patch.sh").read_text()
        self.assertIn('types="${CHECKPATCH_TYPES:-BRACES}"', script)
        self.assertIn("'*.c' '*.h'", script)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("scripts/check-patch.sh", workflow)

    def test_the_not_done_line_still_holds_for_python_shell_yaml_and_cmake(self):
        # Header and brace checks are not linting of the languages: no linter is configured.
        self.assertIn("no linting of Python, shell, YAML and CMake", flat(section()))


if __name__ == "__main__":
    unittest.main()
