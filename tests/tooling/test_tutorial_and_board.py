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

    def test_the_prerequisites_point_at_the_certificate_folder_before_reopen_in_container(self):
        # Approved change: one conditional pointer; the steps are in the folder README and the symptom is in
        # Getting started.
        part = section(TUTORIAL, r"dev container")
        self.assertIn("re-signs TLS", part)
        self.assertIn("(../.devcontainer/certs/README.md)", part)
        self.assertIn("getting-started.md#prerequisites", part)
        self.assertIn("PEM `.crt`", part)
        self.assertLess(part.index(".devcontainer/certs/"), part.index("Reopen in Container"))

    def test_it_is_linked_at_the_top_of_the_readme_and_of_the_index(self):
        for name, before in (("README.md", "## What it provides"), ("docs/README.md", "## Paths by task")):
            top = read(name).split(before)[0]
            self.assertRegex(top, r"\]\((?:docs/)?tutorial\.md\)", name)


class BoardPage(Common, unittest.TestCase):
    PAGE = BOARD_PAGE

    def test_it_carries_no_untested_trail(self):
        # Approved change: a verification trail has no place on a how-to page.
        self.assertNotRegex(read(BOARD_PAGE), r"(?i)untested|nobody has followed|has never run")

    def test_the_authorisation_paragraph_stays_before_the_first_section(self):
        top = " ".join(read(BOARD_PAGE).split("\n## ")[0].split())
        self.assertIn("**Authorisation.**", top)
        self.assertIn("project owner's explicit authorisation", top)
        self.assertIn("an earlier approval does not carry over", top)
        self.assertIn("stop before touching the board", top)

    def test_the_route_sections_are_there_in_order(self):
        wanted = (r"build", r"connect.*probe", r"dev container with the probe", r"flash.*debug.*restore",
                  r"net.*bench", r"known limits")
        found = [h.lower() for h in headings(BOARD_PAGE)]
        position = -1
        for pattern in wanted:
            matches = [i for i, h in enumerate(found) if re.search(pattern, h) and i > position]
            self.assertTrue(matches, f"no heading for {pattern!r} after position {position}: {found}")
            position = matches[0]

    def test_flash_and_debug_steps_are_the_crux_board_pages_and_not_copied(self):
        # Approved change: the probe, flash, debug and recovery steps have one home, the Crux board pages at the pin.
        code = "\n".join(code_blocks(read(BOARD_PAGE)))
        self.assertNotRegex(code, r"(?m)^\s*west (flash|debug|attach)\b")
        self.assertNotIn("JLinkExe", code)
        pin = re.search(r"revision: ([0-9a-f]{40})", read("west.yml")).group(1)
        body = read(BOARD_PAGE)
        for page in ("docs/boards/mimxrt1060_evkb.md", "docs/board-jlink-usbipd.md"):
            self.assertIn(f"https://github.com/wonny-labs/crux-pilot/blob/{pin}/{page}", body, page)

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

    def test_the_network_values_are_those_of_the_net_image_and_the_net_note(self):
        # Approved change: hashes and the capture window are measurements of one run and stay in the net note.
        page, note = read(BOARD_PAGE), read(NET_NOTE)
        self.assertNotRegex(page, r"\b[0-9a-f]{64}\b")
        for value in ("192.168.77.1", "192.168.77.2", "42420", "02:43:52:55:58:20"):
            self.assertIn(value, page, value)
            self.assertIn(value, note, value)
        self.assertIn('"192.168.77.2"', read("app/conf/net.conf"))

    def test_the_net_board_build_is_the_one_of_ci(self):
        # CI runs from the workspace folder; the page runs the same command from the repository root.
        expected = norm(ci_step_run("net", "Cross-build net with the baseline gate required")).replace(
            "crux-controller/", "")
        self.assertTrue(any(expected in norm(code) for code in code_blocks(read(BOARD_PAGE))), expected)

    def test_the_page_links_the_dev_container_files_of_the_board_route(self):
        targets = {path for path, _, _ in links(BOARD_PAGE)}
        for name in (".devcontainer/devcontainer.json", ".devcontainer/jlink/install-jlink.sh",
                     "scripts/bootstrap.sh", ".vscode/launch.json"):
            self.assertIn(name, targets, name)

    def test_the_probe_is_connected_before_the_first_jlink_check(self):
        # Approved change: on Windows the probe is attached with usbipd-win before lsusb and the J-Link status;
        # bind only when the device is not shared yet; no --auto-attach and no board-host step.
        body = read(BOARD_PAGE)
        step = body[body.index("## 2. Connect the probe"):body.index("## 3.")]
        code = "\n".join(code_blocks(step))
        for command in ("usbipd list", "usbipd bind --busid <BUSID>", "usbipd attach --wsl --busid <BUSID>"):
            self.assertIn(command, code, command)
        self.assertLess(code.index("usbipd list"), code.index("usbipd bind"))
        self.assertLess(code.index("usbipd bind"), code.index("usbipd attach"))
        prose = norm(without_code(step))
        self.assertIn("`1366`", prose)
        self.assertIn("`Not shared`", prose)
        self.assertIn("`Shared`", prose)
        self.assertLess(body.index("## 2. Connect the probe"), body.index("lsusb"))
        self.assertNotIn("board-host", body)

    def test_no_current_page_attaches_with_auto_attach(self):
        # The board page's run list says the recorded Crux run was attached without the option; no step or
        # command of any page uses it.
        for name in (BOARD_PAGE, TUTORIAL, "docs/getting-started.md", "docs/troubleshooting.md",
                     "docs/dev-container.md", "README.md"):
            text = read(name)
            if name == BOARD_PAGE:
                text = text[text.index("## The route"):]
            self.assertNotIn("--auto-attach", text, name)

    def test_the_page_names_the_board_profiles(self):
        body = norm(read(BOARD_PAGE))
        for profile in ("Board: Debug", "Board: Attach", "Board: Attach (external)"):
            self.assertIn(f"**{profile}**", body, profile)

    def test_the_run_list_records_the_crux_run_without_auto_attach(self):
        # Crux's guide at the pin records the attach without --auto-attach in its Dev Container and the earlier
        # runs with a separate board Dev Container configuration.
        body = norm(read(BOARD_PAGE))
        self.assertIn("a usbipd attach without `--auto-attach`", body)
        self.assertIn("an earlier, separate board Dev Container configuration", body)
        self.assertNotIn("with `--auto-attach`", body)
        self.assertIn("Not run: step 2 in the form of this page", body)

    def test_one_plain_list_of_what_has_been_run(self):
        # Approved change: what was run and what was not is in one list, not spread over the steps.
        body = read(BOARD_PAGE)
        self.assertEqual(1, body.count("**What has been run**"))
        self.assertEqual(1, len(re.findall(r"(?m)^Not run: ", body)))

    def test_the_page_no_longer_mentions_a_second_container_or_the_board_shell(self):
        body = read(BOARD_PAGE)
        for word in ("board-shell", "build-base", ".devcontainer/board", "optional board container"):
            self.assertNotIn(word, body, word)


