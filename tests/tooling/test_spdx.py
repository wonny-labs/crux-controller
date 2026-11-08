"""Tests of release/parse_spdx.py, the parser for the tag-value SPDX files of west spdx."""

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "release"))

import parse_spdx  # noqa: E402

HEADER = """SPDXVersion: SPDX-2.3
DataLicense: CC0-1.0
SPDXID: SPDXRef-DOCUMENT
DocumentName: app-sources
DocumentNamespace: http://spdx.org/spdxdocs/zephyr-app-sources-1234
Creator: Tool: Zephyr SPDX builder
Created: 2026-11-08T10:00:00Z
"""

PACKAGES = """
# A comment line between sections.
##### Package: zephyr

PackageName: zephyr
SPDXID: SPDXRef-zephyr
PackageLicenseConcluded: NOASSERTION
PackageDownloadLocation: NOASSERTION
FilesAnalyzed: true
PackageVerificationCode: 0123456789abcdef0123456789abcdef01234567
PackageLicenseInfoFromFiles: NOASSERTION
PackageLicenseDeclared: Apache-2.0
PackageCopyrightText: <text>Copyright (c) Zephyr contributors
Second line of the notice</text>

PackageName: crux-pilot
SPDXID: SPDXRef-crux-pilot
PackageDownloadLocation: NOASSERTION
PackageLicenseConcluded: NOASSERTION

FileName: ./main.c
SPDXID: SPDXRef-File-main
FileChecksum: SHA1: 0123456789abcdef0123456789abcdef01234567
LicenseConcluded: NOASSERTION
LicenseInfoInFile: NOASSERTION
FileCopyrightText: NONE

Relationship: SPDXRef-DOCUMENT DESCRIBES SPDXRef-zephyr
"""


def parse(text):
    return parse_spdx.parse(text)


class ParseValid(unittest.TestCase):
    def test_a_header_only_document_has_no_packages(self):
        document = parse(HEADER)
        self.assertEqual("SPDX-2.3", document.header["SPDXVersion"])
        self.assertEqual(0, document.package_count)
        self.assertEqual(0, document.file_count)

    def test_counts_packages_and_files(self):
        document = parse(HEADER + PACKAGES)
        self.assertEqual(2, document.package_count)
        self.assertEqual(1, document.file_count)
        self.assertEqual(["zephyr", "crux-pilot"], document.package_names)

    def test_a_multi_line_text_value_is_one_value(self):
        document = parse(HEADER + PACKAGES)
        notice = document.packages[0]["PackageCopyrightText"]
        self.assertIn("Second line of the notice", notice)
        self.assertTrue(notice.startswith("Copyright"))

    def test_a_value_may_contain_colons(self):
        document = parse(HEADER + PACKAGES)
        self.assertEqual("SHA1: 0123456789abcdef0123456789abcdef01234567",
                         document.files[0]["FileChecksum"])

    def test_creator_may_repeat(self):
        text = HEADER + "Creator: Organization: Example\n"
        self.assertEqual(2, len(parse(text).creators))

    def test_windows_line_endings_are_accepted(self):
        self.assertEqual(0, parse((HEADER + PACKAGES).replace("\n", "\r\n")).package_count - 2)

    def test_a_text_value_that_contains_a_tag_looking_line_stays_inside(self):
        text = HEADER + "\nPackageName: p\nSPDXID: SPDXRef-p\nPackageComment: <text>\nPackageName: not a package\n</text>\n"
        self.assertEqual(1, parse(text).package_count)


