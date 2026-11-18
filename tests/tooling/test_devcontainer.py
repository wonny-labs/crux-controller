# SPDX-License-Identifier: Apache-2.0
"""Checks of the dev container: the image is pinned and agrees with the CI jobs it stands in for.

The dev container is a convenience for a developer on Windows with WSL2 and Docker Engine. CI stays the
reference. These tests read files only; they do not start Docker or use the network.
"""

import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEVCONTAINER = ROOT / ".devcontainer"
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
WORKFLOW = WORKFLOWS / "devcontainer.yml"


def read(path):
    return pathlib.Path(path).read_text()


def ci_job(name):
    return yaml.safe_load(read(CI))["jobs"][name]


def ci_step(job, fragment):
    matches = [step for step in ci_job(job)["steps"] if fragment in step.get("name", "")]
    assert len(matches) == 1, f"{fragment!r} in {job}: {len(matches)} steps"
    return matches[0]


def norm(text):
    """Collapse whitespace and line continuations so that a command compares by its words."""
    return " ".join(text.replace("\\", " ").split())


def requirement_pins(text):
    return dict(re.findall(r"^([A-Za-z0-9_.-]+)==(\S+)$", text, re.MULTILINE))


class Dockerfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(DEVCONTAINER / "Dockerfile")

    def test_the_base_image_is_ubuntu_24_04_pinned_by_digest(self):
        first = next(line for line in self.text.splitlines() if line.startswith("FROM "))
        self.assertRegex(first, r"^FROM \S*ubuntu-24\.04@sha256:[0-9a-f]{64}$")

    def test_there_is_only_one_base_image(self):
        self.assertEqual(1, len(re.findall(r"^FROM ", self.text, re.MULTILINE)))

    def test_the_zephyr_sdk_version_is_the_one_of_the_ci_jobs(self):
        sdk = ci_job("s1")["env"]["SDK_VERSION"]
        self.assertRegex(self.text, rf"(?m)^ENV ZEPHYR_SDK_VERSION={re.escape(sdk)}\b")

    def test_every_ci_job_that_uses_the_sdk_uses_the_same_version_as_the_image(self):
        versions = {ci_job(name)["env"]["SDK_VERSION"] for name in ("s1", "s2", "s3", "s4", "s5", "s6")}
        self.assertEqual(1, len(versions), versions)

    def test_the_host_packages_of_the_s1_job_are_installed(self):
        run = ci_step("s1", "Install host packages")["run"]
        wanted = set(run.split("--no-install-recommends", 1)[1].replace("\\", " ").split())
        self.assertTrue({"build-essential", "gcc-multilib", "device-tree-compiler", "gperf",
                         "libmagic1", "libsdl2-dev", "python3-dev", "xz-utils"} <= wanted, wanted)
        for package in wanted:
            self.assertRegex(self.text, rf"(?m)^\s+{re.escape(package)}( \\)?$", package)

    def test_the_virtual_environment_package_is_installed(self):
        self.assertRegex(self.text, r"(?m)^\s+python3-venv( \\)?$")

    def test_clang_tidy_is_the_version_that_the_static_analysis_job_pins(self):
        run = ci_step("static", "Install the pinned tools")["run"]
        pinned = re.search(r"clang-tidy-18=(\S+)", run).group(0)
        self.assertIn(pinned, self.text)

    def test_the_image_does_not_bake_in_secrets_or_the_workspace(self):
        for word in ("COPY ", "ADD ", "docker.sock", "host.docker.internal"):
            self.assertNotIn(word, self.text)

    def test_the_image_selects_the_sdk_and_the_virtual_environment(self):
        self.assertIn("ZEPHYR_SDK_INSTALL_DIR=/opt/crux-cache/sdk/zephyr-sdk-${ZEPHYR_SDK_VERSION}", self.text)
        self.assertIn("/opt/crux-cache/venv/bin", self.text)


