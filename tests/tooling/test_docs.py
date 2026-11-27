# SPDX-License-Identifier: Apache-2.0
"""Checks of the repository's role and release documents: the role wording is present, the promises
that are not made (a support period, a name reserved for another project) are absent, and the
dependency page covers west.yml."""

import pathlib
import re
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROLE = (
    "Crux Controller is the official reference consumer firmware for ongoing integration, "
    "evaluation and regression testing of Crux Platform capabilities through public and approved "
    "composition interfaces. It may provide supporting evidence for relevant platform milestones, "
    "but it is not a mandatory exit criterion for any of them."
)
DOCS = (
    "README.md", "SECURITY.md", "RELEASE.md", "CHANGELOG.md", "docs/dependencies.md",
    "CONTRIBUTING.md",
)


def text(name):
    return " ".join((ROOT / name).read_text().split())


class Role(unittest.TestCase):
    # Approved behaviour change: the README is an entry page and leaves the milestone wording out; the
    # role sentence has one home, the role section of CONTRIBUTING.md.
    def test_contributing_states_the_role_sentence_verbatim_and_the_readme_does_not_repeat_it(self):
        self.assertIn(ROLE, text("CONTRIBUTING.md"))
        self.assertNotIn("milestone", text("README.md"))
        self.assertNotIn("exit criterion", text("README.md"))

    def test_no_document_says_it_is_simply_not_an_exit_criterion(self):
        for name in DOCS:
            for sentence in re.split(r"(?<=[.!?])\s", text(name)):
                if "exit criterion" in sentence:
                    self.assertTrue(
                        "mandatory exit criterion" in sentence, f"{name}: {sentence}"
                    )

    def test_the_name_reserved_for_the_crux_sample_is_not_used(self):
        for name in DOCS:
            self.assertNotRegex(text(name).lower(), r"the reference controller", name)


class Promises(unittest.TestCase):
    def test_no_support_period_is_promised(self):
        for name in DOCS:
            body = text(name).lower()
            self.assertNotRegex(body, r"\b(5|five)[- ]years?\b", name)
        for name in ("SECURITY.md", "RELEASE.md"):
            self.assertIn("no support period", text(name).lower(), name)
            self.assertIn("latest release", text(name).lower(), name)

    def test_security_policy_names_no_person_and_no_address(self):
        body = (ROOT / "SECURITY.md").read_text()
        self.assertNotRegex(body, r"[\w.+-]+@[\w-]+\.[\w.]+")
        self.assertIn("private vulnerability reporting", body)

    def test_release_document_keeps_the_image_out_and_the_tag_with_the_owner(self):
        body = text("RELEASE.md")
        self.assertIn("never published", body)
        self.assertIn("approval", body)
        self.assertIn("05a50475", body)
        self.assertIn("docs/product-composition.md", body)


