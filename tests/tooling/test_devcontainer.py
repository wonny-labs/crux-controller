# SPDX-License-Identifier: Apache-2.0
"""Checks of the dev container: the image is pinned and agrees with the CI jobs it stands in for.

The dev container is a convenience for a developer on Windows with WSL2 and Docker Engine. CI stays the
reference. Most tests read files. The tests of setup.sh and check-host.sh run the real scripts in temporary
folders, against stand-ins for west, python3, sudo and docker. None of them starts Docker or uses the network.
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


def files_with_nul_bytes(root):
    """The files of `root` that hold NUL bytes: the tracked files of a Git checkout, else a walk.

    A zip copy has no .git. The walk then skips dot-files and the folders the build creates. A
    developer's untracked leftovers (a macOS .DS_Store) must not fail a teammate's run.
    """
    root = pathlib.Path(root).resolve()
    names = None
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True).stdout.strip()
        if pathlib.Path(top).resolve() == root:
            listing = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                                     capture_output=True, check=True).stdout
            names = [name for name in listing.decode().split("\0") if name]
    except (OSError, subprocess.CalledProcessError):
        names = None
    if names is None:
        skipped = {"build", ".venv", "__pycache__", ".pytest_cache"}
        names = []
        for directory, folders, files in os.walk(root):
            folders[:] = [f for f in folders if not f.startswith(".") and f not in skipped
                          and not f.startswith("twister-out")]
            names += [str((pathlib.Path(directory) / f).relative_to(root)) for f in files
                      if not f.startswith(".")]
    return sorted(name for name in names
                  if (root / name).is_file() and b"\0" in (root / name).read_bytes())


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
        sdk = ci_job("workload")["env"]["SDK_VERSION"]
        self.assertRegex(self.text, rf"(?m)^ENV ZEPHYR_SDK_VERSION={re.escape(sdk)}\b")

    def test_every_ci_job_that_uses_the_sdk_uses_the_same_version_as_the_image(self):
        versions = {ci_job(name)["env"]["SDK_VERSION"] for name in ("workload", "net", "file", "system", "sntp", "management")}
        self.assertEqual(1, len(versions), versions)

    def test_the_host_packages_of_the_workload_job_are_installed(self):
        run = ci_step("workload", "Install host packages")["run"]
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
        for word in ("ADD ", "docker.sock", "host.docker.internal"):
            self.assertNotIn(word, self.text)
        # The only COPY line takes the J-Link folder of the build context (.devcontainer/), never the
        # workspace. The certificate folder is bind-mounted, not copied (OrganisationCertificatesInTheImage).
        self.assertEqual(["COPY jlink/ /tmp/crux-jlink/"], re.findall(r"(?m)^COPY .*$", self.text))

    PROXY_NAMES = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy")

    def test_the_comment_says_what_the_test_checks_about_the_digest(self):
        # The test checks that the base image is pinned by a digest. It does not compare the digest with
        # anything, so the comment must not say that it checks the digest.
        self.assertNotIn("checks the digest", self.text)
        self.assertIn("checks that the base image is pinned by digest", " ".join(self.text.split()))

    def test_ca_certificates_and_curl_are_installed(self):
        for package in ("ca-certificates", "curl"):
            self.assertRegex(self.text, rf"(?m)^\s+{package}( \\)?$")

    def test_the_proxy_settings_are_not_declared_as_build_arguments(self):
        # Docker predefines the proxy build arguments: `--build-arg http_proxy=...` reaches the RUN
        # steps without an ARG line, and a predefined argument is left out of `docker history`. A
        # declared ARG would make a proxy URL with credentials visible in the history of the image.
        for name in self.PROXY_NAMES:
            self.assertNotRegex(self.text, rf"(?m)^ARG {name}\b", name)
        self.assertIn("predefined", " ".join(self.text.split()))

    def test_no_proxy_value_is_stored_in_the_image_environment(self):
        # No ENV line: it would keep the proxy of the company that built the image in every container.
        environment = re.findall(r"(?m)^ENV (?:[^\n]*\\\n)*[^\n]*$", self.text)
        self.assertTrue(environment)
        for block in environment:
            self.assertNotIn("proxy", block.lower())
        self.assertNotRegex(self.text, r"(?im)^(ENV|LABEL)\b.*proxy")

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
        for line in ("* text=auto eol=lf", "*.sh text eol=lf", "*.py text eol=lf", ".devcontainer/** text eol=lf",
                     "*.cmake text eol=lf", "CMakeLists.txt text eol=lf", "Kconfig text eol=lf",
                     "*.yml text eol=lf", "*.md text eol=lf"):
            self.assertIn(line, self.attributes)

    def test_the_default_line_ending_is_lf_so_that_core_autocrlf_false_does_not_give_crlf(self):
        # With core.autocrlf=false (the advice of the documentation) the default core.eol=native applies
        # to every text file without its own eol attribute. On Windows that is CRLF.
        self.assertEqual("* text=auto eol=lf", self.attributes[next(
            i for i, line in enumerate(self.attributes) if line and not line.startswith("#"))])

    def test_no_file_is_binary_so_no_binary_pattern_is_needed(self):
        self.assertEqual([], files_with_nul_bytes(ROOT), "a binary file needs a `binary` line in .gitattributes")
        marked = [line.split()[0] for line in self.attributes if line.split()[1:] == ["binary"]]
        self.assertEqual([], marked)

    def test_a_local_leftover_with_nul_bytes_is_not_a_tracked_binary_file(self):
        # A macOS .DS_Store holds NUL bytes. It is untracked on a teammate's machine and must not fail the test.
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory).resolve()
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            (root / "script.sh").write_text("echo ok\n")
            (root / "image.bin").write_bytes(b"a\0b")
            subprocess.run(["git", "-C", str(root), "add", "script.sh", "image.bin"], check=True)
            (root / ".DS_Store").write_bytes(b"\0\0\0")
            (root / "notes" / "scratch.dat").parent.mkdir()
            (root / "notes" / "scratch.dat").write_bytes(b"\0")
            self.assertEqual(["image.bin"], files_with_nul_bytes(root))

    def test_without_a_git_folder_dot_files_and_build_folders_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory).resolve()
            (root / ".DS_Store").write_bytes(b"\0")
            (root / "build").mkdir()
            (root / "build" / "out.bin").write_bytes(b"\0")
            (root / "twister-out-workload").mkdir()
            (root / "twister-out-workload" / "x.bin").write_bytes(b"\0")
            (root / "data.bin").write_bytes(b"\0")
            (root / "fine.txt").write_text("text\n")
            self.assertEqual(["data.bin"], files_with_nul_bytes(root))

    def test_gitignore_keeps_python_caches_and_twister_output_out_of_the_tree(self):
        for line in ("build/", ".venv/", "__pycache__/", "*.pyc", "twister-out*/", ".pytest_cache/"):
            self.assertIn(line, self.ignore)

    def test_the_container_files_use_lf_line_endings(self):
        # Every file under .devcontainer, including the J-Link folder. A J-Link package that a developer put
        # into .devcontainer/jlink/packages/ is a local binary, ignored by Git.
        files = sorted(p for p in DEVCONTAINER.rglob("*") if p.is_file() and p.suffix != ".deb")
        files += [ROOT / "scripts" / "dev-shell.sh", ROOT / "scripts" / "bootstrap.sh"]
        self.assertIn(DEVCONTAINER / "Dockerfile", files)
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
                     "twister-out", "twister-out-workload"):
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
        # A clone cannot be put in / in a test, so the real check function runs with that path.
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; check_layout /crux-controller /crux-controller', "check", str(self.path)],
            env={"PATH": "/usr/bin:/bin", "HOME": str(self.fixture.home)}, capture_output=True, text=True)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("directly in the root directory", result.stderr)

    def test_it_refuses_a_clone_folder_that_is_a_symbolic_link_hiding_a_home_directory_mount(self):
        # ~/crux-controller -> /somewhere/crux-controller: the logical parent is the home directory, and
        # a mount of <folder>/.. may resolve to it, so the logical parent is compared too.
        real = self.fixture.base / "real"
        (real / "crux-controller" / ".devcontainer").mkdir(parents=True)
        shutil.copy(self.path, real / "crux-controller" / ".devcontainer" / "check-host.sh")
        (self.fixture.home / "crux-controller").symlink_to(real / "crux-controller")
        script = self.fixture.home / "crux-controller" / ".devcontainer" / "check-host.sh"
        result = subprocess.run(["bash", str(script)], env={"PATH": "/usr/bin:/bin", "HOME": str(self.fixture.home)},
                                capture_output=True, text=True)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("home directory", result.stderr)

    def test_the_extra_certificate_file_of_the_workspace_is_not_a_stranger(self):
        (self.fixture.workspace / ".crux-extra-ca.crt").write_text("x\n")
        result = self.fixture.check_host()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout + result.stderr)

    def test_it_only_warns_about_other_entries_in_the_parent_folder(self):
        (self.fixture.workspace / "zephyr").mkdir()
        (self.fixture.workspace / "holiday-photos").mkdir()
        (self.fixture.workspace / ".hidden-notes").write_text("x\n")
        (self.fixture.workspace / "twister-out-net").mkdir()
        result = self.fixture.check_host()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("warning", result.stderr)
        self.assertIn("holiday-photos", result.stderr)
        self.assertIn(".hidden-notes", result.stderr)
        self.assertNotIn("zephyr", result.stderr)
        self.assertNotIn("twister-out-net", result.stderr)

    def test_the_messages_go_to_the_standard_error_stream(self):
        (self.fixture.workspace / "other").mkdir()
        result = self.fixture.check_host()
        self.assertEqual("", result.stdout)

    def test_it_needs_no_tool_beyond_bash_and_the_coreutils(self):
        text = read(self.path)
        for tool in ("docker", "git ", "python", "realpath", "readlink -f", "find ", "-printf"):
            self.assertNotIn(tool, text)


class CommentsDescribeWhatIsTrue(unittest.TestCase):
    """The comments of the container files must not present a change of dev-shell.sh as done."""

    def test_no_comment_says_that_dev_shell_passes_proxies_mounts_the_certificate_or_runs_the_host_check(self):
        for name in ("Dockerfile", "check-host.sh", "setup.sh"):
            text = " ".join(read(DEVCONTAINER / name).replace("# ", " ").split())
            for phrase in ("and scripts/dev-shell.sh pass", "scripts/dev-shell.sh mounts it",
                           "scripts/dev-shell.sh runs it before it builds"):
                self.assertNotIn(phrase, text, f"{name}: {phrase}")

    def test_the_setup_header_names_the_route_that_works_and_the_proxy_limits(self):
        header = read(DEVCONTAINER / "setup.sh").split("set -euo pipefail", 1)[0]
        for fragment in (".crux-extra-ca.crt", "/workspaces/ws/.crux-extra-ca.crt", "CRUX_EXTRA_CA_FILE",
                         "does not yet", "127.0.0.1", "docker inspect", "a terminal that you open later"):
            self.assertIn(fragment, header)


class Requirements(unittest.TestCase):
    def test_the_tool_pins_are_those_of_the_ci_jobs(self):
        pins = requirement_pins(read(DEVCONTAINER / "requirements-tools.txt"))
        ci_tools = requirement_pins("\n".join(
            re.findall(r"(?:cmake|ninja|west)==\S+", ci_step("workload", "Install pinned build tools")["run"])
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

    def test_the_vscode_extensions_survive_a_rebuild_in_a_folder_the_user_owns(self):
        # The volume keeps the installed extensions across rebuilds. The image creates the folder for the
        # user, so a new volume takes the user as owner instead of root.
        self.assertIn("target=/home/vscode/.vscode-server/extensions", " ".join(self.data["mounts"]))
        dockerfile = read(DEVCONTAINER / "Dockerfile")
        self.assertRegex(dockerfile, r'install -d -o "\$USER_UID" -g "\$USER_GID" [^\n]*'
                                     r'/home/vscode/\.vscode-server/extensions\n')

    PROXY_NAMES = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy")

    def test_it_has_a_clear_name(self):
        self.assertIn("Crux Controller", self.data["name"])

    def test_the_proxy_settings_of_the_host_reach_the_build_and_the_container(self):
        # An unset host variable gives an empty string, which the build argument and setup.sh both
        # treat as "no proxy".
        for section in (self.data["build"]["args"], self.data["containerEnv"]):
            for name in self.PROXY_NAMES:
                self.assertEqual("${localEnv:%s}" % name, section[name], name)

    def test_the_github_token_of_the_host_reaches_the_container_tools(self):
        self.assertEqual({"GH_TOKEN": "${localEnv:GH_TOKEN}"}, self.data["remoteEnv"])

    def test_the_layout_is_checked_on_the_host_before_the_container_is_created(self):
        command = self.data["initializeCommand"]
        self.assertEqual("bash .devcontainer/check-host.sh", command)  # bash, so a lost execute bit does not matter
        self.assertTrue((DEVCONTAINER / "check-host.sh").is_file())

    def test_the_mounts_are_the_cache_and_the_extensions_and_the_run_arguments_add_only_the_usb_bus(self):
        self.assertEqual(["source=crux-controller-dev-cache-${devcontainerId},target=/opt/crux-cache,type=volume",
                          "source=crux-controller-vscode-extensions,target=/home/vscode/.vscode-server/extensions,"
                          "type=volume"],
                         self.data["mounts"])
        self.assertEqual("source=${localWorkspaceFolder}/..,target=/workspaces/ws,type=bind",
                         self.data["workspaceMount"])
        self.assertEqual(["--platform=linux/amd64", "--device-cgroup-rule=c 189:* rmw", "-v",
                          "/dev/bus/usb:/dev/bus/usb"], self.data["runArgs"])

    def test_the_bootstrap_entry_runs_after_creation(self):
        # scripts/bootstrap.sh runs setup.sh; tests/tooling/test_bootstrap.py tests the entry.
        self.assertEqual("bash scripts/bootstrap.sh --keep-going", self.data["postCreateCommand"])

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

    def test_it_runs_the_sdk_install_of_the_workload_job_with_the_same_toolchain(self):
        run = ci_step("workload", "Install the Zephyr SDK")["run"]
        self.assertIn("--gnu-toolchains arm-zephyr-eabi", run)
        self.assertIn("--gnu-toolchains arm-zephyr-eabi", self.text)
        self.assertIn('sdk_version="${ZEPHYR_SDK_VERSION:?', self.text)
        self.assertIn('west sdk install --version "$sdk_version"', self.text)

    def test_it_installs_the_three_zephyr_requirement_files_of_the_workload_job(self):
        run = ci_step("workload", "Fetch the workspace")["run"]
        for name in ("requirements-base.txt", "requirements-build-test.txt", "requirements-run-test.txt"):
            self.assertIn(name, run)
            self.assertIn(name, self.text)

    def test_it_does_not_switch_the_mbed_group_on(self):
        self.assertNotIn("group-filter", self.text)

    def test_it_refuses_a_home_directory_as_the_workspace(self):
        self.assertIn(".bashrc", self.text)


# The stand-ins for the tools that setup.sh calls. They record every call and a few environment
# variables in $FAKE_LOG, and they create the files the real tools would create, so that the real text
# of setup.sh runs unchanged in a temporary workspace. Nothing here starts a container or uses the network.
STUB_PRELUDE = r"""#!/bin/bash
dump_env() {
    for n in http_proxy HTTP_PROXY https_proxy HTTPS_PROXY no_proxy NO_PROXY \
             SSL_CERT_FILE REQUESTS_CA_BUNDLE PIP_CERT GIT_SSL_CAINFO ZEPHYR_BASE; do
        printf 'ENV %s %s=%s\n' "$1" "$n" "${!n-<unset>}" >>"$FAKE_LOG"
    done
}
"""

STUB_VENV_PYTHON = STUB_PRELUDE + r"""
echo "python $*" >>"$FAKE_LOG"
dump_env python
if [ "${FAKE_PIP_FAIL:-}" = 1 ] && [ "$1" = "-m" ] && [ "$2" = "pip" ]; then
    echo "stub: pip install failed" >&2
    exit 1
