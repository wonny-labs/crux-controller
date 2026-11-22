# SPDX-License-Identifier: Apache-2.0
"""Checks of the setup pages: the facts in docs/try-on-native-sim.md and docs/troubleshooting.md that a
file of this repository can disprove.

They read files only. They do not start Docker, use the network or run the scripts. A statement about
how a tool behaves on a developer machine is not checked here: the page labels those.
"""

import os
import pathlib
import re
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "try-on-native-sim.md"
TROUBLE = ROOT / "docs" / "troubleshooting.md"
README = ROOT / "README.md"
DEVCONTAINER = ROOT / ".devcontainer"
WORKFLOWS = ROOT / ".github" / "workflows"

# Pages of the documentation set that other changes add. A link to one of them resolves in the
# final tree, so a link check of this page does not insist on the file.
PLANNED_PAGES = {"docs/README.md", "docs/first-change.md", "docs/reviewing.md"}

ONE_SHOT_TWISTER = (
    "west twister -p native_sim/native/64 -T crux-controller/tests/native_sim "
    "--inline-logs --clobber-output -O twister-out"
)


def read(path):
    return pathlib.Path(path).read_text()


def norm(text):
    """Collapse whitespace and line continuations so that a command compares by its words."""
    return " ".join(text.replace("\\", " ").split())


def headings(text):
    """(level, title, first line index of the body) of every heading outside a code fence."""
    found = []
    fenced = False
    for number, line in enumerate(text.splitlines()):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else re.match(r"^(#{1,6}) (.+?)\s*$", line)
        if match:
            found.append((len(match.group(1)), match.group(2), number + 1))
    return found


def section(text, title):
    """The text of the heading `title` up to the next heading of the same or a higher level."""
    lines = text.splitlines()
    found = headings(text)
    for index, (level, name, start) in enumerate(found):
        if name == title:
            end = len(lines)
            for later_level, _, later_start in found[index + 1:]:
                if later_level <= level:
                    end = later_start - 1
                    break
            return "\n".join(lines[start - 1 - 1:end])
    raise AssertionError(f"no heading {title!r}")


def slug(title):
    plain = re.sub(r"[`*]", "", title).lower()
    return re.sub(r"[^\w\- ]", "", plain).replace(" ", "-")


def anchors(text):
    seen = {}
    result = set()
    for _, title, _ in headings(text):
        base = slug(title)
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    return result


def code_blocks(text, language="bash"):
    return re.findall(r"```" + language + r"\n(.*?)```", text, re.DOTALL)


SKIPPED_FOLDERS = ("build", ".venv", "__pycache__", ".pytest_cache")


def files_with_carriage_return(root):
    """The text files of the repository that hold a CR byte.

    With Git, only the tracked files count: a runner or a developer machine also holds compiled
    Python files and build output that were never part of the repository. Without Git the folder is
    walked, skipping hidden folders, build output and compiled files. A file with a NUL byte is binary.
    """
    root = pathlib.Path(root)
    listing = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)
    if listing.returncode == 0:
        names = [name for name in listing.stdout.decode("utf-8", "surrogateescape").split("\0") if name]
    else:
        names = []
        for directory, folders, files in os.walk(root):
            folders[:] = [
                folder for folder in folders
                if not folder.startswith(".") and folder not in SKIPPED_FOLDERS
                and not folder.startswith("twister-out")
            ]
            for name in files:
                if not name.endswith(".pyc"):
                    names.append(str((pathlib.Path(directory) / name).relative_to(root)))
    found = []
    for name in sorted(names):
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" not in data and b"\r" in data:
            found.append(name)
    return found


def ztest_count(directory):
    total = 0
    for path in pathlib.Path(directory).rglob("*.c"):
        total += len(re.findall(r"^ZTEST\(", read(path), re.MULTILINE))
    return total


def testcase_ids(directory):
    ids = []
    for path in sorted(pathlib.Path(directory).rglob("testcase.yaml")):
        ids += list(yaml.safe_load(read(path))["tests"])
    return ids


