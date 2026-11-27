#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that each package of the SPDX documents that ``west spdx`` wrote is complete.

The element check of specification criterion 35. A package is complete when it has

* a name (``PackageName``);
* a version (``PackageVersion``) that is not ``NOASSERTION``;
* a supplier (``PackageSupplier``) that is not ``NOASSERTION``;
* a unique identifier: an ``ExternalRef`` of the type ``purl``, ``cpe23Type`` or ``cpe22Type``;
* a relationship: its SPDX identifier appears in a ``Relationship`` of one of the documents, which
  is how ``west spdx`` ties a package to the image.

Each finding is printed as ``<file>: <package>: <what is missing>``, then one summary line. The
default mode fails (exit 1) on any finding. ``--report`` prints the same and exits 0: the nightly
tier reports, because ``west spdx`` gives a supplier only through a CPE and the table that fills the
missing suppliers and identifiers before a release (specification section 6.3) does not exist yet.
A file that does not parse fails in both modes (exit 2). Files are named by base name only, and
nothing is written or uploaded.
"""

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import parse_spdx  # noqa: E402

IDENTIFIER_TYPES = {"purl", "cpe23Type", "cpe22Type"}
REFERENCE = re.compile(r"(?:DocumentRef-[A-Za-z0-9.\-]+:)?(SPDXRef-[A-Za-z0-9.\-]+)")


def packages_and_relationships(text):
    """Return (packages, referenced identifiers) of one document."""
    packages = []
    referenced = set()
    current = None
    for _number, tag, value in parse_spdx.read_pairs(text):
        if tag == "PackageName":
            current = {"name": value, "id": None, "version": None, "supplier": None,
                       "identifier": False}
            packages.append(current)
        elif tag in parse_spdx.SECTION_START:
            current = None
        elif tag == "Relationship":
            for match in REFERENCE.finditer(value):
                referenced.add(match.group(1))
        elif current is not None:
            if tag == "SPDXID" and current["id"] is None:
                current["id"] = value
            elif tag == "PackageVersion":
                current["version"] = value
            elif tag == "PackageSupplier":
                current["supplier"] = value
            elif tag == "ExternalRef":
                fields = value.split()
                if len(fields) >= 3 and fields[1] in IDENTIFIER_TYPES:
                    current["identifier"] = True
    return packages, referenced


def missing(package, referenced):
    """What the package lacks, as short phrases."""
    gaps = []
    if not package["name"]:
        gaps.append("no name")
    if not package["version"] or package["version"] == "NOASSERTION":
        gaps.append("no version")
    if not package["supplier"] or package["supplier"] == "NOASSERTION":
        gaps.append("no supplier")
    if not package["identifier"]:
        gaps.append("no purl or CPE")
    if package["id"] is None or package["id"] not in referenced:
        gaps.append("no relationship")
    return gaps


def check_dir(directory):
    """Return (package count, findings) for the .spdx files of a folder."""
    files = sorted(pathlib.Path(directory).glob("*.spdx"))
    if not files:
        raise parse_spdx.SpdxError(f"no .spdx file in {pathlib.Path(directory).name}")
    documents = []
    referenced = set()
    for path in files:
        packages, refs = packages_and_relationships(path.read_text(encoding="utf-8"))
        documents.append((path.name, packages))
        referenced |= refs
    findings = []
    count = 0
    for name, packages in documents:
        for package in packages:
            count += 1
            for gap in missing(package, referenced):
                findings.append(f"{name}: {package['name'] or '(unnamed)'}: {gap}")
    return count, findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", required=True, help="folder with the .spdx files")
    parser.add_argument("--report", action="store_true", help="print the findings and exit 0")
    args = parser.parse_args(argv)
    try:
        count, findings = check_dir(args.dir)
    except (parse_spdx.SpdxError, OSError, UnicodeDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding)
    print(f"{count} packages, {len(findings)} findings")
    if findings and not args.report:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