fi
exit 0
"""

STUB_PYTHON3 = STUB_PRELUDE + r"""
echo "python3 $*" >>"$FAKE_LOG"
if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
    shift 2
    clear=""
    if [ "$1" = "--clear" ]; then clear=1; shift; fi
    dir="$1"
    if [ -n "$clear" ]; then rm -rf "$dir"; fi
    mkdir -p "$dir/bin"
    cp "$FAKE_VENV_PYTHON" "$dir/bin/python"
    chmod +x "$dir/bin/python"
    if [ "${FAKE_NO_PIP:-}" != 1 ]; then
        printf '#!/bin/bash\nexit 0\n' >"$dir/bin/pip"
        chmod +x "$dir/bin/pip"
    fi
fi
"""

STUB_WEST = STUB_PRELUDE + r"""
echo "west $*" >>"$FAKE_LOG"
dump_env west
case "$1" in
--version)
    echo "West version: v1.4.0"
    ;;
init)
    # The real west refuses a folder that already has a .west folder.
    if [ -e .west ]; then
        echo "FATAL ERROR: already initialized in $PWD, aborting." >&2
        exit 1
    fi
    mkdir .west
    if [ "${FAKE_INIT_FAIL:-}" = 1 ]; then exit 1; fi
    echo "[manifest]" >.west/config
    ;;
