# SPDX-License-Identifier: Apache-2.0
"""Stop new drift from docs/documentation-guidelines.md.

Every current-state page (entry, tutorial, how-to guide, reference and explanation) states what is true
now. Change history, dates, verification trails and status have their own homes. This test looks for the
usual lexical markers of those topics and fails only when a page has more of them than its entry in
fixtures/docs_page_types.json. Fixing a page lowers its entry; an entry is never raised.

Dated pages (docs/findings, docs/history, CHANGELOG.md) are not scanned.
"""

import json
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "docs_page_types.json"

CURRENT_TYPES = {"entry", "tutorial", "how-to", "reference", "explanation"}
OTHER_TYPES = {"record", "history"}

# Folders whose pages are dated and not scanned.
TYPED_FOLDERS = {"docs/findings/": "record", "docs/history/": "history"}
UNSCANNED = {"CHANGELOG.md"}

MONTHS = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")

# rule name -> (pattern, flags, where the topic belongs)
RULES = {
    "history": (
        r"\b(?:was|were|has been|have been|is now|are now) "
        r"(?:removed|renamed|replaced|dropped|deleted)\b"
        r"|\b(?:moved|renamed) from\b|\bpreviously\b|\bno longer\b|\bformerly\b"
        r"|\bwill be (?:frozen|removed|deprecated)\b",
        re.IGNORECASE,
        "change history: CHANGELOG or docs/history/",
    ),
    "provenance": (
        r"\bmerged in \[?(?:PR|pull request)\b|\bfor review in a Draft PR\b"
        rf"|\b(?:on|since|until|of) \d{{1,2}} (?:{MONTHS}) 20\d\d\b"
        rf"|\b(?:{MONTHS}) \d{{1,2}},? 20\d\d\b",
        re.IGNORECASE,
        "provenance and dates: the pull request, the issue, CHANGELOG or docs/history/",
    ),
    "status": (
        r"^Status:|\bExperimental\b|\bUnstable\b|\bto be removed\b|\bdeprecated\b",
        re.MULTILINE,
        "lifecycle status: the roadmap or the issue",
    ),
    "verification": (
        r"\b(?:was|were|has|have|had) (?:not|never) (?:been )?(?:run|tried|tested|verified|reproduced|"
        r"measured|started|checked|exercised)\b"
        r"|\b(?:untested|unverified|unrun)\b|\bnot (?:yet )?(?:tested|verified|reproduced)\b"
        r"|\bgeneral knowledge\b|\b(?:ran|run) once on\b|\bnot yet (?:run|possible|decided)\b",
        re.IGNORECASE,
        "verification trails and routes not run: docs/history/setup-checks.md or the issue",
    ),
}

FENCE = re.compile(r"^\s*(```|~~~)")
CODE_SPAN = re.compile(r"`[^`]*`")


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def page_type(path, types):
    for folder, kind in TYPED_FOLDERS.items():
        if path.startswith(folder):
            return kind
    # A page nobody has classified yet gets the strictest treatment.
    return types.get(path, "reference")


def scanned_pages():
    raw = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z", "--", "*.md"])
    for entry in raw.split(b"\0"):
        path = entry.decode()
        if (not path or path in UNSCANNED or path.startswith(tuple(TYPED_FOLDERS))
                or not (ROOT / path).is_file()):
            continue
        if path.startswith("docs/") or "/" not in path:
            yield path


def findings(path, text, kind):
    """Return (rule, line number, matched text) for a page of the given type."""
    if kind not in CURRENT_TYPES:
        return []
    found = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Text in a code span is quoted, such as a symbol or a marker being described.
        prose = CODE_SPAN.sub("", line)
        for rule, (pattern, flags, _) in RULES.items():
            for match in re.finditer(pattern, prose, flags):
                found.append((rule, number, match.group(0)))
    return found


def counts(path, text, kind):
    result = {}
    for rule, _, _ in findings(path, text, kind):
        result[rule] = result.get(rule, 0) + 1
    return result


class DocsPageTypesTest(unittest.TestCase):
    def test_no_page_has_more_markers_than_its_allowlist(self):
        fixture = load_fixture()
        allow = fixture["allowlist"]
        problems = []
        for path in scanned_pages():
            kind = page_type(path, fixture["types"])
            text = (ROOT / path).read_text(encoding="utf-8")
            limit = allow.get(path, {})
            for rule, number in sorted(counts(path, text, kind).items()):
                if number > limit.get(rule, 0):
                    lines = [f"{n}: '{m}'" for r, n, m in findings(path, text, kind) if r == rule]
                    problems.append(
                        f"{path} ({kind}): {number} '{rule}' markers, allowlist "
                        f"{limit.get(rule, 0)} ({RULES[rule][2]}); lines {', '.join(lines)}")
        self.assertEqual([], problems, "\n" + "\n".join(problems))

    def test_fixture_uses_known_types_rules_and_pages(self):
        fixture = load_fixture()
        for path, kind in fixture["types"].items():
            with self.subTest(path=path):
                self.assertIn(kind, CURRENT_TYPES | OTHER_TYPES)
                self.assertTrue((ROOT / path).is_file(), f"{path} is listed but missing")
        for path, limits in fixture["allowlist"].items():
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), f"{path} is listed but missing")
                for rule, number in limits.items():
                    self.assertIn(rule, RULES)
                    self.assertGreater(number, 0)

    def test_every_scanned_page_is_typed(self):
        types = load_fixture()["types"]
        self.assertEqual([], [p for p in scanned_pages() if p not in types])

    def test_each_rule_finds_its_marker(self):
        samples = {
            "history": ["The queue header was removed", "It previously used NVS",
                        "The option is no longer read", "This page moved from docs/old.md"],
            "provenance": ["Approved on 23 November 2026", "Measured on November 18, 2026",
                           "Status: merged in [PR #210](x)"],
            "status": ["Status: proposal", "The symbol is deprecated"],
            "verification": ["The route was not run", "It has never been tested here",
                             "This step is untested", "The exact message was not reproduced",
                             "The cause is general knowledge"],
        }
        for rule, lines in samples.items():
            for line in lines:
                with self.subTest(line=line):
                    self.assertIn(rule, {r for r, _, _ in findings("x.md", line, "how-to")})

    def test_current_text_and_dated_pages_pass(self):
        text = ("Build the image with west.\n"
                "The handle is invalid after close.\n"
                "The marker `was removed` is quoted in a code span.\n"
                "```\nthis was removed in a code block\n```\n")
        self.assertEqual([], findings("x.md", text, "tutorial"))
        self.assertEqual([], findings("x.md", "The route was not run", "record"))

    def test_typed_folders_and_unclassified_pages(self):
        self.assertEqual("reference", page_type("docs/new-page.md", {}))
        self.assertEqual("history", page_type("docs/history/x.md", {}))
        self.assertEqual("record", page_type("docs/findings/x.md", {"docs/findings/x.md": "how-to"}))


if __name__ == "__main__":
    unittest.main()
