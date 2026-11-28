# SPDX-License-Identifier: Apache-2.0
"""Checks of tests/template/run.sh, the template check of criterion 47, with fakes in place of west,
the image and the host timeout.

The rules held here:

- the workspace step follows the joining steps of template/README.md with the commit of the clone
  that runs it, clones that commit before west update, checks the resolved project list, the
  framework's commit and the template checks of the copy, and refuses a folder that it did not make;
- the build steps use the verified Zephyr gate; the native_sim build checks that the framework is the
  project of the workspace, and the board build refuses the options of a development build;
- the run step passes only when the log shows init and then start of the template's descriptor;
- the template's build file and path check runs for every change in the job boundary; the steps of
  this script are nightly checks: the native_sim steps in the job template, the board build in the
  job base, where the Zephyr SDK is.
"""

import os
import pathlib
import re
import stat
import subprocess
import tempfile
import unittest

import ci_map

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUN = ROOT / "tests" / "template" / "run.sh"
NATIVE_OPTIONS = ("CONFIG_ZEPHYR_CRUX_CONTROLLER_MODULE=y", "CONFIG_CRUX_CONTROLLER_FRAMEWORK=y",
                  "CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION=y", "CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT=y",
                  "CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL=y", "CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC=y")
BOARD_OPTIONS = NATIVE_OPTIONS + ("CONFIG_STACK_CANARIES=y", "CONFIG_HW_STACK_PROTECTION=y", "CONFIG_RETENTION=y")

# A fake west: `west build ... -d DIR ...` writes the outputs of a build into DIR from the variables
# FAKE_CONFIG and FAKE_DTS, and the module list names FAKE_MODULE; anything else fails.
FAKE_WEST = """#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == build ]] || exit 9
dir=
while [[ $# -gt 0 ]]; do
    if [[ "$1" == -d ]]; then dir=$2; shift; fi
    shift
done
mkdir -p "$dir/zephyr"
printf '%b' "$FAKE_CONFIG" > "$dir/zephyr/.config"
printf '%b' "$FAKE_DTS" > "$dir/zephyr/zephyr.dts"
printf '%s:%s\\n' crux-controller "$FAKE_MODULE" > "$dir/zephyr_modules.txt"
: > "$dir/zephyr/zephyr.bin"
: > "$dir/zephyr/zephyr.elf"
"""
# A host timeout for any host: drop -k SECONDS and the duration, run the rest.
FAKE_TIMEOUT = """#!/usr/bin/env bash
[[ "$1" == -k ]] && shift 2
shift
exec "$@"
"""


def executable(path, text):
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class Fakes:
    """A workspace folder made as the script makes it, and a folder of fake commands."""

    def __init__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._dir.name)
        self.folder = self.root / "workspace"
        (self.folder / ".west").mkdir(parents=True)
        (self.folder / ".template-workspace").write_text("")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        executable(self.bin / "west", FAKE_WEST)
        executable(self.bin / "timeout", FAKE_TIMEOUT)

    def image(self, lines, status=0):
        exe = self.folder / "build" / "native_sim" / "zephyr" / "zephyr.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"echo '{line}'\n" for line in lines)
        executable(exe, f"#!/usr/bin/env bash\necho \"args: $*\"\n{body}exit {status}\n")

    def run(self, step, **env):
        return subprocess.run(["bash", str(RUN), step, str(self.folder)], capture_output=True, text=True,
                              env={**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                                   "CRUX_TEMPLATE_ANY_HOST": "1", **env})

    def close(self):
        self._dir.cleanup()


class RunStep(unittest.TestCase):
    def setUp(self):
        self.fakes = Fakes()
        self.addCleanup(self.fakes.close)

    def test_init_then_start_passes_and_the_simulation_stops_at_a_time_limit(self):
        self.fakes.image(["<inf> crux_logging: framework: step", "<inf> crux_logging: product: init",
                          "<inf> crux_logging: product: start"])
        result = self.fakes.run("run")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("args: --stop_at=30", result.stdout)

    def test_start_before_init_fails(self):
        self.fakes.image(["<inf> crux_logging: product: start", "<inf> crux_logging: product: init"])
        self.assertEqual(1, self.fakes.run("run").returncode)

    def test_a_missing_entry_fails(self):
        for lines in (["<inf> crux_logging: product: init"], ["<inf> crux_logging: product: start"], []):
            with self.subTest(lines=lines):
                self.fakes.image(lines)
                self.assertEqual(1, self.fakes.run("run").returncode)

    def test_an_image_that_fails_fails(self):
        self.fakes.image(["<inf> crux_logging: product: init", "<inf> crux_logging: product: start"], status=3)
        self.assertEqual(1, self.fakes.run("run").returncode)


