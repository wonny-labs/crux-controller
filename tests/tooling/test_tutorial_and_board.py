# SPDX-License-Identifier: Apache-2.0
"""Checks of the tutorial page, the board route and the optional board container.

The tests are structural: the pages have the sections that a reader needs, their links resolve, every
repository file that a command names exists, the build and run commands are those of the CI jobs, and the
board container keeps the safety properties of the route (no privileged container, the J-Link package only
from a local file, a read-only compare before any write). They do not pin sentences. Nothing here starts
Docker, touches USB or uses the network: the board shell script runs against a stand-in for docker.
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
TUTORIAL = "docs/tutorial.md"
BOARD_PAGE = "docs/board-bring-up.md"
BOARD_DIR = ROOT / ".devcontainer" / "board"
BOARD_SHELL = ROOT / "scripts" / "board-shell.sh"
BUILD_BASE = BOARD_DIR / "build-base.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"
S2_NOTE = "docs/findings/s2-first-board-run.md"


def read(name):
    return (ROOT / name).read_text()


def norm(text):
    return " ".join(text.replace("\\", " ").split())


def without_code(body):
    return re.sub(r"```.*?```", "", body, flags=re.S)


def code_blocks(body, language=None):
    blocks = re.findall(r"```([\w-]*)\n(.*?)```", body, flags=re.S)
    return [code for lang, code in blocks if language is None or lang == language]


def slug(heading):
    heading = heading.strip().lower().replace("`", "")
    heading = re.sub(r"[^\w\- ]", "", heading)
    return heading.replace(" ", "-")


def headings(name):
    return [m.group(2) for m in re.finditer(r"(?m)^(#{2,3}) (.*)$", without_code(read(name)))]


def anchors(name):
    found, seen = set(), {}
    for line in without_code(read(name)).splitlines():
        match = re.match(r"#{1,6}\s+(.*)$", line)
        if match:
            base = slug(match.group(1))
            count = seen.get(base, 0)
            seen[base] = count + 1
            found.add(base if count == 0 else f"{base}-{count}")
    return found


def links(name):
    out = []
    base = (ROOT / name).parent
    for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", without_code(read(name))):
        if re.match(r"[a-z]+:", target):
            continue
        path, _, anchor = target.partition("#")
        resolved = (base / path).resolve() if path else (ROOT / name).resolve()
        out.append((str(resolved.relative_to(ROOT)), anchor, target))
    return out


def section(name, heading_pattern):
    """The text of the first `##` section whose heading matches the pattern, up to the next `##`."""
    body = read(name)
    match = re.search(rf"^## .*{heading_pattern}.*$", body, re.M | re.I)
    assert match, f"{name}: no section matching {heading_pattern!r}"
    end = body.find("\n## ", match.end())
    return body[match.start():end if end != -1 else len(body)]


def ci_step_run(job, fragment):
    steps = [s for s in yaml.safe_load(CI.read_text())["jobs"][job]["steps"] if fragment in s.get("name", "")]
    assert len(steps) == 1, fragment
    board = yaml.safe_load(CI.read_text())["jobs"][job]["env"].get("BOARD", "")
    return steps[0]["run"].replace("${{ env.BOARD }}", board)


REPO_PATH = re.compile(r"(?<![\w/.-])((?:scripts|\.devcontainer|tests|app|docs)/[\w*./@-]+)")


def named_paths(code):
    """Repository paths named in a code block, relative to the repository root."""
    found = set()
    for token in REPO_PATH.findall(code):
        found.add(token.rstrip(".,;:"))
    for token in re.findall(r"crux-controller/((?:scripts|\.devcontainer|tests|app)/[\w./-]+)", code):
        found.add(token.rstrip(".,;:"))
    return {p for p in found if "*" not in p and "<" not in p}


class Common:
    PAGE = None

    def test_every_relative_link_and_anchor_resolves(self):
        for path, anchor, target in links(self.PAGE):
            self.assertTrue((ROOT / path).exists(), f"{self.PAGE}: {target}")
            if anchor and path.endswith(".md"):
                self.assertIn(anchor, anchors(path), f"{self.PAGE}: {target}")

    def test_every_repository_file_that_a_command_names_exists(self):
        for code in code_blocks(read(self.PAGE)):
            for path in named_paths(code):
                self.assertTrue((ROOT / path).exists(), f"{self.PAGE}: {path}")

    def test_no_personal_path(self):
        self.assertNotRegex(read(self.PAGE), r"/Users/|/home/[a-z]|/private/|[A-Z]:\\\\")


class Tutorial(Common, unittest.TestCase):
    PAGE = TUTORIAL

    def test_the_page_exists(self):
        self.assertTrue((ROOT / TUTORIAL).is_file())

    def test_the_steps_are_there_in_order(self):
        wanted = (r"clone", r"dev container", r"build", r"native_sim", r"host tests",
                  r"tooling tests.*boundary|boundary.*tooling tests", r"next")
        found = [h.lower() for h in headings(TUTORIAL)]
        position = -1
        for pattern in wanted:
            matches = [i for i, h in enumerate(found) if re.search(pattern, h) and i > position]
            self.assertTrue(matches, f"no heading for {pattern!r} after position {position}: {found}")
            position = matches[0]

    def test_it_has_a_section_with_the_times_and_says_where_they_come_from(self):
        part = section(TUTORIAL, r"how long")
        self.assertRegex(part, r"\d+ min")
        self.assertIn("CI", part)

    def test_both_container_routes_are_named(self):
        part = section(TUTORIAL, r"dev container")
        self.assertIn("scripts/dev-shell.sh", part)
        self.assertIn("Reopen in Container", part)

    def test_the_build_is_the_s1_cross_build_of_ci(self):
        expected = norm(ci_step_run("s1", "Cross-build S1 with the baseline gate required"))
        self.assertTrue(any(expected in norm(code) for code in code_blocks(read(TUTORIAL))), expected)

    def test_the_native_sim_run_is_the_twister_step_of_ci(self):
        expected = norm(ci_step_run("s1", "Run the S1 scenario on native_sim"))
        self.assertTrue(any(expected in norm(code) for code in code_blocks(read(TUTORIAL))), expected)

    def test_the_host_tool_and_boundary_commands_are_those_of_ci(self):
        body = norm("\n".join(code_blocks(read(TUTORIAL))))
        for command in ("cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=OFF",
                        "ctest --test-dir build/host --output-on-failure",
                        "python -m unittest discover -s tests/tooling",
                        "python crux-controller/scripts/check_boundary.py --repo crux-controller --crux-root crux-pilot"):
            self.assertIn(command, body, command)

    def test_the_clone_address_is_generic(self):
        self.assertIn("<repository-url>", read(TUTORIAL))
        self.assertNotIn("github.com/wonny-labs", read(TUTORIAL))

    def test_it_points_at_the_detailed_pages_instead_of_copying_them(self):
        targets = {path for path, _, _ in links(TUTORIAL)}
        for name in ("docs/try-on-native-sim.md", "docs/troubleshooting.md", "docs/first-change.md",
                     "docs/board-bring-up.md"):
            self.assertIn(name, targets, name)
        self.assertLess(len(read(TUTORIAL).split()), len(read("docs/try-on-native-sim.md").split()) / 3)

    def test_it_says_what_is_untested(self):
        self.assertRegex(read(TUTORIAL), r"(?i)nobody has run[^.]*WSL2|WSL2[^.]*not (been )?(run|tested)")

    def test_it_is_linked_at_the_top_of_the_readme_and_of_the_index(self):
        for name, before in (("README.md", "## What it provides"), ("docs/README.md", "## Paths by task")):
            top = read(name).split(before)[0]
            self.assertRegex(top, r"\]\((?:docs/)?tutorial\.md\)", name)


class BoardPage(Common, unittest.TestCase):
    PAGE = BOARD_PAGE

    def test_it_says_at_the_top_that_the_route_is_untested_on_hardware(self):
        top = read(BOARD_PAGE).split("\n## ")[0]
        self.assertRegex(top, r"(?i)untested on hardware")

    def test_the_authorisation_paragraph_stays_before_the_first_section(self):
        top = " ".join(read(BOARD_PAGE).split("\n## ")[0].split())
        self.assertIn("**Authorisation.**", top)
        self.assertIn("project owner's explicit authorisation", top)
        self.assertIn("an earlier approval does not carry over", top)
        self.assertIn("stop before touching the board", top)

    def test_the_route_sections_are_there_in_order(self):
        wanted = (r"what is needed", r"build", r"attach.*probe|probe.*wsl", r"board container",
                  r"compare", r"flash", r"debug", r"restore", r"record", r"stop conditions")
        found = [h.lower() for h in headings(BOARD_PAGE)]
        position = -1
        for pattern in wanted:
            matches = [i for i, h in enumerate(found) if re.search(pattern, h) and i > position]
            self.assertTrue(matches, f"no heading for {pattern!r} after position {position}: {found}")
            position = matches[0]

    def test_flash_and_debug_use_the_jlink_runner(self):
        code = "\n".join(code_blocks(read(BOARD_PAGE)))
        commands = re.findall(r"(?m)^\s*west (flash|debug|attach)\b(.*)$", code)
        self.assertTrue({"flash", "debug"} <= {c for c, _ in commands}, commands)
        for verb, rest in commands:
            self.assertRegex(rest, r"(--runner|-r) jlink\b", f"west {verb}{rest}")

    def test_the_read_only_compare_comes_before_any_write(self):
        body = read(BOARD_PAGE)
        compare = re.search(r"(?m)^## .*[Cc]ompare.*$", body).start()
        first_write = min(m.start() for m in re.finditer(r"(?m)^\s*west (flash|debug)\b", body))
        self.assertLess(compare, first_write)

    def test_the_jlink_commander_scripts_are_read_only(self):
        scripts = code_blocks(read(BOARD_PAGE), "jlink")
        self.assertTrue(scripts, "the compare step has no J-Link Commander script (a ```jlink block)")
        allowed = {"savebin", "verifybin", "exit", "q", "qc", "sleep"}
        for script in scripts:
            for line in script.splitlines():
                word = line.strip().split(" ")[0].lower() if line.strip() else ""
                if word:
                    self.assertIn(word, allowed, f"not a read-only J-Link Commander command: {line}")

    def test_no_privileged_container_and_the_usb_access_is_narrow(self):
        body = read(BOARD_PAGE)
        self.assertIn("--device-cgroup-rule", body)
        self.assertIn("/dev/bus/usb", body)
        self.assertIn("usbipd", body)
        self.assertIn('MODE="0660"', body)
        self.assertIn('GROUP="plugdev"', body)
        self.assertNotIn('MODE="0666"', body)
        for line in body.splitlines():
            if "--privileged" in line:
                self.assertRegex(line, r"(?i)\bno\b|\bnot\b|never|without", line)

    def test_the_jlink_package_comes_from_a_file_you_download(self):
        self.assertIn(".devcontainer/board/jlink/", read(BOARD_PAGE))
        self.assertNotRegex("\n".join(code_blocks(read(BOARD_PAGE))), r"(?i)(curl|wget)[^\n]*segger")

    def test_the_s2_hashes_and_network_values_are_those_of_the_s2_note(self):
        page, note = read(BOARD_PAGE), read(S2_NOTE)
        hashes = set(re.findall(r"\b[0-9a-f]{64}\b", page))
        self.assertTrue(hashes)
        for value in hashes:
            self.assertIn(value, note, value)
        for value in ("192.168.77.1", "192.168.77.2", "42420", "02:43:52:55:58:20", "180 seconds"):
            self.assertIn(value, page, value)
        self.assertIn('"192.168.77.2"', read("app/conf/s2.conf"))

    def test_the_s2_board_build_is_the_one_of_ci(self):
        expected = norm(ci_step_run("s2", "Cross-build S2 with the baseline gate required"))
        self.assertTrue(any(expected in norm(code) for code in code_blocks(read(BOARD_PAGE))), expected)

    def test_the_jlink_device_and_flash_base_match_zephyrs_board_settings_as_the_page_cites_them(self):
        body = read(BOARD_PAGE)
        self.assertIn("MIMXRT1062xxx6A", body)
        self.assertIn("0x60000000", body)
        self.assertIn("board.cmake", body)

    def test_the_page_links_the_board_container_files(self):
        targets = {path for path, _, _ in links(BOARD_PAGE)}
        for name in (".devcontainer/board/devcontainer.json", ".devcontainer/board/Dockerfile",
                     "scripts/board-shell.sh"):
            self.assertIn(name, targets, name)


class BoardContainerFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.json_text = (BOARD_DIR / "devcontainer.json").read_text()
        cls.data = json.loads(cls.json_text)
        cls.default = json.loads((ROOT / ".devcontainer" / "devcontainer.json").read_text())
        cls.dockerfile = (BOARD_DIR / "Dockerfile").read_text()

    def test_it_is_a_layer_on_the_default_image(self):
        self.assertRegex(self.dockerfile, r"(?m)^ARG BASE_IMAGE=crux-controller-dev$")
        self.assertRegex(self.dockerfile, r"(?m)^FROM \$\{BASE_IMAGE\}$")
        self.assertEqual("crux-controller-dev", self.data["build"]["args"]["BASE_IMAGE"])
        self.assertIn("--platform=linux/amd64", self.data["build"]["options"])

    def test_the_jlink_package_is_only_copied_from_the_local_folder_and_never_fetched(self):
        self.assertRegex(self.dockerfile, r"(?m)^COPY jlink/ ")
        self.assertNotRegex(self.dockerfile, r"(?i)\b(curl|wget|ADD)\b[^\n]*(http|segger)")
        self.assertNotRegex(self.dockerfile, r"(?m)^ADD ")
        self.assertIn("JLink_Linux_*_x86_64.deb", self.dockerfile)

    def test_no_jlink_package_is_tracked_and_the_folder_ignores_them(self):
        ignore = (BOARD_DIR / "jlink" / ".gitignore").read_text().split()
        self.assertIn("*", ignore)
        listing = subprocess.run(["git", "-C", str(ROOT), "ls-files", ".devcontainer/board"],
                                 capture_output=True, text=True, check=False).stdout.split()
        self.assertEqual([], [n for n in listing if n.endswith(".deb")])

    def test_no_privilege_and_only_the_usb_bus_with_a_device_cgroup_rule(self):
        for word in ("--privileged", "docker.sock", "host.docker.internal", "--network", "/mnt/c", "--device="):
            self.assertNotIn(word, self.json_text)
        self.assertNotIn("features", self.data)
        self.assertIn("--device-cgroup-rule=c 189:* rmw", self.data["runArgs"])
        # The udev rule of the board page gives the probe to the group plugdev, mode 0660.
        self.assertIn("--group-add=plugdev", self.data["runArgs"])
        self.assertIn("source=/dev/bus/usb,target=/dev/bus/usb,type=bind", self.data["mounts"])

    def test_the_workspace_user_volume_and_setup_are_those_of_the_default_container(self):
        for key in ("workspaceMount", "workspaceFolder", "remoteUser", "updateRemoteUserUID", "postCreateCommand",
                    "containerEnv", "remoteEnv"):
            self.assertEqual(self.default[key], self.data[key], key)
        self.assertIn(self.default["mounts"][0], self.data["mounts"])

    def test_the_base_image_is_built_on_the_host_first(self):
        self.assertEqual("bash .devcontainer/board/build-base.sh", self.data["initializeCommand"])
        text = BUILD_BASE.read_text()
        self.assertIn("bash .devcontainer/check-host.sh", text.replace('"$repo/', "").replace("$repo/", ""))
        self.assertIn("--platform linux/amd64", text)
        self.assertIn('"$repo/.devcontainer"', text)

    def test_the_proxy_settings_of_the_host_reach_the_board_build_as_in_the_default_container(self):
        proxies = {k: v for k, v in self.default["build"]["args"].items() if "proxy" in k.lower()}
        self.assertEqual(6, len(proxies))
        for name, value in proxies.items():
            self.assertEqual(value, self.data["build"]["args"].get(name), name)

    def test_the_board_dockerfile_declares_no_proxy_argument_like_the_default_one(self):
        # Docker predefines the proxy build arguments; a declared ARG would put a value into the image history.
        self.assertNotRegex(self.dockerfile, r"(?mi)^ARG\s+\w*proxy")

    def test_the_name_says_it_is_untested(self):
        self.assertIn("Crux Controller", self.data["name"])
        self.assertIn("untested", self.data["name"].lower())

    def test_the_default_container_does_not_reach_usb(self):
        text = (ROOT / ".devcontainer" / "devcontainer.json").read_text()
        for word in ("/dev/bus/usb", "device-cgroup-rule", "jlink"):
            self.assertNotIn(word, text)

    def test_the_scripts_are_executable_bash_with_the_spdx_line_second(self):
        for path in (BOARD_SHELL, BUILD_BASE):
            text = path.read_text()
            self.assertTrue(os.access(path, os.X_OK), path.name)
            self.assertEqual(["#!/usr/bin/env bash", "# SPDX-License-Identifier: Apache-2.0"], text.splitlines()[:2])
            self.assertIn("set -euo pipefail", text)


class BoardShellRuns(unittest.TestCase):
    """scripts/board-shell.sh against a stand-in for docker, in a throwaway workspace."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name).resolve()
        self.repo = base / "ws" / "crux-controller"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / ".devcontainer" / "board" / "jlink").mkdir(parents=True)
        for path in (BOARD_SHELL, BUILD_BASE, ROOT / ".devcontainer" / "check-host.sh"):
            target = self.repo / path.relative_to(ROOT)
            shutil.copy(path, target)
            target.chmod(target.stat().st_mode | stat.S_IXUSR)
        (self.repo / ".devcontainer" / "Dockerfile").write_text("FROM scratch\n")
        (self.repo / ".devcontainer" / "board" / "Dockerfile").write_text("FROM scratch\n")
        self.usb = base / "usb"
        self.usb.mkdir()
        self.bin = base / "bin"
        self.bin.mkdir()
        self.log = base / "docker.log"
        docker = self.bin / "docker"
        docker.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{self.log}"\n')
        docker.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args, extra_env=None):
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.usb.parent / "home"),
               "CRUX_BOARD_USB_DIR": str(self.usb), **(extra_env or {})}
        return subprocess.run(["bash", str(self.repo / "scripts" / "board-shell.sh"), *args],
                              capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, check=False)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_without_the_jlink_package_it_stops_before_docker(self):
        result = self.run_script("true")
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn(".devcontainer/board/jlink/", result.stderr)
        self.assertEqual([], self.calls())

    def test_with_two_packages_it_stops(self):
        for version in ("V800", "V810"):
            (self.repo / ".devcontainer" / "board" / "jlink" / f"JLink_Linux_{version}_x86_64.deb").write_bytes(b"x")
        result = self.run_script("true")
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual([], self.calls())

    def test_without_the_usb_folder_it_stops(self):
        (self.repo / ".devcontainer" / "board" / "jlink" / "JLink_Linux_V800_x86_64.deb").write_bytes(b"x")
        self.usb.rmdir()
        result = self.run_script("true")
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("usbipd", result.stderr)
        self.assertEqual([], self.calls())

    def test_it_builds_both_images_and_runs_with_narrow_usb_access(self):
        (self.repo / ".devcontainer" / "board" / "jlink" / "JLink_Linux_V800_x86_64.deb").write_bytes(b"x")
        result = self.run_script("west", "--version")
        self.assertEqual(0, result.returncode, result.stderr)
        calls = self.calls()
        builds = [c for c in calls if c.startswith("build ")]
        runs = [c for c in calls if c.startswith("run ")]
        self.assertEqual(2, len(builds), calls)
        self.assertTrue(builds[0].endswith("/.devcontainer"), builds[0])
        self.assertIn("BASE_IMAGE=crux-controller-dev", builds[1])
        self.assertTrue(builds[1].endswith("/.devcontainer/board"), builds[1])
        self.assertEqual(1, len(runs), calls)
        run = runs[0]
        self.assertIn("--device-cgroup-rule c 189:* rmw", run)
        self.assertIn("--group-add plugdev", run)
        self.assertIn(f"-v {self.usb}:/dev/bus/usb", run)
        self.assertIn(f"-v {self.repo.parent}:/workspaces/ws", run)
        self.assertRegex(run, r"-v crux-controller-dev-cache-\d+:/opt/crux-cache")
        self.assertIn("bash .devcontainer/setup.sh", run)
        self.assertTrue(run.endswith("west --version"), run)
        for word in ("--privileged", "docker.sock", "--network", "--device "):
            self.assertNotIn(word, run)

    def test_a_proxy_of_the_host_reaches_both_builds_by_name_only(self):
        (self.repo / ".devcontainer" / "board" / "jlink" / "JLink_Linux_V800_x86_64.deb").write_bytes(b"x")
        secret = "http://user:secret@proxy.invalid:3128"
        result = self.run_script("true", extra_env={"HTTP_PROXY": secret, "no_proxy": "localhost"})
        self.assertEqual(0, result.returncode, result.stderr)
        builds = [c for c in self.calls() if c.startswith("build ")]
        self.assertEqual(2, len(builds), builds)
        for build in builds:
            self.assertIn("--build-arg HTTP_PROXY ", build)
            self.assertIn("--build-arg no_proxy ", build)
            self.assertNotIn("--build-arg https_proxy", build)
        self.assertNotIn(secret, self.log.read_text())

    def test_without_a_proxy_no_proxy_argument_is_passed(self):
        (self.repo / ".devcontainer" / "board" / "jlink" / "JLink_Linux_V800_x86_64.deb").write_bytes(b"x")
        result = self.run_script("true")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotRegex(self.log.read_text(), r"(?i)--build-arg \w*proxy")

    def test_it_uses_the_cache_volume_of_dev_shell(self):
        # The same name for the same workspace folder, so the SDK is not fetched a second time.
        dev_shell = (ROOT / "scripts" / "dev-shell.sh").read_text()
        text = BOARD_SHELL.read_text()
        for line in ('volume_prefix="crux-controller-dev-cache"',
                     'volume="$volume_prefix-$(printf \'%s\' "$workspace" | cksum | cut -d\' \' -f1)"'):
            self.assertIn(line, dev_shell)
            self.assertIn(line, text)


if __name__ == "__main__":
    unittest.main()
