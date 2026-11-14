#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail when the resolved west workspace could fetch a GPL stack of the Crux manifest.

The Crux manifest puts Mbed TLS and TF-PSA-Crypto in the same optional group as wolfSSL,
wolfSSH and wolfPSA (``crux-secure-management``). The group is off by default. A product that
enables it would fetch all five unless its manifest narrows the Crux import. This repository
narrows the import with ``import: name-blocklist`` on the ``crux-pilot`` project, so the three
wolf projects are not in the resolved manifest at all. This script checks that on two inputs:

* ``--mode default`` reads ``west list --all -f '{name} {active}'`` of the workspace as it is
  fetched by every job. No wolf project is listed, the Mbed pair is not active (the group is
  off) and Reliance Edge (GPLv2, group ``crux-reliance``) is not active.
* ``--mode mbed`` reads the same listing after ``crux-secure-management`` is switched on in the
  runner. No wolf project is listed, the Mbed pair is active and Reliance Edge is not active.

``check_manifest`` is the static counterpart over the parsed ``west.yml``: the Crux import must
be narrowed by name so that no wolf project passes, and no optional group is enabled. Only name
filters are understood. The listing is the evidence, the static check is the quick guard that
runs without west.

Exit status: 0 when the check passes, 1 when it finds a problem, 2 when the input cannot be read.
"""

import argparse
import sys

WOLF_PROJECTS = ("wolfssl", "wolfssh", "wolfpsa")
MBED_PROJECTS = ("mbedtls", "tf-psa-crypto")
RELIANCE_PROJECT = "reliance-edge"
OPTIONAL_GROUPS = ("crux-secure-management", "crux-reliance")
# A listing that lacks these did not resolve the Crux and Zephyr manifests, so it proves nothing.
REQUIRED_ACTIVE = ("crux-pilot", "zephyr")
MODES = ("default", "mbed")


def parse_listing(text):
    """Return {name: active} from lines of ``<name> <active|inactive>``, the way ``west list``
    prints ``{active}``. Raise ValueError for any other line."""
    projects = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 2 or fields[1] not in ("active", "inactive"):
            raise ValueError(f"line {number} is not '<name> <active|inactive>': {line!r}")
        projects[fields[0]] = fields[1] == "active"
    return projects


def check_listing(text, mode):
    """Return a list of problems with a `west list --all` listing, empty when it passes."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}, expected one of {MODES}")
    projects = parse_listing(text)
    problems = []
    for name in REQUIRED_ACTIVE:
        if projects.get(name) is not True:
            problems.append(f"{name} is not an active project: the manifest did not resolve")
    for name in WOLF_PROJECTS:
        if name in projects:
            state = "active" if projects[name] else "inactive"
            problems.append(f"{name} is in the resolved manifest ({state}): the import is not narrowed")
    if projects.get(RELIANCE_PROJECT):
        problems.append(f"{RELIANCE_PROJECT} is active: its group must stay off")
    for name in MBED_PROJECTS:
        active = projects.get(name, False)
        if mode == "mbed" and not active:
            problems.append(f"{name} is not active with the Mbed TLS group on")
        if mode == "default" and active:
            problems.append(f"{name} is active in the default workspace: the group must stay off")
    return problems


def check_manifest(manifest):
    """Return a list of problems with the parsed `manifest:` mapping of west.yml."""
    problems = []
    for entry in manifest.get("group-filter") or []:
        entry = str(entry)
        if entry.startswith("+") and entry[1:] in OPTIONAL_GROUPS:
            problems.append(f"{entry[1:]} is enabled in the manifest: optional groups stay off")
    pilot = next((p for p in manifest.get("projects", []) if p.get("name") == "crux-pilot"), None)
    if pilot is None:
        return problems + ["the manifest has no crux-pilot project"]
    imported = pilot.get("import")
    if not isinstance(imported, dict):
        return problems + ["the crux-pilot import is not narrowed: it has no name filter"]
    blocklist = imported.get("name-blocklist")
    allowlist = imported.get("name-allowlist")
    if blocklist is None and allowlist is None:
        return problems + [
            "the crux-pilot import is not narrowed: it has no name-blocklist or name-allowlist"
        ]
    for name in WOLF_PROJECTS:
        if blocklist is not None and name not in blocklist:
            problems.append(f"the crux-pilot import does not block {name}")
        if allowlist is not None and name in allowlist:
            problems.append(f"the crux-pilot import allows {name}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument(
        "--listing", help="file with `west list --all -f '{name} {active}'`; default stdin"
    )
    args = parser.parse_args(argv)
    try:
        if args.listing:
            with open(args.listing) as handle:
                text = handle.read()
        else:
            text = sys.stdin.read()
        problems = check_listing(text, args.mode)
    except (OSError, ValueError) as error:
        print(f"check_mbed_only: {error}", file=sys.stderr)
        return 2
    for problem in problems:
        print(f"PROBLEM {problem}")
    if problems:
        return 1
    print(f"Mbed-only check passed ({args.mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