class BuildSteps(unittest.TestCase):
    def setUp(self):
        self.fakes = Fakes()
        self.addCleanup(self.fakes.close)

    def build(self, step, options, dts="crux-watchdog0 controller_storage controller_retained\n", module=None):
        module = module or str(self.fakes.folder / "crux-controller")
        return self.fakes.run(step, FAKE_CONFIG="\\n".join(options) + "\\n", FAKE_DTS=dts, FAKE_MODULE=module)

    def test_the_native_sim_build_passes_with_the_framework_of_the_workspace(self):
        result = self.build("build", NATIVE_OPTIONS)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_the_native_sim_build_fails_without_a_service_or_with_another_module(self):
        for missing in NATIVE_OPTIONS:
            with self.subTest(missing=missing):
                self.assertEqual(1, self.build("build", [o for o in NATIVE_OPTIONS if o != missing]).returncode)
        self.assertEqual(1, self.build("build", NATIVE_OPTIONS, module="/elsewhere/crux-controller").returncode)

    def test_the_board_build_passes_with_the_product_options(self):
        result = self.build("board", BOARD_OPTIONS)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("No flash", result.stdout)

    def test_the_board_build_refuses_a_development_option(self):
        for option in ("CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG=y", "CONFIG_FAKE_ENTROPY_NATIVE_SIM=y",
                       "CONFIG_TEST_RANDOM_GENERATOR=y", "CONFIG_SHELL=y", "CONFIG_TASK_WDT_HW_FALLBACK=y",
                       "CONFIG_CRUX_DEVELOPMENT_IMAGE=y", "CONFIG_CRUX_WEB_PLAIN_HTTP_FOR_TESTS=y"):
            with self.subTest(option=option):
                self.assertEqual(1, self.build("board", BOARD_OPTIONS + (option,)).returncode)

    def test_the_board_build_needs_the_hardening_and_the_devicetree_roles(self):
        for missing in BOARD_OPTIONS:
            with self.subTest(missing=missing):
                self.assertEqual(1, self.build("board", [o for o in BOARD_OPTIONS if o != missing]).returncode)
        self.assertEqual(1, self.build("board", BOARD_OPTIONS, dts="controller_storage\n").returncode)


