"""Tests of scripts/check_boundary.py."""

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_boundary  # noqa: E402


class Repo:
    """A throwaway repository layout with files written from a dict."""

    def __init__(self, files):
        self._dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._dir.name)
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def close(self):
        self._dir.cleanup()


def run(files, crux_root=None):
    repo = Repo(files)
    try:
        return check_boundary.check(repo.root, crux_root)
    finally:
        repo.close()


def reasons(violations):
    return [v.include for v in violations]


class AppRules(unittest.TestCase):
    def test_clean_application_passes(self):
        files = {"app/src/main.c": "#include <crux/time.h>\n#include <stdint.h>\n"}
        self.assertEqual([], run(files))

    def test_zephyr_header_fails(self):
        files = {"app/src/main.c": "#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_zephyr_printk_header_fails(self):
        files = {"app/src/main.c": "#include <zephyr/sys/printk.h>\n"}
        self.assertEqual(["zephyr/sys/printk.h"], reasons(run(files)))

    def test_vendor_header_fails(self):
        files = {"app/src/main.c": "#include <fsl_enet.h>\n"}
        self.assertEqual(["fsl_enet.h"], reasons(run(files)))

    def test_crux_port_header_fails(self):
        # The file binding lives in a port header that no <crux/...> header
        # declares. A product reaches it only by a private include path.
        files = {"app/src/main.c": '#include "file_native.h"\n'}
        self.assertEqual(["file_native.h"], reasons(run(files)))

    def test_nested_crux_path_fails(self):
        files = {"app/src/main.c": "#include <crux/ports/zephyr/file_native.h>\n"}
        self.assertEqual(["crux/ports/zephyr/file_native.h"], reasons(run(files)))

    def test_socket_profile_headers_pass_in_the_application(self):
        names = [
            "sys/socket.h", "netinet/in.h", "arpa/inet.h", "poll.h",
            "fcntl.h", "unistd.h", "errno.h", "time.h",
        ]
        text = "".join(f"#include <{n}>\n" for n in names)
        self.assertEqual([], run({"app/src/net.c": text}))

    def test_other_posix_header_fails_in_the_application(self):
        files = {"app/src/main.c": "#include <pthread.h>\n"}
        self.assertEqual(["pthread.h"], reasons(run(files)))

    def test_local_quoted_header_passes(self):
        files = {
            "app/src/main.c": '#include "adapter.h"\n',
            "app/src/adapter.h": "#include <stdint.h>\n",
        }
        self.assertEqual([], run(files))

    def test_local_header_in_a_subdirectory_resolves(self):
        files = {
            "app/src/main.c": '#include "net/client.h"\n',
            "app/src/net/client.h": "",
        }
        self.assertEqual([], run(files))

    def test_commented_include_is_ignored(self):
        text = '/* #include <zephyr/kernel.h> */\n// #include <fsl_enet.h>\n'
        self.assertEqual([], run({"app/src/main.c": text}))

    def test_spaced_include_forms_are_found(self):
        files = {"app/src/main.c": "  #  include   <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_violation_names_file_and_line(self):
        files = {"app/src/main.c": "#include <stdint.h>\n#include <zephyr/kernel.h>\n"}
        (violation,) = run(files)
        self.assertEqual("app/src/main.c", violation.path)
        self.assertEqual(2, violation.line)

    def test_header_files_are_scanned_too(self):
        files = {"app/src/adapter.h": "#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))


class WorkloadRules(unittest.TestCase):
    def test_iso_c_only_passes(self):
        files = {"workload/cycle.c": "#include <stdint.h>\n#include <string.h>\n"}
        self.assertEqual([], run(files))

    def test_crux_header_fails_in_the_workload(self):
        files = {"workload/cycle.c": "#include <crux/time.h>\n"}
        self.assertEqual(["crux/time.h"], reasons(run(files)))

    def test_socket_header_fails_in_the_workload(self):
        files = {"workload/cycle.c": "#include <sys/socket.h>\n"}
        self.assertEqual(["sys/socket.h"], reasons(run(files)))

    def test_zephyr_header_fails_in_the_workload(self):
        files = {"workload/cycle.c": "#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_local_header_passes_in_the_workload(self):
        files = {
            "workload/cycle.c": '#include "workload/cycle.h"\n',
            "workload/include/workload/cycle.h": "",
        }
        self.assertEqual([], run(files))


class CruxPublicHeaders(unittest.TestCase):
    def crux_root(self, names):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = pathlib.Path(directory.name)
        for name in names:
            path = root / "components" / "x" / "include" / "crux" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        return root

    def test_known_public_header_passes(self):
        root = self.crux_root(["time.h"])
        files = {"app/src/main.c": "#include <crux/time.h>\n"}
        self.assertEqual([], run(files, crux_root=root))

    def test_unknown_crux_header_fails_when_the_public_set_is_known(self):
        root = self.crux_root(["time.h"])
        files = {"app/src/main.c": "#include <crux/secret.h>\n"}
        self.assertEqual(["crux/secret.h"], reasons(run(files, crux_root=root)))


class Scope(unittest.TestCase):
    def test_missing_directories_are_skipped(self):
        self.assertEqual([], run({"README.md": ""}))

    def test_files_outside_the_scanned_directories_are_not_checked(self):
        files = {"tests/host/test.c": "#include <zephyr/kernel.h>\n"}
        self.assertEqual([], run(files))


class CommandLine(unittest.TestCase):
    def invoke(self, files, *extra):
        repo = Repo(files)
        self.addCleanup(repo.close)
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", str(repo.root), *extra],
            capture_output=True,
            text=True,
        )

    def test_exit_zero_when_clean(self):
        result = self.invoke({"app/src/main.c": "#include <crux/time.h>\n"})
        self.assertEqual(0, result.returncode, result.stderr)

    def test_exit_one_and_report_when_violated(self):
        result = self.invoke({"app/src/main.c": "#include <zephyr/kernel.h>\n"})
        self.assertEqual(1, result.returncode)
        self.assertIn("app/src/main.c:1", result.stdout)
        self.assertIn("zephyr/kernel.h", result.stdout)

    def test_exit_two_for_a_missing_repository(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", "/nonexistent-dir"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, result.returncode)


class ThisRepository(unittest.TestCase):
    def test_repository_keeps_the_boundary(self):
        self.assertEqual([], check_boundary.check(ROOT, None))


if __name__ == "__main__":
    unittest.main()
