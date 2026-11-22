#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the Crux product include check from a local Crux checkout, with the hashes that CI pins.

The Boundary check job of .github/workflows/ci.yml downloads two files of Crux from a pinned
commit, checks their SHA-256 and runs them on this repository:

    templates/product/check_domain_includes.py   run as: python3 <file> --product .
    templates/product/style/check-includes.sh    run as: bash <file>   (the style kit wrapper)

This script does the same without a download. It takes both files from a Crux checkout, checks
each against its pinned SHA-256 and runs them in that order from the root of this repository. A
file that is missing or has another hash stops the run before anything is executed.

The pins have one source. When .github/workflows/ci.yml exists, they are read from the env of
those two steps (CHECK_COMMIT, CHECK_SHA256, KIT_COMMIT, CHECKER_SHA256, WRAPPER_SHA256). In a
checkout without .github, they are read from scripts/include-check-pins.json, which a test keeps
equal to ci.yml while ci.yml exists.

The Crux checkout is --crux-root, or else the folder crux, then crux-pilot, beside this
repository (the west workspace layout). The checkout's own revision is not checked: a revision
other than the pinned commit passes when both files are the same.

Usage: python3 scripts/check_include_domains.py [--repo DIR] [--crux-root DIR]
Exit status: 0 the check passed, 1 or the checker's status when it reports violations,
2 the check could not run (pins unreadable, Crux checkout or file missing, hash differs).
"""

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

CHECKER = "templates/product/check_domain_includes.py"
WRAPPER = "templates/product/style/check-includes.sh"
WORKFLOW = pathlib.Path(".github") / "workflows" / "ci.yml"
DATA_FILE = pathlib.Path("scripts") / "include-check-pins.json"
CRUX_FOLDERS = ("crux", "crux-pilot")
WORKFLOW_KEYS = ("CHECK_COMMIT", "CHECK_SHA256", "KIT_COMMIT", "CHECKER_SHA256", "WRAPPER_SHA256")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class CheckError(Exception):
    """The check could not run. The message says why."""


def read_workflow_pins(path):
    """Read the pins of the two include check steps from ci.yml, without a YAML library.

    Each key must appear exactly once as `KEY: value`. The two checker hashes and the two commits
    must be equal, because both steps run the same checker from the same commit.
    """
    text = pathlib.Path(path).read_text()
    values = {}
    for key in WORKFLOW_KEYS:
        found = re.findall(rf"^\s*{key}:\s*([0-9a-f]+)\s*$", text, re.MULTILINE)
        if len(found) != 1:
            raise CheckError(f"{path}: expected {key} exactly once, found {len(found)}")
        values[key] = found[0]
    if values["CHECK_SHA256"] != values["CHECKER_SHA256"]:
        raise CheckError(f"{path}: CHECK_SHA256 and CHECKER_SHA256 differ; both steps must pin "
                         "the same checker")
    if values["CHECK_COMMIT"] != values["KIT_COMMIT"]:
        raise CheckError(f"{path}: CHECK_COMMIT and KIT_COMMIT differ")
    return validate(
        {"commit": values["CHECK_COMMIT"],
         "files": {CHECKER: values["CHECK_SHA256"], WRAPPER: values["WRAPPER_SHA256"]}},
        path,
    )


def read_data_pins(path):
    """Read the pins from the data file that stands in for ci.yml in a checkout without it."""
    try:
        data = json.loads(pathlib.Path(path).read_text())
    except FileNotFoundError:
        raise CheckError(f"{path} not found, and there is no {WORKFLOW} to read the pins from")
    except (OSError, ValueError) as error:
        raise CheckError(f"{path}: cannot read the pins: {error}")
    return validate(data, path)


def validate(pins, source):
    if not isinstance(pins, dict) or set(pins) != {"commit", "files"}:
        raise CheckError(f"{source}: the pins need exactly the keys commit and files")
    if not isinstance(pins["commit"], str) or not COMMIT.match(pins["commit"]):
        raise CheckError(f"{source}: the commit is not a 40-digit hash")
    files = pins["files"]
    if not isinstance(files, dict) or set(files) != {CHECKER, WRAPPER}:
        raise CheckError(f"{source}: the files must be exactly {CHECKER} and {WRAPPER}")
    for name, digest in files.items():
        if not isinstance(digest, str) or not SHA256.match(digest):
            raise CheckError(f"{source}: the SHA-256 of {name} is not 64 hexadecimal digits")
    pins["source"] = str(source)
    return pins


def load_pins(repo):
    workflow = repo / WORKFLOW
    if workflow.is_file():
        return read_workflow_pins(workflow)
    return read_data_pins(repo / DATA_FILE)


def find_crux_root(repo, given):
    if given is not None:
        root = pathlib.Path(given)
        if not root.is_dir():
            raise CheckError(f"the Crux checkout {root} does not exist")
        return root.resolve()
    for name in CRUX_FOLDERS:
        candidate = repo.parent / name
        if candidate.is_dir():
            return candidate.resolve()
    names = " or ".join(str(repo.parent / name) for name in CRUX_FOLDERS)
    raise CheckError(f"no Crux checkout at {names}; pass its folder with --crux-root")


def verify(crux_root, pins):
    """Return the paths of the checker and the wrapper after their hashes matched the pins."""
    paths = {}
    for name, expected in pins["files"].items():
        path = crux_root / name
        if not path.is_file():
            raise CheckError(f"{name} not found in the Crux checkout {crux_root}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise CheckError(
                f"SHA-256 of {path} is {actual}, but {pins['source']} pins {expected} "
                f"(taken from Crux commit {pins['commit']}). Update the Crux checkout, or "
                "repin in ci.yml and the data file together."
            )
        paths[name] = path
    return paths[CHECKER], paths[WRAPPER]


def run(repo, checker, wrapper):
    """Run the checker, then the wrapper, from the repository root, as the workflow does."""
    environment = dict(os.environ, PYTHON=sys.executable)
    commands = (
        [sys.executable, str(checker), "--product", "."],
        ["bash", str(wrapper)],
    )
    for command in commands:
        print("+ " + " ".join(command), flush=True)
        try:
            status = subprocess.run(command, cwd=repo, env=environment).returncode
        except OSError as error:
            raise CheckError(f"cannot run {command[0]}: {error}")
        if status != 0:
            return status
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_repo = pathlib.Path(__file__).resolve().parents[1]
    parser.add_argument("--repo", default=default_repo, type=pathlib.Path,
                        help="root of this repository (default: the one holding this script)")
    parser.add_argument("--crux-root", default=None,
                        help="Crux checkout (default: crux, then crux-pilot, beside the repository)")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    try:
        pins = load_pins(repo)
        crux_root = find_crux_root(repo, args.crux_root)
        print(f"check_include_domains: pins from {pins['source']}, Crux checkout {crux_root}",
              flush=True)
        checker, wrapper = verify(crux_root, pins)
        status = run(repo, checker, wrapper)
    except CheckError as error:
        print(f"check_include_domains: {error}", file=sys.stderr)
        return 2
    if status != 0:
        print(f"check_include_domains: the include check failed (status {status})",
              file=sys.stderr)
    else:
        print("check_include_domains: the include check passed")
    return status


if __name__ == "__main__":
    sys.exit(main())