def backticked_repository_paths(text):
    """Tokens in backticks that name a file or folder of this repository."""
    top = ("scripts/", "docs/", "tests/", ".devcontainer/", ".github/", "budgets/", "app/", "workload/",
           "release/")
    roots = ("west.yml", "CONTRIBUTING.md", "README.md", "RELEASE.md", "CHANGELOG.md", ".clang-format",
             ".clang-tidy", ".gitignore")
    paths = set()
    for token in re.findall(r"`([^`\n]+)`", text):
        token = token.strip()
        if " " in token or any(mark in token for mark in "<>*$"):
            continue
        if token.startswith(top) or token in roots:
            paths.add(token.rstrip(","))
    return sorted(paths)


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(PAGE)
        cls.dev = section(cls.text, "Dev container")
        cls.quick = section(cls.text, "Quick start")
        cls.setup = read(DEVCONTAINER / "setup.sh")
        cls.shell = read(ROOT / "scripts" / "dev-shell.sh")


class Structure(Page):
    def test_the_quick_start_is_the_first_subsection_of_the_dev_container_section(self):
        found = headings(self.text)
        titles = [title for _, title, _ in found]
        container = titles.index("Dev container")
        self.assertEqual("Quick start", titles[container + 1])
        self.assertEqual(3, found[container + 1][0])

    def test_the_container_route_comes_before_the_native_route(self):
        titles = [title for _, title, _ in headings(self.text)]
        self.assertLess(titles.index("Dev container"), titles.index("What you need first"))

    def test_the_page_no_longer_says_that_everything_runs_on_ubuntu_24_04(self):
        self.assertNotIn("Everything below runs on", self.text)

    def test_the_opening_names_both_routes_in_order(self):
        opening = self.text[:self.text.index("\n## ")]
        self.assertLess(opening.index("1. "), opening.index("2. "))
        self.assertIn("(#quick-start)", opening)
        self.assertIn("(#what-you-need-first)", opening)

    def test_the_opening_says_what_a_macos_user_can_do_natively(self):
        opening = self.text[:self.text.index("\n## ")]
        self.assertIn("macOS", opening)
        self.assertIn("tooling tests", opening)
        self.assertIn("boundary check", opening)
        self.assertIn("host tests", opening)

    def test_the_evidence_section_follows_the_commands(self):
        titles = [title for _, title, _ in headings(self.text)]
        why = titles.index("Why the evidence comes from CI")
        for earlier in ("Run the S1 to S5 scenarios", "Run the host tests",
                        "Run the tooling tests and the boundary check", "If something fails"):
            self.assertLess(titles.index(earlier), why, earlier)
        self.assertLess(why, titles.index("What has been checked"))

    def test_every_numbered_list_counts_up_by_one(self):
        fenced = False
        previous = None
        for number, line in enumerate(self.text.splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            match = re.match(r"^(\d+)\. ", line)
            if match:
                value = int(match.group(1))
                if previous is not None:
                    self.assertEqual(previous + 1, value, f"line {number}: {line[:50]}")
                previous = value
            elif line.strip() and not line.startswith((" ", "\t")):
                previous = None

    def test_the_sections_that_the_task_names_exist(self):
        titles = {title for _, title, _ in headings(self.text)}
        for title in ("Network and prerequisites", "Behind a proxy or with a company certificate",
                      "Layout", "After a pin or SDK change",
                      "If the dev container fails"):
            self.assertIn(title, titles)
        # The copy procedures moved to docs/history/copy-procedures.md; the guide describes a clone.
        self.assertNotIn("From a copy without Git history", titles)
        self.assertIn("From a copy without Git history", read(ROOT / "docs" / "history" / "copy-procedures.md"))

    def test_the_headings_that_other_files_link_to_still_exist(self):
        found = anchors(self.text)
        for anchor in ("dev-container", "why-the-evidence-comes-from-ci", "what-has-been-checked",
                       "what-you-need-first", "run-the-s1-to-s5-scenarios"):
            self.assertIn(anchor, found)


class QuickStart(Page):
    def commands(self):
        return "\n".join(code_blocks(self.quick))

    def test_the_docker_steps_are_there(self):
        commands = self.commands()
        self.assertIn('sudo usermod -aG docker "$USER"', commands)
        self.assertIn("sudo service docker start", commands)
        self.assertIn("docker run --rm hello-world", commands)
        self.assertIn("/etc/wsl.conf", self.quick)

    def test_the_sources_go_in_a_folder_named_crux_controller_under_a_parent_of_its_own(self):
        self.assertIn("~/work/crux-controller-workspace/crux-controller", self.quick)
        self.assertIn("/mnt/c", self.quick)
        self.assertIn("empty", self.quick)

    def test_the_exec_bit_restore_covers_the_scripts_that_the_container_needs(self):
        for name in ("scripts/dev-shell.sh", ".devcontainer/setup.sh"):
            self.assertTrue((ROOT / name).is_file(), name)
        self.assertTrue(list((ROOT / "scripts").glob("*.sh")))
        self.assertTrue(list(DEVCONTAINER.glob("*.sh")))

    def test_the_first_run_command_and_what_done_looks_like(self):
        self.assertIn("bash scripts/dev-shell.sh west --version", self.commands())
        # The setup script prints this line last, and `west --version` then prints its own.
        self.assertIn("printf 'setup: workspace %s, Zephyr SDK %s, %s\\n'", self.setup)
        sdk = re.search(r"ENV ZEPHYR_SDK_VERSION=(\S+)", read(DEVCONTAINER / "Dockerfile")).group(1)
        west = re.search(r"^west==(\S+)$", read(DEVCONTAINER / "requirements-tools.txt"), re.M).group(1)
        self.assertIn(f"setup: workspace /workspaces/ws, Zephyr SDK {sdk}, West version: v{west}", self.quick)

    def test_the_one_shot_twister_command_is_the_one_that_ci_and_the_container_job_run(self):
        commands = self.commands()
        self.assertIn(
            "bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && " + ONE_SHOT_TWISTER + "'", commands
        )
        # dev-shell.sh runs a command with the repository as working directory, so the command
        # changes into the workspace folder first, as the container job does.
        self.assertIn("-w /workspaces/ws/crux-controller", self.shell)
        container_job = norm(read(WORKFLOWS / "devcontainer.yml"))
        self.assertIn("cd /workspaces/ws " + ONE_SHOT_TWISTER, container_job)
        ci_steps = yaml.safe_load(read(WORKFLOWS / "ci.yml"))["jobs"]["s1"]["steps"]
        ci_run = [step["run"] for step in ci_steps if step.get("name") == "Run the S1 scenario on native_sim"]
        self.assertEqual([ONE_SHOT_TWISTER], [norm(run) for run in ci_run])

    def test_the_tooling_tests_run_through_the_script_as_the_container_job_runs_them(self):
        self.assertIn("bash scripts/dev-shell.sh python -m unittest discover -s tests/tooling", self.commands())
        self.assertIn("dev-shell.sh python -m unittest discover -s tests/tooling",
                      norm(read(WORKFLOWS / "devcontainer.yml")))

    def test_one_scenario_has_a_command_and_its_directory_exists(self):
        self.assertIn("-T crux-controller/tests/native_sim/s1", self.quick)
        self.assertTrue((ROOT / "tests" / "native_sim" / "s1" / "testcase.yaml").is_file())

    def test_the_quick_start_says_where_the_outputs_are(self):
        self.assertIn("twister-out", self.quick)
        self.assertIn("build/", self.quick)
        self.assertIn("build/", read(ROOT / ".gitignore"))

    def test_every_script_named_in_a_command_of_the_page_exists(self):
        for block in code_blocks(self.text):
            for token in re.findall(r"(?<![\w/.-])((?:scripts|\.devcontainer)/[\w*./-]+)", block):
                if "*" in token:
                    self.assertTrue(list(ROOT.glob(token)), token)
                else:
                    self.assertTrue((ROOT / token).exists(), token)


class Counts(Page):
    def test_the_native_sim_directory_has_17_configurations_and_31_test_cases(self):
        self.assertEqual(17, len(testcase_ids(ROOT / "tests" / "native_sim")))
        self.assertEqual(31, ztest_count(ROOT / "tests" / "native_sim"))
        self.assertIn("17 of 17 executed test configurations passed", self.text)
        self.assertIn("31 of 31 executed test cases passed", self.text)

    def test_the_s6_directory_has_one_configuration_and_ten_test_cases(self):
        self.assertEqual(1, len(testcase_ids(ROOT / "tests" / "native_sim_mbed")))
        self.assertEqual(10, ztest_count(ROOT / "tests" / "native_sim_mbed"))
        self.assertIn("1 of 1 executed test configurations passed", self.text)
        self.assertIn("10 of 10 executed test cases passed", self.text)

    def test_the_page_lists_every_twister_id_of_the_native_sim_directory(self):
        for identifier in testcase_ids(ROOT / "tests" / "native_sim"):
            parts = identifier.split(".")
            self.assertIn(".".join(parts[:3]), self.text, identifier)
            if len(parts) > 3:
                self.assertIn(f".{parts[3]}", self.text, identifier)


class Network(Page):
    def test_the_page_names_the_registry_host_of_the_dockerfile(self):
        base = re.search(r"^FROM (\S+?)/", read(DEVCONTAINER / "Dockerfile"), re.M).group(1)
        self.assertIn(f"`{base}`", section(self.text, "Network and prerequisites"))

    def test_the_page_names_the_hosts_of_the_manifest_and_the_package_installs(self):
        hosts = section(self.text, "Network and prerequisites")
        for remote in re.findall(r"url-base: https://([\w.-]+)/", read(ROOT / "west.yml")):
            self.assertIn(f"`{remote}`", hosts)
        self.assertIn("pip install", self.setup)
        self.assertIn("PyPI", hosts)
        self.assertIn("apt-get install", read(DEVCONTAINER / "Dockerfile"))
        self.assertIn("api.github.com", hosts)

    def test_the_token_variable_is_the_one_that_the_scripts_pass_on(self):
        self.assertIn("GH_TOKEN", self.shell)
        self.assertIn("GH_TOKEN", self.setup)
        self.assertIn("`GH_TOKEN`", section(self.text, "Network and prerequisites"))

    def test_the_wsl_resource_guidance_is_kept(self):
        self.assertIn(".wslconfig", self.dev)
        self.assertIn("processors", self.dev)

    def test_the_offline_case_is_not_claimed(self):
        self.assertRegex(section(self.text, "Network and prerequisites"), r"(?i)offline.*not tested")


class Proxy(Page):
    """The page describes what the files do at this revision, and no more."""

    def setUp(self):
        self.proxy = section(self.text, "Behind a proxy or with a company certificate")
        self.shell_lower = self.shell.lower()
        self.json = read(DEVCONTAINER / "devcontainer.json")

    def test_the_section_names_the_variables_the_files_and_the_host_side_settings(self):
        for name in ("http_proxy", "https_proxy", "no_proxy", "CRUX_EXTRA_CA_FILE", ".crux-extra-ca.crt",
                     "~/.docker/config.json", "GH_TOKEN"):
            self.assertIn(f"`{name}`", self.proxy)
        self.assertIn("docker run --rm curlimages/curl -I https://github.com", self.proxy)
        self.assertIn("general knowledge", self.proxy)

    def test_the_vs_code_route_passes_the_proxy_variables_and_the_page_says_so(self):
        config = __import__("json").loads(self.json)
        for name in ("http_proxy", "https_proxy", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
            self.assertEqual("${localEnv:" + name + "}", config["build"]["args"][name])
            self.assertEqual("${localEnv:" + name + "}", config["containerEnv"][name])
        self.assertEqual("${localEnv:GH_TOKEN}", config["remoteEnv"]["GH_TOKEN"])
        self.assertRegex(self.proxy, r"VS Code route passes")

    def test_dev_shell_passes_no_proxy_variable_and_no_certificate_and_the_page_does_not_say_it_does(self):
        # If the script starts to pass them, this test fails and the page has to change with it.
        message = ("a change to dev-shell.sh adds these features: update docs/try-on-native-sim.md and "
                   "docs/troubleshooting.md in the same change")
        self.assertNotIn("proxy", self.shell_lower, message)
        self.assertNotIn("CRUX_EXTRA_CA_FILE", self.shell, message)
        self.assertNotIn("check-host", self.shell, message)
        self.assertIn("-e GH_TOKEN", self.shell)
        self.assertRegex(self.proxy, r"`scripts/dev-shell\.sh` passes only `GH_TOKEN`")
        for phrase in ("passes it into the image build", "Give `scripts/dev-shell.sh` the certificate",
                       "mounted read-only", "a message of `scripts/dev-shell.sh` that the daemon",
                       "dev-shell.sh` passes it", "dev-shell.sh` runs the host check"):
            self.assertNotIn(phrase, self.text)

    def test_setup_handles_the_ca_file_and_the_variable_as_the_page_says(self):
        self.assertIn(".crux-extra-ca.crt", self.setup)
        self.assertIn("CRUX_EXTRA_CA_FILE", self.setup)
        self.assertIn("which is not a readable file", self.setup)
        self.assertIn("which is not a readable file", self.text)
        self.assertIn("~/work/crux-controller-workspace/.crux-extra-ca.crt", self.proxy)
        self.assertIn("/workspaces/ws/.crux-extra-ca.crt", self.proxy)
        convert = "openssl x509 -inform der -in company.cer -out company.crt"
        self.assertIn(convert, self.setup)
        self.assertIn(convert, self.proxy)
        for word in ("PEM", "pip.conf", "both routes"):
            self.assertIn(word, self.proxy)
        self.assertIn(".crux-extra-ca.crt", read(DEVCONTAINER / "check-host.sh"))

    def test_the_proxy_variables_are_exported_by_setup_and_only_their_names_are_printed(self):
        self.assertIn("http_proxy:HTTP_PROXY https_proxy:HTTPS_PROXY no_proxy:NO_PROXY", self.setup)
        self.assertRegex(self.proxy, r"names[^.]*never (the )?values|never (the )?values")
        self.assertIn("127.0.0.1", self.proxy)
        self.assertIn("docker inspect", self.proxy)

    def test_the_dockerfile_declares_no_proxy_argument_as_the_page_may_say(self):
        dockerfile = read(DEVCONTAINER / "Dockerfile")
        self.assertNotRegex(dockerfile, r"(?m)^ARG\s+(?i:http_proxy|https_proxy|no_proxy)")


class CopyAndLayout(Page):
    def test_the_layout_section_explains_the_mount_and_the_two_cache_volumes(self):
        layout = section(self.text, "Layout")
        for word in (".west", "zephyr/", "modules/", "crux-pilot", "empty", "/workspaces/ws"):
            self.assertIn(word, layout)
        self.assertIn("docker volume ls --filter name=crux-controller-dev-cache", layout)
        self.assertIn("docker volume rm", layout)

    def test_the_volume_prefix_is_the_one_of_the_script_and_of_devcontainer_json(self):
        prefix = re.search(r'^volume_prefix="([^"]+)"', self.shell, re.M).group(1)
        self.assertEqual("crux-controller-dev-cache", prefix)
        self.assertIn(f"source={prefix}-${{devcontainerId}}", read(DEVCONTAINER / "devcontainer.json"))
        self.assertIn(f"{prefix}-<", self.text)

    def test_the_workspace_is_the_parent_folder_of_the_clone(self):
        self.assertIn('workspace="$(dirname "$repo")"', self.shell)
        self.assertIn("${localWorkspaceFolder}/..", read(DEVCONTAINER / "devcontainer.json"))

    def test_no_file_of_the_repository_has_a_carriage_return(self):
        # The fix for a copy with CRLF line ends strips every CR. That is safe only while no file
        # of the repository needs one.
        self.assertEqual([], files_with_carriage_return(ROOT))

    def test_the_hidden_files_that_a_zip_can_lose_exist(self):
        for name in (".clang-format", ".clang-tidy", ".gitignore", ".devcontainer", ".github"):
            self.assertTrue((ROOT / name).exists(), name)

    def test_the_recipe_after_a_pin_or_sdk_change(self):
        after = section(self.text, "After a pin or SDK change")
        self.assertIn("west update", after)
        self.assertIn("bash .devcontainer/setup.sh", after)
        self.assertIn("rebuil", after)
        self.assertIn("/opt/crux-cache/sdk", after)
        dockerfile = read(DEVCONTAINER / "Dockerfile")
        self.assertIn("ZEPHYR_SDK_INSTALL_DIR=/opt/crux-cache/sdk/zephyr-sdk-${ZEPHYR_SDK_VERSION}", dockerfile)
        self.assertIn("west update", self.setup)

    def test_the_failure_section_points_at_troubleshooting_which_names_the_cases(self):
        # The failure list lives in troubleshooting.md only; this page points there.
        self.assertIn("troubleshooting.md", section(self.text, "If the dev container fails"))
        trouble = read(TROUBLE)
        for word in ("daemon", "docker.sock", "bash\\r", "Permission denied", ".git"):
            self.assertIn(word, trouble)
        # The messages that the pages quote from the scripts are in the scripts.
        self.assertIn("the clone is in a folder named", self.setup)
        self.assertIn("the clone is in a folder named", trouble)
        self.assertIn("looks like a home directory", self.setup)
        self.assertIn("looks like a home directory", trouble)


class OnMain(Page):
    """Statements about setup.sh, check-host.sh and the repository files that exist at this revision."""

    def test_check_host_is_in_the_file_list_and_described(self):
        container = section(self.text, "What the container is")
        self.assertIn("`.devcontainer/check-host.sh`", container)
        self.assertIn("initializeCommand", container)
        self.assertIn('"initializeCommand": "bash .devcontainer/check-host.sh"',
                      read(DEVCONTAINER / "devcontainer.json"))
        script = read(DEVCONTAINER / "check-host.sh")
        for marker in (".ssh", ".gnupg", ".bashrc", ".profile", ".gitconfig"):
            self.assertIn(marker, script)
            self.assertIn(f"`{marker}`", container)
        self.assertIn("exit status 2", script)
        self.assertIn("warn", container)

    def test_the_step_failure_message_and_the_rerun_command_are_the_ones_of_setup(self):
        self.assertIn("setup: failed during %s; rerun: bash .devcontainer/setup.sh", self.setup)
        for page in (self.text, read(TROUBLE)):
            self.assertIn("setup: failed during", page)
        self.assertIn("rerun: bash .devcontainer/setup.sh", self.text)

    def test_the_sdk_marker_and_the_one_time_reinstall_are_described(self):
        self.assertIn(".crux-installed", self.setup)
        after = section(self.text, "After a pin or SDK change")
        self.assertIn("`.crux-installed`", after)
        self.assertIn("once", after)
        self.assertIn("several GiB", after)

    def test_setup_recovers_what_the_page_says_it_recovers(self):
        self.assertIn("an interrupted west init", self.setup)
        self.assertIn("is incomplete", self.setup)
        self.assertIn("exec 1>&2", self.setup)
        layout = section(self.text, "What the container is")
        self.assertIn("standard error", layout)

    def test_the_line_ends_are_pinned_by_gitattributes_and_the_page_says_a_clone_has_lf(self):
        self.assertIn("* text=auto eol=lf", read(ROOT / ".gitattributes"))
        self.assertIn(".gitattributes", read(TROUBLE))

    def test_the_page_does_not_call_a_changed_behaviour_planned(self):
        self.assertNotIn("planned", self.text.lower())


class CarriageReturnScan(unittest.TestCase):
    def test_only_a_tracked_file_with_crlf_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "lf.txt").write_bytes(b"one\ntwo\n")
            (root / "crlf.txt").write_bytes(b"one\r\ntwo\r\n")
            (root / "image.bin").write_bytes(b"\0\r\n\0")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\r\n")
            (root / "untracked.txt").write_bytes(b"a\r\n")
            subprocess.run(["git", "-C", str(root), "add", "lf.txt", "crlf.txt", "image.bin"], check=True)
            self.assertEqual(["crlf.txt"], files_with_carriage_return(root))

    def test_without_git_hidden_folders_build_output_and_compiled_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "lf.txt").write_bytes(b"one\n")
            (root / "crlf.txt").write_bytes(b"one\r\n")
            for folder in (".hidden", "build", "__pycache__", ".pytest_cache", "twister-out-s1", ".venv"):
                (root / folder).mkdir()
                (root / folder / "f.txt").write_bytes(b"\r\n")
            (root / "mod.pyc").write_bytes(b"\r\n")
            self.assertEqual(["crlf.txt"], files_with_carriage_return(root))


