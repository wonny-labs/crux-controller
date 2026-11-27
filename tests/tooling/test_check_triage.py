# SPDX-License-Identifier: Apache-2.0
"""Tests of release/check_triage.py, the release check of known vulnerabilities (criterion 36)."""

import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "release"))

import check_triage  # noqa: E402

PURL = "pkg:github/Mbed-TLS/mbedtls@v3.6.4"
CPE = "cpe:2.3:a:arm:mbed_tls:3.6.4:*:*:*:*:*:*:*"
FIRMWARE = "pkg:generic/crux-controller@0.1.0"


def grype_match(vuln="CVE-2026-0001", related=(), purl=PURL, cpes=(CPE,), name="mbedtls"):
    """One match as Grype's JSON output writes it."""
    return {
        "vulnerability": {"id": vuln, "fix": {"versions": [], "state": "not-fixed"}},
        "relatedVulnerabilities": [{"id": item} for item in related],
        "matchDetails": [],
        "artifact": {"name": name, "version": "v3.6.4", "purl": purl, "cpes": list(cpes)},
    }


def statement(status, vuln="CVE-2026-0001", products=None, timestamp=None, **fields):
    item = {
        "vulnerability": {"name": vuln},
        "products": products if products is not None else [{"@id": PURL}],
        "status": status,
    }
    if timestamp:
        item["timestamp"] = timestamp
    if status == "not_affected" and "justification" not in fields and "impact_statement" not in fields:
        fields["justification"] = "vulnerable_code_not_present"
    if status == "affected" and "action_statement" not in fields:
        fields["action_statement"] = "Update to the fixed release."
    item.update(fields)
    return item


def document(*statements, **fields):
    doc = {
        "@context": "https://openvex.dev/ns/v0.2.0",
        "@id": "https://github.com/wonny-labs/crux-controller/release/triage",
        "author": "crux-controller maintainers",
        "timestamp": "2026-11-27T00:00:00Z",
        "version": 1,
        "statements": list(statements),
    }
    doc.update(fields)
    return doc


class Fixture:
    """A folder of Grype JSON reports and a triage document."""

    def __init__(self, base, matches, triage):
        self.base = pathlib.Path(base)
        self.matches = self.base / "matches"
        self.matches.mkdir()
        (self.matches / "app.grype.json").write_text(json.dumps({"matches": matches}))
        self.triage = self.base / "triage.openvex.json"
        self.triage.write_text(json.dumps(triage))

    def findings(self):
        return check_triage.check(self.matches, self.triage)[1]


class ReleaseGate(unittest.TestCase):
    def assert_fails(self, matches, triage, text):
        with tempfile.TemporaryDirectory() as base:
            findings = Fixture(base, matches, triage).findings()
            self.assertEqual(1, len(findings), findings)
            self.assertIn(text, findings[0])
            self.assertIn("CVE-2026-0001", findings[0])

    def assert_passes(self, matches, triage):
        with tempfile.TemporaryDirectory() as base:
            self.assertEqual([], Fixture(base, matches, triage).findings())

    def test_a_match_without_a_triage_record_fails(self):
        self.assert_fails([grype_match()], document(), "no triage record")

    def test_status_affected_fails(self):
        self.assert_fails([grype_match()], document(statement("affected")), "affected")

    def test_status_under_investigation_fails(self):
        self.assert_fails(
            [grype_match()], document(statement("under_investigation")), "under investigation"
        )

    def test_status_not_affected_passes(self):
        self.assert_passes([grype_match()], document(statement("not_affected")))

    def test_status_fixed_passes(self):
        self.assert_passes([grype_match()], document(statement("fixed")))

    def test_no_match_passes(self):
        self.assert_passes([], document())

    def test_a_record_for_another_package_does_not_count(self):
        other = statement("not_affected", products=[{"@id": "pkg:github/someone/other@1.0"}])
        self.assert_fails([grype_match()], document(other), "no triage record")

    def test_a_record_for_another_vulnerability_does_not_count(self):
        other = statement("not_affected", vuln="CVE-2026-9999")
        self.assert_fails([grype_match()], document(other), "no triage record")

    def test_the_record_may_name_an_alias_of_the_match(self):
        match = grype_match(vuln="GHSA-aaaa-bbbb-cccc", related=("CVE-2026-0001",))
        self.assert_passes([match], document(statement("not_affected")))

    def test_the_record_may_carry_the_alias_itself(self):
        item = statement("not_affected", vuln="GHSA-aaaa-bbbb-cccc")
        item["vulnerability"]["aliases"] = ["CVE-2026-0001"]
        self.assert_passes([grype_match()], document(item))

    def test_the_package_may_be_named_by_cpe_identifier(self):
        products = [{"@id": "urn:example:mbedtls", "identifiers": {"cpe23": CPE}}]
        self.assert_passes([grype_match()], document(statement("not_affected", products=products)))

    def test_the_package_may_be_a_subcomponent_of_the_firmware(self):
        products = [{"@id": FIRMWARE, "subcomponents": [{"@id": PURL}]}]
        self.assert_passes([grype_match()], document(statement("not_affected", products=products)))

    def test_the_latest_record_wins(self):
        early = statement("under_investigation", timestamp="2026-11-01T00:00:00Z")
        late = statement("not_affected", timestamp="2026-11-20T00:00:00Z")
        self.assert_passes([grype_match()], document(late, early))
        reopened = statement("under_investigation", timestamp="2026-11-25T00:00:00Z")
        self.assert_fails(
            [grype_match()], document(early, late, reopened), "under investigation"
        )

    def test_a_statement_without_timestamp_takes_the_document_timestamp(self):
        early = statement("under_investigation", timestamp="2026-11-01T00:00:00Z")
        self.assert_passes([grype_match()], document(early, statement("not_affected")))

    def test_two_latest_records_with_different_status_fail(self):
        one = statement("not_affected", timestamp="2026-11-20T00:00:00Z")
        two = statement("affected", timestamp="2026-11-20T00:00:00Z")
        self.assert_fails([grype_match()], document(one, two), "conflicting")

    def test_a_match_found_in_two_documents_is_reported_once(self):
        with tempfile.TemporaryDirectory() as base:
            fixture = Fixture(base, [grype_match()], document())
            (fixture.matches / "zephyr.grype.json").write_text(
                json.dumps({"matches": [grype_match()]})
            )
            count, findings = check_triage.check(fixture.matches, fixture.triage)
            self.assertEqual(1, count)
            self.assertEqual(1, len(findings), findings)


