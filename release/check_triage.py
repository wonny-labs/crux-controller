#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that each known vulnerability of the release SBOM has a triage record that allows a release.

The release check of specification criterion 36. It reads the JSON reports that
``scripts/ci/match-vulnerabilities.sh --json`` wrote (Grype's JSON output, one file per SPDX
document) and the triage records in an OpenVEX document (``release/triage.openvex.json``).

A record covers a match when its vulnerability ``name`` or one of its ``aliases`` equals the id
of the match or one of Grype's related ids, and one of its products, or a subcomponent of one,
has an ``@id`` or an identifier (``purl``, ``cpe23``, ``cpe22``) equal to the purl or a CPE of the
matched package. The comparison is exact. When several records cover a match, the one with the
latest timestamp wins (a statement without one takes the document timestamp). Two latest records
with different statuses are a conflict.

The check fails (exit 1) on a match

* with no record;
* whose record has the status ``affected``: in VEX, ``affected`` means this release carries the
  vulnerability without a fix (a fix in this release is the status ``fixed``);
* whose record has the status ``under_investigation``;
* whose latest records conflict.

The statuses ``not_affected`` and ``fixed`` pass. A triage document that is not valid OpenVEX for
the fields used here, or a folder without a report, fails with exit 2. Each finding is printed as
``<vulnerability> in <package> <version>: <reason>``, then one summary line. Nothing is written or
uploaded. The nightly run does not use this check: it only reports the matches.
"""

import argparse
import datetime
import json
import pathlib
import sys

CONTEXT_PREFIX = "https://openvex.dev/ns/"
STATUSES = {"not_affected", "affected", "fixed", "under_investigation"}
JUSTIFICATIONS = {
    "component_not_present",
    "vulnerable_code_not_present",
    "vulnerable_code_not_in_execute_path",
    "vulnerable_code_cannot_be_controlled_by_adversary",
    "inline_mitigations_already_exist",
}
IDENTIFIER_TYPES = ("purl", "cpe23", "cpe22")
FAILING = {
    "affected": "status affected: the release carries it with no fix",
    "under_investigation": "status under investigation",
}


class TriageError(Exception):
    """The triage document or the match reports cannot be used."""


def parse_time(value, where):
    if not isinstance(value, str):
        raise TriageError(f"{where}: timestamp must be an RFC 3339 string")
    try:
        moment = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TriageError(f"{where}: timestamp {value!r} is not RFC 3339") from error
    if moment.tzinfo is None:
        raise TriageError(f"{where}: timestamp {value!r} has no time zone")
    return moment


def product_keys(product, where):
    """The identifiers of a product and of its subcomponents."""
    if not isinstance(product, dict):
        raise TriageError(f"{where}: a product must be an object")
    keys = set()
    if isinstance(product.get("@id"), str) and product["@id"]:
        keys.add(product["@id"])
    identifiers = product.get("identifiers", {})
    if isinstance(identifiers, dict):
        keys.update(
            value for kind, value in identifiers.items()
            if kind in IDENTIFIER_TYPES and isinstance(value, str) and value
        )
    if not keys:
        raise TriageError(f"{where}: a product needs an @id or a purl or CPE identifier")
    for number, sub in enumerate(product.get("subcomponents", [])):
        keys |= product_keys(sub, f"{where}.subcomponents[{number}]")
    return keys


def load_triage(path):
    """Return the statements of an OpenVEX document as dictionaries ready for matching."""
    try:
        doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise TriageError(f"{pathlib.Path(path).name}: {error}") from error
    if not isinstance(doc, dict):
        raise TriageError("the triage document must be a JSON object")
    for field in ("@context", "@id", "author", "timestamp", "version", "statements"):
        if field not in doc:
            raise TriageError(f"the triage document needs {field}")
    if not isinstance(doc["@context"], str) or not doc["@context"].startswith(CONTEXT_PREFIX):
        raise TriageError(f"@context must start with {CONTEXT_PREFIX}")
    if isinstance(doc["version"], bool) or not isinstance(doc["version"], int) or doc["version"] < 1:
        raise TriageError("version must be a positive integer")
    if not isinstance(doc["statements"], list):
        raise TriageError("statements must be a list")
    default_time = parse_time(doc["timestamp"], "document")

    records = []
    for number, item in enumerate(doc["statements"]):
        where = f"statements[{number}]"
        if not isinstance(item, dict):
            raise TriageError(f"{where}: must be an object")
        vulnerability = item.get("vulnerability")
        if not isinstance(vulnerability, dict) or not vulnerability.get("name"):
            raise TriageError(f"{where}: vulnerability needs a name")
        names = {vulnerability["name"], *vulnerability.get("aliases", [])}
        status = item.get("status")
        if status not in STATUSES:
            raise TriageError(f"{where}: status {status!r} is not one of {sorted(STATUSES)}")
        if status == "not_affected":
            justification = item.get("justification")
            if justification is not None and justification not in JUSTIFICATIONS:
                raise TriageError(f"{where}: justification {justification!r} is not an OpenVEX label")
            if not justification and not item.get("impact_statement"):
                raise TriageError(f"{where}: not_affected needs a justification or an impact_statement")
        if status == "affected" and not item.get("action_statement"):
            raise TriageError(f"{where}: affected needs an action_statement")
        products = item.get("products")
        if not isinstance(products, list) or not products:
            raise TriageError(f"{where}: a statement must name a product")
        keys = set()
        for index, product in enumerate(products):
            keys |= product_keys(product, f"{where}.products[{index}]")
        moment = parse_time(item["timestamp"], where) if "timestamp" in item else default_time
        records.append({"names": names, "keys": keys, "status": status, "time": moment})
    return records


def load_matches(directory):
    """Return the distinct matches of the Grype JSON reports of a folder."""
    files = sorted(pathlib.Path(directory).glob("*.json"))
    if not files:
        raise TriageError(f"no .json report in {pathlib.Path(directory).name}")
    matches = {}
    for path in files:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise TriageError(f"{path.name}: {error}") from error
        if not isinstance(report, dict) or not isinstance(report.get("matches"), list):
            raise TriageError(f"{path.name}: no matches list, so it is not a Grype JSON report")
        for match in report["matches"]:
            try:
                vuln = match["vulnerability"]["id"]
                artifact = match["artifact"]
            except (KeyError, TypeError) as error:
                raise TriageError(f"{path.name}: a match lacks {error}") from error
            related = {item.get("id") for item in match.get("relatedVulnerabilities", [])}
            keys = {artifact.get("purl"), *artifact.get("cpes", [])} - {None, ""}
            key = (vuln, artifact.get("name", ""), artifact.get("version", ""), artifact.get("purl", ""))
            entry = matches.setdefault(key, {"ids": {vuln}, "keys": set()})
            entry["ids"] |= related - {None}
            entry["keys"] |= keys
    return matches


def verdict(match, records):
    """The reason a match stops the release, or None when it may be released."""
    covering = [
        record for record in records
        if record["names"] & match["ids"] and record["keys"] & match["keys"]
    ]
    if not covering:
        return "no triage record with a VEX status"
    latest = max(record["time"] for record in covering)
    statuses = {record["status"] for record in covering if record["time"] == latest}
    if len(statuses) > 1:
        return f"conflicting latest triage records ({', '.join(sorted(statuses))})"
    return FAILING.get(statuses.pop())


def check(matches_dir, triage_path):
    """Return (number of distinct matches, findings)."""
    records = load_triage(triage_path)
    matches = load_matches(matches_dir)
    findings = []
    for (vuln, name, version, _purl), match in sorted(matches.items()):
        reason = verdict(match, records)
        if reason:
            findings.append(f"{vuln} in {name} {version}: {reason}")
    return len(matches), findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--matches", required=True, help="folder with the Grype JSON reports")
    parser.add_argument("--triage", required=True, help="the OpenVEX triage document")
    args = parser.parse_args(argv)
    try:
        count, findings = check(args.matches, args.triage)
    except TriageError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding)
    print(f"{count} matches, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