class Review(Page):
    """Statements that a review of the first version found false or unsafe."""

    def test_no_sentence_promises_a_dev_container_result_for_every_revision(self):
        self.assertNotIn("for the revision that you are reading", self.text)
        checked = section(self.text, "What has been checked")
        self.assertIn("Actions tab", checked)
        self.assertIn("by hand", checked)
        workflow = yaml.safe_load(read(WORKFLOWS / "devcontainer.yml"))
        paths = workflow[True]["pull_request"]["paths"]
        self.assertNotIn("docs/**", paths)
        self.assertIn("a docs-only", checked)

    def test_the_runs_of_the_checks_name_their_revision(self):
        checked = section(self.text, "What has been checked")
        self.assertIn("f7d3fab", checked)
        self.assertIn("not a published commit", checked)
        self.assertNotIn("at that revision", checked)

    def test_the_quick_start_sends_a_proxy_user_to_the_host_part_first(self):
        text = self.text
        start = self.quick
        self.assertIn("Behind a company proxy?", start)
        self.assertLess(start.index("Behind a company proxy?"), start.index("1. Install Docker Engine"))
        self.assertIn("(#behind-a-proxy-or-with-a-company-certificate)", start)

    def test_the_daemon_proxy_does_not_cover_the_apt_steps_of_the_build(self):
        proxy = section(self.text, "Behind a proxy or with a company certificate")
        self.assertIn("not the `apt-get` steps of the image build", proxy)
        self.assertIn("daemon.json", proxy)

    def test_the_vs_code_environment_is_labelled_and_a_running_server_is_mentioned(self):
        proxy = section(self.text, "Behind a proxy or with a company certificate")
        self.assertIn("keeps its old environment", proxy)
        self.assertIn("wsl --shutdown", proxy)
        self.assertRegex(proxy, r"environment of the process that starts VS Code[^.]*general knowledge")

    def test_docker_hub_is_listed_for_both_pulls_of_the_page(self):
        hosts = section(self.text, "Network and prerequisites")
        row = next(line for line in hosts.splitlines() if line.startswith("| Docker Hub"))
        self.assertIn("hello-world", row)
        self.assertIn("curlimages/curl", row)

    def test_the_wsl_daemon_start_failure_row_is_there_and_labelled(self):
        row = next(line for line in read(TROUBLE).splitlines() if "iptables" in line)
        self.assertIn("general knowledge", row)
        self.assertIn("not tested", row)


