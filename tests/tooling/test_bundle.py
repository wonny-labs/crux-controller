"""Tests of release/assemble_bundle.py, release/check_bundle.py and release/rebuild_compare.py."""

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "release"))
sys.path.insert(0, str(ROOT / "budgets"))

import assemble_bundle  # noqa: E402
import check_bundle  # noqa: E402
import collect  # noqa: E402
import rebuild_compare  # noqa: E402

IMAGE = b"\x10\x20\x30\x40" * 16
CONFIG = b"CONFIG_LOG=y\n# a comment\n# CONFIG_SHELL is not set\n\nCONFIG_MAIN_STACK_SIZE=4096\n"
TARGET = "mimxrt1060_evk@B//qspi"
METADATA = {
    "product_version": "0.1.0+1",
    "security_counter": 0,
    "release_tag": "v0.1.0",
    "sdk_version": "1.0.1",
    "runner_image": "ubuntu-24.04",
    "target": TARGET,
}
LOCK = "manifest:\n  projects:\n    - name: crux-pilot\n      revision: db5adca\n"
PINS = "CONTRACT crux-pilot db5adca28bd3\nOK zephyr dccb09599635\n"


def make_build_dir(base, image=IMAGE, config=CONFIG):
    build = pathlib.Path(base) / "build"
    (build / "zephyr").mkdir(parents=True)
    (build / "zephyr" / "zephyr.bin").write_bytes(image)
    (build / "zephyr" / ".config").write_bytes(config)
    return build


def make_inputs(base):
    base = pathlib.Path(base)
    lock = base / "west.lock.yml"
    lock.write_text(LOCK)
    pins = base / "pins.txt"
    pins.write_text(PINS)
    return lock, pins


def make_bundle(base, **overrides):
    base = pathlib.Path(base)
    build = make_build_dir(base)
    lock, pins = make_inputs(base)
    metadata = {**METADATA, **overrides}
    return assemble_bundle.assemble(build, lock, pins, base / "bundle", metadata)


def read_manifest(bundle):
    return json.loads((bundle / "release-manifest.json").read_text())


def write_manifest(bundle, manifest):
    (bundle / "release-manifest.json").write_text(json.dumps(manifest, indent=2))