class RepositoryFiles(unittest.TestCase):
    """A zip copy or a Windows checkout must not turn the container scripts into CRLF files."""

    @classmethod
    def setUpClass(cls):
        cls.attributes = read(ROOT / ".gitattributes").splitlines()
        cls.ignore = read(ROOT / ".gitignore").splitlines()

    def test_gitattributes_normalises_text_and_pins_lf_for_the_files_the_container_runs(self):
        for line in ("* text=auto", "*.sh text eol=lf", "*.py text eol=lf", ".devcontainer/** text eol=lf",
                     "*.cmake text eol=lf", "CMakeLists.txt text eol=lf", "Kconfig text eol=lf",
                     "*.yml text eol=lf", "*.md text eol=lf"):
            self.assertIn(line, self.attributes)

    def test_gitattributes_marks_no_binary_pattern_without_such_a_file(self):
        # The repository tracks no image, archive or other binary file, so no pattern is needed.
        marked = [line.split()[0] for line in self.attributes if line.split()[1:] == ["binary"]]
        self.assertEqual([], marked)

    def test_gitignore_keeps_python_caches_and_twister_output_out_of_the_tree(self):
        for line in ("build/", ".venv/", "__pycache__/", "*.pyc", "twister-out*/", ".pytest_cache/"):
            self.assertIn(line, self.ignore)

    def test_the_container_files_use_lf_line_endings(self):
        files = sorted(DEVCONTAINER.iterdir()) + [ROOT / "scripts" / "dev-shell.sh"]
        for path in files:
            self.assertNotIn(b"\r", path.read_bytes(), path.name)


class HostFixture:
    """A throwaway workspace folder with a copy of the files the host-side checks use."""

    def __init__(self, clone="crux-controller", scripts=("check-host.sh",)):
        self.directory = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.directory.name).resolve()
        self.workspace = self.base / "ws"
        self.home = self.base / "home"
        self.repo = self.workspace / clone
        for path in (self.home, self.repo / ".devcontainer", self.repo / "scripts"):
            path.mkdir(parents=True)
        for name in scripts:
            source = DEVCONTAINER / name
            if not source.exists():
                source = ROOT / "scripts" / name
            target = (self.repo / ("scripts" if source.parent.name == "scripts" else ".devcontainer") / name)
            shutil.copy(source, target)

    def close(self):
        self.directory.cleanup()

    def check_host(self, **env):
        # Only bash and the coreutils of the host: this is what a WSL distribution is sure to have.
        environment = {"PATH": "/usr/bin:/bin", "HOME": str(self.home)}
        environment.update(env)
        return subprocess.run(["bash", str(self.repo / ".devcontainer" / "check-host.sh")],
                              env=environment, capture_output=True, text=True)


