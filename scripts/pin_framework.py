#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pin the controller framework in the west manifest of a copy of the application template.

    pin_framework.py --framework CLONE path/to/product/west.yml

The revision of the project crux-controller becomes the full commit SHA that the Git clone CLONE
has checked out. The first pin also writes that SHA as ``template-revision`` in ``self: userdata``,
the record of the framework commit that the copy was made from; a later pin moves the revision and
keeps the record. The file is changed line by line, so its comments stay. The project must import
its manifest (``import: true``), so that Crux comes at the commit that the framework verified.

A west manifest names a branch, a tag or a SHA as a revision, and only a SHA gives the same
workspace every time (west manifest documentation, "Revisions"). Exit status 0 on success, 1 for a
manifest of another shape, 2 for a usage error; the file is left as it was on failure.
"""

import argparse
import pathlib
import re
import subprocess
import sys

import yaml

PROJECT = "crux-controller"
RECORD = "template-revision"
UNSET = "none"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ITEM = re.compile(r"^(\s*)- name:\s*(\S+)\s*$")
KEY = re.compile(r"^(\s*)([A-Za-z0-9_-]+):(.*)$")


class ShapeError(Exception):
    pass


def head_of(clone):
    try:
        sha = subprocess.run(["git", "-C", str(clone), "rev-parse", "--verify", "HEAD^{commit}"],
                             check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return sha if FULL_SHA.match(sha) else None


def project_lines(lines):
    """The indexes of the lines of the project item named PROJECT."""
    found = []
    for index, line in enumerate(lines):
        item = ITEM.match(line)
        if item and item.group(2) == PROJECT:
            indent = len(item.group(1))
            end = index + 1
            while end < len(lines):
                text = lines[end]
                if text.strip() and not text.lstrip().startswith("#"):
                    if len(text) - len(text.lstrip()) <= indent:
                        break
                end += 1
            found.append(range(index, end))
    if len(found) != 1:
        raise ShapeError(f"the manifest lists {len(found)} projects named {PROJECT}, not one")
    return found[0]


def replace_value(lines, indexes, key, value):
    hits = [i for i in indexes if (m := KEY.match(lines[i])) and m.group(2) == key]
    if len(hits) != 1:
        raise ShapeError(f"{len(hits)} lines {key}: where one is expected")
    index = hits[0]
    indent = KEY.match(lines[index]).group(1)
    newline = "\n" if lines[index].endswith("\n") else ""
    old = KEY.match(lines[index]).group(3).split("#", 1)[0].strip()
    lines[index] = f"{indent}{key}: {value}{newline}"
    return old


def pin(text, sha):
    """Return the pinned text, or raise ShapeError."""
    data = yaml.safe_load(text) or {}
    projects = data.get("manifest", {}).get("projects") or []
    named = [p for p in projects if isinstance(p, dict) and p.get("name") == PROJECT]
    if len(named) != 1:
        raise ShapeError(f"the manifest lists {len(named)} projects named {PROJECT}, not one")
    if named[0].get("import") is not True:
        raise ShapeError(f"the project {PROJECT} does not import its manifest (import: true)")
    lines = text.splitlines(keepends=True)
    replace_value(lines, project_lines(lines), "revision", sha)
    record = [i for i, line in enumerate(lines) if (m := KEY.match(line)) and m.group(2) == RECORD]
    if len(record) != 1:
        raise ShapeError(f"the manifest has {len(record)} lines {RECORD}: under self: userdata, not one")
    current = KEY.match(lines[record[0]]).group(3).split("#", 1)[0].strip()
    if current == UNSET:
        replace_value(lines, record, RECORD, sha)
    pinned = "".join(lines)
    check = yaml.safe_load(pinned)["manifest"]
    project = next(p for p in check["projects"] if p.get("name") == PROJECT)
    recorded = (check.get("self") or {}).get("userdata", {}).get(RECORD)
    if project.get("revision") != sha or not FULL_SHA.match(str(recorded)):
        raise ShapeError(f"the pinned manifest does not read back with {sha} and a {RECORD} under self: userdata")
    return pinned, recorded


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--framework", required=True, type=pathlib.Path,
                        help="the clone of crux-controller at the commit to pin")
    parser.add_argument("manifest", type=pathlib.Path)
    args = parser.parse_args(argv)
    sha = head_of(args.framework)
    if sha is None:
        print(f"pin_framework.py: {args.framework} is not a Git clone with a commit checked out", file=sys.stderr)
        return 2
    try:
        text = args.manifest.read_text()
    except OSError as error:
        print(f"pin_framework.py: cannot read {args.manifest}: {error}", file=sys.stderr)
        return 2
    try:
        pinned, recorded = pin(text, sha)
    except (ShapeError, yaml.YAMLError, AttributeError, TypeError) as error:
        print(f"pin_framework.py: {args.manifest}: {error}", file=sys.stderr)
        return 1
    args.manifest.write_text(pinned)
    print(f"{PROJECT} at {sha}; the copy was made from {recorded}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