class Script(unittest.TestCase):
    def setUp(self):
        # The commands of the script, without its comment lines.
        self.text = "\n".join(line for line in RUN.read_text().splitlines()
                              if not line.lstrip().startswith("#") or line.startswith("#!"))

    def test_the_script_is_executable_and_strict(self):
        self.assertTrue(os.access(RUN, os.X_OK))
        self.assertTrue(self.text.startswith("#!/usr/bin/env bash\n"))
        self.assertIn("set -euo pipefail", self.text)

    def test_the_workspace_follows_the_joining_steps_with_the_commit_of_the_clone(self):
        self.assertIn("rev-parse HEAD", self.text)
        self.assertIn('cp -R "$repo/template" "$folder/product"', self.text)
        self.assertIn('scripts/pin_framework.py" --framework "$repo"', self.text)
        self.assertIn("west init -l product", self.text)
        self.assertLess(self.text.index("git clone"), self.text.index("west update"))
        self.assertIn("checkout --quiet --detach", self.text)

    def workspace_body(self):
        start = self.text.index("make_workspace() {")
        return self.text[start:self.text.index("\n}\n", start)]

    def test_the_project_list_is_checked_before_the_mbed_modules_are_fetched(self):
        # The order of tests/product_integration/run.sh (CONTRIBUTING.md, "The pin and the
        # manifest"): the copy's manifest switches the group on, so the first update runs with the
        # group off, and nothing of the group is fetched before both checks passed.
        body = self.workspace_body()
        steps = ["west config --local manifest.group-filter -- -crux-secure-management",
                 "update_workspace",
                 "check_mbed_only.py --mode default < list-default.txt",
                 "west config --local --delete manifest.group-filter",
                 "check_mbed_only.py --mode mbed --baseline list-default.txt < list-mbed.txt"]
        positions = [body.index(step) for step in steps]
        self.assertEqual(sorted(positions), positions)
        second_update = body.index("update_workspace", positions[1] + 1)
        self.assertLess(positions[-1], second_update)
        self.assertEqual(2, body.count("update_workspace"))
        self.assertNotIn("west update", body)
        self.assertNotIn("+crux-secure-management", self.text)
        self.assertIn("west update --path-cache \"$CRUX_TEMPLATE_WEST_CACHE\"", self.text)

    def test_the_workspace_checks_the_project_list_the_commit_and_the_copy(self):
        body = self.workspace_body()
        update = body.rindex("update_workspace")
        for needle in ("rev-parse HEAD)\" == \"$sha\"", "west list crux-controller -f '{sha}'",
                       "scripts/check_template.py\" --root \"$folder/product\"", "pip install"):
            with self.subTest(needle=needle):
                self.assertLess(update, body.index(needle))
        self.assertLess(body.index("--mode mbed"), update)
        for name in ("wolfssl", "wolfssh", "wolfpsa"):
            self.assertIn(name, body)

    def test_it_never_reuses_a_folder_that_it_did_not_make(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = pathlib.Path(directory) / "workspace"
            folder.mkdir()
            (folder / "keep.txt").write_text("not ours")
            result = subprocess.run(["bash", str(RUN), "workspace", str(folder)], capture_output=True, text=True,
                                    env={**os.environ, "CRUX_TEMPLATE_ANY_HOST": "1"})
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertTrue((folder / "keep.txt").is_file())

    def test_a_step_without_a_workspace_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            for step in ("build", "run", "test", "board"):
                with self.subTest(step=step):
                    result = subprocess.run(["bash", str(RUN), step, directory], capture_output=True, text=True,
                                            env={**os.environ, "CRUX_TEMPLATE_ANY_HOST": "1"})
                    self.assertEqual(1, result.returncode, result.stderr)

    def test_usage_errors_exit_2(self):
        for arguments in ([], ["unknown", "/tmp/x"], ["workspace"], ["workspace", ""], ["workspace", "/"],
                          ["build", "//"], ["run", "relative/folder"]):
            with self.subTest(arguments=arguments):
                result = subprocess.run(["bash", str(RUN), *arguments], capture_output=True, text=True,
                                        env={**os.environ, "CRUX_TEMPLATE_ANY_HOST": "1"})
                self.assertEqual(2, result.returncode, result.stderr)

    def test_every_build_uses_the_verified_zephyr_gate(self):
        self.assertEqual(2, self.text.count("west build -p always"))
        self.assertEqual(3, self.text.count("CRUX_REQUIRE_VERIFIED_ZEPHYR=ON"))
        self.assertIn("mimxrt1060_evk@B/mimxrt1062/qspi", self.text)
        self.assertIn("native_sim/native/64", self.text)

    def test_it_needs_linux_for_native_sim(self):
        self.assertIn("uname -s", self.text)


@ci_map.needs_tomllib
class NightlyChecks(unittest.TestCase):
    def test_the_job_template_runs_the_native_sim_steps_and_the_joining_test_in_the_nightly_tier(self):
        checks = ci_map.checks("template")
        self.assertEqual(["template-workspace", "template-build", "template-run", "template-test",
                          "template-joining-steps"], [c["id"] for c in checks])
        for check in checks:
            with self.subTest(check=check["id"]):
                self.assertEqual(["nightly"], check.get("tiers"))
        for step in ("workspace", "build", "run", "test"):
            self.assertIn(f'tests/template/run.sh {step} "${{RUNNER_TEMP:-/tmp}}/template"',
                          ci_map.run(f"template-{step}"))
        self.assertIn("CRUX_TEMPLATE_REQUIRE_WEST=1", ci_map.run("template-joining-steps"))
        self.assertIn("test_template_joining", ci_map.run("template-joining-steps"))

    def test_the_board_build_runs_in_the_base_job_after_its_sdk(self):
        ids = ci_map.ids("base")
        self.assertLess(ids.index("base-sdk"), ids.index("template-board-workspace"))
        self.assertEqual(ids.index("template-board-workspace") + 1, ids.index("template-board-build"))
        for check_id in ("template-board-workspace", "template-board-build"):
            with self.subTest(check=check_id):
                self.assertEqual(["nightly"], ci_map.check(check_id).get("tiers"))
        self.assertIn("CRUX_TEMPLATE_WEST_CACHE", ci_map.run("template-board-workspace"))
        self.assertIn('tests/template/run.sh board "${RUNNER_TEMP:-/tmp}/template-reference"',
                      ci_map.run("template-board-build"))
        # Crux's consumer boundary check refuses an include path with a native word after a
        # separator (cmake/CruxConsumerBoundary.cmake), so the workspace folder holds none.
        native = re.compile(r"(^|[/;:=<>_-])(zephyr|boards?|soc|vendor|nxp|cmsis|nrfx|mcux|fsl)"
                            r"([/;:=<>_-]|$)")
        for check_id in ("template-board-workspace", "template-board-build"):
            folder = re.search(r'"\$\{RUNNER_TEMP:-/tmp\}/([^"]+)"', ci_map.run(check_id)).group(1)
            self.assertIsNone(native.search("/" + folder.lower()), (check_id, folder))
        self.assertIn('CRUX_TEMPLATE_BOARD="$BOARD"', ci_map.run("template-board-build"))

    def test_the_template_check_runs_for_every_change_in_the_boundary_job(self):
        # Criterion 48 holds on every pull request, as the boundary check does.
        check = ci_map.check("template-check")
        self.assertEqual("boundary", check["job"])
        self.assertEqual("always", check["scope"])
        self.assertNotIn("tiers", check)
        self.assertIn("python scripts/check_template.py", check["run"])

    def test_the_job_template_prepares_nothing_outside_its_checks(self):
        self.assertEqual("", ci_map.prepare_branch("template").strip())


if __name__ == "__main__":
    unittest.main()
