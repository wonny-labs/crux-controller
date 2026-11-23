# SPDX-License-Identifier: Apache-2.0
"""Checks of the one Dev Container: it is board-ready, builds without the J-Link package, and the host-side steps.

The Dev Container is one configuration. It always has the USB bus of the host and a device cgroup rule, and it
installs the SEGGER J-Link software when a package or a hosted copy is given. Nothing here starts Docker, a
probe or the network: the install script is run only up to its first decision, and scripts/dev-shell.sh runs
against a stand-in for docker.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEVCONTAINER = ROOT / ".devcontainer"
JLINK = DEVCONTAINER / "jlink"


class OneConfiguration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (DEVCONTAINER / "devcontainer.json").read_text()
        cls.data = json.loads(cls.text)
        cls.dockerfile = (DEVCONTAINER / "Dockerfile").read_text()

    def test_there_is_no_second_configuration_and_no_board_shell(self):
        self.assertEqual([], sorted(p.name for p in DEVCONTAINER.rglob("devcontainer.json")
                                    if p != DEVCONTAINER / "devcontainer.json"))
        self.assertFalse((DEVCONTAINER / "board").exists())
        self.assertFalse((ROOT / "scripts" / "board-shell.sh").exists())

    def test_the_usb_bus_and_the_device_cgroup_rule_are_there_and_nothing_wider(self):
        args = self.data["runArgs"]
        self.assertIn("--device-cgroup-rule=c 189:* rmw", args)
        self.assertIn("/dev/bus/usb:/dev/bus/usb", args)
        for word in ("--privileged", "docker.sock", "host.docker.internal", "--network", "/mnt/c", "--device="):
            self.assertNotIn(word, self.text)

    def test_the_jlink_build_arguments_default_to_auto_with_no_package_and_no_url(self):
        args = self.data["build"]["args"]
        self.assertEqual("auto", args["CRUX_JLINK"])
        for name in ("CRUX_JLINK_DEB", "CRUX_JLINK_DEB_SHA256", "CRUX_JLINK_URL"):
            self.assertEqual("", args[name], name)

    def test_the_dockerfile_installs_jlink_unless_it_is_switched_off_and_never_from_segger(self):
        self.assertRegex(self.dockerfile, r"(?m)^COPY jlink/ ")
        self.assertIn('"$CRUX_JLINK" != 0', self.dockerfile)
        self.assertIn("install-jlink.sh", self.dockerfile)
        self.assertNotRegex(self.dockerfile, r"(?i)\b(curl|wget)\b[^\n]*(http|segger)")
        self.assertNotRegex(self.dockerfile, r"(?m)^ADD ")
        self.assertNotRegex(self.dockerfile, r"(?mi)^ARG\s+\w*proxy")

    def test_bootstrap_runs_after_creation_and_prints_its_status_on_attach(self):
        self.assertEqual("bash scripts/bootstrap.sh --keep-going", self.data["postCreateCommand"])
        self.assertEqual("bash scripts/bootstrap.sh status", self.data["postAttachCommand"])
        self.assertEqual("${localEnv:CRUX_BOOTSTRAP:all}", self.data["containerEnv"]["CRUX_BOOTSTRAP"])

    def test_the_name_does_not_claim_a_hardware_result(self):
        self.assertIn("Crux Controller", self.data["name"])
        self.assertNotIn("tested on hardware", self.data["name"].lower())

    def test_the_layout_check_still_runs_on_the_host_before_the_container_is_created(self):
        self.assertEqual("bash .devcontainer/check-host.sh", self.data["initializeCommand"])


class JlinkFolder(unittest.TestCase):
    def test_the_package_folder_tracks_only_its_readme_and_ignore_file(self):
        ignore = (JLINK / "packages" / ".gitignore").read_text().split()
        self.assertIn("*", ignore)
        listing = subprocess.run(["git", "-C", str(ROOT), "ls-files", ".devcontainer/jlink"],
                                 capture_output=True, text=True, check=False).stdout.split()
        self.assertEqual([], [n for n in listing if n.endswith(".deb")])

    def test_the_udev_rule_has_one_home_in_the_pinned_crux_checkout(self):
        # board-host installs the rule of the Crux checkout; a second copy here would drift from it.
        self.assertFalse((JLINK / "99-crux-jlink.rules").exists())
        pin = re.search(r"revision: ([0-9a-f]{40})", (ROOT / "west.yml").read_text()).group(1)
        page = (ROOT / "docs" / "board-bring-up.md").read_text()
        self.assertIn(f"crux-pilot/blob/{pin}/.devcontainer/jlink/99-crux-jlink.rules", page)
        for name in ("install-jlink.sh",):
            self.assertNotIn("from 99-crux-jlink.rules on the Linux host", (JLINK / name).read_text())

    def test_every_relative_link_of_the_markdown_files_under_devcontainer_resolves(self):
        found = sorted(DEVCONTAINER.rglob("*.md"))
        self.assertTrue(found)
        for path in found:
            for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", path.read_text()):
                if re.match(r"[a-z]+:", target):
                    continue
                file_part, _, anchor = target.partition("#")
                resolved = (path.parent / file_part).resolve()
                self.assertTrue(resolved.exists(), f"{path.relative_to(ROOT)}: {target}")
                if anchor and resolved.suffix == ".md":
                    heads = [re.sub(r"[^\w\- ]", "", h.lower().replace("`", "")).replace(" ", "-")
                             for h in re.findall(r"(?m)^#{1,6} (.*)$", resolved.read_text())]
                    self.assertIn(anchor, heads, f"{path.relative_to(ROOT)}: {target}")

    def test_the_install_script_is_posix_sh_with_the_spdx_line_second(self):
        path = JLINK / "install-jlink.sh"
        lines = path.read_text().splitlines()
        self.assertEqual(["#!/bin/sh", "# SPDX-License-Identifier: Apache-2.0"], lines[:2])
        self.assertTrue(os.access(path, os.X_OK))


class InstallScriptDecisions(unittest.TestCase):
    """The branches of install-jlink.sh that end before apt-get."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = pathlib.Path(self._tmp.name)

    def run_script(self, **env):
        full = {"PATH": "/usr/bin:/bin"}
        full.update(env)
        return subprocess.run(["sh", str(JLINK / "install-jlink.sh"), str(self.folder)],
                              capture_output=True, text=True, env=full)

    def test_auto_without_a_package_warns_and_succeeds(self):
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("warning: no SEGGER J-Link package", result.stderr)

    def test_one_without_a_package_fails_and_names_where_to_put_it(self):
        result = self.run_script(CRUX_JLINK="1")
        self.assertEqual(1, result.returncode)
        self.assertIn(".devcontainer/jlink/packages/", result.stderr)

    def test_a_url_needs_the_checksum_and_https(self):
        result = self.run_script(CRUX_JLINK_URL="https://example.invalid/x.deb")
        self.assertEqual(1, result.returncode)
        self.assertIn("CRUX_JLINK_DEB_SHA256", result.stderr)
        result = self.run_script(CRUX_JLINK_URL="http://example.invalid/x.deb", CRUX_JLINK_DEB_SHA256="0" * 64)
        self.assertEqual(1, result.returncode)
        self.assertIn("https://", result.stderr)

    def test_two_packages_are_refused(self):
        for version in ("V800", "V810"):
            (self.folder / f"JLink_Linux_{version}_x86_64.deb").write_bytes(b"x")
        result = self.run_script()
        self.assertEqual(1, result.returncode)
        self.assertIn("exactly one", result.stderr)

    def test_a_wrong_checksum_stops_before_the_install(self):
        (self.folder / "JLink_Linux_V800_x86_64.deb").write_bytes(b"x")
        result = self.run_script(CRUX_JLINK_DEB_SHA256="0" * 64)
        self.assertEqual(1, result.returncode)
        self.assertIn("expected", result.stderr)

    def test_an_unknown_mode_is_refused(self):
        self.assertEqual(1, self.run_script(CRUX_JLINK="yes").returncode)