class MarkdownLinks(unittest.TestCase):
    """Relative links and anchors of the three files that this page set owns resolve."""

    FILES = (PAGE, TROUBLE)

    def test_the_relative_links_and_anchors_resolve(self):
        problems = []
        for path in self.FILES + (README,):
            text = read(path)
            body = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", body):
                if re.match(r"^(https?:|mailto:)", target):
                    continue
                file_part, _, fragment = target.partition("#")
                resolved = (path.parent / file_part).resolve() if file_part else path
                relative = resolved.relative_to(ROOT).as_posix() if ROOT in resolved.parents or resolved == ROOT else ""
                if relative in PLANNED_PAGES and not resolved.exists():
                    continue
                if not resolved.exists():
                    problems.append(f"{path.name}: {target}: no such file")
                    continue
                if fragment and resolved.suffix == ".md" and fragment not in anchors(read(resolved)):
                    problems.append(f"{path.name}: {target}: no such heading")
        self.assertEqual([], problems)


class Troubleshooting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(TROUBLE)

    def rows(self):
        rows = []
        for line in self.text.splitlines():
            if line.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line):
                # A pipe inside a cell is written \| and does not end the cell.
                rows.append([cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip()[1:-1])])
        return rows

    def test_the_tables_have_five_columns_and_a_header(self):
        header = ["Symptom", "Where it appears", "Cause", "Fix", "More"]
        rows = self.rows()
        self.assertIn(header, rows)
        for row in rows:
            self.assertEqual(5, len(row), row)

    def test_there_are_enough_symptoms_and_none_is_empty(self):
        rows = [row for row in self.rows() if row[0] != "Symptom"]
        self.assertGreaterEqual(len(rows), 20)
        for row in rows:
            for cell in row:
                self.assertTrue(cell, row)

    def test_every_file_or_script_that_the_page_names_exists(self):
        paths = backticked_repository_paths(self.text)
        self.assertTrue(paths)
        for name in paths:
            self.assertTrue((ROOT / name).exists(), name)

    def test_every_message_that_the_page_quotes_is_in_the_file_that_prints_it(self):
        messages = {
            "scripts/check-format.sh": ("but clang-format", "is required", "cannot run"),
            "scripts/check_boundary.py": ("run from the repository root or pass --repo",
                                          "boundary violation(s)", "no checked tree under",
                                          "not a public Crux header at the pinned revision"),
            "scripts/analyze_host.py": ("cannot run cmake", "Not analysed",
                                        "is version", "cannot run"),
            "scripts/check_spdx.py": ("needs the first line",),
            "budgets/check.py": ("unknown step, no limits are declared for it",
                                 "measured but no limit is declared",
                                 "a limit is declared but the region was not measured"),
            ".github/workflows/budget.yml": ("the step was not built",),
            "scripts/dev-shell.sh": ("the clone must be in a folder named crux-controller",),
            ".devcontainer/setup.sh": ("the clone is in a folder named", "looks like a home directory",
                                       "failed during", "which is not a readable file",
                                       "is not a PEM certificate", "is incomplete",
                                       "no install marker"),
            ".devcontainer/check-host.sh": ("the clone is in a folder named", "is your home directory",
                                            "looks like a home directory",
                                            "the clone is directly in the root directory",
                                            "also holds"),
            "tests/tooling/test_text_accuracy.py": ("does not name these scripts",),
        }
        for name, fragments in messages.items():
            source = read(ROOT / name)
            for fragment in fragments:
                self.assertIn(fragment, source, f"{name}: {fragment}")
                self.assertIn(fragment, self.text, f"troubleshooting.md: {fragment}")

    def test_the_format_check_version_is_the_one_of_the_script_and_the_tool_pins(self):
        required = re.search(r'required_version="([^"]+)"', read(ROOT / "scripts" / "check-format.sh")).group(1)
        self.assertEqual(required, re.search(r"^clang-format==(\S+)$",
                                             read(DEVCONTAINER / "requirements-tools.txt"), re.M).group(1))
        self.assertIn(f"clang-format {required}", self.text)
        self.assertIn(f"clang-format=={required}", self.text)

    def test_the_boundary_exit_codes_are_the_ones_of_the_script(self):
        source = read(ROOT / "scripts" / "check_boundary.py")
        self.assertIn("return 2", source)
        self.assertIn("return 1", source)
        self.assertIn("exit status 2", self.text)

    def test_the_boundary_line_format_is_the_one_that_the_script_prints(self):
        self.assertIn('print(f"{v.path}:{v.line}: {v.include}: {v.reason}")',
                      read(ROOT / "scripts" / "check_boundary.py"))
        self.assertIn("path:line: include: reason", self.text)

    def test_the_strong_boundary_form_is_the_one_that_ci_runs(self):
        strong = "check_boundary.py --repo crux-controller --crux-root crux-pilot"
        self.assertIn(strong, self.text)
        self.assertIn(strong, norm(read(WORKFLOWS / "ci.yml")))

    def test_the_doc_pinned_tests_it_names_exist(self):
        for name in ("test_text_accuracy.py", "test_s4.py", "test_s5.py", "test_s6.py"):
            self.assertIn(name, self.text)
            self.assertTrue((ROOT / "tests" / "tooling" / name).is_file(), name)

    def test_the_ci_log_section_points_at_the_job_table_and_does_not_copy_it(self):
        self.assertIn("CONTRIBUTING.md#build-and-test", self.text)
        self.assertNotIn("| Workflow | Jobs | When |", self.text)
        for job in ("Tooling tests", "Static analysis", "Boundary check"):
            self.assertIn(job, read(ROOT / "CONTRIBUTING.md"))

    def test_the_job_names_in_the_log_guide_are_jobs_of_the_workflows(self):
        guide = section(self.text, "How to read the CI logs")
        names = []
        for workflow in ("ci.yml", "budget.yml", "devcontainer.yml"):
            names += [job["name"] for job in yaml.safe_load(read(WORKFLOWS / workflow))["jobs"].values()]
        quoted = ("Tooling tests", "Static analysis", "Patch style", "Boundary check", "West pins", "Budget",
                  "Dev container", "S1", "S2 build")
        for job in quoted:
            self.assertIn(f"`{job}`", guide)
            self.assertTrue(any(name.startswith(job) for name in names), job)

    def test_the_pep_668_and_enum_compare_rows_refer_to_the_pages_that_state_them(self):
        self.assertIn("PEP 668", self.text)
        self.assertIn("externally-managed-environment", self.text)
        self.assertIn("-Werror=enum-compare", self.text)
        self.assertIn("-Werror=enum-compare", read(ROOT / "docs" / "adding-a-step.md"))

    def test_the_text_has_no_private_planning_reference(self):
        self.assertIsNone(re.search(r"\b(?:OD|WD)[0-9]+\b|skeleton plan|work package", self.text, re.I))


class Readme(unittest.TestCase):
    def test_the_quick_start_section_points_at_the_first_hour_and_the_details(self):
        text = read(README)
        start = text.index("## Quick start")
        paragraph = text[start:text.index("\n## ", start + 1)]
        self.assertIn("docs/first-hour.md", paragraph)
        self.assertIn("docs/try-on-native-sim.md#quick-start", paragraph)
        self.assertIn("bash scripts/dev-shell.sh", paragraph)
        self.assertIn("docs/troubleshooting.md", paragraph)
        self.assertIn("WSL2", paragraph)
        self.assertIn("Docker Engine", paragraph)
        self.assertLessEqual(len(paragraph.strip().splitlines()), 16)


if __name__ == "__main__":
    unittest.main()
