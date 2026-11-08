#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Parse the tag-value SPDX 2.3 files that ``west spdx`` writes.

The release dry run uses this to answer one question: does the ``west spdx`` output parse? A
file fails when

* a line is neither blank, a ``#`` comment, nor ``Tag: value`` (with ``<text>...</text>`` values
  allowed to span lines), or its tag is not an SPDX 2.3 tag-value tag;
* a ``<text>`` value is never closed;
* the document header lacks one of ``SPDXVersion`` (must be ``SPDX-2.3``), ``DataLicense``
  (``CC0-1.0``), ``SPDXID`` (``SPDXRef-DOCUMENT``), ``DocumentName``, ``DocumentNamespace``,
  ``Creator`` or ``Created`` (a UTC timestamp), or has an empty value for one of them;
* a package or file has no ``SPDXID``, or an ``SPDXID`` occurs twice.

This is a syntax and header check. It does not check licence expressions, checksums or
relationships, and it is not a general SPDX validator. Nothing is uploaded and no file is
modified. Output names files by base name only.
"""

import argparse
import pathlib
import re
import sys

VERSION = "SPDX-2.3"
HEADER_REQUIRED = (
    "SPDXVersion", "DataLicense", "SPDXID", "DocumentName", "DocumentNamespace", "Creator", "Created",
)
HEADER_TAGS = set(HEADER_REQUIRED) | {
    "ExternalDocumentRef", "LicenseListVersion", "CreatorComment", "DocumentComment",
}
PACKAGE_TAGS = {
    "PackageName", "PackageVersion", "PackageFileName", "PackageSupplier", "PackageOriginator",
    "PackageDownloadLocation", "FilesAnalyzed", "PackageVerificationCode", "PackageChecksum",
    "PackageHomePage", "PackageSourceInfo", "PackageLicenseConcluded",
    "PackageLicenseInfoFromFiles", "PackageLicenseDeclared", "PackageLicenseComments",
    "PackageCopyrightText", "PackageSummary", "PackageDescription", "PackageComment",
    "ExternalRef", "ExternalRefComment", "PrimaryPackagePurpose", "BuiltDate", "ReleaseDate",
    "ValidUntilDate",
}
FILE_TAGS = {
    "FileName", "FileType", "FileChecksum", "LicenseConcluded", "LicenseInfoInFile",
    "LicenseComments", "FileCopyrightText", "FileComment", "FileNotice", "FileContributor",
    "FileAttributionText",
}
SNIPPET_TAGS = {
    "SnippetSPDXID", "SnippetFromFileSPDXID", "SnippetByteRange", "SnippetLineRange",
    "SnippetLicenseConcluded", "LicenseInfoInSnippet", "SnippetLicenseComments",
    "SnippetCopyrightText", "SnippetComment", "SnippetName", "SnippetAttributionText",
}
OTHER_TAGS = {
    "LicenseID", "ExtractedText", "LicenseName", "LicenseCrossReference", "LicenseComment",
    "Relationship", "RelationshipComment", "Annotator", "AnnotationDate", "AnnotationType",
    "SPDXREF", "AnnotationComment", "PackageAttributionText",
    # Deprecated in SPDX 2.3 but still part of the tag-value format.
    "FileDependency", "ArtifactOfProjectName", "ArtifactOfProjectHomePage", "ArtifactOfProjectURI",
    "Reviewer", "ReviewDate", "ReviewComment",
}
KNOWN_TAGS = HEADER_TAGS | PACKAGE_TAGS | FILE_TAGS | SNIPPET_TAGS | OTHER_TAGS
# Tags that open a new section. SPDXID belongs to the section it follows.
SECTION_START = {"PackageName": "package", "FileName": "file", "SnippetSPDXID": "snippet",
                 "LicenseID": "license"}
LINE = re.compile(r"^([A-Za-z][A-Za-z0-9]*):[ \t]*(.*)$")
CREATED = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CREATOR = re.compile(r"^(Tool|Organization|Person):\s*\S")


class SpdxError(ValueError):
    """The file is not a tag-value SPDX 2.3 document that this check accepts."""


class Document:
    def __init__(self):
        self.header = {}
        self.creators = []
        self.packages = []
        self.files = []

    @property
    def package_count(self):
        return len(self.packages)

    @property
    def file_count(self):
        return len(self.files)

    @property
    def package_names(self):
        return [package["PackageName"] for package in self.packages]


def read_pairs(text):
    """Return ``(line_number, tag, value)`` for each tag-value pair."""
    pairs = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0
    while index < len(lines):
        number = index + 1
        line = lines[index]
        index += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = LINE.match(line)
        if not match:
            raise SpdxError(f"line {number}: not a Tag: value line")
        tag, value = match.groups()
        if tag not in KNOWN_TAGS:
            raise SpdxError(f"line {number}: unknown tag {tag}")
        if value.startswith("<text>"):
            body = value[len("<text>"):]
            parts = []
            while "</text>" not in body:
                parts.append(body)
                if index >= len(lines):
                    raise SpdxError(f"line {number}: <text> value of {tag} is never closed")
                body = lines[index]
                index += 1
            parts.append(body[: body.index("</text>")])
            value = "\n".join(parts)
        pairs.append((number, tag, value.strip()))
    return pairs


def parse(text):
    """Parse one document. Raise SpdxError with the reason when it is not acceptable."""
    document = Document()
    section = "header"
    current = document.header
    seen_ids = set()

    def check_id(number, element):
        if "SPDXID" not in element:
            raise SpdxError(f"line {number}: {section} has no SPDXID")
        if element["SPDXID"] in seen_ids:
            raise SpdxError(f"duplicate SPDXID {element['SPDXID']}")
        seen_ids.add(element["SPDXID"])

    pending_number = 0
    for number, tag, value in read_pairs(text):
        if tag in SECTION_START:
            if section != "header":
                if section in ("package", "file"):
                    check_id(pending_number, current)
            else:
                check_header(document)
            section = SECTION_START[tag]
            pending_number = number
            current = {}
            if section == "package":
                document.packages.append(current)
            elif section == "file":
                document.files.append(current)
            current[tag] = value
            continue
        if section == "other" and tag in PACKAGE_TAGS | FILE_TAGS | SNIPPET_TAGS:
            raise SpdxError(f"line {number}: {tag} appears before any section start")
        if section == "header":
            if tag not in HEADER_TAGS:
                if tag in PACKAGE_TAGS | FILE_TAGS | SNIPPET_TAGS:
                    raise SpdxError(f"line {number}: {tag} appears before any section start")
                # Relationship and similar tags may follow the header directly.
                section = "other"
                current = {}
                check_header(document)
                continue
            if tag == "Creator":
                document.creators.append(value)
            current.setdefault(tag, value)
        else:
            current.setdefault(tag, value)
    if section == "header":
        check_header(document)
    elif section in ("package", "file"):
        check_id(pending_number, current)
    return document


def check_header(document):
    header = document.header
    for tag in HEADER_REQUIRED:
        if not header.get(tag) and not (tag == "Creator" and document.creators):
            raise SpdxError(f"document header lacks {tag} or has it empty")
    if header["SPDXVersion"] != VERSION:
        raise SpdxError(f"SPDXVersion is {header['SPDXVersion']}, expected {VERSION}")
    if header["DataLicense"] != "CC0-1.0":
        raise SpdxError(f"DataLicense is {header['DataLicense']}, expected CC0-1.0")
    if header["SPDXID"] != "SPDXRef-DOCUMENT":
        raise SpdxError(f"SPDXID of the document is {header['SPDXID']}, expected SPDXRef-DOCUMENT")
    if not CREATED.match(header["Created"]):
        raise SpdxError(f"Created is not a UTC timestamp: {header['Created']}")
    for creator in document.creators:
        if not CREATOR.match(creator):
            raise SpdxError(f"Creator must start with Tool:, Organization: or Person: ({creator})")


def parse_file(path):
    return parse(pathlib.Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", help=".spdx files")
    parser.add_argument("--dir", help="directory whose *.spdx files are parsed")
    args = parser.parse_args(argv)
    paths = [pathlib.Path(name) for name in args.files]
    if args.dir:
        directory = pathlib.Path(args.dir)
        if not directory.is_dir():
            print(f"{directory.name}: not a directory", file=sys.stderr)
            return 2
        paths += sorted(directory.glob("*.spdx"))
    if not paths:
        print("no .spdx files to parse", file=sys.stderr)
        return 2
    failed = 0
    for path in paths:
        try:
            document = parse_file(path)
        except OSError as error:
            # The message of an OSError carries the full path. Name the file by base name only.
            print(f"{path.name}: {error.strerror or type(error).__name__}", file=sys.stderr)
            failed += 1
            continue
        except (SpdxError, UnicodeDecodeError) as error:
            print(f"{path.name}: {error}", file=sys.stderr)
            failed += 1
            continue
        print(f"{path.name}: {document.header['SPDXVersion']}, "
              f"{document.package_count} packages, {document.file_count} files")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
