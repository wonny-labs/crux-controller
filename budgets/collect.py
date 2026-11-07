#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect the static resource use of one build step into a measurement.

Reads the logs that the workflow keeps in ``<build>/budget/``:

* ``build.log``: the output of ``west build``, whose link step prints a memory region table;
* ``rom_report.log`` and ``ram_report.log``: the output of the ``rom_report`` and ``ram_report``
  targets, whose ``Root`` row holds the symbol total.

The region table (linker view) and the two report totals (symbol view) measure different
things and are kept apart. Nothing here measures run time: stack use, heap peaks and timing
need a running image.
"""

import argparse
import hashlib
import json
import pathlib
import re
import sys

TARGET = "mimxrt1060_evk@B//qspi"

# Same definition as firmware_identity in crux-pilot's scripts/record-build-provenance.py and
# the guide's build-record section: the target, the hash of zephyr.bin and the hash of .config
# without comments or blank lines, but with "# CONFIG_X is not set" lines.
IDENTITY_ALGORITHM = "crux-firmware-identity-v1"
DISABLED_OPTION = re.compile(rb"# CONFIG_[A-Za-z0-9_]+ is not set")

UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
REGION_LINE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9_]+):\s+(?P<used>\d+)\s+(?P<used_unit>B|KB|MB|GB)"
    r"\s+(?P<size>\d+)\s+(?P<size_unit>B|KB|MB|GB)\s+[\d.]+%\s*$"
)
REPORT_ROOT = re.compile(r"^\s*Root\s+(\d+)\b", re.MULTILINE)

# Kconfig values that decide resource use. Recorded when present, so a change in a limit can
# be read next to the configuration that caused it.
RESOURCE_SYMBOLS = (
    "CONFIG_MAIN_STACK_SIZE",
    "CONFIG_LOG_BUFFER_SIZE",
    "CONFIG_LOG_PROCESS_THREAD_STACK_SIZE",
    "CONFIG_NET_PKT_RX_COUNT",
    "CONFIG_NET_PKT_TX_COUNT",
    "CONFIG_NET_BUF_RX_COUNT",
    "CONFIG_NET_BUF_TX_COUNT",
    "CONFIG_NET_MAX_CONTEXTS",
    "CONFIG_NET_MAX_CONN",
)


def parse_regions(text):
    """Return {region: {"used": bytes, "size": bytes}} from the linker's region table."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.lstrip().startswith("Memory region"):
            break
    else:
        raise ValueError("no memory region table in the build log")
    regions = {}
    for line in lines[index + 1 :]:
        match = REGION_LINE.match(line)
        if not match:
            break
        regions[match["name"]] = {
            "used": int(match["used"]) * UNITS[match["used_unit"]],
            "size": int(match["size"]) * UNITS[match["size_unit"]],
        }
    if not regions:
        raise ValueError("the memory region table has no rows")
    return regions


def parse_report_total(text):
    """Return the symbol total from the Root row of a rom_report or ram_report log."""
    match = REPORT_ROOT.search(text)
    if not match:
        raise ValueError("no Root row in the report")
    return int(match[1])


def normalised_config(content):
    kept = [
        line
        for line in content.splitlines()
        if line and (not line.startswith(b"#") or DISABLED_OPTION.fullmatch(line))
    ]
    return b"".join(line + b"\n" for line in kept)


def firmware_identity(image_sha256, config_bytes, target):
    identity = {
        "algorithm": IDENTITY_ALGORITHM,
        "target": target,
        "image_sha256": image_sha256,
        "configuration_sha256": hashlib.sha256(normalised_config(config_bytes)).hexdigest(),
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def configured_values(config_bytes):
    values = {}
    for raw in config_bytes.decode(errors="replace").splitlines():
        name, separator, value = raw.partition("=")
        if separator and name in RESOURCE_SYMBOLS:
            values[name] = value
    return values


def collect(build_dir, step, target=TARGET):
    build = pathlib.Path(build_dir)
    logs = build / "budget"
    image = (build / "zephyr" / "zephyr.bin").read_bytes()
    config = (build / "zephyr" / ".config").read_bytes()
    image_sha256 = hashlib.sha256(image).hexdigest()
    return {
        "step": step,
        "regions": parse_regions((logs / "build.log").read_text()),
        "rom_report": parse_report_total((logs / "rom_report.log").read_text()),
        "ram_report": parse_report_total((logs / "ram_report.log").read_text()),
        "zephyr_bin_size": len(image),
        "zephyr_bin_sha256": image_sha256,
        "firmware_identity": firmware_identity(image_sha256, config, target),
        "configured": configured_values(config),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--out", help="write the measurement here instead of standard output")
    args = parser.parse_args(argv)
    try:
        measurement = collect(args.build_dir, args.step, args.target)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    text = json.dumps(measurement, indent=2, sort_keys=True) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