completion)
    # `completion` is a Zephyr extension command: west knows it only in a workspace after west update.
    if [ ! -d zephyr/scripts ]; then
        echo "west: unknown command \"completion\"" >&2
        exit 1
    fi
    if [ "${FAKE_COMPLETION_FAIL:-}" = 1 ]; then
        echo "# partial"
        echo "west: completion failed" >&2
        exit 1
    fi
    echo "# west completion script for $2"
    ;;
update)
    if [ "${FAKE_UPDATE_FAIL:-}" = 1 ]; then exit 1; fi
    mkdir -p zephyr/scripts modules
    for name in base build-test run-test; do echo "pytest" >"zephyr/scripts/requirements-$name.txt"; done
    ;;
sdk)
    shift 2
    while [ $# -gt 0 ]; do
        case "$1" in
        --install-base) base="$2"; shift ;;
        --version) version="$2"; shift ;;
        esac
        shift
    done
    target="$base/zephyr-sdk-$version"
    if [ "${FAKE_SDK_FAIL:-}" = 1 ]; then
        mkdir -p "$target/partial"
        exit 1
    fi
    if [ "${FAKE_SDK_NO_COMPILER:-}" = 1 ]; then
        mkdir -p "$target"
    elif [ "${FAKE_SDK_SYMLINK:-}" = 1 ]; then
        mkdir -p "$target/gnu/arm-zephyr-eabi/bin"
        printf '#!/bin/bash\nexit 0\n' >"$target/gnu/arm-zephyr-eabi/bin/gcc-real"
        chmod +x "$target/gnu/arm-zephyr-eabi/bin/gcc-real"
        ln -s gcc-real "$target/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc"
    else
        mkdir -p "$target/gnu/arm-zephyr-eabi/bin"
        printf '#!/bin/bash\nexit 0\n' >"$target/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc"
        chmod +x "$target/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc"
    fi
    ;;