class ParseInvalid(unittest.TestCase):
    def fails(self, text, fragment):
        with self.assertRaises(parse_spdx.SpdxError) as raised:
            parse(text)
        self.assertIn(fragment, str(raised.exception))

    def test_an_empty_file_is_refused(self):
        self.fails("", "SPDXVersion")

    def test_each_header_field_is_required(self):
        for tag in ("SPDXVersion", "DataLicense", "SPDXID", "DocumentName",
                    "DocumentNamespace", "Creator", "Created"):
            lines = [line for line in HEADER.splitlines() if not line.startswith(tag + ":")]
            self.fails("\n".join(lines) + "\n" + PACKAGES, tag)

    def test_a_header_field_with_an_empty_value_is_refused(self):
        self.fails(HEADER.replace("DocumentName: app-sources", "DocumentName:"), "DocumentName")

    def test_wrong_version_is_refused(self):
        self.fails(HEADER.replace("SPDX-2.3", "SPDX-2.2"), "SPDX-2.3")

    def test_wrong_data_license_is_refused(self):
        self.fails(HEADER.replace("CC0-1.0", "MIT"), "CC0-1.0")

    def test_the_document_id_must_be_the_document(self):
        self.fails(HEADER.replace("SPDXRef-DOCUMENT", "SPDXRef-x"), "SPDXRef-DOCUMENT")

    def test_created_must_be_a_utc_timestamp(self):
        self.fails(HEADER.replace("2026-11-08T10:00:00Z", "yesterday"), "Created")

    def test_creator_needs_a_known_kind(self):
        self.fails(HEADER.replace("Creator: Tool: Zephyr SPDX builder", "Creator: somebody"), "Creator")

    def test_a_line_without_a_tag_is_refused_with_its_number(self):
        text = HEADER + "this is not a tag value line\n"
        self.fails(text, "line 8")

    def test_an_unknown_tag_is_refused(self):
        self.fails(HEADER + "Bogus: 1\n", "Bogus")

    def test_an_unterminated_text_value_is_refused(self):
        self.fails(HEADER + "PackageName: p\nPackageComment: <text>never closed\n", "<text>")

    def test_a_package_tag_after_a_relationship_without_a_section_is_refused(self):
        text = HEADER + "Relationship: SPDXRef-DOCUMENT DESCRIBES SPDXRef-x\nPackageVersion: 1\n"
        self.fails(text, "before any section start")

    def test_an_incomplete_header_followed_directly_by_a_relationship_is_refused(self):
        lines = [line for line in HEADER.splitlines() if not line.startswith("Created:")]
        text = "\n".join(lines) + "\nRelationship: SPDXRef-DOCUMENT DESCRIBES SPDXRef-x\n"
        self.fails(text, "Created")

    def test_a_package_tag_directly_after_the_header_is_refused(self):
        self.fails(HEADER + "PackageVersion: 1\n", "before any section start")

    def test_an_indented_comment_is_skipped(self):
        self.assertEqual(0, parse(HEADER + "   # indented comment\n").package_count)

    def test_a_repeated_tag_keeps_its_first_value(self):
        text = HEADER + "\nPackageName: p\nSPDXID: SPDXRef-p\nPackageVersion: 1\nPackageVersion: 2\n"
        self.assertEqual("1", parse(text).packages[0]["PackageVersion"])

    def test_deprecated_tags_still_parse(self):
        text = HEADER + "\nFileName: ./a.c\nSPDXID: SPDXRef-a\nFileDependency: ./b.c\n"
        self.assertEqual(1, parse(text).file_count)

    def test_a_package_before_the_header_is_refused(self):
        self.fails("PackageName: p\n" + HEADER, "SPDXVersion")

    def test_a_package_without_an_spdxid_is_refused(self):
        self.fails(HEADER + "\nPackageName: p\n\nPackageName: q\nSPDXID: SPDXRef-q\n", "SPDXID")

    def test_duplicate_spdxids_are_refused(self):
        text = HEADER + "\nPackageName: p\nSPDXID: SPDXRef-p\n\nPackageName: q\nSPDXID: SPDXRef-p\n"
        self.fails(text, "duplicate")


class CommandLine(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "release" / "parse_spdx.py"), *args],
            capture_output=True, text=True,
        )

    def write(self, directory, name, text):
        path = pathlib.Path(directory) / name
        path.write_text(text)
        return path

    def test_prints_the_package_count_of_each_document(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "app.spdx", HEADER + PACKAGES)
            self.write(directory, "zephyr.spdx", HEADER)
            result = self.run_tool("--dir", directory)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("app.spdx: SPDX-2.3, 2 packages, 1 files", result.stdout)
        self.assertIn("zephyr.spdx: SPDX-2.3, 0 packages, 0 files", result.stdout)

    def test_output_names_files_by_base_name_only(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "app.spdx", HEADER)
            result = self.run_tool("--dir", directory)
        self.assertNotIn(directory, result.stdout + result.stderr)

    def test_a_broken_file_fails_the_run_and_names_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "good.spdx", HEADER)
            self.write(directory, "bad.spdx", "nonsense\n")
            result = self.run_tool("--dir", directory)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("bad.spdx", result.stderr)
        self.assertIn("good.spdx: SPDX-2.3", result.stdout)

    def test_a_directory_without_spdx_files_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_tool("--dir", directory)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("no .spdx files", result.stderr)

    def test_an_unreadable_file_names_no_directory(self):
        result = self.run_tool("/nonexistent-spdx-dir/a.spdx")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("a.spdx", result.stderr)
        self.assertNotIn("nonexistent-spdx-dir", result.stderr + result.stdout)

    def test_a_missing_directory_fails(self):
        result = self.run_tool("--dir", "/nonexistent-spdx-dir")
        self.assertNotEqual(0, result.returncode)

    def test_files_may_be_named_directly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, "one.spdx", HEADER + PACKAGES)
            result = self.run_tool(str(path))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("one.spdx: SPDX-2.3, 2 packages", result.stdout)


class WorkflowStep(unittest.TestCase):
    def test_the_release_dry_run_parses_the_spdx_files_after_west_spdx_and_uploads_nothing(self):
        import yaml

        data = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text())
        steps = data["jobs"]["dry-run"]["steps"]
        commands = [step.get("run", "") for step in steps]
        spdx_at = next(i for i, c in enumerate(commands) if "west spdx -d" in c)
        parse_at = next(i for i, c in enumerate(commands) if "parse_spdx.py" in c)
        self.assertGreater(parse_at, spdx_at)
        self.assertIn("build/s2/spdx", commands[parse_at])
        for step in steps:
            self.assertNotIn("upload-artifact", step.get("uses", ""))
        tests_step = "\n".join(commands)
        self.assertIn("test_spdx.py", tests_step)


if __name__ == "__main__":
    unittest.main()
