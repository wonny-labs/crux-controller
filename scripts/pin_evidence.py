#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Write the review text of the pin pull request and put the CI evidence of step 3 into it.

Step 3 of CONTRIBUTING.md, "The pin and the manifest", asks for the SHA-256 of the net zephyr.bin,
its firmware_identity and the budget tables. CI already prints them: the release dry run prints
the release manifest, and each Budget job prints its table. This script reads those job logs as
text and copies only values of a known shape (64-hex hashes, region rows of numbers) into a
marked section of the body, so it can rerun on the same body. It builds nothing and needs only the
standard library, so any CI can call it.

    pin_evidence.py body
        print what a person checks and an empty evidence section; the Crux pin bot appends it
        (--append-body) after its own text, which names both pins and the Crux log
    pin_evidence.py evidence --body FILE --head SHA [--release-log FILE] [--budget-log FILE]...
        print FILE with the evidence section replaced, or appended when it has none

Exit status: 0 printed, 2 bad input.
"""

import argparse
import pathlib
import re
import sys

START = "<!-- crux-pin-evidence:start -->"
END = "<!-- crux-pin-evidence:end -->"

SHA1 = re.compile(r"[0-9a-f]{40}")
# A CI log line may carry a job and a step name (gh run view --log) and a timestamp.
PREFIX = re.compile(r"^(?:[^\t\n]*\t){0,2}(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z ?)?")
RELEASE_VALUE = re.compile(r'^\s*"(zephyr_bin_sha256|firmware_identity)": "([0-9a-f]{64})",?\s*$')
TABLE_HEAD = re.compile(r"^\| ([a-z][a-z0-9_-]*) region \| Used \(B\) \| Size \(B\) \| Free \(%\) \|$")
TABLE_RULE = "| --- | ---: | ---: | ---: |"
TABLE_ROW = re.compile(r"^\| ([A-Za-z0-9_]+) \| (\d+) \| (\d+) \| (-?\d+\.\d|nan) \|$")


def lines(text):
    for line in text.lstrip("﻿").splitlines():
        yield PREFIX.sub("", line, count=1).rstrip()


def release_values(text):
    """The net image hash and firmware identity that the release dry run printed."""
    found = {}
    for line in lines(text):
        match = RELEASE_VALUE.match(line)
        if match:
            key, value = match.groups()
            if found.setdefault(key, value) != value:
                raise ValueError(f"the log holds two different values of {key}")
    return found


def budget_tables(text):
    """{configuration: [(region, used, size, free)]} from the tables that the Budget jobs printed."""
    tables, step, rows = {}, None, None
    for line in lines(text):
        head = TABLE_HEAD.match(line)
        if head:
            step, rows = head.group(1), []
            continue
        if step is None:
            continue
        if line == TABLE_RULE and not rows:
            continue
        row = TABLE_ROW.match(line)
        if row:
            rows.append((row.group(1), int(row.group(2)), int(row.group(3)), row.group(4)))
            continue
        if rows:
            tables[step] = rows
        step, rows = None, None
    if step is not None and rows:
        tables[step] = rows
    return tables


# The rows of the budget.yml matrix, in its order (test_pin_update.py compares the two).
CONFIG_ORDER = ("minimal", "workload", "net", "file", "system", "sntp", "management", "base")


def config_order(tables):
    """The configurations of the tables in the order of the budget matrix; an unknown one goes last."""
    known = [name for name in CONFIG_ORDER if name in tables]
    return known + sorted(name for name in tables if name not in CONFIG_ORDER)


def section(head, release_log, budget_log):
    out = [START, f"### CI evidence at `{head}`", ""]
    values = release_values(release_log) if release_log else {}
    if values:
        out += [
            "From the `release` dry run:",
            "",
            "| `net` image | Value |",
            "| --- | --- |",
            f"| `zephyr.bin` SHA-256 | `{values.get('zephyr_bin_sha256', 'not found')}` |",
            f"| `firmware_identity` | `{values.get('firmware_identity', 'not found')}` |",
        ]
    else:
        out.append("`net` hash and `firmware_identity`: not available (no finished `release` dry run "
                   "at this commit, or it did not print the release manifest).")
    out.append("")
    tables = budget_tables(budget_log) if budget_log else {}
    if tables:
        out += ["From the `budget` run:", ""]
        for step in config_order(tables):
            out += [f"| {step} region | Used (B) | Size (B) | Free (%) |", TABLE_RULE]
            out += [f"| {name} | {used} | {size} | {free} |" for name, used, size, free in tables[step]]
            out.append("")
    else:
        out += ["Budget tables: not available (no finished `budget` run at this commit).", ""]
    out.append("Compare with the previous pin; say in the pull request if numbers move.")
    out.append(END)
    return "\n".join(out) + "\n"


def splice(body, new_section):
    start, end = body.find(START), body.find(END)
    if start != -1 and end > start:
        return body[:start] + new_section + body[end + len(END):].lstrip("\n")
    return body.rstrip("\n") + "\n\n" + new_section


def review_body():
    return (
        "The pin bot opened this pull request. It does not merge itself.\n\n"
        "Before approving, a person:\n\n"
        "- reads the Crux changes above and writes the reason into the commit message, the comment\n"
        "  above the pin in `west.yml` and the `CHANGELOG.md` entry (a commit of a person stops the\n"
        "  bot from refreshing the branch);\n"
        "- checks the quotes of the pin that the hook leaves alone (`KEPT` in `scripts/crux-pin-hook`:\n"
        "  two in `CONTRIBUTING.md`, and the `nsos_rdhup.cmake` copy, whose test fails until it is\n"
        "  compared with the new Crux) and moves them when they still hold at the new pin;\n"
        "- checks that CI is green, the `West pins` job and the `release` dry run included;\n"
        "- compares the evidence below with the previous pin. A limit in `budgets/limits.json` is\n"
        "  not changed here to make a bump pass.\n\n"
        + section("pending", None, None).replace(
            "### CI evidence at `pending`", "### CI evidence (filled in when CI has run)")
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("body")
    evidence = commands.add_parser("evidence")
    evidence.add_argument("--body", required=True)
    evidence.add_argument("--head", required=True)
    evidence.add_argument("--release-log")
    evidence.add_argument("--budget-log", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "body":
            sys.stdout.write(review_body())
            return 0
        if not SHA1.fullmatch(args.head):
            raise ValueError(f"--head must be a 40-character lower-case hex SHA, got {args.head!r}")
        release = pathlib.Path(args.release_log).read_text(errors="replace") if args.release_log else None
        budget = "\n".join(pathlib.Path(p).read_text(errors="replace") for p in args.budget_log) or None
        text = pathlib.Path(args.body).read_text(encoding="utf-8")
        sys.stdout.write(splice(text, section(args.head, release, budget)))
        return 0
    except (OSError, ValueError) as error:
        print(f"pin_evidence: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