class DevShellRuns(unittest.TestCase):
    """scripts/dev-shell.sh against a stand-in for docker, in a throwaway workspace."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = pathlib.Path(self._tmp.name).resolve()
        self.repo = base / "ws" / "crux-controller"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / ".devcontainer").mkdir()
        shutil.copy(ROOT / "scripts" / "dev-shell.sh", self.repo / "scripts" / "dev-shell.sh")
        self.usb = base / "usb"
        self.bin = base / "bin"
        self.bin.mkdir()
        self.log = base / "docker.log"
        docker = self.bin / "docker"
        docker.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{self.log}"\n')
        docker.chmod(0o755)

    def run_script(self, *args, usb=True, **env):
        if usb:
            self.usb.mkdir(exist_ok=True)
        full = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.usb.parent / "home"),
                "CRUX_BOARD_USB_DIR": str(self.usb), **env}
        return subprocess.run(["bash", str(self.repo / "scripts" / "dev-shell.sh"), *args],
                              capture_output=True, text=True, env=full, stdin=subprocess.DEVNULL)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def run_line(self):
        runs = [c for c in self.calls() if c.startswith("run ")]
        self.assertEqual(1, len(runs), self.calls())
        return runs[0]

    def test_with_a_usb_folder_the_container_gets_it_with_the_narrow_rule(self):
        result = self.run_script("west", "--version")
        self.assertEqual(0, result.returncode, result.stderr)
        run = self.run_line()
        self.assertIn(f"-v {self.usb}:/dev/bus/usb", run)
        self.assertIn("--device-cgroup-rule c 189:* rmw", run)
        for word in ("--privileged", "docker.sock", "--network", "--device "):
            self.assertNotIn(word, run)

    def test_without_a_usb_folder_it_still_runs_and_passes_no_usb_flag(self):
        result = self.run_script("true", usb=False)
        self.assertEqual(0, result.returncode, result.stderr)
        run = self.run_line()
        self.assertNotIn("/dev/bus/usb", run)
        self.assertNotIn("device-cgroup-rule", run)

    def test_it_is_one_build_and_one_run(self):
        self.run_script("true")
        self.assertEqual(1, len([c for c in self.calls() if c.startswith("build ")]))

    def test_the_hosted_package_settings_reach_the_build_by_name_only(self):
        url = "https://packages.invalid/secret-path/JLink.deb"
        self.run_script("true", CRUX_JLINK_URL=url, CRUX_JLINK_DEB_SHA256="a" * 64)
        build = [c for c in self.calls() if c.startswith("build ")][0]
        self.assertIn("--build-arg CRUX_JLINK_URL", build)
        self.assertIn("--build-arg CRUX_JLINK_DEB_SHA256", build)
        self.assertNotIn(url, self.log.read_text())

    def test_it_runs_the_bootstrap_entry_for_the_workspace_before_the_command(self):
        self.run_script("west", "--version")
        run = self.run_line()
        self.assertIn("bash scripts/bootstrap.sh zephyr", run)
        self.assertTrue(run.endswith("west --version"), run)

    def test_it_passes_no_proxy_variable_to_the_build(self):
        self.run_script("true", HTTP_PROXY="http://proxy.invalid:3128")
        self.assertNotRegex(self.log.read_text(), r"(?i)proxy")


if __name__ == "__main__":
    unittest.main()