class TriageDocument(unittest.TestCase):
    def assert_invalid(self, triage, text):
        with tempfile.TemporaryDirectory() as base:
            fixture = Fixture(base, [], triage)
            with self.assertRaises(check_triage.TriageError) as raised:
                fixture.findings()
            self.assertIn(text, str(raised.exception))

    def test_the_repository_triage_file_is_a_valid_document(self):
        check_triage.load_triage(ROOT / "release" / "triage.openvex.json")

    def test_an_unknown_status_is_refused(self):
        self.assert_invalid(document(statement("ignored")), "status")

    def test_not_affected_needs_a_justification_or_an_impact_statement(self):
        item = statement("not_affected", justification="")
        del item["justification"]
        self.assert_invalid(document(item), "justification")

    def test_an_unknown_justification_is_refused(self):
        self.assert_invalid(document(statement("not_affected", justification="trust_me")), "justification")

    def test_affected_needs_an_action_statement(self):
        item = statement("affected")
        del item["action_statement"]
        self.assert_invalid(document(item), "action_statement")

    def test_a_statement_needs_a_product(self):
        self.assert_invalid(document(statement("fixed", products=[])), "product")
        self.assert_invalid(document(statement("fixed", products=[{}])), "product")

    def test_a_statement_needs_a_vulnerability_name(self):
        item = statement("fixed")
        item["vulnerability"] = {}
        self.assert_invalid(document(item), "vulnerability")

    def test_the_document_needs_the_openvex_context_and_fields(self):
        self.assert_invalid(document(**{"@context": "https://example.org/vex"}), "@context")
        for field in ("@id", "author", "timestamp", "version", "statements"):
            with self.subTest(field=field):
                triage = document()
                del triage[field]
                self.assert_invalid(triage, field)

    def test_a_malformed_timestamp_is_refused(self):
        self.assert_invalid(document(statement("fixed", timestamp="yesterday")), "timestamp")

    def test_a_folder_without_reports_is_refused(self):
        with tempfile.TemporaryDirectory() as base:
            fixture = Fixture(base, [], document())
            (fixture.matches / "app.grype.json").unlink()
            with self.assertRaises(check_triage.TriageError):
                fixture.findings()

    def test_a_report_without_matches_list_is_refused(self):
        with tempfile.TemporaryDirectory() as base:
            fixture = Fixture(base, [], document())
            (fixture.matches / "app.grype.json").write_text("{}")
            with self.assertRaises(check_triage.TriageError):
                fixture.findings()


class CommandLine(unittest.TestCase):
    SCRIPT = str(ROOT / "release" / "check_triage.py")

    def run_check(self, matches, triage):
        with tempfile.TemporaryDirectory() as base:
            fixture = Fixture(base, matches, triage)
            return subprocess.run(
                [sys.executable, self.SCRIPT, "--matches", str(fixture.matches),
                 "--triage", str(fixture.triage)],
                capture_output=True, text=True,
            )

    def test_exit_0_when_every_match_is_triaged(self):
        result = self.run_check([grype_match()], document(statement("not_affected")))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("1 matches, 0 findings", result.stdout)

    def test_exit_1_on_a_finding(self):
        result = self.run_check([grype_match()], document())
        self.assertEqual(1, result.returncode)
        self.assertIn("CVE-2026-0001", result.stdout)
        self.assertIn("1 matches, 1 findings", result.stdout)

    def test_exit_2_on_an_invalid_triage_document(self):
        result = self.run_check([], {"statements": []})
        self.assertEqual(2, result.returncode)
        self.assertIn("error:", result.stderr)

    def test_main_returns_the_same_codes(self):
        with tempfile.TemporaryDirectory() as base:
            fixture = Fixture(base, [grype_match()], document())
            with contextlib.redirect_stdout(io.StringIO()):
                code = check_triage.main(
                    ["--matches", str(fixture.matches), "--triage", str(fixture.triage)]
                )
            self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
