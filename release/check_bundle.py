#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check a release bundle before anything is published.

The check stops publication when the bundle

* has no valid ``release-manifest.json`` (schema in release-manifest.schema.json);
* holds an image, ``.elf``, ``.map`` or similar file, or any file that starts like an ELF;
* lists hashes that do not match its items, or holds an item the manifest does not list;
* has an item with an absolute path of a build machine or one of the private strings.

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
UNIX_ABSOLUTE = re.compile(
    r"(?<![A-Za-z0-9_.:/~-])/(?:Users|home|private|tmp|var|opt|usr|etc|root|mnt|workspaces|__w)/\S+"
)
WINDOWS_ABSOLUTE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\\S")


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

    for path in items:
        name = path.relative_to(bundle).as_posix()
        data = path.read_bytes()
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or data.startswith(ELF_MAGIC):
            problems.append(f"{name}: an image, ELF or map file must not be in a bundle")
            continue
        text = data.decode("utf-8", errors="replace")
        for match in UNIX_ABSOLUTE.finditer(text):
            problems.append(f"{name}: absolute path {match.group(0)!r}")
        for match in WINDOWS_ABSOLUTE.finditer(text):
            problems.append(f"{name}: absolute path {match.group(0)!r}")
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
    lines = pathlib.Path(path).read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("bundle")
    parser.add_argument("--private-strings", help="file with one private string per line")
    args = parser.parse_args(argv)
    private = read_private_strings(args.private_strings) if args.private_strings else []
    problems = check(args.bundle, private)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("bundle check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
