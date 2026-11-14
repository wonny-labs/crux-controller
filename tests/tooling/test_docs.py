"""Checks of the repository's role and release documents: the wording the owner approved is
present, the promises the owner declined are absent, and the dependency page covers west.yml."""

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
    def test_readme_states_the_role_sentence_verbatim(self):
        self.assertIn(ROLE, text("README.md"))

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
        self.assertIn("37c92b18", body)
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

    def test_the_two_groups_that_stay_off_are_named(self):
        page = text("docs/dependencies.md")
        self.assertIn("`crux-secure-management`", page)
        self.assertIn("`crux-reliance`", page)

    def test_the_page_documents_how_the_crux_import_is_narrowed(self):
        page = text("docs/dependencies.md")
        for phrase in ("name-blocklist", "scripts/check_mbed_only.py",
                       "west list --all -f '{name} {active}'", "negative control"):
            self.assertIn(phrase, page, phrase)
        for name in ("wolfssl", "wolfssh", "wolfpsa", "mbedtls", "tf-psa-crypto"):
            self.assertIn(f"`{name}`", page, name)

    def test_the_page_states_the_proof_level_and_why_a_blocklist(self):
        page = text("docs/dependencies.md")
        for phrase in ("project-list level", "no job fetches or builds with the group on",
                       "only active projects", "not run", "allowlist", "drops Zephyr"):
            self.assertIn(phrase, page, phrase)

    def test_the_pinned_crux_revision_matches_the_manifest(self):
        manifest = yaml.safe_load((ROOT / "west.yml").read_text())["manifest"]
        pilot = next(p for p in manifest["projects"] if p["name"] == "crux-pilot")
        short = pilot["revision"][:8]
        for name in ("RELEASE.md", "docs/dependencies.md", "CHANGELOG.md"):
            self.assertIn(short, text(name), name)


class Tracking(unittest.TestCase):
    """The pages say where the management finding is tracked, and do not promise a filing."""

    def test_the_finding_names_the_issues_that_track_it(self):
        body = text("docs/findings/management-has-no-public-composition.md")
        self.assertNotIn("No issue tracks it yet", body)
        self.assertIn("#40", body)
        self.assertIn("#44", body)
        self.assertIn("has not happened", body)

    def test_the_readme_names_the_epic_and_its_steps_and_no_trial_issue(self):
        body = text("README.md")
        self.assertNotIn("trial issue", body)
        for number in ("#44", "#40", "#41", "#42", "#43"):
            self.assertIn(number, body, number)
        self.assertIn("Nothing has been filed in `crux-pilot` yet", body)


class Contributing(unittest.TestCase):
    """The guide names the CI jobs and the steps that the workflows actually define."""

    @staticmethod
    def workflow(name):
        return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())

    def build_steps(self):
        names = [job["name"] for job in self.workflow("ci.yml")["jobs"].values()]
        steps = [m.group(1) for m in (re.match(r"(S\d) build\b", n) for n in names) if m]
        self.assertTrue(steps, "no step build job found in ci.yml")
        return steps

    def budget_steps(self):
        matrix = self.workflow("budget.yml")["jobs"]["budget"]["strategy"]["matrix"]
        return [entry["step"] for entry in matrix["include"]]

    def test_the_ci_row_lists_every_step_build_job(self):
        body = text("CONTRIBUTING.md")
        for step in self.build_steps():
            self.assertIn(f"`{step} build`", body, step)

    def test_the_budget_row_covers_the_steps_of_the_budget_matrix(self):
        steps = self.budget_steps()
        self.assertIn(f"`Budget` for S0 to {steps[-1]}:", text("CONTRIBUTING.md"))

    def test_the_role_section_names_the_steps_built_in_ci(self):
        last = max(self.build_steps(), key=lambda step: int(step[1:]))
        self.assertIn(f"Steps S0 to {last} are built in CI", text("CONTRIBUTING.md"))


if __name__ == "__main__":
    unittest.main()
