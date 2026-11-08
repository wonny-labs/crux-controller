"""Checks of the repository's role and release documents: the wording the owner approved is
present, the promises the owner declined are absent, and the dependency page covers west.yml."""

import pathlib
import re
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROLE = (
    "crux-controller is the official reference consumer firmware for ongoing integration, "
    "evaluation and regression testing of Crux Platform capabilities through public and approved "
    "composition interfaces. It may provide supporting evidence for relevant platform milestones, "
    "but it is not a mandatory exit criterion for any of them."
)
DOCS = ("README.md", "SECURITY.md", "RELEASE.md", "CHANGELOG.md", "docs/dependencies.md")


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

    def test_the_pinned_crux_revision_matches_the_manifest(self):
        manifest = yaml.safe_load((ROOT / "west.yml").read_text())["manifest"]
        pilot = next(p for p in manifest["projects"] if p["name"] == "crux-pilot")
        short = pilot["revision"][:8]
        for name in ("RELEASE.md", "docs/dependencies.md", "CHANGELOG.md"):
            self.assertIn(short, text(name), name)


if __name__ == "__main__":
    unittest.main()
