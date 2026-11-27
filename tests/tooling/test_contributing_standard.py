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
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_host  # noqa: E402
import check_spdx  # noqa: E402
import ci_map  # noqa: E402

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


def without_cmake_comments(text):
    """The CMake text without its comment lines: a comment may name a file that is not a source."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def host_built_sources():
    """The sources of this repository that tests/host builds, read from its CMake files."""
    sources = set()
    host = without_cmake_comments((ROOT / "tests/host/CMakeLists.txt").read_text())
    for name in re.findall(r"(?<![\w./-])([\w./-]+\.c)\b", host):
        sources.add((ROOT / "tests/host" / name).resolve())
    workload = without_cmake_comments((ROOT / "workload/CMakeLists.txt").read_text())
    for name in re.findall(r"(?<![\w./-])([\w./-]+\.c)\b", workload):
        sources.add((ROOT / "workload" / name).resolve())
    return sources


def tracked_c_sources():
    """The sources that scripts/analyze_host.py lists: tracked, or new and not ignored."""
    return {path.resolve() for path in analyze_host.tracked_sources(ROOT)}


def not_analysed():
    return sorted(tracked_c_sources() - host_built_sources())


def statements(text, command):
    """The argument text of each `command(...)` call of a CMake file."""
    return re.findall(rf"^\s*{command}\((.*?)\)", text, re.MULTILINE | re.DOTALL)


def c_names(text):
    return {pathlib.PurePosixPath(n).name for n in re.findall(r"[\w./${}-]+\.c\b", text)}


def product_sources_with_warning_flags():
    """Basenames of the sources that the application's CMake files build with -Wall -Wextra -Werror."""
    flags = "-Wall -Wextra -Werror"
    flagged = set()
    app = (ROOT / "app/CMakeLists.txt").read_text()
    if f"target_compile_options(app PRIVATE {flags})" in app:
        for args in statements(app, "target_sources"):
            if args.startswith("app "):
                flagged |= c_names(args)
    os_zone = (ROOT / "app/os/CMakeLists.txt").read_text()
    for args in statements(os_zone, "set_source_files_properties"):
        if 'COMPILE_OPTIONS "-Wall;-Wextra;-Werror"' in args:
            flagged |= c_names(args)
    # The framework sources that the configurations of app/ compile into the target app.
    configurations = (ROOT / "framework/configurations.cmake").read_text()
    if f"target_compile_options(app PRIVATE {flags})" in app:
        for args in statements(configurations, "target_sources"):
            if args.startswith("app "):
                flagged |= c_names(args)
    # The framework library of the module, for the base image.
    module = (ROOT / "zephyr/CMakeLists.txt").read_text()
    if f"zephyr_library_compile_options({flags})" in module:
        for args in statements(module, "zephyr_library_sources"):
            flagged |= c_names(args)
    compose = (ROOT / "framework/compose/CMakeLists.txt").read_text()
    if f"target_compile_options(compose PRIVATE {flags})" in compose:
        for command in ("add_library", "target_sources"):
            for args in statements(compose, command):
                if args.startswith("compose "):
                    flagged |= c_names(args)
    return flagged


def scenario_cmake_files():
    return sorted([*(ROOT / "tests").glob("native_sim*/*/CMakeLists.txt"),
                   *(ROOT / "tests").glob("framework/*/CMakeLists.txt"),
                   ROOT / "tests" / "product_integration" / "CMakeLists.txt"])


def sources_given_compile_options_by_scenarios():
    names = set()
    for path in scenario_cmake_files():
        for args in statements(path.read_text(), "set_source_files_properties"):
            if "COMPILE_OPTIONS" in args:
                names |= c_names(args)
    return names


