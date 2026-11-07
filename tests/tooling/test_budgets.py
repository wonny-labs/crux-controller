"""Tests of budgets/collect.py and budgets/check.py."""

import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "budgets"))

import check  # noqa: E402
import collect  # noqa: E402

CONFIG = b"CONFIG_MAIN_STACK_SIZE=4096\n# a comment with a path /home/runner\n# CONFIG_SHELL is not set\n\nCONFIG_LOG=y\n"
IMAGE = b"\x01\x02\x03\x04" * 8


def make_build_dir(directory):
    build = pathlib.Path(directory)
    (build / "budget").mkdir(parents=True)
    (build / "zephyr").mkdir()
    shutil.copy(FIXTURES / "build.log", build / "budget" / "build.log")
    shutil.copy(FIXTURES / "rom_report.log", build / "budget" / "rom_report.log")
    shutil.copy(FIXTURES / "ram_report.log", build / "budget" / "ram_report.log")
    (build / "zephyr" / "zephyr.bin").write_bytes(IMAGE)
    (build / "zephyr" / ".config").write_bytes(CONFIG)
    return build


class Collect(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.build = make_build_dir(pathlib.Path(self.directory.name) / "build")

    def test_collect_reads_regions(self):
        measurement = collect.collect(self.build, "S0")
        self.assertEqual("S0", measurement["step"])
        self.assertEqual(
            {"used": 32432, "size": 8 * 1024 * 1024}, measurement["regions"]["FLASH"]
        )
        self.assertEqual({"used": 4288, "size": 32 * 1024 * 1024}, measurement["regions"]["RAM"])
        self.assertEqual({"used": 0, "size": 128 * 1024}, measurement["regions"]["ITCM"])
        self.assertEqual(
            {"FLASH", "RAM", "ITCM", "DTCM", "OCRAM", "OCRAM2", "IDT_LIST"},
            set(measurement["regions"]),
        )

    def test_rom_and_ram_reports_kept_separate(self):
        measurement = collect.collect(self.build, "S0")
        self.assertEqual(32080, measurement["rom_report"])
        self.assertEqual(4256, measurement["ram_report"])

    def test_image_size_and_hash(self):
        measurement = collect.collect(self.build, "S0")
        self.assertEqual(len(IMAGE), measurement["zephyr_bin_size"])
        self.assertEqual(hashlib.sha256(IMAGE).hexdigest(), measurement["zephyr_bin_sha256"])

    def test_firmware_identity_follows_the_documented_definition(self):
        # image hash, plus the hash of .config without comments and blank lines but with
        # "# CONFIG_X is not set" lines, under the target and the algorithm name.
        config = b"CONFIG_MAIN_STACK_SIZE=4096\n# CONFIG_SHELL is not set\nCONFIG_LOG=y\n"
        identity = {
            "algorithm": "crux-firmware-identity-v1",
            "target": collect.TARGET,
            "image_sha256": hashlib.sha256(IMAGE).hexdigest(),
            "configuration_sha256": hashlib.sha256(config).hexdigest(),
        }
        expected = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(expected, collect.collect(self.build, "S0")["firmware_identity"])

    def test_configured_values_are_recorded(self):
        measurement = collect.collect(self.build, "S0")
        self.assertEqual("4096", measurement["configured"]["CONFIG_MAIN_STACK_SIZE"])
        self.assertNotIn("CONFIG_SHELL", measurement["configured"])

    def test_units_are_scaled(self):
        text = (
            "Memory region         Used Size  Region Size  %age Used\n"
            "           FLASH:        2 KB         1 MB      0.20%\n"
            "             RAM:        1 MB         1 GB      0.10%\n"
        )
        self.assertEqual(
            {"FLASH": {"used": 2048, "size": 1048576}, "RAM": {"used": 1048576, "size": 1073741824}},
            collect.parse_regions(text),
        )

    def test_a_log_without_the_table_is_an_error(self):
        with self.assertRaises(ValueError):
            collect.parse_regions("[1/1] Linking\n")

    def test_a_report_without_a_total_is_an_error(self):
        with self.assertRaises(ValueError):
            collect.parse_report_total("nothing here\n")

    def test_a_missing_log_is_an_error(self):
        (self.build / "budget" / "ram_report.log").unlink()
        with self.assertRaises(FileNotFoundError):
            collect.collect(self.build, "S0")


def measurement(regions, step="S2"):
    return {"step": step, "regions": regions}


def limits(per_step):
    return {"min_free_percent": per_step}


class Check(unittest.TestCase):
    def test_check_passes_under_limit(self):
        m = measurement({"FLASH": {"used": 700, "size": 1000}})
        self.assertEqual([], check.check(m, limits({"S2": {"FLASH": 25}})))

    def test_check_passes_exactly_at_the_limit(self):
        m = measurement({"FLASH": {"used": 750, "size": 1000}})
        self.assertEqual([], check.check(m, limits({"S2": {"FLASH": 25}})))

    def test_check_fails_over_limit(self):
        m = measurement({"FLASH": {"used": 751, "size": 1000}})
        messages = check.check(m, limits({"S2": {"FLASH": 25}}))
        self.assertEqual(1, len(messages))
        self.assertIn("FLASH", messages[0])
        self.assertIn("25", messages[0])

    def test_check_fails_when_a_region_is_full_or_overfull(self):
        m = measurement({"FLASH": {"used": 1200, "size": 1000}})
        self.assertEqual(1, len(check.check(m, limits({"S2": {"FLASH": 0}}))))

    def test_check_fails_when_a_limited_region_is_not_measured(self):
        m = measurement({"FLASH": {"used": 1, "size": 1000}})
        messages = check.check(m, limits({"S2": {"FLASH": 25, "OCRAM": 25}}))
        self.assertEqual(1, len(messages))
        self.assertIn("OCRAM", messages[0])
        self.assertIn("not measured", messages[0])

    def test_check_fails_when_a_measured_region_has_no_limit(self):
        m = measurement(
            {"FLASH": {"used": 1, "size": 1000}, "OCRAM": {"used": 1, "size": 1000}}
        )
        messages = check.check(m, limits({"S2": {"FLASH": 25}}))
        self.assertEqual(1, len(messages))
        self.assertIn("OCRAM", messages[0])
        self.assertIn("no limit", messages[0])

    def test_check_fails_on_unknown_step(self):
        m = measurement({"FLASH": {"used": 1, "size": 1000}}, step="S9")
        messages = check.check(m, limits({"S2": {"FLASH": 25}}))
        self.assertEqual(1, len(messages))
        self.assertIn("S9", messages[0])

    def test_check_reports_every_violation(self):
        m = measurement(
            {"FLASH": {"used": 900, "size": 1000}, "RAM": {"used": 900, "size": 1000}}
        )
        self.assertEqual(2, len(check.check(m, limits({"S2": {"FLASH": 25, "RAM": 25}}))))

    def test_a_region_of_size_zero_fails(self):
        m = measurement({"FLASH": {"used": 0, "size": 0}})
        self.assertEqual(1, len(check.check(m, limits({"S2": {"FLASH": 25}}))))

    def test_table_lists_every_region_with_its_free_percentage(self):
        m = measurement({"FLASH": {"used": 250, "size": 1000}})
        table = check.table(m)
        self.assertIn("FLASH", table)
        self.assertIn("75.0", table)


class DeclaredLimits(unittest.TestCase):
    def test_limits_file_declares_s0_to_s2_with_placeholder_margins(self):
        data = json.loads((ROOT / "budgets" / "limits.json").read_text())
        for step in ("S0", "S1", "S2"):
            self.assertEqual(
                {"FLASH", "RAM", "ITCM", "DTCM", "OCRAM", "OCRAM2", "IDT_LIST"},
                set(data["min_free_percent"][step]),
            )
            self.assertTrue(all(v == 25 for v in data["min_free_percent"][step].values()))

    def test_the_s0_fixture_passes_the_declared_limits(self):
        data = json.loads((ROOT / "budgets" / "limits.json").read_text())
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        build = make_build_dir(pathlib.Path(directory.name) / "build")
        self.assertEqual([], check.check(collect.collect(build, "S0"), data))


class BudgetWorkflow(unittest.TestCase):
    def load(self):
        import yaml

        return yaml.safe_load((ROOT / ".github" / "workflows" / "budget.yml").read_text())

    def commands(self):
        job = self.load()["jobs"]["budget"]
        return "\n".join(step.get("run", "") for step in job["steps"])

    def test_every_step_is_built_with_the_gate_required(self):
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", self.commands())

    def test_the_job_collects_checks_and_summarises(self):
        commands = self.commands()
        self.assertIn("budgets/collect.py", commands)
        self.assertIn("budgets/check.py", commands)
        self.assertIn("GITHUB_STEP_SUMMARY", commands)

    def test_the_job_covers_the_declared_steps_and_uploads_nothing(self):
        job = self.load()["jobs"]["budget"]
        steps = {entry["step"] for entry in job["strategy"]["matrix"]["include"]}
        data = json.loads((ROOT / "budgets" / "limits.json").read_text())
        self.assertTrue(steps <= set(data["min_free_percent"]))
        for step in job["steps"]:
            self.assertNotIn("upload-artifact", step.get("uses", ""))


class CommandLine(unittest.TestCase):
    def test_collect_then_check_through_the_command_line(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        build = make_build_dir(pathlib.Path(directory.name) / "build")
        out = pathlib.Path(directory.name) / "s0.json"
        collected = subprocess.run(
            [sys.executable, str(ROOT / "budgets" / "collect.py"), "--build-dir", str(build),
             "--step", "S0", "--out", str(out)],
            capture_output=True, text=True,
        )
        self.assertEqual(0, collected.returncode, collected.stderr)
        checked = subprocess.run(
            [sys.executable, str(ROOT / "budgets" / "check.py"), "--measurement", str(out),
             "--limits", str(ROOT / "budgets" / "limits.json")],
            capture_output=True, text=True,
        )
        self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)

    def test_check_exits_one_on_a_violation(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        measurement_path = pathlib.Path(directory.name) / "m.json"
        limits_path = pathlib.Path(directory.name) / "l.json"
        measurement_path.write_text(
            json.dumps(measurement({"FLASH": {"used": 999, "size": 1000}}))
        )
        limits_path.write_text(json.dumps(limits({"S2": {"FLASH": 25}})))
        result = subprocess.run(
            [sys.executable, str(ROOT / "budgets" / "check.py"), "--measurement",
             str(measurement_path), "--limits", str(limits_path)],
            capture_output=True, text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("FLASH", result.stdout)


if __name__ == "__main__":
    unittest.main()