class Dependencies(unittest.TestCase):
    def test_every_west_project_is_listed_with_its_revision(self):
        manifest = yaml.safe_load((ROOT / "west.yml").read_text())["manifest"]
        page = (ROOT / "docs" / "dependencies.md").read_text()
        for project in manifest["projects"]:
            self.assertIn(f"`{project['name']}`", page, project["name"])
            self.assertIn(str(project["revision"]), page, project["name"])

    def test_the_table_lists_the_crux_route_projects_with_full_revisions(self):
        page = (ROOT / "docs" / "dependencies.md").read_text()
        rows = {}
        for line in page.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == 5 and cells[0].startswith("`"):
                match = re.search(r"`([0-9a-f]{40})`", cells[1])
                rows[cells[0].strip("`")] = match.group(1) if match else None
        for name in ("zephyr", "cmsis", "cmsis_6", "hal_nxp", "littlefs", "fatfs", "crux-pilot", "picolibc"):
            self.assertIn(name, rows)
            self.assertIsNotNone(rows[name], f"{name} has no 40-digit revision in its row")

    def test_the_groups_that_stay_off_are_named(self):
        page = text("docs/dependencies.md")
        self.assertIn("`crux-secure-management`", page)
        self.assertIn("`crux-reliance`", page)
        self.assertIn("`crux-boot`", page)

    def test_the_page_documents_how_the_crux_import_is_narrowed(self):
        page = text("docs/dependencies.md")
        for phrase in ("name-blocklist", "scripts/check_mbed_only.py",
                       "west list --all -f '{name} {active}'", "negative control"):
            self.assertIn(phrase, page, phrase)
        for name in ("wolfssl", "wolfssh", "wolfpsa", "mbedtls", "tf-psa-crypto"):
            self.assertIn(f"`{name}`", page, name)

    def test_the_page_states_the_proof_level_and_why_a_blocklist(self):
        page = text("docs/dependencies.md")
        # The management capability added a job that fetches with the group on, so the sentence that no job does is
        # replaced by one that names the two places that do, and the proof level is still stated.
        for phrase in ("project-list level", "The `management build` job and the `Budget` row of `management`",
                       "only active projects", "not run", "allowlist", "drops Zephyr"):
            self.assertIn(phrase, page, phrase)
        self.assertNotIn("no job fetches or builds with the group on", page)

    def test_the_page_names_what_the_group_check_catches_and_what_was_not_run(self):
        page = text("docs/dependencies.md")
        self.assertIn("a project that the group would activate", page)
        self.assertNotIn("a project that Crux adds to the group later", page)
        self.assertIn("the first CI run of the `management` job was the first fetch with the group on", page)
        self.assertIn("records its result at `bb3ffefd`", page)
        self.assertNotIn("which was not run here", page)

    def test_the_pinned_crux_revision_matches_the_manifest(self):
        manifest = yaml.safe_load((ROOT / "west.yml").read_text())["manifest"]
        crux = next(p for p in manifest["projects"] if p["name"] == "crux-pilot")
        short = crux["revision"][:8]
        for name in ("RELEASE.md", "docs/dependencies.md", "CHANGELOG.md"):
            self.assertIn(short, text(name), name)


class Tracking(unittest.TestCase):
    """The pages say where the management finding is tracked, and do not promise a filing."""

    def test_the_finding_names_the_issues_that_track_it(self):
        body = text("docs/findings/management-has-no-public-composition.md")
        self.assertNotIn("No issue tracks it yet", body)
        self.assertRegex(body, r"#40\b")
        self.assertRegex(body, r"#44\b")
        self.assertIn("has not happened", body)

    def test_the_main_documents_point_at_the_tracking_history(self):
        for name in ("docs/roadmap.md", "docs/README.md", "docs/glossary.md"):
            self.assertIn("history/board-runs-and-tracking.md", text(name), name)
        self.assertIn("Nothing has been filed in `crux-pilot`", text("docs/roadmap.md"))


class CiEvidenceRationale(unittest.TestCase):
    """The architecture page explains why evidence comes from CI, in agreement with CONTRIBUTING.md."""

    def section(self):
        page = (ROOT / "docs" / "architecture.md").read_text()
        start = page.index("## Why the evidence comes from CI")
        end = page.find("\n## ", start + 1)
        return " ".join(page[start:end if end != -1 else len(page)].split())

    def test_the_section_reports_what_contributing_says_now(self):
        contributing = text("CONTRIBUTING.md")
        self.assertIn("CI is the reference for the Zephyr builds and the Twister runs", contributing)
        self.assertNotIn("describes no local Zephyr build", contributing)
        section = self.section()
        self.assertIn("CI is the reference for the Zephyr builds and the Twister runs", section)
        self.assertIn("a local result does not replace CI", section)
        self.assertIn("gives no reason", section)

    def test_the_section_does_not_claim_a_conflict_with_contributing(self):
        section = self.section()
        for phrase in ("describes no local Zephyr build", "predates this page", "separate reviewed change"):
            self.assertNotIn(phrase, section)

    def test_the_section_agrees_with_getting_started_about_the_supported_route(self):
        self.assertIn("nobody has run the Dev Container on WSL2", self.section())
        # Getting started names one supported route and does not describe a route that was not run.
        self.assertIn("x86_64 Linux machine with Docker Engine. This is the supported route",
                      text("docs/getting-started.md"))
        self.assertNotIn("WSL2", text("docs/getting-started.md"))