esac
"""

STUB_SUDO = r"""#!/bin/bash
echo "sudo $*" >>"$FAKE_LOG"
"""


class SetupFixture:
    """A temporary workspace with the real setup.sh, stand-ins for west, python3 and sudo, and a log."""

    def __init__(self, clone="crux-controller"):
        self.directory = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.directory.name).resolve()
        self.workspace = self.base / "ws"
        self.repo = self.workspace / clone
        self.cache = self.base / "cache"
        self.home = self.base / "home"
        self.bin = self.base / "bin"
        self.log = self.base / "calls.log"
        self.sdk_dir = self.cache / "sdk" / "zephyr-sdk-1.0.1"
        for path in (self.repo / ".devcontainer", self.cache, self.home, self.bin):
            path.mkdir(parents=True)
        for name in ("setup.sh", "requirements-tools.txt"):
            shutil.copy(DEVCONTAINER / name, self.repo / ".devcontainer" / name)
        self.log.write_text("")
        (self.base / "venv-python").write_text(STUB_VENV_PYTHON)
        for name, text in (("python3", STUB_PYTHON3), ("west", STUB_WEST), ("sudo", STUB_SUDO)):
            self.stub(name, text)
        # The host may lack GNU stat or sha256sum (macOS); the container has both.
        if subprocess.run(["stat", "-c", "%u", str(self.base)], capture_output=True).returncode != 0:
            self.stub("stat", '#!/bin/bash\nid -u\n')
        if shutil.which("sha256sum") is None:
            self.stub("sha256sum", '#!/bin/bash\nexec shasum -a 256 "$@"\n')

    def stub(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def close(self):
        self.directory.cleanup()

    def run(self, **env):
        environment = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(self.home),
            "GIT_CONFIG_GLOBAL": str(self.home / ".gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "CRUX_CACHE_DIR": str(self.cache),
            "ZEPHYR_SDK_VERSION": "1.0.1",
            "ZEPHYR_SDK_INSTALL_DIR": str(self.sdk_dir),
            "FAKE_LOG": str(self.log),
            "FAKE_VENV_PYTHON": str(self.base / "venv-python"),
        }
        environment.update(env)
        script = self.repo / ".devcontainer" / "setup.sh"
        return subprocess.run(["bash", str(script)], env=environment, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True)

    def calls(self, prefix=None):
        lines = [line for line in self.log.read_text().splitlines() if not line.startswith("ENV ")]
        return [line for line in lines if prefix is None or line.startswith(prefix)]

    def env_seen(self, tool):
        found = {}
        for line in self.log.read_text().splitlines():
            if line.startswith(f"ENV {tool} "):
                name, _, value = line[len(f"ENV {tool} "):].partition("=")
                found[name] = value
        return found

    def env_at(self, call_prefix):
        """The environment variables that the first call starting with `call_prefix` saw."""
        lines = self.log.read_text().splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith(call_prefix))
        found = {}
        for line in lines[start + 1:]:
            if not line.startswith("ENV "):
                break
            name, _, value = line.split(" ", 2)[2].partition("=")
            found[name] = value
        return found

    def sdk_installs(self):
        return self.calls("west sdk install")


class SetupRuns(unittest.TestCase):
    """The real setup.sh against stand-ins: what it does, in what order, and how it recovers."""

    def setUp(self):
        self.fixture = SetupFixture()
        self.addCleanup(self.fixture.close)

    def ok(self, **env):
        result = self.fixture.run(**env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout, "setup.sh must keep the standard output clean")
        return result

    def test_a_fresh_workspace_is_set_up_in_the_order_of_the_workload_job(self):
        self.ok()
        calls = self.fixture.calls()
        steps = ["west init -l crux-controller", "west update", "west sdk install"]
        positions = [next(i for i, call in enumerate(calls) if call.startswith(step)) for step in steps]
        self.assertEqual(sorted(positions), positions)
        self.assertTrue(any(call.startswith("python -m pip install") for call in calls))
        self.assertTrue((self.fixture.sdk_dir / ".crux-installed").is_file())

    def test_everything_it_prints_goes_to_the_standard_error_stream(self):
        result = self.ok()
        self.assertEqual("", result.stdout)
        last = result.stderr.rstrip("\n").splitlines()[-1]
        self.assertEqual(f"setup: workspace {self.fixture.workspace}, Zephyr SDK 1.0.1, West version: v1.4.0", last)

    def test_a_second_run_does_nothing_again(self):
        self.ok()
        before = self.fixture.calls()
        result = self.ok()
        new = self.fixture.calls()[len(before):]
        # Only the offline west completion script is written again (test_editor_tools.py).
        self.assertEqual(["west completion bash", "west --version"], new)
        self.assertIn("the workspace is initialised", result.stderr)

    def test_the_sdk_directory_without_the_install_marker_is_removed_and_installed_again(self):
        self.ok()
        marker = self.fixture.sdk_dir / ".crux-installed"
        marker.unlink()
        (self.fixture.sdk_dir / "left-over").write_text("x\n")
        result = self.ok()
        self.assertEqual(2, len(self.fixture.sdk_installs()))
        self.assertFalse((self.fixture.sdk_dir / "left-over").exists())
        self.assertTrue(marker.is_file())
        self.assertIn("incomplete", result.stderr)
        self.assertIn(str(self.fixture.sdk_dir), result.stderr)

    def test_an_sdk_with_the_marker_is_complete_and_a_missing_compiler_only_warns(self):
        # The marker is the test of completeness. A compiler that is not found (a layout the search does
        # not know) must not start a reinstall of several GiB on every run.
        self.ok()
        next(self.fixture.sdk_dir.rglob("arm-zephyr-eabi-gcc")).unlink()
        for _ in range(2):
            result = self.ok()
            self.assertIn("warning: no arm-zephyr-eabi-gcc", result.stderr)
        self.assertEqual(1, len(self.fixture.sdk_installs()))
        self.assertTrue((self.fixture.sdk_dir / ".crux-installed").is_file())

    def test_a_compiler_that_is_a_symbolic_link_is_found(self):
        self.ok(FAKE_SDK_SYMLINK="1")
        result = self.ok(FAKE_SDK_SYMLINK="1")
        self.assertNotIn("warning", result.stderr)
        self.assertEqual(1, len(self.fixture.sdk_installs()))

    def test_an_sdk_folder_without_the_marker_is_installed_again_even_if_a_compiler_is_there(self):
        self.ok()
        (self.fixture.sdk_dir / ".crux-installed").unlink()
        self.ok()
        self.assertEqual(2, len(self.fixture.sdk_installs()))

    def test_a_failed_sdk_install_leaves_no_marker_and_names_the_step(self):
        result = self.fixture.run(FAKE_SDK_FAIL="1")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse((self.fixture.sdk_dir / ".crux-installed").exists())
        self.assertIn("setup: failed during the Zephyr SDK install; rerun: bash .devcontainer/setup.sh",
                      result.stderr)
        # The next run starts again and succeeds, because the partial directory has no marker.
        self.ok()
        self.assertFalse((self.fixture.sdk_dir / "partial").exists())
        self.assertTrue((self.fixture.sdk_dir / ".crux-installed").is_file())

    def test_a_finished_install_without_a_compiler_warns_and_is_not_repeated_on_every_run(self):
        result = self.fixture.run(FAKE_SDK_NO_COMPILER="1")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("warning: no arm-zephyr-eabi-gcc", result.stderr)
        self.assertTrue((self.fixture.sdk_dir / ".crux-installed").is_file())
        self.ok(FAKE_SDK_NO_COMPILER="1")
        self.assertEqual(1, len(self.fixture.sdk_installs()))

    def test_the_sdk_removal_is_refused_for_a_path_that_is_not_a_zephyr_sdk_folder_in_the_cache(self):
        cache = self.fixture.cache
        (cache / "sdk" / "x").mkdir(parents=True)
        outside = self.fixture.base / "outside" / "zephyr-sdk-1.0.1"
        outside.mkdir(parents=True)
        cases = {
            "a dot-dot component": str(cache / "sdk" / "x" / ".." / "zephyr-sdk-1.0.1"),
            "the cache itself": str(cache),
            "another name": str(cache / "sdk" / "x"),
            "outside the cache": str(outside),
        }
        for label, path in cases.items():
            with self.subTest(label):
                folder = pathlib.Path(path)
                keep = (folder / "keep-me") if label != "a dot-dot component" else (cache / "sdk" / "zephyr-sdk-1.0.1" / "keep-me")
                keep.parent.mkdir(parents=True, exist_ok=True)
                keep.write_text("x\n")
                result = self.fixture.run(ZEPHYR_SDK_INSTALL_DIR=path)
                self.assertNotEqual(0, result.returncode, label)
                self.assertIn("is not removed", result.stderr)
                self.assertTrue(keep.exists(), label)
                self.assertEqual([], self.fixture.sdk_installs(), label)

    def test_a_virtual_environment_without_pip_is_created_again(self):
        self.ok()
        (self.fixture.cache / "venv" / "bin" / "pip").unlink()
        self.ok()
        creations = self.fixture.calls("python3 -m venv")
        self.assertEqual(2, len(creations))
        self.assertIn("--clear", creations[1])
        self.assertTrue((self.fixture.cache / "venv" / "bin" / "pip").is_file())

    def test_a_complete_virtual_environment_is_kept(self):
        self.ok()
        self.ok()
        self.assertEqual(1, len(self.fixture.calls("python3 -m venv")))

    def test_a_failed_pip_install_names_the_step(self):
        result = self.fixture.run(FAKE_PIP_FAIL="1")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("setup: failed during the Python virtual environment; rerun: bash .devcontainer/setup.sh",
                      result.stderr)

    def test_an_interrupted_west_init_without_config_is_started_again(self):
        (self.fixture.workspace / ".west").mkdir()
        result = self.ok()
        self.assertEqual(1, len(self.fixture.calls("west init")))
        self.assertTrue((self.fixture.workspace / ".west" / "config").is_file())
        self.assertIn(".west", result.stderr)

    def test_a_west_folder_with_config_but_without_zephyr_only_runs_the_update(self):
        (self.fixture.workspace / ".west").mkdir()
        (self.fixture.workspace / ".west" / "config").write_text("[manifest]\n")
        self.ok()
        self.assertEqual([], self.fixture.calls("west init"))
        self.assertEqual(1, len(self.fixture.calls("west update")))

    def test_a_failed_update_is_run_again_by_the_next_run(self):
        result = self.fixture.run(FAKE_UPDATE_FAIL="1")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("setup: failed during the west workspace; rerun: bash .devcontainer/setup.sh",
                      result.stderr)
        self.assertTrue((self.fixture.workspace / ".west" / "crux-devcontainer-update.pending").exists())
        self.ok()
        self.assertEqual(1, len(self.fixture.calls("west init")))
        self.assertEqual(2, len(self.fixture.calls("west update")))

    def test_the_safe_directory_setting_is_added_once(self):
        self.ok()
        self.ok()
        # Isolated from the git settings of the machine that runs the test.
        listed = subprocess.run(
            ["git", "config", "--global", "--get-all", "safe.directory"],
            env={**os.environ, "HOME": str(self.fixture.home), "GIT_CONFIG_NOSYSTEM": "1",
                 "GIT_CONFIG_GLOBAL": str(self.fixture.home / ".gitconfig")},
            capture_output=True, text=True,
        ).stdout.split()
        self.assertTrue((self.fixture.home / ".gitconfig").is_file())
        self.assertEqual(["*"], listed)

    def test_a_clone_with_another_name_is_refused_with_the_old_message(self):
        fixture = SetupFixture(clone="crux-controller-main")
        self.addCleanup(fixture.close)
        result = fixture.run()
        self.assertEqual(1, result.returncode)
        self.assertIn("the clone is in a folder named 'crux-controller-main'", result.stderr)
        self.assertEqual([], fixture.calls())

    def test_a_home_directory_as_the_workspace_is_refused_for_every_marker(self):
        for marker in (".bashrc", ".profile", ".ssh", ".gnupg", ".gitconfig"):
            with self.subTest(marker=marker):
                path = self.fixture.workspace / marker
                path.mkdir()
                result = self.fixture.run()
                self.assertEqual(1, result.returncode)
                self.assertIn(f"({marker} is in it)", result.stderr)
                path.rmdir()
        self.assertEqual([], self.fixture.calls())


class SetupNetwork(unittest.TestCase):
    """Proxy settings and the certificate of a proxy that inspects TLS, in the real setup.sh."""

    BUNDLE = "/etc/ssl/certs/ca-certificates.crt"
    PROXY_VARIABLES = ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "no_proxy", "NO_PROXY")
    CERTIFICATE_VARIABLES = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "PIP_CERT", "GIT_SSL_CAINFO")

    def setUp(self):
        self.fixture = SetupFixture()
        self.addCleanup(self.fixture.close)
        self.certificate = self.fixture.base / "company-ca.crt"
        self.certificate.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")

    def run_setup(self, **env):
        # The test host's own proxy settings must not leak into the run.
        clean = {name: "" for name in self.PROXY_VARIABLES}
        clean.update(env)
        return self.fixture.run(**clean)

    def test_without_the_variables_nothing_changes(self):
        result = self.run_setup(http_proxy="", HTTP_PROXY="")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], [call for call in self.fixture.calls() if "update-ca-certificates" in call])
        seen = self.fixture.env_seen("python")
        for name in self.CERTIFICATE_VARIABLES:
            self.assertEqual("<unset>", seen[name], name)
        self.assertNotIn("proxy settings", result.stderr)

    def test_a_lower_case_proxy_is_exported_in_both_cases_to_pip_and_west(self):
        result = self.run_setup(http_proxy="http://proxy.example:3128", https_proxy="http://proxy.example:3129",
                                no_proxy="localhost,127.0.0.1")
        self.assertEqual(0, result.returncode, result.stderr)
        for tool in ("python", "west"):
            seen = self.fixture.env_seen(tool)
            self.assertEqual("http://proxy.example:3128", seen["http_proxy"], tool)
            self.assertEqual("http://proxy.example:3128", seen["HTTP_PROXY"], tool)
            self.assertEqual("http://proxy.example:3129", seen["https_proxy"], tool)
            self.assertEqual("http://proxy.example:3129", seen["HTTPS_PROXY"], tool)
            self.assertEqual("localhost,127.0.0.1", seen["no_proxy"], tool)
            self.assertEqual("localhost,127.0.0.1", seen["NO_PROXY"], tool)

    def test_an_upper_case_proxy_is_exported_in_both_cases(self):
        result = self.run_setup(HTTPS_PROXY="http://upper.example:8080")
        self.assertEqual(0, result.returncode, result.stderr)
        seen = self.fixture.env_seen("west")
        self.assertEqual("http://upper.example:8080", seen["https_proxy"])
        self.assertEqual("http://upper.example:8080", seen["HTTPS_PROXY"])
        self.assertEqual("", seen["http_proxy"])  # setup.sh sets no other proxy: empty, as the test passed it

    def test_the_proxy_url_is_never_printed_because_it_can_hold_a_password(self):
        result = self.run_setup(http_proxy="http://user:secret@proxy.example:3128")
        self.assertNotIn("secret", result.stderr)
        self.assertNotIn("proxy.example", result.stderr)
        self.assertIn("proxy settings", result.stderr)

    def test_the_proxy_is_in_the_environment_of_every_tool_from_the_first_call(self):
        # West runs git, and the SDK download may run curl: both read the same variables.
        self.run_setup(http_proxy="http://proxy.example:3128")
        for call in ("python -m pip install", "west init", "west update", "west sdk install"):
            seen = self.fixture.env_at(call)
            self.assertEqual("http://proxy.example:3128", seen["http_proxy"], call)
            self.assertEqual("http://proxy.example:3128", seen["HTTP_PROXY"], call)

    def test_an_extra_certificate_is_installed_and_the_system_bundle_is_selected(self):
        result = self.run_setup(CRUX_EXTRA_CA_FILE=str(self.certificate))
        self.assertEqual(0, result.returncode, result.stderr)
        sudo = self.fixture.calls("sudo")
        install = f"sudo install -m 0644 {self.certificate} /usr/local/share/ca-certificates/crux-extra-ca.crt"
        self.assertIn(install, sudo)
        self.assertIn("sudo update-ca-certificates", sudo)
        self.assertLess(sudo.index(install), sudo.index("sudo update-ca-certificates"))
        for tool in ("python", "west"):
            seen = self.fixture.env_seen(tool)
            for name in self.CERTIFICATE_VARIABLES:
                self.assertEqual(self.BUNDLE, seen[name], f"{tool} {name}")

    def test_the_certificate_is_installed_before_any_download(self):
        self.run_setup(CRUX_EXTRA_CA_FILE=str(self.certificate))
        calls = self.fixture.calls()
        update = calls.index("sudo update-ca-certificates")
        first_tool = min(i for i, call in enumerate(calls) if call.startswith(("python", "west")))
        self.assertLess(update, first_tool)

    def test_a_missing_certificate_file_stops_the_setup_with_the_name_of_the_variable(self):
        result = self.run_setup(CRUX_EXTRA_CA_FILE=str(self.fixture.base / "missing.crt"))
        self.assertEqual(1, result.returncode)
        self.assertIn("CRUX_EXTRA_CA_FILE", result.stderr)
        self.assertIn("not a readable file", result.stderr)
        self.assertIn("setup: failed during the network settings; rerun: bash .devcontainer/setup.sh",
                      result.stderr)
        self.assertEqual([], self.fixture.calls())

    def fixed_file(self, text=None):
        path = self.fixture.workspace / ".crux-extra-ca.crt"
        path.write_text(text if text is not None else self.certificate.read_text())
        return path

    def test_the_certificate_file_in_the_workspace_folder_is_installed_without_any_variable(self):
        fixed = self.fixed_file()
        result = self.run_setup()
        self.assertEqual(0, result.returncode, result.stderr)
        sudo = self.fixture.calls("sudo")
        self.assertIn(f"sudo install -m 0644 {fixed} /usr/local/share/ca-certificates/crux-extra-ca.crt", sudo)
        self.assertIn("sudo update-ca-certificates", sudo)
        for tool in ("python", "west"):
            for name in self.CERTIFICATE_VARIABLES:
                self.assertEqual(self.BUNDLE, self.fixture.env_seen(tool)[name], f"{tool} {name}")
        self.assertIn(".crux-extra-ca.crt", result.stderr)  # the source is named
        self.assertNotIn("MIIB", result.stderr)  # the contents are not printed

    def test_the_fixed_file_is_installed_before_the_first_download_tool_runs(self):
        self.fixed_file()
        self.run_setup()
        calls = self.fixture.calls()
        update = calls.index("sudo update-ca-certificates")
        first_tool = min(i for i, call in enumerate(calls) if call.startswith(("python", "west")))
        self.assertLess(update, first_tool)

    def test_the_variable_wins_over_the_fixed_file(self):
        fixed = self.fixed_file()
        result = self.run_setup(CRUX_EXTRA_CA_FILE=str(self.certificate))
        self.assertEqual(0, result.returncode, result.stderr)
        installs = [call for call in self.fixture.calls("sudo") if call.startswith("sudo install")]
        self.assertEqual(1, len(installs), installs)
        self.assertIn(str(self.certificate), installs[0])
        self.assertNotIn(str(fixed), installs[0])

    def test_a_variable_that_names_no_readable_file_is_an_error_even_if_the_fixed_file_exists(self):
        self.fixed_file()
        result = self.run_setup(CRUX_EXTRA_CA_FILE=str(self.fixture.base / "typo.crt"))
        self.assertEqual(1, result.returncode)
        self.assertIn("not a readable file", result.stderr)
        self.assertEqual([], self.fixture.calls())

    def test_a_fixed_file_that_is_not_pem_is_refused_and_named(self):
        fixed = self.fixed_file("not a certificate\n")
        result = self.run_setup()
        self.assertEqual(1, result.returncode)
        self.assertIn("not a PEM certificate", result.stderr)
        self.assertIn(str(fixed), result.stderr)
        self.assertIn("openssl x509 -inform der", result.stderr)
        self.assertEqual([], self.fixture.calls())

    def test_a_dangling_symbolic_link_as_the_fixed_file_is_an_error_and_not_skipped(self):
        (self.fixture.workspace / ".crux-extra-ca.crt").symlink_to(self.fixture.base / "gone.crt")
        result = self.run_setup()
        self.assertEqual(1, result.returncode)
        self.assertIn("not a readable file", result.stderr)
        self.assertEqual([], self.fixture.calls())

    def test_a_fixed_file_that_is_a_folder_is_refused(self):
        (self.fixture.workspace / ".crux-extra-ca.crt").mkdir()
        result = self.run_setup()
        self.assertEqual(1, result.returncode)
        self.assertIn("not a readable file", result.stderr)

    def test_without_the_fixed_file_and_the_variable_no_certificate_is_installed(self):
        result = self.run_setup()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], [call for call in self.fixture.calls("sudo") if "ca-certificates" in call])
        self.assertNotIn("certificate", result.stderr)

    def test_a_certificate_that_is_not_pem_is_refused_with_the_conversion_command(self):
        der = self.fixture.base / "company.cer"
        der.write_bytes(b"\x30\x82\x01\x0a\x02\x82")
        result = self.run_setup(CRUX_EXTRA_CA_FILE=str(der))
        self.assertEqual(1, result.returncode)
        self.assertIn("not a PEM certificate", result.stderr)
        self.assertIn("openssl x509 -inform der", result.stderr)
        self.assertEqual([], self.fixture.calls())


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
        for path in (".devcontainer/**", "scripts/dev-shell.sh", "scripts/bootstrap.sh", ".vscode/**", "west.yml",
                     ".github/workflows/devcontainer.yml"):
            self.assertIn(path, paths)

    def test_the_permissions_are_read_only_and_set_once(self):
        self.assertEqual({"contents": "read"}, self.data["permissions"])
        self.assertNotIn("permissions", self.job)

    def test_the_image_build_skips_the_j_link_software(self):
        # The SEGGER download accepts SEGGER's terms of use, so CI does not run it: the job sets
        # CRUX_JLINK=0, which scripts/dev-shell.sh passes to the build by name.
        self.assertEqual("0", str(self.job["env"]["CRUX_JLINK"]))

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

    def test_the_twister_step_matches_the_one_of_the_workload_job(self):
        run = " ".join(ci_step("workload", "Run the workload scenario on native_sim")["run"].replace("\\", " ").split())
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

    def test_the_workload_steps_after_twister_are_those_of_the_workload_job(self):
        board = ci_job("workload")["env"]["BOARD"]
        commands = norm(self.commands)
        for fragment in ("Cross-build workload with the baseline gate required", "Check the outputs exist",
                         "Check the resolved workload configuration"):
            run = ci_step("workload", fragment)["run"].replace("${{ env.BOARD }}", board)
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


CERTS = DEVCONTAINER / "certs"
INSTALL_CERTS = DEVCONTAINER / "install-org-certs.sh"
SYSTEM_BUNDLE = "/etc/ssl/certs/ca-certificates.crt"


def run_instructions(text):
    """The RUN instructions of a Dockerfile, in order, each joined over its continuation lines."""
    joined = re.sub(r"\\\n", " ", text)
    return [line for line in joined.splitlines() if line.startswith("RUN ")]


def env_values(text):
    """NAME=value pairs of every ENV instruction, joined over continuation lines."""
    joined = re.sub(r"\\\n", " ", text)
    values = {}
    for line in joined.splitlines():
        if line.startswith("ENV "):
            values.update(dict(re.findall(r"(\w+)=(\S+)", line)))
    return values


class OrganisationCertificatesInTheImage(unittest.TestCase):
    """The root certificates of an organisation whose proxy inspects TLS, placed in .devcontainer/certs/."""

    BUNDLE_VARIABLES = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE", "GIT_SSL_CAINFO", "PIP_CERT",
                        "NODE_EXTRA_CA_CERTS")

    @classmethod
    def setUpClass(cls):
        cls.text = read(DEVCONTAINER / "Dockerfile")
        cls.runs = run_instructions(cls.text)

    def test_the_certificates_are_installed_by_the_first_run_step_before_any_download(self):
        # apt-get, the J-Link download and every later step must already trust the certificates.
        self.assertIn("install-org-certs.sh /tmp/crux-certs", self.runs[0])
        downloads = [i for i, run in enumerate(self.runs)
                     if re.search(r"apt-get|curl|wget|pip|install-jlink\.sh|git ", run)]
        self.assertTrue(downloads)
        self.assertNotIn(0, downloads)

    def test_the_certificate_folder_is_bind_mounted_into_the_one_step_and_never_copied(self):
        # A BuildKit bind mount exposes the folder and the script to that RUN step only, so no file of the
        # folder is stored in a layer of the image; only what update-ca-certificates installs stays.
        step = self.runs[0]
        self.assertTrue(step.startswith("RUN --mount=type=bind,source=certs,target=/tmp/crux-certs "), step)
        self.assertIn("--mount=type=bind,source=install-org-certs.sh,target=/tmp/install-org-certs.sh", step)
        self.assertTrue(step.endswith("sh /tmp/install-org-certs.sh /tmp/crux-certs"), step)
        self.assertNotIn(",rw", step)
        for line in re.findall(r"(?m)^(?:COPY|ADD) .*$", self.text):
            self.assertNotIn("certs", line)
            self.assertNotIn("install-org-certs.sh", line)
        self.assertLess(self.text.index("RUN --mount=type=bind,source=certs"), self.text.index("RUN apt-get"))

    def test_the_package_step_refreshes_the_bundle_after_it_installs_ca_certificates(self):
        # When the base image has no ca-certificates yet, the first step cannot build the bundle: the
        # package step does it once the package is there.
        apt = next(run for run in self.runs if "apt-get install" in run)
        self.assertLess(apt.index("ca-certificates"), apt.index("update-ca-certificates"))

    def test_every_tool_uses_the_system_bundle_and_the_variables_are_set_before_any_download(self):
        values = env_values(self.text)
        for name in self.BUNDLE_VARIABLES:
            self.assertEqual(SYSTEM_BUNDLE, values.get(name), name)
        block = self.text.index("ENV REQUESTS_CA_BUNDLE=")
        self.assertLess(block, self.text.index("RUN apt-get"))
        self.assertLess(block, self.text.index("COPY jlink/"))

    def test_the_bundle_path_is_the_one_that_setup_sh_selects(self):
        self.assertIn(f"system_ca_bundle={SYSTEM_BUNDLE}", read(DEVCONTAINER / "setup.sh"))

    def test_no_step_turns_certificate_checks_off(self):
        lowered = (self.text + read(INSTALL_CERTS)).lower()
        for weakening in ("--no-check-certificate", "curl -k", "--insecure", "--trusted-host",
                          "git_ssl_no_verify", "sslverify=false", "pythonhttpsverify=0"):
            self.assertNotIn(weakening, lowered)


class OrganisationCertificateFolder(unittest.TestCase):
    def test_the_folder_has_a_readme_and_a_keep_file_and_no_ignore_file_of_its_own(self):
        self.assertTrue((CERTS / "README.md").is_file())
        self.assertTrue((CERTS / ".gitkeep").is_file())
        self.assertFalse((CERTS / ".gitignore").exists())

    def test_the_root_ignore_file_keeps_everything_but_the_keep_file_and_the_readme_out_of_git(self):
        rules = read(ROOT / ".gitignore").splitlines()
        start = rules.index(".devcontainer/certs/*")
        self.assertEqual([".devcontainer/certs/*", "!.devcontainer/certs/.gitkeep", "!.devcontainer/certs/README.md"],
                         rules[start:start + 3])

    def test_git_ignores_a_certificate_placed_in_the_folder(self):
        if not (ROOT / ".git").exists():
            self.skipTest("not a Git checkout")
        for name in ("org-root.crt", "org-root.cer", "org-root.pem", "nested/org.crt"):
            result = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "--no-index",
                                     f".devcontainer/certs/{name}"], check=False)
            self.assertEqual(0, result.returncode, name)
        for name in ("README.md", ".gitkeep"):
            result = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "--no-index",
                                     f".devcontainer/certs/{name}"], check=False)
            self.assertEqual(1, result.returncode, name)

    def tracked(self, *paths):
        if not (ROOT / ".git").exists():
            self.skipTest("not a Git checkout")
        listing = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", *paths],
                                 capture_output=True, text=True, check=True).stdout
        return sorted(listing.split())

    def test_the_folder_tracks_only_its_keep_file_and_readme(self):
        self.assertEqual([".devcontainer/certs/.gitkeep", ".devcontainer/certs/README.md"],
                         self.tracked(".devcontainer/certs"))

    def test_no_certificate_file_is_tracked_anywhere(self):
        # Every developer places their own file locally; none goes into the repository or a copy of it.
        self.assertEqual([], self.tracked(":(glob,icase)**/*.crt", ":(glob,icase)**/*.pem",
                                          ":(glob,icase)**/*.cer", ":(glob,icase)**/*.der"))

    def test_no_page_suggests_committing_a_certificate(self):
        pages = [CERTS / "README.md", ROOT / "docs" / "dev-container.md", ROOT / "docs" / "troubleshooting.md"]
        for page in pages:
            text = " ".join(read(page).split()).lower()
            for phrase in ("commit the certificate", "commit your certificate", "commit the ca",
                           "git add .devcontainer/certs", "add the certificate to the repository"):
                self.assertNotIn(phrase, text, page.name)

    def test_the_readme_says_what_goes_there_and_points_at_the_one_home(self):
        text = " ".join(read(CERTS / "README.md").split())
        for fragment in (".crt", ".pem", ".cer", "Rebuild Container", "never committed",
                         "../../docs/dev-container.md#behind-a-proxy-or-with-a-company-certificate"):
            self.assertIn(fragment, text)


class InstallOrgCertsScript(unittest.TestCase):
    """The real install-org-certs.sh in temporary folders, with a stand-in for update-ca-certificates.

    The certificates are made by openssl at run time in a temporary folder; no certificate is committed.
    """

    @classmethod
    def setUpClass(cls):
        cls.pem = None
        openssl = shutil.which("openssl")
        if openssl:
            work = pathlib.Path(tempfile.mkdtemp())
            try:
                subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                                "-subj", "/CN=Test Root", "-keyout", str(work / "key.pem"),
                                "-out", str(work / "c.pem")], capture_output=True, check=True)
                cls.pem = (work / "c.pem").read_text()
            finally:
                shutil.rmtree(work)

    def setUp(self):
        self.base = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base)
        self.source = self.base / "certs"
        self.source.mkdir()
        (self.source / "README.md").write_text("# readme\n")
        (self.source / ".gitkeep").write_text("")
        self.target = self.base / "target"
        self.stubs = self.base / "bin"
        self.stubs.mkdir()
        self.log = self.base / "calls.log"
        stub = self.stubs / "update-ca-certificates"
        stub.write_text(f"#!/bin/sh\necho update-ca-certificates >> '{self.log}'\n")
        stub.chmod(0o755)
        if self.pem is None:
            self.skipTest("no openssl on this host")
        self.PEM = self.pem

    def assert_stopped(self, result, *messages):
        # The build stops, names the file, and installs nothing at all.
        self.assertNotEqual(0, result.returncode)
        for message in messages:
            self.assertIn(message, result.stderr)
        self.assertIn("no organisation CA was installed", result.stderr)
        self.assertEqual([], self.installed())
        self.assertEqual([], self.updates())

    def run_script(self, with_update=True, openssl=None):
        env = {"PATH": (f"{self.stubs}:" if with_update else "") + "/usr/bin:/bin"}
        if openssl is not None:
            env["CRUX_OPENSSL"] = openssl
        return subprocess.run(["/bin/sh", str(INSTALL_CERTS), str(self.source), str(self.target)],
                              capture_output=True, text=True, env=env, check=False)

    def updates(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def installed(self):
        return sorted(p.name for p in self.target.iterdir()) if self.target.exists() else []

    def der_certificate(self):
        """A real DER certificate made by openssl, or a skip when the test host has no openssl."""
        openssl = shutil.which("openssl")
        if not openssl:
            self.skipTest("no openssl on this host")
        work = self.base / "make"
        work.mkdir()
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-subj", "/CN=Test Root", "-keyout", str(work / "key.pem"), "-out", str(work / "c.pem")],
                       capture_output=True, check=True)
        subprocess.run([openssl, "x509", "-in", str(work / "c.pem"), "-outform", "der",
                        "-out", str(work / "c.der")], capture_output=True, check=True)
        return (work / "c.der").read_bytes()

    def test_an_empty_folder_installs_nothing_and_succeeds(self):
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], self.installed())
        self.assertEqual([], self.updates())
        self.assertIn("no certificate", result.stdout + result.stderr)

    def test_a_missing_folder_is_the_same_as_an_empty_one(self):
        shutil.rmtree(self.source)
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], self.updates())

    def test_a_pem_certificate_is_installed_and_the_bundle_is_built_once(self):
        (self.source / "org-root.crt").write_text(self.PEM)
        (self.source / "org-issuing.crt").write_text(self.PEM)
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["org-issuing.crt", "org-root.crt"], self.installed())
        self.assertEqual(self.PEM, (self.target / "org-root.crt").read_text())
        self.assertEqual(["update-ca-certificates"], self.updates())
        self.assertIn("org-root.crt", result.stdout)
        body = self.PEM.splitlines()[1]
        self.assertNotIn(body, result.stdout + result.stderr)  # the contents are not printed

    def test_pem_files_ending_in_pem_or_cer_are_installed_as_crt(self):
        (self.source / "org-a.pem").write_text(self.PEM)
        (self.source / "org-b.cer").write_text(self.PEM)
        (self.source / "ORG-C.PEM").write_text(self.PEM)
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["ORG-C.crt", "org-a.crt", "org-b.crt"], self.installed())

    def test_two_files_with_the_same_stem_are_both_installed(self):
        (self.source / "org.crt").write_text(self.PEM)
        (self.source / "org.pem").write_text(self.PEM)
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["org-pem.crt", "org.crt"], self.installed())

    def test_names_that_collide_never_overwrite_an_installed_file(self):
        for name in ("a.crt", "a.pem", "a-pem.crt", "a b.crt", "a_b.crt"):
            (self.source / name).write_text(self.PEM)
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(5, len(self.installed()), self.installed())
        self.assertIn("installed 5 certificate(s)", result.stdout)

    def test_windows_line_ends_are_removed_and_a_last_line_end_is_added(self):
        (self.source / "org-root.crt").write_bytes(self.PEM.rstrip("\n").replace("\n", "\r\n").encode())
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.PEM, (self.target / "org-root.crt").read_text())

    def test_a_der_certificate_is_converted_to_pem(self):
        (self.source / "org-root.cer").write_bytes(self.der_certificate())
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["org-root.crt"], self.installed())
        self.assertTrue((self.target / "org-root.crt").read_text().startswith("-----BEGIN CERTIFICATE-----"))
        self.assertIn("converted org-root.cer from DER", result.stdout)
        self.assertEqual(["update-ca-certificates"], self.updates())

    def test_without_openssl_a_der_certificate_is_skipped_with_the_conversion_command(self):
        (self.source / "org-root.cer").write_bytes(b"\x30\x82\x01\x0a\x02\x82")
        result = self.run_script(openssl=str(self.base / "no-openssl"))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], self.installed())
        self.assertEqual([], self.updates())
        self.assertIn("skipping org-root.cer", result.stderr)
        self.assertIn("openssl x509 -inform der", result.stderr)

    def test_a_file_that_is_neither_pem_nor_der_stops_the_build(self):
        (self.source / "org-root.crt").write_bytes(b"\x30\x82\x01\x0a\x02\x82")
        result = self.run_script()
        self.assert_stopped(result, "error: .devcontainer/certs/org-root.crt: is neither a PEM nor a DER certificate.")

    def test_a_pem_block_that_does_not_parse_stops_the_build(self):
        (self.source / "org-root.crt").write_text("-----BEGIN CERTIFICATE-----\nMIIBbroken\n-----END CERTIFICATE-----\n")
        result = self.run_script()
        self.assert_stopped(result, "error: .devcontainer/certs/org-root.crt: is not a valid certificate.")

    def test_a_file_with_another_ending_is_skipped_with_a_hint(self):
        (self.source / "org-root.der").write_text(self.PEM)
        (self.source / "notes.txt").write_text("text\n")
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], self.installed())
        self.assertIn("skipping org-root.der: only .crt, .pem and .cer files are installed", result.stderr)
        self.assertIn("skipping notes.txt", result.stderr)

    def test_a_file_that_holds_a_private_key_stops_the_build(self):
        (self.source / "bundle.pem").write_text(self.PEM + "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----\n")
        result = self.run_script()
        self.assert_stopped(result, "error: .devcontainer/certs/bundle.pem: holds a private key. "
                                    "Put only the CA certificate here, never a key.")
        self.assertNotIn("MIIE", result.stdout + result.stderr)

    def test_a_bundle_is_installed_as_one_file_per_certificate(self):
        (self.source / "chain.crt").write_text(self.PEM + self.PEM)
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["chain-1.crt", "chain-2.crt"], self.installed())
        self.assertEqual(self.PEM, (self.target / "chain-2.crt").read_text())

    def test_a_bundle_never_overwrites_a_file_staged_earlier(self):
        # chain-2.crt (one certificate) is staged first; chain.crt (two) must not land on chain-2.crt.
        (self.source / "chain-2.crt").write_text(self.PEM)
        (self.source / "chain.crt").write_text(self.PEM + self.PEM)
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(3, len(self.installed()), self.installed())
        self.assertIn("installed 3 certificate(s)", result.stdout)

    def test_a_pem_marker_that_is_not_on_a_line_of_its_own_stops_the_build_without_openssl(self):
        (self.source / "odd.crt").write_text("  -----BEGIN CERTIFICATE-----\nMIIB\n  -----END CERTIFICATE-----\n")
        result = self.run_script(openssl=str(self.base / "no-openssl"))
        self.assert_stopped(result, "error: .devcontainer/certs/odd.crt: holds no certificate block that can be read.")
        self.assertNotIn("mv:", result.stderr)

    def test_a_broken_block_after_a_good_one_stops_the_build(self):
        broken = "-----BEGIN CERTIFICATE-----\nMIIBbroken\n-----END CERTIFICATE-----\n"
        (self.source / "chain.crt").write_text(self.PEM + broken)
        result = self.run_script()
        self.assert_stopped(result, "error: .devcontainer/certs/chain.crt: certificate 2 of 2 is not a valid certificate.")

    def test_a_pem_block_that_is_not_a_certificate_stops_the_build(self):
        key = "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQ\n-----END PUBLIC KEY-----\n"
        (self.source / "mixed.pem").write_text(self.PEM + key)
        result = self.run_script()
        self.assert_stopped(result, "error: .devcontainer/certs/mixed.pem: holds a PEM block that is not a certificate.")

    def test_a_private_key_stops_the_build_whatever_the_file_ending(self):
        for name in ("org.key", "notes.txt"):
            with self.subTest(name):
                (self.source / name).write_text("-----BEGIN EC PRIVATE KEY-----\nMHcC\n-----END EC PRIVATE KEY-----\n")
                result = self.run_script()
                self.assert_stopped(result, f"error: .devcontainer/certs/{name}: holds a private key.")
                (self.source / name).unlink()

    def test_a_bad_file_installs_nothing_even_next_to_a_good_one(self):
        (self.source / "a-good.crt").write_text(self.PEM)
        (self.source / "b-bad.crt").write_text("not a certificate\n")
        result = self.run_script()
        self.assert_stopped(result, "b-bad.crt")
        self.assertIn("Fix or remove the files named above, then rebuild the container.", result.stderr)

    def test_a_file_with_another_ending_does_not_stop_the_good_ones(self):
        (self.source / "notes.txt").write_text("text\n")
        (self.source / "good.crt").write_text(self.PEM)
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["good.crt"], self.installed())
        self.assertEqual(["update-ca-certificates"], self.updates())

    def test_a_name_with_spaces_is_installed_under_a_safe_name(self):
        (self.source / "Org Root CA (2026).crt").write_text(self.PEM)
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["Org_Root_CA__2026_.crt"], self.installed())

    def test_folders_and_the_readme_and_keep_file_are_not_reported(self):
        (self.source / "sub").mkdir()
        (self.source / "sub" / "x.crt").write_text(self.PEM)
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], self.installed())
        for name in ("README.md", ".gitkeep"):
            self.assertNotIn(name, result.stderr)

    def test_without_update_ca_certificates_the_files_wait_for_the_package_step(self):
        (self.source / "org-root.crt").write_text(self.PEM)
        result = self.run_script(with_update=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["org-root.crt"], self.installed())
        self.assertIn("update-ca-certificates is not in the base image", result.stdout)

    def test_it_is_a_posix_shell_script_that_downloads_nothing(self):
        text = read(INSTALL_CERTS)
        self.assertTrue(text.startswith("#!/bin/sh\n"))
        body = text.split("set -eu", 1)[1]
        for tool in ("bash", "python", "curl", "wget"):
            self.assertNotIn(tool, body)


class Documentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Getting started states what is untested and sets the container up; the Dev Container
        # reference holds what the container is and what it needs.
        cls.page = read(ROOT / "docs" / "getting-started.md")
        cls.section = cls.page[cls.page.index("## Prerequisites"):cls.page.index("## Without the Dev Container")]
        cls.ref = read(ROOT / "docs" / "dev-container.md")
        cls.readme = read(ROOT / "README.md")

    def test_the_section_names_the_supported_route_and_only_x86_64_ran_in_ci(self):
        self.assertIn("This is the supported route", self.section)
        self.assertNotIn("WSL2", self.section)
        self.assertIn("x86_64", self.section)
        self.assertIn("binfmt", self.ref)
        self.assertNotIn("emulated and slow", self.section)
        self.assertNotIn("emulated and slow", self.ref)

    def test_the_readme_does_not_promise_other_architectures(self):
        line = self.readme[self.readme.index("Supported:"):]
        line = line[:line.index(".")]
        self.assertIn("x86_64", line)
        self.assertNotIn("any host", line)

    def test_the_rerun_output_names_the_west_update_reminder(self):
        # On a rerun setup.sh still prints the reminder to run west update after a pin move (SetupRuns).
        text = " ".join(self.ref.split())
        self.assertNotIn(", nothing for a step that is already done", text)
        self.assertIn("almost nothing for a step that is already done", text)
        self.assertIn("reminds you to run `west update` after the pin in `west.yml` moves", text)

    def test_the_certificate_route_names_the_buildkit_bind_mount(self):
        text = " ".join(self.ref.split())
        self.assertIn("BuildKit bind mount", text)
        self.assertIn("a builder without BuildKit stops at that step", text)

    def test_the_section_names_the_differences_from_the_ci_runner(self):
        for word in ("actions/setup-python", "python3-venv", "curl", "sudo", "clang-tidy-18"):
            self.assertIn(word, self.ref)

    def test_the_section_says_what_the_container_job_builds_and_runs(self):
        self.assertIn("RT1060-EVKB", self.ref)
        self.assertIn("cross-build", self.ref)

    def test_the_section_covers_a_failed_setup_and_the_wsl_resources(self):
        self.assertIn("bash .devcontainer/setup.sh", self.section)
        self.assertIn(".wslconfig", self.ref)
        self.assertIn("processors", self.ref)

    def test_the_product_include_check_is_not_said_to_predate_the_pin_in_the_workflow(self):
        self.assertNotIn("predates", read(WORKFLOW))

    def test_the_product_include_check_is_not_said_to_predate_the_pin_in_ci(self):
        # The pinned crux-pilot contains the script with the hash that ci.yml checks, so the comment
        # above the download says so instead of claiming that the pin predates the script.
        text = read(CI)
        self.assertNotIn("predates", text)
        comment = " ".join(
            line.strip().lstrip("#").strip()
            for line in text[: text.index("- name: Run the Crux Pilot product include check")]
            .splitlines()[-6:]
            if line.strip().startswith("#")
        )
        self.assertIn("The crux-pilot revision pinned in west.yml contains the same script", comment)


if __name__ == "__main__":
    unittest.main()