class CheckHostScript(unittest.TestCase):
    path = DEVCONTAINER / "check-host.sh"

    def setUp(self):
        self.fixture = HostFixture()
        self.addCleanup(self.fixture.close)

    def test_the_script_is_an_executable_bash_script_with_the_spdx_line_second(self):
        lines = read(self.path).splitlines()
        self.assertEqual("#!/usr/bin/env bash", lines[0])
        self.assertEqual("# SPDX-License-Identifier: Apache-2.0", lines[1])
        self.assertIn("set -euo pipefail", lines)
        self.assertTrue(os.access(self.path, os.X_OK))

    def test_it_accepts_the_layout_of_the_documentation_without_a_word(self):
        for name in ("crux-controller", ".west", "zephyr", "modules", "bootloader", "tools", "crux-pilot",
                     "twister-out", "twister-out-s1"):
            (self.fixture.workspace / name).mkdir(exist_ok=True)
        result = self.fixture.check_host()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout + result.stderr)

    def test_it_refuses_a_clone_that_is_not_named_crux_controller(self):
        fixture = HostFixture(clone="crux-controller-main")
        self.addCleanup(fixture.close)
        result = fixture.check_host()
        self.assertEqual(2, result.returncode)
        self.assertIn("check-host:", result.stderr)
        self.assertIn("crux-controller-main", result.stderr)
        self.assertIn("named crux-controller", result.stderr)

    def test_it_refuses_the_home_directory_as_the_parent_folder(self):
        result = self.fixture.check_host(HOME=str(self.fixture.workspace))
        self.assertEqual(2, result.returncode)
        self.assertIn("home directory", result.stderr)

    def test_it_refuses_a_home_directory_that_is_reached_through_a_symbolic_link(self):
        link = self.fixture.base / "link-to-ws"
        link.symlink_to(self.fixture.workspace)
        result = self.fixture.check_host(HOME=str(link))
        self.assertEqual(2, result.returncode)
        self.assertIn("home directory", result.stderr)

    def test_it_refuses_a_parent_folder_that_holds_a_home_directory_marker(self):
        for marker in (".ssh", ".gnupg", ".bashrc", ".profile", ".gitconfig"):
            with self.subTest(marker=marker):
                path = self.fixture.workspace / marker
                path.mkdir() if marker in (".ssh", ".gnupg") else path.write_text("x\n")
                result = self.fixture.check_host()
                self.assertEqual(2, result.returncode)
                self.assertIn(marker, result.stderr)
                self.assertIn("looks like a home directory", result.stderr)
                shutil.rmtree(path) if path.is_dir() else path.unlink()

    def test_it_refuses_the_root_directory_as_the_parent_folder(self):
        text = read(self.path)
        self.assertIn('"/"', text)

    def test_it_only_warns_about_other_entries_in_the_parent_folder(self):
        (self.fixture.workspace / "zephyr").mkdir()
        (self.fixture.workspace / "holiday-photos").mkdir()
        (self.fixture.workspace / ".hidden-notes").write_text("x\n")
        (self.fixture.workspace / "twister-out-s2").mkdir()
        result = self.fixture.check_host()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("warning", result.stderr)
        self.assertIn("holiday-photos", result.stderr)
        self.assertIn(".hidden-notes", result.stderr)
        self.assertNotIn("zephyr", result.stderr)
        self.assertNotIn("twister-out-s2", result.stderr)

    def test_the_messages_go_to_the_standard_error_stream(self):
        (self.fixture.workspace / "other").mkdir()
        result = self.fixture.check_host()
        self.assertEqual("", result.stdout)

    def test_it_needs_no_tool_beyond_bash_and_the_coreutils(self):
        text = read(self.path)
        for tool in ("docker", "git ", "python", "realpath", "readlink -f", "find ", "-printf"):
            self.assertNotIn(tool, text)


class Requirements(unittest.TestCase):
    def test_the_tool_pins_are_those_of_the_ci_jobs(self):
        pins = requirement_pins(read(DEVCONTAINER / "requirements-tools.txt"))
        ci_tools = requirement_pins("\n".join(
            re.findall(r"(?:cmake|ninja|west)==\S+", ci_step("s1", "Install pinned build tools")["run"])
        ).replace(" ", "\n"))
        self.assertEqual({"cmake", "ninja", "west"}, set(ci_tools))
        for name, version in ci_tools.items():
            self.assertEqual(version, pins.get(name), name)
        formatter = re.search(r"clang-format==(\S+)", ci_step("static", "Install the pinned tools")["run"])
        self.assertEqual(formatter.group(1), pins.get("clang-format"))
        self.assertIn("pyyaml", pins)

    def test_every_line_is_pinned(self):
        for line in read(DEVCONTAINER / "requirements-tools.txt").splitlines():
            if line.strip() and not line.startswith("#"):
                self.assertRegex(line, r"^[A-Za-z0-9_.-]+==\S+$")


class DevcontainerJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(DEVCONTAINER / "devcontainer.json")
        cls.data = json.loads(cls.text)

    def test_it_builds_the_dockerfile_for_amd64(self):
        self.assertEqual("Dockerfile", self.data["build"]["dockerfile"])
        self.assertIn("--platform=linux/amd64", self.data["build"]["options"])

    def test_it_needs_no_docker_desktop_feature_and_no_host_access(self):
        for word in ("host.docker.internal", "docker.sock", "--privileged", "gateway", "/mnt/c", "${localEnv:HOME}"):
            self.assertNotIn(word, self.text)
        self.assertNotIn("features", self.data)

    def test_the_user_follows_the_uid_of_the_host_user(self):
        self.assertEqual("vscode", self.data["remoteUser"])
        self.assertIs(True, self.data["updateRemoteUserUID"])

    def test_the_workspace_is_the_parent_folder_with_the_clone_named_crux_controller(self):
        self.assertIn("source=${localWorkspaceFolder}/..,", self.data["workspaceMount"])
        target = re.search(r"target=([^,]+)", self.data["workspaceMount"]).group(1)
        self.assertEqual(f"{target}/crux-controller", self.data["workspaceFolder"])

    def test_the_sdk_and_the_virtual_environment_live_in_a_named_volume_of_this_container(self):
        # One volume for each dev container, so that two workspaces with different Zephyr
        # requirements do not share (and keep replacing) one virtual environment.
        self.assertTrue(any(
            "target=/opt/crux-cache" in mount and "type=volume" in mount
            and "${devcontainerId}" in mount for mount in self.data["mounts"]
        ), self.data["mounts"])

    def test_the_setup_script_runs_after_creation(self):
        self.assertEqual("bash .devcontainer/setup.sh", self.data["postCreateCommand"])

    def test_the_workspace_target_is_the_one_of_the_dockerfile_environment(self):
        target = re.search(r"target=([^,]+)", self.data["workspaceMount"]).group(1)
        self.assertIn(f"ZEPHYR_BASE={target}/zephyr", read(DEVCONTAINER / "Dockerfile"))


class SetupScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(DEVCONTAINER / "setup.sh")

    def test_it_stops_on_the_first_error(self):
        self.assertIn("set -euo pipefail", self.text)

    def test_west_init_and_update_run_only_when_the_workspace_is_not_initialised(self):
        guard = self.text.index('if [[ ! -d "$workspace/.west"')
        init = self.text.index("west init -l crux-controller", guard)
        update = self.text.index("west update\n", init)
        self.assertLess(guard, init)
        self.assertLess(init, update)

    def test_an_interrupted_update_is_run_again(self):
        # The pending marker is written after west init and removed only after west update ends.
        self.assertIn('pending="$workspace/.west/crux-devcontainer-update.pending"', self.text)
        guard = self.text.index('if [[ ! -d "$workspace/.west"')
        condition = self.text[guard:self.text.index("then", guard)]
        self.assertIn('-f "$pending"', condition)
        init = self.text.index("west init -l crux-controller", guard)
        touch = self.text.index('touch "$pending"', init)
        update = self.text.index("west update\n", touch)
        remove = self.text.index('rm -f "$pending"', update)
        self.assertLess(init, touch)
        self.assertLess(update, remove)

    def test_the_setup_does_not_read_the_standard_input_of_the_caller(self):
        self.assertIn("</dev/null", read(ROOT / "scripts" / "dev-shell.sh"))

    def test_it_runs_the_sdk_install_of_the_s1_job_with_the_same_toolchain(self):
        run = ci_step("s1", "Install the Zephyr SDK")["run"]
        self.assertIn("--gnu-toolchains arm-zephyr-eabi", run)
        self.assertIn("--gnu-toolchains arm-zephyr-eabi", self.text)
        self.assertIn('sdk_version="${ZEPHYR_SDK_VERSION:?', self.text)
        self.assertIn('west sdk install --version "$sdk_version"', self.text)

    def test_it_installs_the_three_zephyr_requirement_files_of_the_s1_job(self):
        run = ci_step("s1", "Fetch the workspace")["run"]
        for name in ("requirements-base.txt", "requirements-build-test.txt", "requirements-run-test.txt"):
            self.assertIn(name, run)
            self.assertIn(name, self.text)

    def test_it_does_not_switch_the_mbed_group_on(self):
        self.assertNotIn("group-filter", self.text)

    def test_it_refuses_a_home_directory_as_the_workspace(self):
        self.assertIn(".bashrc", self.text)


class DevShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "scripts" / "dev-shell.sh"
        cls.text = read(cls.path)

    def test_the_script_is_executable_and_stops_on_error(self):
        self.assertTrue(os.access(self.path, os.X_OK))
        self.assertTrue(self.text.startswith("#!/usr/bin/env bash"))
        self.assertIn("set -euo pipefail", self.text)

    def test_it_builds_the_same_dockerfile_and_runs_the_same_setup(self):
        self.assertIn(".devcontainer", self.text)
        self.assertIn("setup.sh", self.text)
        self.assertIn("--platform linux/amd64", self.text)

    def test_it_mounts_the_workspace_where_the_dev_container_does(self):
        data = json.loads(read(DEVCONTAINER / "devcontainer.json"))
        target = re.search(r"target=([^,]+)", data["workspaceMount"]).group(1)
        self.assertIn(target, self.text)
        volume = re.search(r"source=([^,$]+)", " ".join(data["mounts"])).group(1)
        self.assertIn(volume, self.text)
        self.assertIn('volume="$volume_prefix-$(', self.text)  # one volume for each workspace folder

    def test_it_passes_a_piped_standard_input_to_the_command(self):
        self.assertIn("! -t 0", self.text)

    def test_it_uses_no_privilege_no_socket_and_no_home_mount(self):
        for word in ("--privileged", "docker.sock", "host.docker.internal", '"$HOME"', "--network host"):
            self.assertNotIn(word, self.text)

    def test_it_passes_the_host_user_id_to_the_image(self):
        self.assertIn("USER_UID", self.text)
        self.assertIn("USER_GID", self.text)
        self.assertIn("USER_UID", read(DEVCONTAINER / "Dockerfile"))


class DevcontainerWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(WORKFLOW)
        cls.data = yaml.safe_load(cls.text)
        # PyYAML reads the key "on" as the boolean True.
        cls.on = cls.data.get("on", cls.data.get(True))
        cls.job = next(iter(cls.data["jobs"].values()))
        cls.commands = "\n".join(step.get("run", "") for step in cls.job["steps"])

    def test_it_runs_on_the_files_that_decide_the_container_and_by_hand(self):
        self.assertEqual({"pull_request", "push", "workflow_dispatch"}, set(self.on))
        self.assertEqual(["main"], self.on["push"]["branches"])
        self.assertEqual(self.on["pull_request"]["paths"], self.on["push"]["paths"])
        paths = self.on["pull_request"]["paths"]
        # west.yml moves the pin, and with it the Zephyr requirement files that setup.sh installs.
        for path in (".devcontainer/**", "scripts/dev-shell.sh", "west.yml",
                     ".github/workflows/devcontainer.yml"):
            self.assertIn(path, paths)

    def test_the_permissions_are_read_only_and_set_once(self):
        self.assertEqual({"contents": "read"}, self.data["permissions"])
        self.assertNotIn("permissions", self.job)

    def test_it_uploads_nothing_and_starts_no_hardware_command(self):
        for word in ("upload-artifact", "west flash", "west debug", "JLink", "pyocd", "openocd"):
            self.assertNotIn(word, self.text)

    def test_it_uses_only_the_actions_that_ci_yml_uses(self):
        allowed = set(re.findall(r"uses: (\S+)", read(CI)))
        used = set(re.findall(r"uses: (\S+)", self.text))
        self.assertTrue(used <= allowed, used - allowed)

    def test_it_runs_the_checks_inside_the_container_through_the_script(self):
        self.assertIn("scripts/dev-shell.sh", self.commands)
        self.assertIn("python -m unittest discover -s tests/tooling", self.commands)
        self.assertIn("check_boundary.py --repo crux-controller --crux-root crux-pilot", self.commands)
        self.assertIn("west twister -p native_sim/native/64 -T crux-controller/tests/native_sim", self.commands)
        self.assertIn("--inline-logs --clobber-output", self.commands)

    def test_the_twister_step_matches_the_one_of_the_s1_job(self):
        run = " ".join(ci_step("s1", "Run the S1 scenario on native_sim")["run"].replace("\\", " ").split())
        self.assertIn(run, " ".join(self.commands.replace("\\", " ").split()))

    def test_the_product_include_check_runs_the_script_of_the_pin_after_checking_its_hash(self):
        # The pinned crux-pilot contains the script, with the hash that ci.yml checks the download
        # against. The container job runs that copy instead of downloading a second one.
        expected = ci_step("boundary", "Run the Crux Pilot product include check")["env"]["CHECK_SHA256"]
        steps = [step for step in self.job["steps"] if "product include check" in step.get("name", "")]
        self.assertEqual(1, len(steps))
        step = steps[0]
        self.assertEqual(expected, step["env"]["CHECK_SHA256"])
        run = step["run"]
        self.assertNotIn("curl", run)
        self.assertLess(run.index("sha256sum --check"), run.index("dev-shell.sh"))
        self.assertIn("crux-pilot/templates/product/check_domain_includes.py", run)
        self.assertIn("--product", run)

    def test_the_s1_steps_after_twister_are_those_of_the_s1_job(self):
        board = ci_job("s1")["env"]["BOARD"]
        commands = norm(self.commands)
        for fragment in ("Cross-build S1 with the baseline gate required", "Check the outputs exist",
                         "Check the resolved S1 configuration"):
            run = ci_step("s1", fragment)["run"].replace("${{ env.BOARD }}", board)
            self.assertIn(norm(run), commands, fragment)
        self.assertIn("-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON", self.commands)

    def test_the_host_tests_run_with_the_sanitizers_off_and_on_as_ci_does(self):
        matrix = ci_job("host")["strategy"]["matrix"]["sanitize"]
        self.assertEqual(["OFF", "ON"], matrix)
        for value in matrix:
            self.assertIn(f"-DWORKLOAD_SANITIZE={value}", self.commands)

    def test_the_job_has_a_time_limit_and_the_ubuntu_runner_of_ci(self):
        self.assertEqual("ubuntu-24.04", self.job["runs-on"])
        self.assertIn("timeout-minutes", self.job)


class Documentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = read(ROOT / "docs" / "try-on-native-sim.md")
        cls.section = cls.page[cls.page.index("## Dev container"):cls.page.index("## If something fails")]
        cls.readme = read(ROOT / "README.md")

    def test_the_section_says_that_nobody_ran_it_on_wsl2_and_only_x86_64_ran_in_ci(self):
        self.assertIn("Nobody has run it on WSL2 yet", self.section)
        self.assertIn("x86_64", self.section)
        self.assertIn("binfmt", self.section)
        self.assertNotIn("emulated and slow", self.section)

    def test_the_readme_does_not_promise_other_architectures(self):
        line = self.readme[self.readme.index("On Windows with WSL2"):]
        line = line[:line.index("yet)")]
        self.assertIn("x86_64", line)
        self.assertNotIn("any host", line)

    def test_the_section_names_the_differences_from_the_ci_runner(self):
        for word in ("actions/setup-python", "python3-venv", "curl", "sudo", "clang-tidy-18"):
            self.assertIn(word, self.section)

    def test_the_section_says_what_the_container_job_builds_and_runs(self):
        self.assertIn("RT1060-EVKB", self.section)
        self.assertIn("cross-build", self.section)

    def test_the_section_covers_a_failed_setup_and_the_wsl_resources(self):
        self.assertIn("bash .devcontainer/setup.sh", self.section)
        self.assertIn(".wslconfig", self.section)
        self.assertIn("processors", self.section)

    def test_the_product_include_check_is_not_said_to_predate_the_pin_in_the_workflow(self):
        self.assertNotIn("predates", read(WORKFLOW))


if __name__ == "__main__":
    unittest.main()
