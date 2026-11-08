#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare a rebuild with the release record.

A rebuild at another workspace path must give the same ``zephyr.bin`` and the same
``firmware_identity`` (the definition of budgets/collect.py). Nothing else is compared:
``build_id``, ``.elf``, ``.map`` and the whole ``.config`` differ between paths.
"""

import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "budgets"))

import collect  # noqa: E402


def compare(record, build_dir, target=collect.TARGET):
    """Return one message per difference, and an empty list when both values match."""
    build = pathlib.Path(build_dir)
    image = (build / "zephyr" / "zephyr.bin").read_bytes()
    config = (build / "zephyr" / ".config").read_bytes()
    image_sha256 = hashlib.sha256(image).hexdigest()
    rebuilt = {
        "zephyr_bin_sha256": image_sha256,
        "firmware_identity": collect.firmware_identity(image_sha256, config, target),
    }
    return [
        f"{field} differs: record {record.get(field)}, rebuild {value}"
        for field, value in rebuilt.items()
        if record.get(field) != value
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--record", required=True, help="a release-manifest.json")
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--target", default=collect.TARGET)
    args = parser.parse_args(argv)
    try:
        record = json.loads(pathlib.Path(args.record).read_text())
        problems = compare(record, args.build_dir, args.target)
    except (OSError, ValueError) as error:
        print(f"rebuild_compare: {error}", file=sys.stderr)
        return 1
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("rebuild matches the record")
    return 0


if __name__ == "__main__":
    sys.exit(main())
