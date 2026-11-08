#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check a measurement against the limits that were declared before it was taken.

``limits.json`` holds ``{"min_free_percent": {"<step>": {"<region>": number}}}``. Three things
fail, not just an excess: a region over its limit, a measured region that has no limit, and a
limited region that was not measured. A step with no declared limits fails too.
"""

import argparse
import json
import pathlib
import sys


def free_percent(region):
    return 100.0 * (region["size"] - region["used"]) / region["size"]


def check(measurement, limits):
    """Return one message per violation. An empty list means every region is within its limit."""
    step = measurement["step"]
    declared_steps = limits.get("min_free_percent", {})
    if step not in declared_steps:
        return [f"{step}: unknown step, no limits are declared for it"]
    declared = declared_steps[step]
    measured = measurement["regions"]
    messages = []
    for name in sorted(measured):
        if name not in declared:
            messages.append(f"{step} {name}: measured but no limit is declared")
    for name in sorted(declared):
        if name not in measured:
            messages.append(f"{step} {name}: a limit is declared but the region was not measured")
            continue
        region = measured[name]
        if region["size"] <= 0:
            messages.append(f"{step} {name}: the region has size {region['size']}")
        elif free_percent(region) < declared[name]:
            messages.append(
                f"{step} {name}: {free_percent(region):.1f}% free is below the declared "
                f"minimum of {declared[name]}% ({region['used']} of {region['size']} bytes used)"
            )
    return messages


def table(measurement):
    """A markdown table of the measured regions, for a job summary."""
    rows = [
        f"| {measurement['step']} region | Used (B) | Size (B) | Free (%) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name in sorted(measurement["regions"]):
        region = measurement["regions"][name]
        free = free_percent(region) if region["size"] > 0 else float("nan")
        rows.append(f"| {name} | {region['used']} | {region['size']} | {free:.1f} |")
    return "\n".join(rows) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--measurement", required=True)
    parser.add_argument("--limits", required=True)
    args = parser.parse_args(argv)
    try:
        measurement = json.loads(pathlib.Path(args.measurement).read_text())
        limits = json.loads(pathlib.Path(args.limits).read_text())
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    messages = check(measurement, limits)
    for message in messages:
        print(message)
    if messages:
        print(f"{len(messages)} budget violation(s)")
        return 1
    print(f"{measurement['step']}: budget check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