class AssembleBundle(unittest.TestCase):
    def test_bundle_holds_the_lock_the_report_and_the_manifest_but_no_image(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            names = sorted(path.name for path in bundle.iterdir())
            self.assertEqual(["pins-report.txt", "release-manifest.json", "west.lock.yml"], names)

    def test_manifest_records_the_image_hash_and_the_documented_identity(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            manifest = read_manifest(bundle)
            image_sha256 = hashlib.sha256(IMAGE).hexdigest()
            self.assertEqual(image_sha256, manifest["zephyr_bin_sha256"])
            self.assertEqual(
                collect.firmware_identity(image_sha256, CONFIG, TARGET),
                manifest["firmware_identity"],
            )
            self.assertEqual("0.1.0+1", manifest["product_version"])
            self.assertEqual("v0.1.0", manifest["release_tag"])

    def test_manifest_hashes_every_other_item(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            hashes = read_manifest(bundle)["bundle_hashes"]
            self.assertEqual({"pins-report.txt", "west.lock.yml"}, set(hashes))
            self.assertEqual(hashlib.sha256(PINS.encode()).hexdigest(), hashes["pins-report.txt"])

    def test_assemble_refuses_a_build_without_an_image(self):
        with tempfile.TemporaryDirectory() as base:
            build = make_build_dir(base)
            (build / "zephyr" / "zephyr.bin").unlink()
            lock, pins = make_inputs(base)
            with self.assertRaises(FileNotFoundError):
                assemble_bundle.assemble(build, lock, pins, pathlib.Path(base) / "bundle", METADATA)


class CheckBundle(unittest.TestCase):
    def test_schema_accepts_complete_manifest(self):
        with tempfile.TemporaryDirectory() as base:
            self.assertEqual([], check_bundle.check(make_bundle(base)))

    def test_schema_rejects_missing_hash(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            manifest = read_manifest(bundle)
            del manifest["zephyr_bin_sha256"]
            write_manifest(bundle, manifest)
            problems = check_bundle.check(bundle)
            self.assertTrue(any("zephyr_bin_sha256" in problem for problem in problems), problems)

    def test_schema_rejects_a_malformed_hash(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            manifest = read_manifest(bundle)
            manifest["firmware_identity"] = "not-a-hash"
            write_manifest(bundle, manifest)
            problems = check_bundle.check(bundle)
            self.assertTrue(any("firmware_identity" in problem for problem in problems), problems)

    def test_check_rejects_elf_in_bundle(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            (bundle / "zephyr.elf").write_bytes(b"\x7fELF")
            problems = check_bundle.check(bundle)
            self.assertTrue(any("zephyr.elf" in problem for problem in problems), problems)

    def test_check_rejects_map_and_image_files_in_bundle(self):
        for name in ("zephyr.map", "zephyr.bin", "app.hex", "signed.img"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as base:
                bundle = make_bundle(base)
                (bundle / name).write_bytes(b"x")
                problems = check_bundle.check(bundle)
                self.assertTrue(any(name in problem for problem in problems), problems)

    def test_check_rejects_absolute_path_in_item(self):
        for text in (
            "path: /Users/someone/work/app\n",
            "path: /home/runner/work/crux-controller\n",
            "path: C:\\Users\\someone\\app\n",
        ):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as base:
                bundle = make_bundle(base)
                (bundle / "pins-report.txt").write_text(PINS + text)
                manifest = read_manifest(bundle)
                manifest["bundle_hashes"]["pins-report.txt"] = hashlib.sha256(
                    (PINS + text).encode()
                ).hexdigest()
                write_manifest(bundle, manifest)
                problems = check_bundle.check(bundle)
                self.assertTrue(any("pins-report.txt" in problem for problem in problems), problems)

    def test_check_accepts_urls_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            text = PINS + "remote: https://github.com/zephyrproject-rtos/zephyr\npath: modules/hal/nxp\n"
            (bundle / "pins-report.txt").write_text(text)
            manifest = read_manifest(bundle)
            manifest["bundle_hashes"]["pins-report.txt"] = hashlib.sha256(text.encode()).hexdigest()
            write_manifest(bundle, manifest)
            self.assertEqual([], check_bundle.check(bundle))

    def test_check_rejects_private_string(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            text = PINS + "note: the throwaway-private-name project\n"
            (bundle / "pins-report.txt").write_text(text)
            manifest = read_manifest(bundle)
            manifest["bundle_hashes"]["pins-report.txt"] = hashlib.sha256(text.encode()).hexdigest()
            write_manifest(bundle, manifest)
            self.assertEqual([], check_bundle.check(bundle))
            problems = check_bundle.check(bundle, private_strings=["Throwaway-Private-Name"])
            self.assertTrue(any("pins-report.txt" in problem for problem in problems), problems)

    def test_check_rejects_an_item_changed_after_hashing(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            (bundle / "west.lock.yml").write_text(LOCK + "# edited\n")
            problems = check_bundle.check(bundle)
            self.assertTrue(any("west.lock.yml" in problem for problem in problems), problems)

    def test_check_rejects_an_item_missing_from_the_hash_list(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            (bundle / "extra.txt").write_text("extra\n")
            problems = check_bundle.check(bundle)
            self.assertTrue(any("extra.txt" in problem for problem in problems), problems)

    def test_command_line_reads_the_private_string_list_from_a_file(self):
        with tempfile.TemporaryDirectory() as base:
            bundle = make_bundle(base)
            text = PINS + "note: the throwaway-private-name project\n"
            (bundle / "pins-report.txt").write_text(text)
            manifest = read_manifest(bundle)
            manifest["bundle_hashes"]["pins-report.txt"] = hashlib.sha256(text.encode()).hexdigest()
            write_manifest(bundle, manifest)
            names = pathlib.Path(base) / "private.txt"
            names.write_text("# a comment\n\nthrowaway-private-name\n")
            script = str(ROOT / "release" / "check_bundle.py")
            clean = subprocess.run([sys.executable, script, str(bundle)], capture_output=True, text=True)
            self.assertEqual(0, clean.returncode, clean.stderr)
            found = subprocess.run(
                [sys.executable, script, str(bundle), "--private-strings", str(names)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(1, found.returncode)
            self.assertIn("pins-report.txt", found.stderr)


class RebuildCompare(unittest.TestCase):
    def record(self, base):
        return read_manifest(make_bundle(base))

    def test_rebuild_compare_passes_on_match(self):
        with tempfile.TemporaryDirectory() as base:
            record = self.record(base)
            other = make_build_dir(pathlib.Path(base) / "other")
            self.assertEqual([], rebuild_compare.compare(record, other, TARGET))

    def test_rebuild_compare_fails_on_hash_difference(self):
        with tempfile.TemporaryDirectory() as base:
            record = self.record(base)
            other = make_build_dir(pathlib.Path(base) / "other", image=IMAGE + b"\x00")
            problems = rebuild_compare.compare(record, other, TARGET)
            self.assertTrue(any("zephyr_bin_sha256" in problem for problem in problems), problems)

    def test_rebuild_compare_fails_on_identity_difference(self):
        with tempfile.TemporaryDirectory() as base:
            record = self.record(base)
            other = make_build_dir(pathlib.Path(base) / "other", config=CONFIG + b"CONFIG_NEW=y\n")
            problems = rebuild_compare.compare(record, other, TARGET)
            self.assertEqual(1, len(problems), problems)
            self.assertIn("firmware_identity", problems[0])

    def test_rebuild_compare_ignores_comment_only_configuration_changes(self):
        with tempfile.TemporaryDirectory() as base:
            record = self.record(base)
            other = make_build_dir(
                pathlib.Path(base) / "other", config=CONFIG + b"# a path /tmp/elsewhere\n"
            )
            self.assertEqual([], rebuild_compare.compare(record, other, TARGET))


if __name__ == "__main__":
    unittest.main()
