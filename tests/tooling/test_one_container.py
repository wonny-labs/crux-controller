# SPDX-License-Identifier: Apache-2.0
"""Checks of the one Dev Container: it is board-ready, builds without the J-Link package, and the host-side steps.

The Dev Container is one configuration. It always has the USB bus of the host and a device cgroup rule, and it
installs the SEGGER J-Link software from a placed package, a hosted copy or the version pinned in the Dockerfile,
downloaded from SEGGER. Nothing here starts Docker, a probe or the network: the install script runs with
stand-ins for curl, apt-get and usermod, and scripts/dev-shell.sh runs against a stand-in for docker.
"""

import hashlib
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
SEGGER_ENDPOINT = "https://www.segger.com/downloads/jlink/"


def dockerfile_arg(text, name):
    match = re.search(rf"^ARG {name}=(\S*)$", text, re.MULTILINE)
    return match.group(1) if match else None


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

    def test_the_dockerfile_installs_jlink_unless_it_is_switched_off_and_leaves_downloads_to_the_script(self):
        self.assertRegex(self.dockerfile, r"(?m)^COPY jlink/ ")
        self.assertIn('"$CRUX_JLINK" != 0', self.dockerfile)
        self.assertIn("install-jlink.sh", self.dockerfile)
        self.assertNotRegex(self.dockerfile, r"(?i)\b(curl|wget)\b[^\n]*(http|segger)")
        self.assertNotRegex(self.dockerfile, r"(?m)^ADD ")
        self.assertNotRegex(self.dockerfile, r"(?mi)^ARG\s+\w*proxy")

    def test_the_segger_version_and_checksum_are_pinned_once_in_the_dockerfile(self):
        # A bump changes these two values and nothing else.
        version = dockerfile_arg(self.dockerfile, "CRUX_JLINK_SEGGER_VERSION")
        digest = dockerfile_arg(self.dockerfile, "CRUX_JLINK_SEGGER_SHA256")
        self.assertRegex(version or "", r"^V[0-9]+[a-z]?$")
        self.assertRegex(digest or "", r"^[0-9a-f]{64}$")
        holders = subprocess.run(["git", "-C", str(ROOT), "grep", "-l", "-F", digest],
                                 capture_output=True, text=True, check=False).stdout.split()
        self.assertEqual([".devcontainer/Dockerfile"], holders)
        args = self.data["build"]["args"]
        self.assertNotIn("CRUX_JLINK_SEGGER_VERSION", args)
        self.assertNotIn("CRUX_JLINK_SEGGER_SHA256", args)

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

    def test_the_install_script_downloads_only_over_https(self):
        install = (JLINK / "install-jlink.sh").read_text()
        lowered = install.lower()
        for forbidden in ("wget", "--no-check-certificate", "insecure", "curl -k"):
            self.assertNotIn(forbidden, lowered)
        curl_lines = [line.strip() for line in install.splitlines()
                      if re.match(r"(if\s+)?curl\s", line.strip())]
        self.assertEqual(2, len(curl_lines), curl_lines)
        for line in curl_lines:
            for flag in ("--fail", "--proto '=https'", "--proto-redir '=https'"):
                self.assertIn(flag, line)
        self.assertIn('"$url"', curl_lines[0])
        self.assertIn('"$segger_url"', curl_lines[1])
        self.assertIn("--data 'accept_license_agreement=accepted'", curl_lines[1])
        self.assertIn(f'segger_url="{SEGGER_ENDPOINT}', install)

    def test_the_install_script_notes_that_the_download_accepts_the_terms(self):
        self.assertIn("accepts SEGGER's terms of use", (JLINK / "install-jlink.sh").read_text())

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


