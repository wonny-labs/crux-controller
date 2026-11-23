# SPDX-License-Identifier: Apache-2.0
"""Checks of the tutorial page and the board route.

The tests are structural: the pages have the sections that a reader needs, their links resolve, every
repository file that a command names exists, the build and run commands are those of the CI jobs, and the
Dev Container keeps the safety properties of the route (no privileged container, the J-Link package from the
pinned download, a placed file or a hosted copy, a read-only compare before any write). They do not pin sentences. The
Dev Container files are tested in test_one_container.py. Nothing here starts Docker, touches USB or uses the
network.
"""

import pathlib
import re
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
TUTORIAL = "docs/tutorial.md"
BOARD_PAGE = "docs/board-bring-up.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
NET_NOTE = "docs/findings/s2-first-board-run.md"


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


def from_root(command):
    """A command of CI, which runs from the workspace folder, as it reads from the repository root."""
    return norm(command).replace("crux-controller/", "")


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
        wanted = (r"dev container", r"host tests", r"tooling tests.*boundary|boundary.*tooling tests",
                  r"native_sim", r"board", r"build", r"next")
        found = [h.lower() for h in headings(TUTORIAL)]
        position = -1
        for pattern in wanted:
            matches = [i for i, h in enumerate(found) if re.search(pattern, h) and i > position]
            self.assertTrue(matches, f"no heading for {pattern!r} after position {position}: {found}")
            position = matches[0]

    def test_it_carries_no_ci_timings(self):
        # Approved change: a measurement of a CI run has no place on a tutorial.
        self.assertNotRegex(read(TUTORIAL), r"\d+ min\b")
        self.assertFalse([h for h in headings(TUTORIAL) if "how long" in h.lower()])

    def test_both_container_routes_are_named(self):
        part = section(TUTORIAL, r"dev container")
        self.assertIn("scripts/dev-shell.sh", part)
        self.assertIn("Reopen in Container", part)

    def test_the_build_is_the_workload_cross_build_of_ci(self):
        # CI runs from the workspace folder; the tutorial runs the same command from the repository root.
        expected = from_root(ci_step_run("workload", "Cross-build workload with the baseline gate required"))
        self.assertTrue(any(expected in norm(code) for code in code_blocks(read(TUTORIAL))), expected)

    def test_the_native_sim_run_is_the_twister_step_of_ci(self):
        expected = from_root(ci_step_run("workload", "Run the workload scenario on native_sim"))
        self.assertTrue(any(expected in norm(code) for code in code_blocks(read(TUTORIAL))), expected)

    def test_the_host_tool_and_boundary_commands_are_those_of_ci(self):
        body = norm("\n".join(code_blocks(read(TUTORIAL))))
        for command in ("cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=OFF",
                        "ctest --test-dir build/host --output-on-failure",
                        "python -m unittest discover -s tests/tooling",
                        "python scripts/check_boundary.py --crux-root ../crux-pilot"):
            self.assertIn(command, body, command)
        # CI runs the boundary check from the workspace folder with workspace-relative paths.
        ci = "python crux-controller/scripts/check_boundary.py --repo crux-controller --crux-root crux-pilot"
        self.assertIn(ci, norm(CI.read_text()))
        self.assertEqual("python scripts/check_boundary.py --crux-root ../crux-pilot",
                         from_root(ci).replace(" --repo crux-controller", "").replace("--crux-root crux-pilot",
                                                                                      "--crux-root ../crux-pilot"))

    def test_the_clone_address_is_generic(self):
        # The tutorial starts from a working Dev Container; the clone is step 3 of Getting started.
        self.assertNotIn("git clone", read(TUTORIAL))
        for name in (TUTORIAL, "docs/getting-started.md"):
            self.assertNotIn("github.com/wonny-labs", read(name), name)
        self.assertIn("git clone -c core.autocrlf=false <repository-url> crux-controller", read("docs/getting-started.md"))

    def test_it_points_at_the_detailed_pages_instead_of_copying_them(self):
        targets = {path for path, _, _ in links(TUTORIAL)}
        for name in ("docs/getting-started.md", "docs/troubleshooting.md", "docs/first-change.md",
                     "docs/board-bring-up.md"):
            self.assertIn(name, targets, name)
        setup = sum(len(read(name).split()) for name in
                    ("docs/getting-started.md", "docs/dev-container.md", "docs/native-setup.md"))
        self.assertLess(len(read(TUTORIAL).split()), setup / 3)

    def test_parts_a_to_c_with_the_no_board_line_and_the_board_table(self):
        body = read(TUTORIAL)
        parts = [h for h in headings(TUTORIAL) if h.startswith("Part ")]
        self.assertEqual(["Part A", "Part B", "Part C"], [p[:6] for p in parts])
        self.assertLess(body.index("## Part B"), body.index("## Part C"))
        part_c = section(TUTORIAL, r"Part C")
        self.assertIn("| Board | `-b` target | Probe | Board guide |", part_c)
        self.assertIn("`mimxrt1060_evk@B//qspi`", part_c)
        self.assertIn("board-bring-up.md", part_c)
        self.assertIn("roadmap.md", part_c)
        self.assertRegex(part_c, r"authori[sz]ation")

    def test_no_status_words(self):
        # Status lives on the roadmap; the tutorial links it.
        for word in ("Experimental", "Unstable", "frozen", "to be removed", "deprecated"):
            self.assertNotIn(word, read(TUTORIAL), word)

    def test_it_carries_no_untested_trail(self):
        # Approved change: a verification trail has no place on a tutorial.
        self.assertNotRegex(read(TUTORIAL), r"(?i)untested|nobody has run|WSL2[^.]*not (been )?(run|tested)")

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
        wanted = (r"what is needed", r"build", r"attach.*probe|probe.*wsl", r"dev container with the probe",
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
        self.assertNotIn('MODE="0666"', body)
        for line in body.splitlines():
            if "--privileged" in line:
                self.assertRegex(line, r"(?i)\bno\b|\bnot\b|never|without", line)

    def test_the_jlink_software_comes_from_the_pinned_download_or_an_override(self):
        body = norm(read(BOARD_PAGE))
        self.assertIn(".devcontainer/jlink/packages/", body)
        self.assertIn("CRUX_JLINK_URL", body)
        self.assertIn("CRUX_JLINK_SEGGER_VERSION", body)
        self.assertIn("accepts SEGGER's terms of use", body)
        # The build downloads it; no command on the page fetches it by hand.
        self.assertNotRegex("\n".join(code_blocks(read(BOARD_PAGE))), r"(?i)(curl|wget)[^\n]*segger")

    def test_the_net_hashes_and_network_values_are_those_of_the_net_note(self):
        page, note = read(BOARD_PAGE), read(NET_NOTE)
        hashes = set(re.findall(r"\b[0-9a-f]{64}\b", page))
        self.assertTrue(hashes)
        for value in hashes:
            self.assertIn(value, note, value)
        for value in ("192.168.77.1", "192.168.77.2", "42420", "02:43:52:55:58:20", "180 seconds"):
            self.assertIn(value, page, value)
        self.assertIn('"192.168.77.2"', read("app/conf/net.conf"))

    def test_the_net_board_build_is_the_one_of_ci(self):
        expected = norm(ci_step_run("net", "Cross-build net with the baseline gate required"))
        self.assertTrue(any(expected in norm(code) for code in code_blocks(read(BOARD_PAGE))), expected)

    def test_the_jlink_device_and_flash_base_match_zephyrs_board_settings_as_the_page_cites_them(self):
        body = read(BOARD_PAGE)
        self.assertIn("MIMXRT1062xxx6A", body)
        self.assertIn("0x60000000", body)
        self.assertIn("board.cmake", body)

    def test_the_page_links_the_dev_container_files_of_the_board_route(self):
        targets = {path for path, _, _ in links(BOARD_PAGE)}
        for name in (".devcontainer/devcontainer.json", ".devcontainer/jlink/install-jlink.sh",
                     "scripts/bootstrap.sh", ".vscode/launch.json"):
            self.assertIn(name, targets, name)

    def test_the_page_names_the_one_host_step_and_the_auto_attach(self):
        body = read(BOARD_PAGE)
        self.assertIn("usbipd attach --wsl --busid <busid> --auto-attach", body)
        self.assertIn("scripts/bootstrap.sh board-host", body)

    def test_the_page_says_auto_speed_with_the_fallback_and_names_the_two_profiles(self):
        body = norm(read(BOARD_PAGE))
        self.assertIn("auto", body)
        self.assertRegex(body, r"4000.{0,40}400.{0,40}100")
        self.assertIn("Board: Flash and run to main", body)
        self.assertIn("Board: Attach (no reset)", body)

    def test_the_page_no_longer_mentions_a_second_container_or_the_board_shell(self):
        body = read(BOARD_PAGE)
        for word in ("board-shell", "build-base", ".devcontainer/board", "optional board container"):
            self.assertNotIn(word, body, word)


if __name__ == "__main__":
    unittest.main()