class ProductKconfigPrefix(unittest.TestCase):
    def test_the_prefix_is_recorded_as_the_products_own(self):
        body = flat(contributing())
        self.assertIn("`CRUX_CONTROLLER_`", body)
        self.assertRegex(body, r"not Crux platform symbols")

    def test_the_platform_sample_and_the_refusal_are_stated_with_their_reason(self):
        body = flat(section())
        self.assertIn("`CONFIG_CRUX_CONTROLLER_M3`", body)
        self.assertIn("refuses", body)
        self.assertIn("as a further owner of the native watchdog", body)
        self.assertIn("not because of the prefix", body)
        self.assertIn("docs/findings/s4-system-composition.md", body)
        self.assertIn("37c92b18", body)
        self.assertIn("8e3737d2", body)
        self.assertNotIn("at the pinned commit", body)
        self.assertNotRegex(body, r"same prefix, so")
        finding = (ROOT / "docs/findings/s4-system-composition.md").read_text()
        for symbol in ("CRUX_CONTROLLER_M3", "WDT_SHELL", "HWINFO_SHELL", "TASK_WDT_HW_FALLBACK"):
            self.assertIn(symbol, finding)
            self.assertIn(symbol, body.replace("CONFIG_", "") if symbol != "CRUX_CONTROLLER_M3" else body)

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
        missing = set(not_analysed())
        self.assertEqual(14, len(analysed))
        self.assertEqual(20, len(missing))
        self.assertIn("clang-tidy 18", body)
        for family in ("bugprone", "clang-analyzer", "performance", "portability"):
            self.assertIn(f"`{family}`", body)
        self.assertIn("warnings are errors", body)
        self.assertIn("the 14 sources", body)
        self.assertIn("`scripts/analyze_host.py`", body)
        self.assertIn("20 today", body)
        self.assertIn("the sources that the host tests do not build", body)
        self.assertIn("Zephyr or Crux headers or Kconfig values", body)
        self.assertNotIn("because they need Zephyr headers", body)
        self.assertIn("without failing", body)

    def test_ten_product_sources_get_warning_flags_and_six_scenario_sources_do_not(self):
        body = flat(section())
        names = {path.name: path for path in not_analysed()}
        self.assertEqual(20, len(names), "a basename is not unique")
        flagged = product_sources_with_warning_flags()
        scenario = {n for n, p in names.items() if "/tests/" in p.as_posix()}
        product = set(names) - scenario
        self.assertEqual(8, len(scenario))
        self.assertEqual(12, len(product))
        # Each product source is built with the flags by the CMake files that name them.
        self.assertEqual(product, product & flagged, sorted(product - flagged))
        # No scenario source is in a COMPILE_OPTIONS list, and no scenario file sets the flags on
        # a target: they are set only on the product sources that a scenario pulls in.
        given = sources_given_compile_options_by_scenarios()
        for name in scenario:
            self.assertNotIn(name, given)
            self.assertNotIn(name, flagged)
        for path in scenario_cmake_files():
            self.assertNotRegex(path.read_text(), r"target_compile_options\(app", path.name)
        # The text says exactly that.
        self.assertIn("12 of those 20 are product sources", body)
        self.assertIn("`-Wall -Wextra -Werror`", body)
        self.assertIn("The other 8 are the `native_sim` scenario sources", body)
        self.assertIn("not on the scenario source", body)
        self.assertNotIn("Those 16 sources get compiler warnings only", body)
        self.assertNotRegex(body, r"(?i)twister")

    def test_identifier_naming_is_listed_without_options(self):
        body = flat(section())
        tidy = (ROOT / ".clang-tidy").read_text()
        self.assertRegex(tidy, r"(?m)^\s*readability-identifier-naming\s*$")
        self.assertNotIn("CheckOptions", tidy)
        self.assertIn("`readability-identifier-naming` without options", body)
        self.assertIn("checks no naming rule", body)

    def test_the_spdx_allowlist_has_the_length_the_text_gives(self):
        self.assertEqual(2, len(check_spdx.ALLOWLIST))
        self.assertIn("a list of two older scripts", flat(section()))

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
        # The checks of the workflows are in the CI map file and the scripts of scripts/ci.
        workflows += " ".join(p.read_text().lower() for p in ci_map.ci_sources())
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
            # The row shortens a name to its first words: "workload (native_sim and ...)" is `workload`.
            short = job["name"].split(" (")[0]
            self.assertIn(f"`{short}`", row, job_id)

    def test_the_patch_style_job_and_its_rule_are_in_the_row(self):
        row = ci_row()
        self.assertIn("`Patch style`", row)
        self.assertIn("checkpatch", row)
        self.assertIn("BRACES", row)
        self.assertIn("`scripts/check-patch.sh`", row)

    @ci_map.needs_tomllib
    def test_the_spdx_step_is_in_the_tooling_job(self):
        self.assertIn("spdx", ci_map.ids("tooling"))
        self.assertEqual("python scripts/check_spdx.py\n", ci_map.run("spdx"))
        row = ci_row()
        self.assertIn("`spdx`", row)
        self.assertIn("`scripts/check_spdx.py`", row)

    @ci_map.needs_tomllib
    def test_the_kit_step_is_in_the_boundary_job(self):
        self.assertIn("kit-include-check", ci_map.ids("boundary"))
        row = ci_row()
        self.assertIn("style kit as a further check", row)
        self.assertNotIn("one more step", row)


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
        # The Patch style job runs scripts/ci/check-patch-range.sh, which runs the script.
        self.assertIn("scripts/ci/check-patch-range.sh", (ROOT / "scripts/ci/checks.toml").read_text())
        self.assertIn("exec scripts/check-patch.sh", (ROOT / "scripts/ci/check-patch-range.sh").read_text())

    def test_the_not_done_line_still_holds_for_python_shell_yaml_and_cmake(self):
        # Header and brace checks are not linting of the languages: no linter is configured.
        self.assertIn("no linting of Python, shell, YAML and CMake", flat(section()))


if __name__ == "__main__":
    unittest.main()


class ContentRules(unittest.TestCase):
    """The section that says what may not be added is called "Content rules", keeps the employer
    and private-repository items of the public repository, and docs/reviewing.md points at it."""

    HEADING = "## Content rules"

    def body(self):
        text = contributing()
        start = text.index(self.HEADING)
        match = re.search(r"^## ", text[start + len(self.HEADING):], re.MULTILINE)
        end = start + len(self.HEADING) + match.start() if match else len(text)
        return flat(text[start:end])

    def test_the_section_exists_once_under_its_new_name(self):
        self.assertEqual(1, contributing().count(self.HEADING + "\n"))
        self.assertNotIn("## A public repository", contributing())

    def test_the_section_keeps_every_rule(self):
        body = self.body()
        for needle in ("Everything here is public.", "a name of an employer or customer",
                       "a proprietary product or runtime", "a private repository",
                       "a reference to a private planning document", "tests/tooling/test_public_text.py",
                       "the memory sizes of a real product", "secrets, keys or credentials",
                       "an absolute path of a personal or build machine", "Apache-2.0",
                       "no firmware image, `.elf` or `.map` file"):
            self.assertIn(needle, body, needle)

    def test_the_review_checklist_points_at_the_section(self):
        reviewing = (ROOT / "docs" / "reviewing.md").read_text()
        self.assertIn('"Content rules"', reviewing)
        self.assertNotIn('"A public repository"', reviewing)


class CmakeCommentHelper(unittest.TestCase):
    def test_a_comment_that_names_a_c_file_is_not_a_source(self):
        text = "# net_client.c is built unchanged.\nadd_executable(t t.c)  # not a comment line\n"
        kept = without_cmake_comments(text)
        self.assertNotIn("net_client.c", kept)
        self.assertIn("add_executable(t t.c)", kept)

