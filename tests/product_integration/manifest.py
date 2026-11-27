#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Write the commit under test into a copy of the fixture product's manifest.

    manifest.py --revision SHA path/to/west.yml

The file is changed in place: the project crux-controller gets the full commit SHA as its revision,
and nothing else changes. The project must import its manifest (``import: true``), so that Crux
comes at the pin of crux-controller. Exit status 0 on success, 1 for a manifest of another shape,
2 for a usage error; the file is left as it was on failure.
"""

import argparse
import pathlib
import re
import sys

import yaml

PROJECT = "crux-controller"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def rewrite(data, revision):
    """Return a list of problems, empty when the project now has the revision."""
    projects = (data or {}).get("manifest", {}).get("projects") or []
    found = [p for p in projects if isinstance(p, dict) and p.get("name") == PROJECT]
    if len(found) != 1:
        return [f"the manifest lists {len(found)} projects named {PROJECT}, not one"]
    project = found[0]
    if project.get("import") is not True:
        return [f"the project {PROJECT} does not import its manifest (import: true)"]
    project["revision"] = revision
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--revision", required=True, help="the full commit SHA under test")
    parser.add_argument("manifest", type=pathlib.Path)
    args = parser.parse_args(argv)
    if not FULL_SHA.match(args.revision):
        print(f"manifest.py: {args.revision!r} is not a full lowercase commit SHA", file=sys.stderr)
        return 2
    try:
        data = yaml.safe_load(args.manifest.read_text())
    except (OSError, yaml.YAMLError) as error:
        print(f"manifest.py: cannot read {args.manifest}: {error}", file=sys.stderr)
        return 2
    problems = rewrite(data, args.revision)
    if problems:
        for problem in problems:
            print(f"manifest.py: {problem}", file=sys.stderr)
        return 1
    args.manifest.write_text(yaml.safe_dump(data, sort_keys=False))
    print(f"{PROJECT} at {args.revision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