class Contributing(unittest.TestCase):
    """The guide names the CI jobs and the build configurations that the workflows actually define."""

    @staticmethod
    def workflow(name):
        return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())

    def build_steps(self):
        # Found in ci.yml alone, independently of the Budget matrix: every job named "<name> build (...)".
        names = [job["name"] for job in self.workflow("ci.yml")["jobs"].values()]
        steps = [m.group(1) for m in (re.match(r"(\S+) build \(", n) for n in names) if m]
        self.assertTrue(steps, "no build job of a configuration found in ci.yml")
        return steps

    def budget_steps(self):
        matrix = self.workflow("budget.yml")["jobs"]["budget"]["strategy"]["matrix"]
        return list(matrix["config"])

    def other_job_names(self):
        return [job["name"] for job in self.workflow("ci.yml")["jobs"].values()]

    def test_the_ci_row_lists_every_step_build_job(self):
        body = text("CONTRIBUTING.md")
        for step in self.build_steps():
            self.assertIn(f"`{step} build`", body, step)

    def test_the_budget_row_covers_the_steps_of_the_budget_matrix(self):
        steps = self.budget_steps()
        self.assertEqual(steps[0], "base", "the budget matrix must start at base")
        self.assertEqual(len(steps), len(set(steps)))
        self.assertIn(f"`Budget` for `base` to `{steps[-1]}`:", text("CONTRIBUTING.md"))

    def test_the_ci_row_names_the_other_jobs_of_ci_yml(self):
        row = next(
            line for line in (ROOT / "CONTRIBUTING.md").read_text().splitlines()
            if line.startswith("| `ci.yml`")
        )
        names = self.other_job_names()
        for short in (
            "Tooling tests", "West pins", "Host tests", "workload", "Boundary check", "Static analysis",
        ):
            self.assertIn(f"`{short}`", row, short)
            self.assertTrue(
                any(name == short or name.startswith(short + " ") for name in names),
                f"{short} is not a job name of ci.yml",
            )

    def test_the_ci_row_and_the_local_commands_name_the_static_analysis_scripts(self):
        lines = (ROOT / "CONTRIBUTING.md").read_text().splitlines()
        row = next(line for line in lines if line.startswith("| `ci.yml`"))
        for script in ("scripts/check-format.sh", "scripts/analyze_host.py"):
            self.assertTrue((ROOT / script).is_file(), script)
            self.assertIn(f"`{script}`", row, script)
            # The local commands are lines of a code block, apart from the table row.
            self.assertTrue(
                any(script in line and not line.startswith("|") for line in lines), script
            )
        self.assertIn("clang-format 18.1.8", row)
        self.assertIn("clang-tidy 18", row)
        self.assertIn("not analysed", row)

    def test_the_role_section_names_the_steps_built_in_ci(self):
        # Every configuration that has a build job (all but workload, whose job runs native_sim too) is
        # in the budget matrix, and the role section lists the whole matrix in its order.
        steps = self.budget_steps()
        # The workload job is named without "build" because it also runs the native_sim scenarios.
        self.assertEqual(set(steps), set(self.build_steps()) | {"workload"})
        listed = ", ".join(f"`{s}`" for s in steps[:-1]) + f" and `{steps[-1]}`"
        self.assertIn(f"The build configurations {listed} are built in CI", text("CONTRIBUTING.md"))


