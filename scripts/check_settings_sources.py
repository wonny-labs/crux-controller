#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Criterion 32 (gap C5): the Settings File sources that a build compiles are outside Crux's tests/.

Reads the compile database of a build that selects Crux's Settings File provider of Configuration,
lists the sources it compiles for Zephyr's Settings File backend (settings_file.c, settings_line.c and
settings_store.c) and fails when one is missing or lies under the tests/ folder of the Crux checkout.

    check_settings_sources.py --compile-commands BUILD/compile_commands.json --crux-root CRUX
"""

import argparse
import json
import pathlib
import sys

NAMES = ("settings_file.c", "settings_line.c", "settings_store.c")


def sources(database):
    """The absolute path of every source in a compile database."""
    for entry in json.loads(pathlib.Path(database).read_text()):
        path = pathlib.PurePosixPath(entry["file"])
        if not path.is_absolute():
            path = pathlib.PurePosixPath(entry.get("directory", "/")) / path
        yield pathlib.PurePosixPath(*_normalised(path.parts))


def _normalised(parts):
    out = []
    for part in parts:
        if part == "..":
            if len(out) > 1:
                out.pop()
        elif part != ".":
            out.append(part)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--compile-commands", required=True)
    parser.add_argument("--crux-root", required=True)
    args = parser.parse_args(argv)
    tests = pathlib.PurePosixPath(*_normalised(pathlib.PurePosixPath(args.crux_root).parts)) / "tests"
    found = {name: [] for name in NAMES}
    for path in sources(args.compile_commands):
        if path.name in found:
            found[path.name].append(path)
    failures = []
    for name in NAMES:
        if not found[name]:
            failures.append(f"{name}: not compiled; is the Settings File provider selected?")
        for path in found[name]:
            print(f"{name}: {path}")
            if tests in path.parents:
                failures.append(f"{name}: compiled from Crux's tests/ path {path} (gap C5)")
    for failure in failures:
        print(f"error: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
