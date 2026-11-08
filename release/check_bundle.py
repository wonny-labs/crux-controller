#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check a release bundle before anything is published.

The check stops publication when the bundle

* has no valid ``release-manifest.json`` (schema in release-manifest.schema.json);
* holds an image, ``.elf``, ``.map`` or similar file, or any file that starts like an ELF;
* lists hashes that do not match its items, or holds an item the manifest does not list;
* has an item that is not plain UTF-8 text, that holds the image's own bytes, an Intel HEX or
  S-record dump, or an archive (every bundle item is text, so anything else is refused);
* has an item with an absolute path of a build machine or one of the private strings.

The path scan is a regular expression, not a proof: it looks for system roots at the start of
a path-like word (after URLs are removed), for a path after a compiler flag such as ``-I``, for
Windows drive and UNC paths, and for ``file://`` URIs. A form it does not know passes.

The private strings come from a file outside the repository, passed by path, one per line.
Nothing in this repository names them.
"""

import argparse
import hashlib
import json
import pathlib
import re
import sys

MANIFEST = "release-manifest.json"
SCHEMA = pathlib.Path(__file__).resolve().parent / "release-manifest.schema.json"
FORBIDDEN_SUFFIXES = {".elf", ".map", ".bin", ".hex", ".srec", ".s19", ".uf2", ".img"}
ELF_MAGIC = b"\x7fELF"
ARCHIVE_MAGICS = (b"PK\x03\x04", b"\x1f\x8b", b"BZh", b"\xfd7zXZ\x00", b"7z\xbc\xaf\x27\x1c")
# Web and git URLs are removed before the path scan: their slashes are not file paths.
REMOTE_URL = re.compile(r"\b(?:https?|git|ssh)://\S+", re.IGNORECASE)
SYSTEM_ROOTS = (
    "Users|home|private|tmp|var|opt|usr|etc|root|mnt|srv|nix|Volumes|github|workspaces|__w|build|data"
)
# A root at the start of a path-like word, or right after a compiler flag such as -I or -L.
UNIX_ABSOLUTE = re.compile(
    rf"(?:(?<![A-Za-z0-9_.~/-])|(?<=-[A-Za-z]))/(?:{SYSTEM_ROOTS})/\S+"
)
WINDOWS_ABSOLUTE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]\S")
UNC_PATH = re.compile(r"\\\\[^\\\s]+\\[^\\\s]")
FILE_URI = re.compile(r"file://\S*", re.IGNORECASE)
HEX_DUMP = re.compile(r"^(?::[0-9A-Fa-f]{10,}|S[0-9][0-9A-Fa-f]{6,})\s*$", re.MULTILINE)


def validate(value, schema, where, problems):
    """Apply the subset of JSON Schema keywords that the manifest schema uses."""
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            problems.append(f"{where}: must be an object")
            return
        for name in schema.get("required", []):
            if name not in value:
                problems.append(f"{where}: {name} is required")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for name, item in value.items():
            if name in properties:
                validate(item, properties[name], f"{where}.{name}", problems)
            elif extra is False:
                problems.append(f"{where}: {name} is not allowed")
            elif isinstance(extra, dict):
                validate(item, extra, f"{where}.{name}", problems)
    elif kind == "string":
        if not isinstance(value, str):
            problems.append(f"{where}: must be a string")
        elif "pattern" in schema and not re.search(schema["pattern"], value):
            problems.append(f"{where}: does not match {schema['pattern']}")
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{where}: must be an integer")
        elif "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{where}: must be at least {schema['minimum']}")


def path_matches(text):
    """The absolute paths found in a text, by the forms that the module docstring lists."""
    found = set(FILE_URI.findall(text))
    stripped = FILE_URI.sub(" ", REMOTE_URL.sub(" ", text))
    for pattern in (UNIX_ABSOLUTE, WINDOWS_ABSOLUTE, UNC_PATH):
        found.update(match.group(0) for match in pattern.finditer(stripped))
    return found


def check(bundle_dir, private_strings=()):
    """Return one message per problem, or an empty list when the bundle may be published."""
    bundle = pathlib.Path(bundle_dir)
    problems = []
    items = sorted(path for path in bundle.rglob("*") if path.is_file())

    manifest_path = bundle / MANIFEST
    manifest = None
    if not manifest_path.is_file():
        problems.append(f"{MANIFEST}: missing")
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
        except ValueError as error:
            problems.append(f"{MANIFEST}: not valid JSON ({error})")
    if manifest is not None:
        validate(manifest, json.loads(SCHEMA.read_text()), MANIFEST, problems)

    image_sha256 = manifest.get("zephyr_bin_sha256") if isinstance(manifest, dict) else None
    for path in items:
        name = path.relative_to(bundle).as_posix()
        data = path.read_bytes()
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or data.startswith(ELF_MAGIC):
            problems.append(f"{name}: an image, ELF or map file must not be in a bundle")
            continue
        if image_sha256 and hashlib.sha256(data).hexdigest() == image_sha256:
            problems.append(f"{name}: holds the bytes of the image (zephyr_bin_sha256)")
            continue
        if data.startswith(ARCHIVE_MAGICS):
            problems.append(f"{name}: an archive must not be in a bundle")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"{name}: not plain UTF-8 text, so it may be an image or other binary")
            continue
        if HEX_DUMP.search(text):
            problems.append(f"{name}: looks like an Intel HEX or S-record image dump")
            continue
        for found in sorted(path_matches(text)):
            problems.append(f"{name}: absolute path {found!r}")
        lowered = text.lower()
        for private in private_strings:
            if private.lower() in lowered:
                problems.append(f"{name}: holds a private string from the list")

    if isinstance(manifest, dict) and isinstance(manifest.get("bundle_hashes"), dict):
        listed = manifest["bundle_hashes"]
        names = {path.relative_to(bundle).as_posix() for path in items} - {MANIFEST}
        for name in sorted(names - set(listed)):
            problems.append(f"{name}: not listed in bundle_hashes")
        for name in sorted(set(listed) - names):
            problems.append(f"{name}: listed in bundle_hashes but not in the bundle")
        for name in sorted(names & set(listed)):
            actual = hashlib.sha256((bundle / name).read_bytes()).hexdigest()
            if actual != listed[name]:
                problems.append(f"{name}: hash differs from bundle_hashes")
    return problems


def read_private_strings(path):
    stripped = (line.strip() for line in pathlib.Path(path).read_text().splitlines())
    return [line for line in stripped if line and not line.startswith("#")]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("bundle")
    parser.add_argument("--private-strings", help="file with one private string per line")
    args = parser.parse_args(argv)
    if args.private_strings:
        private = read_private_strings(args.private_strings)
    else:
        private = []
        print(
            "warning: no private-string list given, so private strings were not checked",
            file=sys.stderr,
        )
    problems = check(args.bundle, private)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("bundle check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
