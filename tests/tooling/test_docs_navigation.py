# SPDX-License-Identifier: Apache-2.0
"""Checks of the navigation pages and of the terminology that the documents share.

The index must list every document of docs/ and docs/findings/, the links of the new pages must
resolve, the reading time in the README must agree with the index, the glossary must define the
words that the pages use, and the headings of the step recipe must follow one numbering scheme."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
NEW_PAGES = ("docs/README.md", "docs/first-change.md", "docs/reviewing.md", "docs/team-copy.md")
# Documents whose wording this change owns. Findings are kept as recorded and are not listed.
OWNED = (
    "README.md", "docs/README.md", "docs/first-change.md", "docs/reviewing.md", "docs/team-copy.md",
    "docs/adding-a-step.md", "docs/glossary.md", "docs/architecture.md", "docs/composition-zone.md",
)
# Pages that another change writes. A link to one of them is checked as soon as the page, or the
# heading for an anchor, exists, and is skipped while it is missing. Remove an entry from this set
# when the page has been merged, so that the link is checked without an exception.
PLANNED_PAGES = {"docs/troubleshooting.md"}
PLANNED_ANCHORS = {("docs/try-on-native-sim.md", "quick-start")}
FIVE = ("README.md", "docs/roadmap.md", "docs/architecture.md", "docs/try-on-native-sim.md",
        "CONTRIBUTING.md")


def read(name):
    return (ROOT / name).read_text()


def flat(name):
    return " ".join(read(name).split())


def without_code(body):
    return re.sub(r"```.*?```", "", body, flags=re.S)


def slug(heading):
    heading = heading.strip().lower().replace("`", "")
    heading = re.sub(r"[^\w\- ]", "", heading)
    return heading.replace(" ", "-")


def anchors(name):
    found, seen = set(), {}
    for line in without_code(read(name)).splitlines():
        match = re.match(r"#{1,6}\s+(.*)$", line)
        if match:
            base = slug(match.group(1))
            count = seen.get(base, 0)
            seen[base] = count + 1
            found.add(base if count == 0 else f"{base}-{count}")
    return found


def links(name):
    """Relative link targets of a document, as (path from the repository root, anchor)."""
    out = []
    base = (ROOT / name).parent
    for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", without_code(read(name))):
        if re.match(r"[a-z]+:", target):
            continue
        path, _, anchor = target.partition("#")
        resolved = (base / path).resolve() if path else (ROOT / name).resolve()
        out.append((str(resolved.relative_to(ROOT)), anchor, target))
    return out


def documents():
    names = sorted(p.relative_to(DOCS) for p in DOCS.glob("*.md"))
    names += sorted(p.relative_to(DOCS) for p in (DOCS / "findings").glob("*.md"))
    return [n for n in names if str(n) != "README.md"]


def sentences(text):
    text = re.sub(r"`[^`]*`", "X", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # A list item is a sentence of its own, with or without a final full stop.
    text = re.sub(r"\s*\n\s*(?:[-*]|\d+\.) ", ". ", text)
    return [s for s in re.split(r"(?<=[.!?])\s+", " ".join(text.split())) if s]


def section(name, heading):
    body = read(name)
    start = body.index(f"## {heading}")
    end = body.find("\n## ", start + 3)
    return body[start:end if end != -1 else len(body)]


class Index(unittest.TestCase):
    def test_the_index_exists(self):
        self.assertTrue((DOCS / "README.md").is_file())

    def test_the_index_lists_every_document_of_docs_and_findings(self):
        targets = {path for path, _, _ in links("docs/README.md")}
        missing = [f"docs/{n}" for n in documents() if f"docs/{n}" not in targets]
        self.assertEqual([], missing, "docs/README.md does not link these documents")

    def test_the_index_has_a_reading_time_column_and_a_role_path_for_each_task(self):
        body = read("docs/README.md")
        self.assertIn("Reading time", body)
        for heading in ("I want to run it", "I want to change code", "I want to add a step",
                        "I want to review", "I want to know why"):
            self.assertRegex(body, rf"(?m)^#{{2,3}} {heading}\b", heading)

    def test_the_index_says_where_decisions_are_recorded(self):
        body = read("docs/README.md")
        self.assertRegex(body, r"(?m)^## Where decisions are recorded$")
        part = section("docs/README.md", "Where decisions are recorded")
        for needle in ("docs/findings/", "roadmap.md", "CONTRIBUTING.md"):
            self.assertIn(needle, part, needle)

    def test_every_listed_page_has_a_reading_time_in_minutes(self):
        rows = [line for line in read("docs/README.md").splitlines()
                if line.startswith("|") and "](" in line]
        self.assertGreaterEqual(len(rows), len(documents()))
        for row in rows:
            self.assertRegex(row, r"\|\s*(about |under )?\d+ min\s*\|", row)


class Links(unittest.TestCase):
    def test_every_link_of_the_new_pages_resolves(self):
        for name in NEW_PAGES:
            for path, anchor, target in links(name):
                if path in PLANNED_PAGES and not (ROOT / path).exists():
                    continue
                self.assertTrue((ROOT / path).exists(), f"{name}: {target}")
                if anchor and (ROOT / path).suffix == ".md":
                    if (path, anchor) in PLANNED_ANCHORS and anchor not in anchors(path):
                        continue
                    self.assertIn(anchor, anchors(path), f"{name}: {target}")

    def test_every_link_of_the_edited_pages_resolves(self):
        for name in OWNED:
            for path, anchor, target in links(name):
                if path in PLANNED_PAGES and not (ROOT / path).exists():
                    continue
                self.assertTrue((ROOT / path).exists(), f"{name}: {target}")
                if anchor and (ROOT / path).suffix == ".md":
                    if (path, anchor) in PLANNED_ANCHORS and anchor not in anchors(path):
                        continue
                    self.assertIn(anchor, anchors(path), f"{name}: {target}")

    def test_the_new_pages_are_linked_from_the_readme(self):
        targets = {path for path, _, _ in links("README.md")}
        for name in NEW_PAGES:
            self.assertIn(name, targets, name)


class ReadingTime(unittest.TestCase):
    def index_minutes(self):
        minutes = {}
        for line in read("docs/README.md").splitlines():
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            time = re.search(r"(\d+) min", cells[-1] if cells else "")
            link = re.search(r"\]\(([^)#\s]+)", cells[0] if cells else "")
            if time and link:
                path = (DOCS / link.group(1)).resolve()
                minutes[str(path.relative_to(ROOT))] = int(time.group(1))
        return minutes

    def test_the_five_documents_of_the_reading_path_are_in_the_index(self):
        minutes = self.index_minutes()
        for name in FIVE:
            self.assertIn(name, minutes, name)

    def test_the_readme_claims_about_sixty_minutes_and_the_index_agrees(self):
        text = flat("README.md")
        self.assertNotIn("30 minutes", text)
        self.assertIn("about 60 minutes", text)
        total = sum(self.index_minutes()[name] for name in FIVE)
        self.assertLessEqual(abs(total - 60), 5, f"the five pages add up to {total} minutes")

    def test_the_listed_times_follow_the_length_of_each_page(self):
        # About 250 words a minute for technical text. A wide band keeps the check from failing
        # on every edit and still catches a page that has doubled in size or a guess.
        for name, minutes in self.index_minutes().items():
            words = len(read(name).split())
            self.assertLessEqual(minutes, max(2, round(words / 250 * 1.6)), name)
            self.assertGreaterEqual(minutes, max(1, round(words / 250 / 1.6)), name)

    def test_the_readme_reading_path_points_at_the_index(self):
        self.assertIn("docs/README.md", {p for p, _, _ in links("README.md")})


class Glossary(unittest.TestCase):
    ENTRIES = (
        "Product", "PASS, REVISE and ESCALATE", "Files that need a reviewed change", "Reviewer",
        "Owner", "Operator", "Composition", "Product include check", "Platform",
        "Team copy", "Maintainer",
    )

    def test_the_glossary_defines_the_new_entries(self):
        body = read("docs/glossary.md")
        for entry in self.ENTRIES:
            self.assertRegex(body, rf"(?m)^\*\*{re.escape(entry)}\.\*\*", entry)

    def test_the_glossary_says_what_product_means_and_does_not_mean(self):
        body = flat("docs/glossary.md")
        self.assertIn("the firmware that this repository holds", body)
        self.assertIn("not a product in the commercial sense", body)

    def test_the_composition_entry_lists_four_meanings(self):
        part = re.search(r"\*\*Composition\.\*\*(.*?)\n\n\*\*", read("docs/glossary.md"), re.S)
        self.assertIsNotNone(part)
        self.assertGreaterEqual(len(re.findall(r"(?m)^\d\. ", part.group(1))), 4)

    def test_the_owner_entries_agree_with_the_readme_and_security(self):
        glossary = flat("docs/glossary.md")
        self.assertIn("the repository owner", flat("SECURITY.md"))
        self.assertIn("\"the repository owner\"", glossary)
        self.assertIn("the repository owner", flat("README.md"))

    def test_the_verdict_entry_matches_contributing(self):
        glossary = flat("docs/glossary.md")
        contributing = flat("CONTRIBUTING.md")
        self.assertIn("`PASS`, `REVISE` or `ESCALATE`", contributing)
        for needle in ("`PASS`", "`REVISE`", "`ESCALATE`", "one re-check",
                       "unmet acceptance criterion", "factual error"):
            self.assertIn(needle, glossary, needle)

    def test_the_reviewed_files_entry_points_at_the_list(self):
        self.assertIn("adding-a-step.md#files-that-need-a-reviewed-change",
                      read("docs/glossary.md"))
        self.assertIn("files-that-need-a-reviewed-change", anchors("docs/adding-a-step.md"))


class Terminology(unittest.TestCase):
    OLD_NAMES = ("include check script of the Crux style kit", "Crux product include check",
                 "crux-pilot style kit", "style kit include check", "Crux style kit")

    def test_the_include_check_has_one_name_in_the_documents_that_this_change_owns(self):
        for name in OWNED:
            body = flat(name)
            for old in self.OLD_NAMES:
                self.assertNotIn(old, body, f"{name}: {old}")
        self.assertIn("the product include check", flat("docs/composition-zone.md"))
        self.assertIn("the product include check", flat("docs/glossary.md"))

    def test_the_new_pages_use_no_process_wording(self):
        for name in NEW_PAGES:
            self.assertNotRegex(read(name), r"(?i)\b(claude|assistant|chatgpt|llm|agent)\b", name)
            self.assertNotRegex(read(name), r"/Users/|/home/|/private/|[A-Z]:\\", name)

    def test_no_owned_document_keeps_a_dated_or_historical_phrase(self):
        for name in OWNED:
            body = flat(name)
            for phrase in ("Measured on `main` at merge", "in a later commit", "because it was missed",
                           "arrived with"):
                self.assertNotIn(phrase, body, f"{name}: {phrase}")

    def test_the_readme_defines_its_acronyms_where_it_first_uses_them(self):
        body = flat("README.md")
        rules = {
            "EVKB": r"(evaluation board[^.]{0,40}EVKB|EVKB[^.]{0,60}evaluation board)",
            "SNTP": r"SNTP[^.]{0,5}\(?[^.]{0,20}(network time|Simple Network Time Protocol)",
            "Twister": r"Twister[^.]{0,5}\(?[^.]{0,20}test runner",
            "ztest": r"ztest[^.]{0,5}\(?[^.]{0,20}test framework",
            "MDIO": r"MDIO[^.]{0,5}\(?[^.]{0,30}(management|Ethernet)",
            "SBOM": r"SBOM[^.]{0,5}\(?[^.]{0,30}(bill of materials|list of)",
            "PASS": r"`PASS`[^.]{0,5}\(?[^.]{0,60}(no blocking|reviewer)",
        }
        for term, pattern in rules.items():
            first = re.search(rf"(?<![\w-]){re.escape(term)}(?![\w])" if term != "PASS" else r"`PASS`", body)
            self.assertIsNotNone(first, term)
            definition = re.search(pattern, body)
            self.assertIsNotNone(definition, f"{term} is not defined")
            self.assertLessEqual(definition.start(), first.start() + 140, f"{term} is defined late")

    def test_the_long_readme_passages_are_short_sentences(self):
        body = read("README.md")
        passages = {
            "first paragraphs": " ".join(body.split("\n\n")[1:4]),
            "owner bullet": section("README.md", "Roles and references").split("- **The reviewer")[0],
            "status": section("README.md", "Status").split("| Step |")[0],
        }
        for label, text in passages.items():
            for sentence in sentences(text):
                self.assertLessEqual(len(sentence.split()), 40, f"{label}: {sentence}")

    def test_the_role_sentence_and_the_pinned_readme_facts_stay(self):
        text = flat("README.md")
        self.assertIn("Crux Controller is the official reference consumer firmware", text)
        for needle in ("Steps S0 to S6 are on `main`, and there is no release",
                       "Nothing else has run on a board."):
            self.assertIn(needle, text, needle)


class AddingAStep(unittest.TestCase):
    PAGE = "docs/adding-a-step.md"

    def headings(self):
        return [m.groups() for m in re.finditer(r"(?m)^(#{2,3}) (.*)$", without_code(read(self.PAGE)))]

    def test_numbered_sections_use_one_scheme(self):
        top = [t for level, t in self.headings() if level == "##"]
        numbered = [int(m.group(1)) for t in top if (m := re.match(r"(\d+)\. ", t))]
        self.assertEqual(list(range(1, len(numbered) + 1)), numbered)
        self.assertGreaterEqual(len(numbered), 5)
        # Unnumbered sections come after the numbered ones, never between them.
        flags = [bool(re.match(r"\d+\. ", t)) for t in top]
        self.assertEqual(sorted(flags, reverse=True), flags)

    def test_subsections_carry_the_number_of_their_section(self):
        current, expected = None, 0
        for level, title in self.headings():
            if level == "##":
                match = re.match(r"(\d+)\. ", title)
                current, expected = (int(match.group(1)) if match else None), 0
            elif current is not None:
                expected += 1
                self.assertTrue(title.startswith(f"{current}.{expected} "), title)
            else:
                self.fail(f"a subsection outside a numbered section: {title}")

    def test_the_checklist_covers_spdx_format_tidy_and_patch_style(self):
        part = section(self.PAGE, [t for l, t in self.headings() if l == "##" and "heck list" in t][0])
        for needle in ("SPDX-License-Identifier: Apache-2.0", "scripts/check_spdx.py",
                       "scripts/check-format.sh", "scripts/analyze_host.py", "scripts/check-patch.sh"):
            self.assertIn(needle, part, needle)

    def test_the_spdx_rule_matches_what_the_script_covers(self):
        script = read("scripts/check_spdx.py")
        for needle in ("CMakeLists.txt", "Kconfig", ".py", ".sh", ".cmake", ".c", ".h"):
            self.assertIn(needle, script)
        body = flat(self.PAGE)
        self.assertIn("first line", body)
        self.assertIn("the second line when the first is a shebang", body)
        self.assertIn("`.conf` files, devicetree overlays, documents", body)

    def test_the_history_of_s5_and_s6_is_an_appendix_at_the_end(self):
        titles = [t for level, t in self.headings() if level == "##"]
        self.assertIn("Appendix: what S5 and S6 did differently", titles)
        appendix = titles.index("Appendix: what S5 and S6 did differently")
        self.assertEqual(len(titles) - 1, appendix)
        self.assertNotIn("What S5 did differently", [t for t in titles if t != titles[appendix]])
        self.assertNotIn("was updated in a later commit", flat(self.PAGE))

    def test_the_drivers_and_hal_section_states_the_rule_and_where_the_reasoning_lives(self):
        titles = [t for level, t in self.headings() if level == "##"]
        title = "Drivers and HAL: what the rule is and where the reasoning lives"
        found = [t for t in titles if t.endswith(title)]
        self.assertEqual(1, len(found), titles)
        self.assertRegex(found[0], r"^\d+\. ")
        part = " ".join(section(self.PAGE, found[0]).split())
        for needle in ("GPIO, I2C and SPI", "roadmap.md", "composition-zone.md", "architecture.md",
                       "docs/choosing-an-api.md", "8e3737d25d048b14a00c01da00494f58a62958c6"):
            self.assertIn(needle, part, needle)

    def test_the_list_of_files_that_need_a_reviewed_change_is_still_there(self):
        self.assertIn("files-that-need-a-reviewed-change", anchors(self.PAGE))


class Changelog(unittest.TestCase):
    def test_the_unreleased_section_records_the_new_pages(self):
        body = read("CHANGELOG.md")
        unreleased = body[body.index("## Unreleased"):]
        for name in ("docs/README.md", "docs/first-change.md", "docs/reviewing.md",
                     "docs/team-copy.md"):
            self.assertIn(name, unreleased, name)
        self.assertIn("No firmware image changes.", " ".join(unreleased.split()))


class NewPages(unittest.TestCase):
    def test_the_first_change_tutorial_names_the_steps_and_the_commands(self):
        body = read("docs/first-change.md")
        for needle in ("git switch -c", "cmake -S tests/host", "ctest --test-dir",
                       "python -m unittest discover -s tests/tooling", "python scripts/check_boundary.py",
                       "scripts/check-format.sh", "python scripts/check_spdx.py", "<type>: <summary>",
                       "what was checked", "was not run", "tests/host/test_workload.c"):
            self.assertIn(needle, body, needle)
        self.assertIn("CONTRIBUTING.md#build-and-test", " ".join(body.split()))

    def test_the_first_change_example_message_follows_the_commit_rules(self):
        for subject in re.findall(r"(?m)^git commit -m \"([^\"]+)\"", read("docs/first-change.md")):
            self.assertLess(len(subject), 72, subject)
            self.assertRegex(subject, r"^(feat|fix|docs|test|build|ci|refactor|chore): [a-z]", subject)
            self.assertFalse(subject.endswith("."), subject)

    def test_the_reviewing_checklist_cites_contributing_and_the_three_verdicts(self):
        body = flat("docs/reviewing.md")
        for needle in ("`PASS`", "`REVISE`", "`ESCALATE`", "CONTRIBUTING.md", "one re-check",
                       "unmet acceptance criterion", "factual error", "Measured", "Inferred",
                       "Recorded", "Open", "files-that-need-a-reviewed-change",
                       "CONTRIBUTING.md does not say"):
            self.assertIn(needle, body, needle)

    def test_the_team_copy_note_covers_the_copy_tasks(self):
        body = flat("docs/team-copy.md")
        for needle in ("CODEOWNERS", "git init && git add -A", "upstream", "NOTICE", "LICENSE",
                       "SPDX-License-Identifier: Apache-2.0", "west.yml", "`.github/workflows/`",
                       "https://github.com/wonny-labs/crux-controller/issues", "SECURITY.md",
                       "no support period", "python -m unittest discover -s tests/tooling",
                       "#44", "pull request 50"):
            self.assertIn(needle, body, needle)
        self.assertIn("whoever approves merges and releases", body)


if __name__ == "__main__":
    unittest.main()