class GenericWording(unittest.TestCase):
    """The maintained documents state facts without the pull request or issue number that brought
    them, and the first-change page does not tie the clone to one hosting address. Records keep
    their numbers: the changelog, docs/findings/ and docs/history/ are not checked here, and neither
    is the glossary entry that explains what such numbers mean."""

    MAINTAINED = (
        "CONTRIBUTING.md", "docs/adding-a-capability.md", "docs/architecture.md", "docs/composition-zone.md",
        "docs/first-change.md", "docs/reviewing.md", "docs/roadmap.md",
    )
    NUMBER = re.compile(
        r"pull request \d+|\bPR \d+|crux-pilot#\d+|crux-controller#\d+|/pull/\d+|/issues/\d+"
        r"|\bissue #?\d+|(?<![\w&])#\d{1,4}\b"
    )

    def west_comments(self):
        return "\n".join(
            line.split("#", 1)[1] for line in (ROOT / "west.yml").read_text().splitlines() if "#" in line
        )

    def test_the_maintained_documents_name_no_pull_request_or_issue_number(self):
        for name in self.MAINTAINED:
            self.assertEqual([], self.NUMBER.findall(text(name)), name)

    def test_the_west_manifest_comments_name_no_pull_request_or_issue_number(self):
        self.assertEqual([], self.NUMBER.findall(" ".join(self.west_comments().split())))

    def test_the_glossary_states_the_queue_removal_without_a_number(self):
        entry = text("docs/glossary.md")
        entry = entry[entry.index("**Frozen headers.**"):]
        entry = entry[: entry.index("**", len("**Frozen headers.**"))]
        self.assertEqual([], self.NUMBER.findall(entry))

    def test_the_first_change_page_clones_from_the_address_you_were_given(self):
        body = text("docs/first-change.md")
        self.assertIn("git clone <repository-url> crux-controller", body)
        self.assertIn("the address you were given", body)
        self.assertNotIn("git clone https://", body)
        self.assertNotIn("on GitHub", body)

    def test_the_documents_say_the_ci_where_the_sentence_is_not_about_github(self):
        self.assertNotIn("GitHub Actions", text("docs/roadmap.md"))
        self.assertNotIn("GitHub Actions", text("docs/glossary.md"))


class ParagraphRules(unittest.TestCase):
    """The guidelines carry Crux's paragraph and blank-line rules, and no page has two blank lines in a row."""

    def test_the_guidelines_state_the_paragraph_and_blank_line_rules(self):
        body = text("docs/documentation-guidelines.md")
        self.assertIn("\n## Paragraphs and line breaks\n", (ROOT / "docs/documentation-guidelines.md").read_text())
        for rule in ("one sentence on each line", "Do not reflow text that a change does not otherwise touch",
                     "one blank line between paragraphs and around every heading, list, table and fenced code block",
                     "Never put two blank lines in a row", "https://sembr.org/",
                     "https://spec.commonmark.org/0.31.2/#paragraphs"):
            self.assertIn(rule, body, rule)

    def test_no_page_has_two_blank_lines_in_a_row(self):
        names = ["README.md", "CONTRIBUTING.md", "RELEASE.md", "SECURITY.md"]
        names += [str(p.relative_to(ROOT)) for p in sorted((ROOT / "docs").glob("*.md"))]
        for name in names:
            self.assertNotIn("\n\n\n", (ROOT / name).read_text(), name)


class EntryTable(unittest.TestCase):
    def test_the_documentation_map_is_the_last_row_of_where_to_read_next(self):
        # Reader order as in Crux: the task rows first, the map for any other page last.
        body = (ROOT / "README.md").read_text()
        part = body[body.index("## Where to read next"):]
        part = part[:part.index("\n## ")]
        rows = [line for line in part.splitlines() if line.startswith("| ") and not line.startswith("| You want")]
        self.assertEqual("| Find any other page by task | [Documentation map](docs/README.md) |", rows[-1])
        self.assertEqual(1, sum("docs/README.md" in row for row in rows))


if __name__ == "__main__":
    unittest.main()