class InstallScriptDownloads(unittest.TestCase):
    """The whole of install-jlink.sh with stand-ins for curl, apt-get and usermod. No network is used."""

    SEGGER_VERSION = "V996a"
    SEGGER_FILE = "JLink_Linux_V996a_x86_64.deb"
    HOSTED_URL = "https://artifacts.example.invalid/jlink/JLink_Linux_V990_x86_64.deb"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = pathlib.Path(self._tmp.name)
        self.folder = base / "packages"
        self.server = base / "server"
        self.bin = base / "bin"
        for path in (self.folder, self.server, self.bin):
            path.mkdir()
        self.log = base / "calls.log"
        self.udevadm = base / "udevadm"
        # apt-get records whether the udevadm stand-in exists while the package installs.
        self.stub("apt-get", f'''echo "apt-get $*" >> "{self.log}"
case "$1" in install) [ -x "{self.udevadm}" ] && echo "udevadm present" >> "{self.log}" ;; esac''')
        self.stub("usermod", f'echo "usermod $*" >> "{self.log}"')
        # A fake curl: copies server/<last path segment of the URL> to --output, logs the URL and any
        # posted form data, and fails with FAKE_CURL_STATUS.
        self.stub("curl", f'''out=; url=; data=
while [ "$#" -gt 0 ]; do
    case "$1" in
    --output) out=$2; shift ;;
    --data) data="$data $2"; shift ;;
    https://*|http://*) url=$1 ;;
    esac
    shift
done
echo "curl $url$data" >> "{self.log}"
if [ "${{FAKE_CURL_STATUS:-0}}" != 0 ]; then
    echo "curl: (22) The requested URL returned error: 503" >&2
    exit "$FAKE_CURL_STATUS"
fi
cp "{self.server}/${{url##*/}}" "$out"''')
        for tool in ("JLinkExe", "JLinkGDBServer", "JLinkGDBServerCLExe"):
            self.stub(tool, "")

    def stub(self, name, body):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\n")
        path.chmod(0o755)

    def serve(self, name, content):
        (self.server / name).write_bytes(content)
        return hashlib.sha256(content).hexdigest()

    def segger(self, content=b"package from the vendor endpoint", digest=None):
        served = self.serve(self.SEGGER_FILE, content)
        return {"CRUX_JLINK_SEGGER_VERSION": self.SEGGER_VERSION,
                "CRUX_JLINK_SEGGER_SHA256": digest if digest is not None else served}

    def run_install(self, **env):
        # /usr/sbin and /sbin for sha256sum on hosts that keep it there.
        full = {"PATH": f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin", "CRUX_JLINK_UDEVADM": str(self.udevadm)}
        full.update(env)
        return subprocess.run(["sh", str(JLINK / "install-jlink.sh"), str(self.folder)],
                              capture_output=True, text=True, env=full)

    def calls(self):
        return self.log.read_text() if self.log.exists() else ""

    def test_downloads_the_pinned_version_from_segger_when_nothing_else_is_given(self):
        result = self.run_install(**self.segger())
        self.assertEqual(0, result.returncode, result.stderr)
        calls = self.calls()
        self.assertIn(f"curl {SEGGER_ENDPOINT}{self.SEGGER_FILE} accept_license_agreement=accepted", calls)
        self.assertIn(f"install -y --no-install-recommends usbutils ./{self.SEGGER_FILE}", calls)
        self.assertIn("udevadm present", calls)
        self.assertIn("usermod -aG plugdev vscode", calls)
        self.assertIn("terms of use", result.stdout + result.stderr)
        self.assertFalse(self.udevadm.exists())

    def test_order_a_placed_package_wins_over_the_url_and_segger(self):
        (self.folder / "JLink_Linux_V810_x86_64.deb").write_bytes(b"placed package")
        self.serve("JLink_Linux_V990_x86_64.deb", b"hosted copy")
        result = self.run_install(CRUX_JLINK_URL=self.HOSTED_URL, **self.segger())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("curl", self.calls())
        self.assertIn("./JLink_Linux_V810_x86_64.deb", self.calls())

    def test_order_the_url_wins_over_segger(self):
        hosted = self.serve("JLink_Linux_V990_x86_64.deb", b"hosted copy")
        result = self.run_install(CRUX_JLINK_URL=self.HOSTED_URL, CRUX_JLINK_DEB_SHA256=hosted, **self.segger())
        self.assertEqual(0, result.returncode, result.stderr)
        calls = self.calls()
        self.assertIn(f"curl {self.HOSTED_URL}", calls)
        self.assertNotIn("segger.com", calls)
        self.assertIn("usbutils ./JLink_Linux_download_x86_64.deb", calls)

    def test_without_a_pin_nothing_is_downloaded(self):
        result = self.run_install()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("warning: no SEGGER J-Link package", result.stderr)
        self.assertEqual("", self.calls())

    def test_a_failed_segger_download_warns_and_builds_without_jlink(self):
        result = self.run_install(FAKE_CURL_STATUS="22", **self.segger())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("warning: the J-Link download from SEGGER failed", result.stderr)
        self.assertIn("built without the J-Link software", result.stderr)
        self.assertIn(".devcontainer/jlink/packages/", result.stderr)
        calls = self.calls()
        self.assertIn("curl ", calls)
        self.assertNotIn("apt-get", calls)
        self.assertNotIn("usermod", calls)
        self.assertFalse(self.udevadm.exists())

    def test_a_segger_download_with_a_wrong_checksum_warns_and_installs_nothing(self):
        result = self.run_install(**self.segger(content=b"changed upstream", digest="0" * 64))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("SHA-256", result.stderr)
        self.assertIn("0" * 64, result.stderr)
        self.assertIn("built without the J-Link software", result.stderr)
        self.assertNotIn("apt-get", self.calls())
        self.assertNotIn("usermod", self.calls())
        self.assertFalse(self.udevadm.exists())

    def test_required_mode_fails_when_the_segger_download_fails(self):
        result = self.run_install(CRUX_JLINK="1", FAKE_CURL_STATUS="22", **self.segger())
        self.assertNotEqual(0, result.returncode)
        self.assertIn("error: the J-Link download from SEGGER failed", result.stderr)
        self.assertNotIn("apt-get", self.calls())

    def test_required_mode_fails_on_a_segger_checksum_mismatch(self):
        result = self.run_install(CRUX_JLINK="1", **self.segger(digest="0" * 64))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("SHA-256", result.stderr)
        self.assertNotIn("apt-get", self.calls())

    def test_an_upper_case_pin_is_accepted(self):
        environment = self.segger()
        environment["CRUX_JLINK_SEGGER_SHA256"] = environment["CRUX_JLINK_SEGGER_SHA256"].upper()
        result = self.run_install(**environment)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(f"./{self.SEGGER_FILE}", self.calls())

    def test_a_malformed_segger_pin_is_not_downloaded(self):
        for environment in ({"CRUX_JLINK_SEGGER_VERSION": "V996a/../x", "CRUX_JLINK_SEGGER_SHA256": "a" * 64},
                            {"CRUX_JLINK_SEGGER_VERSION": "V996a", "CRUX_JLINK_SEGGER_SHA256": "abc"},
                            {"CRUX_JLINK_SEGGER_VERSION": "V996a"}):
            with self.subTest(environment=environment):
                result = self.run_install(**environment)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("warning:", result.stderr)
                self.assertNotIn("curl", self.calls())


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

    def test_a_segger_pin_override_reaches_the_build_by_name_only(self):
        self.run_script("true", CRUX_JLINK_SEGGER_VERSION="V996a", CRUX_JLINK_SEGGER_SHA256="b" * 64)
        build = [c for c in self.calls() if c.startswith("build ")][0]
        self.assertIn("--build-arg CRUX_JLINK_SEGGER_VERSION ", build)
        self.assertIn("--build-arg CRUX_JLINK_SEGGER_SHA256 ", build)
        self.assertNotIn("b" * 64, build)

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
