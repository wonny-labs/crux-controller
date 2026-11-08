#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble a release bundle: the lock, the pin report and a release manifest.

The bundle holds hashes and identities only. The image, ``.elf`` and ``.map`` files never
enter it: ``zephyr.bin`` is read to hash it, and the bundle records the hash and the
``firmware_identity`` of the build (the definition of budgets/collect.py).
"""

import argparse
import hashlib
import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "budgets"))

import collect  # noqa: E402

MANIFEST = "release-manifest.json"
LOCK_NAME = "west.lock.yml"
PINS_NAME = "pins-report.txt"
REQUIRED_METADATA = (
    "product_version",
    "security_counter",
    "release_tag",
    "sdk_version",
    "runner_image",
)


def sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def assemble(build_dir, lock_path, pins_report, out_dir, metadata=None):
    """Write the bundle into ``out_dir`` and return it.

    ``metadata`` carries product_version, security_counter, release_tag, sdk_version and
    runner_image, and optionally target (default: the controller's board).
    """
    metadata = dict(metadata or {})
    missing = [key for key in REQUIRED_METADATA if key not in metadata]
    if missing:
        raise ValueError(f"missing release metadata: {', '.join(missing)}")
    target = metadata.pop("target", collect.TARGET)

    build = pathlib.Path(build_dir)
    image = (build / "zephyr" / "zephyr.bin").read_bytes()
    config = (build / "zephyr" / ".config").read_bytes()

    out = pathlib.Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(lock_path, out / LOCK_NAME)
    shutil.copyfile(pins_report, out / PINS_NAME)

    image_sha256 = hashlib.sha256(image).hexdigest()
    manifest = {
        "product_version": metadata["product_version"],
        "security_counter": metadata["security_counter"],
        "release_tag": metadata["release_tag"],
        "sdk_version": metadata["sdk_version"],
        "runner_image": metadata["runner_image"],
        "target": target,
        "bundle_hashes": {
            name: sha256_file(out / name) for name in sorted((LOCK_NAME, PINS_NAME))
        },
        "zephyr_bin_sha256": image_sha256,
        "firmware_identity": collect.firmware_identity(image_sha256, config, target),
    }
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--lock", required=True)
    parser.add_argument("--pins-report", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--product-version", required=True)
    parser.add_argument("--security-counter", type=int, required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--sdk-version", required=True)
    parser.add_argument("--runner-image", required=True)
    parser.add_argument("--target", default=collect.TARGET)
    args = parser.parse_args(argv)
    metadata = {
        "product_version": args.product_version,
        "security_counter": args.security_counter,
        "release_tag": args.release_tag,
        "sdk_version": args.sdk_version,
        "runner_image": args.runner_image,
        "target": args.target,
    }
    try:
        out = assemble(args.build_dir, args.lock, args.pins_report, args.out_dir, metadata)
    except (OSError, ValueError) as error:
        print(f"assemble_bundle: {error}", file=sys.stderr)
        return 1
    print(f"bundle written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
