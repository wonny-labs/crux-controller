# SPDX-License-Identifier: Apache-2.0
"""Tests of release/check_sbom.py, the element check of the SBOM (criterion 35)."""

import contextlib
import io
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "release"))

import check_sbom  # noqa: E402

HEADER = """SPDXVersion: SPDX-2.3
DataLicense: CC0-1.0
SPDXID: SPDXRef-DOCUMENT
DocumentName: {name}
DocumentNamespace: http://spdx.org/spdxdocs/{name}
Creator: Tool: test
Created: 2026-11-27T00:00:00Z

"""

COMPLETE = """PackageName: zephyr-sources
SPDXID: SPDXRef-zephyr-sources
PackageVersion: 4.5.0
PackageSupplier: Organization: zephyrproject
PackageDownloadLocation: NOASSERTION
ExternalRef: SECURITY cpe23Type cpe:2.3:o:zephyrproject:zephyr:4.5.0:*:*:*:*:*:*:*

Relationship: SPDXRef-DOCUMENT DESCRIBES SPDXRef-zephyr-sources
"""

INCOMPLETE = """PackageName: mbedtls-deps
SPDXID: SPDXRef-mbedtls-deps
PackageVersion: NOASSERTION
PackageSupplier: NOASSERTION
PackageDownloadLocation: NOASSERTION

PackageName: alone
SPDXID: SPDXRef-alone
PackageVersion: 1.0
PackageSupplier: Organization: someone
ExternalRef: PACKAGE-MANAGER purl pkg:github/someone/alone@1.0

Relationship: DocumentRef-zephyr:SPDXRef-zephyr-sources DEPENDS_ON SPDXRef-mbedtls-deps
"""


def folder(documents):
    directory = tempfile.TemporaryDirectory()
    for name, body in documents.items():
        (pathlib.Path(directory.name) / f"{name}.spdx").write_text(HEADER.format(name=name) + body)
    return directory


def run(directory, *extra):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = check_sbom.main(["--dir", directory, *extra])
    return code, out.getvalue(), err.getvalue()


class ElementCheck(unittest.TestCase):
    def test_a_complete_package_passes(self):
        with folder({"zephyr": COMPLETE}) as directory:
            code, out, _ = run(directory)
        self.assertEqual(0, code)
        self.assertIn("1 packages, 0 findings", out)

    def test_each_missing_element_is_a_finding(self):
        with folder({"zephyr": COMPLETE, "modules-deps": INCOMPLETE}) as directory:
            code, out, _ = run(directory)
        self.assertEqual(1, code)
        self.assertIn("modules-deps.spdx: mbedtls-deps: no version", out)
        self.assertIn("modules-deps.spdx: mbedtls-deps: no supplier", out)
        self.assertIn("modules-deps.spdx: mbedtls-deps: no purl or CPE", out)
        self.assertIn("modules-deps.spdx: alone: no relationship", out)
        self.assertNotIn("mbedtls-deps: no relationship", out)
        self.assertNotIn("alone: no purl or CPE", out)
        self.assertIn("3 packages, 4 findings", out)

    def test_report_mode_prints_the_same_and_passes(self):
        with folder({"zephyr": COMPLETE, "modules-deps": INCOMPLETE}) as directory:
            code, out, _ = run(directory, "--report")
        self.assertEqual(0, code)
        self.assertIn("3 packages, 4 findings", out)

    def test_a_document_that_does_not_parse_fails_in_both_modes(self):
        for extra in ((), ("--report",)):
            with folder({"broken": "this is not a tag value line\n"}) as directory:
                code, _, err = run(directory, *extra)
            self.assertEqual(2, code)
            self.assertIn("error:", err)

    def test_an_empty_folder_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _, err = run(directory, "--report")
        self.assertEqual(2, code)
        self.assertIn("no .spdx file", err)

    def test_output_names_files_by_base_name_only(self):
        with folder({"modules-deps": INCOMPLETE}) as directory:
            _, out, _ = run(directory, "--report")
        self.assertNotIn(directory, out)


if __name__ == "__main__":
    unittest.main()