class ProbeAndCertificateHomes(unittest.TestCase):
    """The usbipd explanation, the certificate symptom and the J-Link version each have one home."""

    def test_the_board_page_is_the_one_home_of_the_usbipd_states(self):
        # Getting started names no WSL2 route (test_docs.py), so the board step is the one home.
        body = read(BOARD_PAGE)
        part = body[body.index("## 2. Connect the probe"):body.index("## 3.")]
        for word in ("`Not shared`", "`Shared`", "`Attached`", "`1366`", "usbipd list", "administrator"):
            self.assertIn(word, part, word)
        self.assertIn("https://learn.microsoft.com/en-us/windows/wsl/connect-usb", part)
        self.assertIn("https://github.com/dorssel/usbipd-win", part)
        for name in ("docs/getting-started.md", TUTORIAL, "docs/troubleshooting.md"):
            self.assertNotIn("`Attached`", read(name), name)

    def test_getting_started_points_at_the_probe_step_without_wsl2_steps(self):
        part = section("docs/getting-started.md", r"If you use a board")
        self.assertIn("board-bring-up.md#2-connect-the-probe", part)
        self.assertNotIn("usbipd", part)

    def test_the_set_up_output_is_quoted_from_the_scripts(self):
        # setup.sh prints a setup: line only when a step does work; step() only records the name.
        setup = read(".devcontainer/setup.sh")
        self.assertRegex(setup, r'step\(\) \{\n    current_step="\$1"\n\}')
        quick = section("README.md", r"Quick start")
        self.assertNotIn("as each step starts", quick)
        self.assertNotIn("names each step as it starts", read("docs/dev-container.md"))
        for line in ("setup: failed during", "bootstrap: workspace   ok", "bootstrap: Zephyr SDK  ok"):
            self.assertIn(line, quick, line)
        self.assertIn("printf 'bootstrap: workspace   ok\\n'", read("scripts/bootstrap.sh"))
        self.assertIn("printf 'bootstrap: Zephyr SDK  ok\\n'", read("scripts/bootstrap.sh"))

    def test_no_stale_untested_pointer_for_the_board_route(self):
        for name in ("docs/dev-container.md", "docs/architecture.md"):
            for line in read(name).splitlines():
                if "board-bring-up.md" in line:
                    self.assertNotIn("untested", line, name)

    def test_troubleshooting_has_a_row_for_a_probe_that_is_not_found(self):
        rows = [line for line in read("docs/troubleshooting.md").splitlines()
                if line.startswith("|") and "probe" in line.lower() and "usbipd attach" in line
                and "twice" not in line]
        self.assertEqual(1, len(rows), rows)
        self.assertIn("board-bring-up.md#2-connect-the-probe", rows[0])
        self.assertIn("board-bring-up.md#vs-code-tasks-and-debug-profiles", rows[0])

    def test_the_probe_row_names_the_jlink_failures_of_a_missing_attach(self):
        # The messages are those of Crux's tutorial at the pin; the board tasks here are not run (board page).
        rows = [line for line in read("docs/troubleshooting.md").splitlines()
                if line.startswith("|") and "probe" in line.lower() and "usbipd attach" in line
                and "twice" not in line]
        self.assertEqual(1, len(rows), rows)
        for message in ("`command exited with status 1: ... JLinkExe`", "`jlink: GDB Server Quit Unexpectedly`",
                        "`lsusb -d 1366:`", "not run here"):
            self.assertIn(message, rows[0], message)

    def test_troubleshooting_has_a_row_for_a_probe_that_is_listed_twice_after_a_reattach(self):
        # Symptom first; the steps were reported from a Windows PC and were not run in this repository.
        rows = [line for line in read("docs/troubleshooting.md").splitlines()
                if line.startswith("|") and "twice" in line]
        self.assertEqual(1, len(rows), rows)
        row = rows[0]
        self.assertTrue(row.startswith("| after the probe is detached and attached again, `lsusb -d 1366:`"), row)
        steps = ["`usbipd detach --busid <BUSID>`", "`wsl --shutdown`", "`usbipd attach --wsl --busid <BUSID>`",
                 "`scripts/bootstrap.sh board-host`"]
        for word in steps + ["`Cannot connect to the probe/programmer`", "sudo", "not in the Dev Container",
                             "not run in this repository"]:
            self.assertIn(word, row, word)
        self.assertEqual(sorted(row.index(s) for s in steps), [row.index(s) for s in steps])
        board = read("docs/troubleshooting.md")
        self.assertGreater(board.index(row), board.index("## The board and the probe"))
        self.assertLess(board.index(row), board.index("## Checks that fail locally"))

    def test_troubleshooting_has_a_row_for_missing_jlink_software(self):
        rows = [line for line in read("docs/troubleshooting.md").splitlines()
                if line.startswith("|") and "`required program JLinkExe not found`" in line]
        self.assertEqual(1, len(rows), rows)
        row = rows[0]
        for word in ("`spawn JLinkGDBServer ENOENT`", "**Board: Flash**", "**Board: Debug**",
                     "bash scripts/bootstrap.sh status", "Rebuild Container Without Cache",
                     "board-bring-up.md#3-open-the-dev-container-with-the-probe", "not run here"):
            self.assertIn(word, row, word)
        self.assertNotIn("usbipd attach", row)
        board = read("docs/troubleshooting.md")
        section_start = board.index("## The board and the probe")
        self.assertGreater(board.index(row), section_start)

    def test_the_probe_step_checks_wsl2_before_usbipd(self):
        body = read(BOARD_PAGE)
        step = body[body.index("## 2. Connect the probe"):body.index("## 3.")]
        prose = norm(without_code(step))
        self.assertIn("`wsl -l -v`", prose)
        self.assertIn("`VERSION` `2`", prose)
        self.assertIn("https://learn.microsoft.com/en-us/windows/wsl/compare-versions", prose)
        self.assertLess(step.index("wsl -l -v"), step.index("usbipd list"))

    def test_the_certificate_symptom_is_generic(self):
        # A certificate error breaks every download, not only the J-Link one.
        rows = [line for line in read("docs/troubleshooting.md").splitlines()
                if line.startswith("|") and "SSL certificate problem" in line]
        self.assertEqual(1, len(rows), rows)
        for word in ("pip", "Git", "west", "`.devcontainer/certs/`", "certs/README.md"):
            self.assertIn(word, rows[0], word)
        for name in ("docs/troubleshooting.md", "docs/getting-started.md", "docs/dev-container.md",
                     ".devcontainer/certs/README.md"):
            for line in read(name).splitlines():
                if re.search(r"SSL certificate problem|certificate error", line):
                    self.assertNotIn("J-Link", line, name)
        for name in ("docs/getting-started.md", ".devcontainer/certs/README.md"):
            text = norm(read(name))
            self.assertIn("`curl: (60) SSL certificate problem", text, name)
            self.assertIn("pip, Git or west", text, name)

    def test_the_jlink_version_has_one_home_the_dockerfile_pin(self):
        self.assertRegex(read(".devcontainer/Dockerfile"), r"(?m)^ARG CRUX_JLINK_SEGGER_VERSION=V\d{3}[a-z]$")
        names = [n for n in (ROOT / "docs").glob("*.md")] + [ROOT / "README.md"]
        for path in names:
            self.assertNotRegex(path.read_text(), r"\bV\d\.?\d{2}[a-z]\b", path.name)


if __name__ == "__main__":
    unittest.main()
