# SPDX-License-Identifier: Apache-2.0
"""Checks of scripts/crux-pin-hook, the hook that the Crux pin tool runs after it has rewritten the
crux-pilot revision in west.yml. The hook updates the other places that quote the pin (CONTRIBUTING.md,
"The pin and the manifest", steps 1 and 2). Every test works on a temporary copy."""

import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "crux-pin-hook"

OLD = "2c017f685e0215e0e269d4bc77272889d06a07d8"
NEW = "0123456789abcdef0123456789abcdef01234567"
NOTE_PIN = "8e3737d25d048b14a00c01da00494f58a62958c6"


def west_yml(revision):
    return (
        "manifest:\n"
        "  projects:\n"
        "    - name: crux-pilot\n"
        "      remote: crux\n"
        "      # Commit of crux-pilot origin/main.\n"
        f"      revision: {revision}\n"
        "    - name: picolibc\n"
        "      revision: 01254932e8e81085817ed61fd858648584ffe37c\n"
    )


def fixture(pin):
    """The lines of each file that quote the pin, as the real files write them."""
    short = pin[:8]
    return {
        "tests/tooling/test_manifest.py":
            f'        revision = load_manifest()["projects"][0]["revision"]\n'
            f'        self.assertEqual(revision, "{pin}")\n',
        "docs/dependencies.md":
            f'    CP["crux-pilot<br/>pinned commit {short}"]\n'
            f"| `crux-pilot` | `{pin}` (a commit, no Crux tag exists) | The platform itself |\n"
            "| `zephyr` | `dccb09599635bdff17633fa7e9dab014b91dce90` (v4.4.2) | Pinned via the Crux contract |\n",
        "RELEASE.md":
            f'"Release": [`docs/product-composition.md` at the pinned revision `{short}`]'
            f"(https://github.com/wonny-labs/crux-pilot/blob/{pin}/docs/product-composition.md).\n",
        "tests/tooling/test_docs.py":
            '        self.assertIn("approval", body)\n'
            f'        self.assertIn("{short}", body)\n',
        "docs/adding-a-step.md":
            f"- In the platform repository, read at the pinned commit `{pin}`:\n"
            f"  [`docs/choosing-an-api.md`](https://github.com/wonny-labs/crux-pilot/blob/{pin}/docs/choosing-an-api.md)\n"
            f"  [`docs/composition-interfaces.md`](https://github.com/wonny-labs/crux-pilot/blob/{pin}/docs/composition-interfaces.md)\n",
        "tests/tooling/test_docs_navigation.py":
            f'                       "docs/choosing-an-api.md", "{pin}"):\n',
        "tests/tooling/test_s4.py":
            f'        self.assertIn("revision: {pin}", manifest)\n',
        "tests/tooling/test_s5.py":
            f'        self.assertIn("revision: {pin}", manifest)\n',
        "tests/tooling/test_s6.py":
            f'    NOTE_PIN = "{NOTE_PIN}"\n'
            f'    PIN = "{pin}"\n',
        "CHANGELOG.md":
            f"- The west manifest imports `crux-pilot` at a pinned commit (`{short}`, which publishes the File\n"
            "- The `crux-pilot` pin moved from `5fa99839` to `2c017f68`, the squash commit.\n",
    }


FINDINGS = f"The current pin is `{OLD}` (see `west.yml`).\n"


class Workspace:
    """A temporary repository root with the fixture files at OLD and west.yml at `revision`."""

    def __init__(self, revision=NEW, pin=OLD, changelog=True):
        self.directory = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.directory.name)
        for name, body in fixture(pin).items():
            if name == "CHANGELOG.md" and not changelog:
                continue
            self.write(name, body)
        self.write("west.yml", west_yml(revision))
        self.write("docs/findings/README.md", FINDINGS)

    def write(self, name, body):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    def read(self, name):
        return (self.root / name).read_text()

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in sorted(self.root.rglob("*")) if p.is_file()}

    def run(self, old=OLD, new=NEW, env=None):
        environment = {k: v for k, v in os.environ.items() if not k.startswith("CRUX_PIN_")}
        if old is not None:
            environment["CRUX_PIN_OLD"] = old
        if new is not None:
            environment["CRUX_PIN_NEW"] = new
        environment.update(env or {})
        return subprocess.run([sys.executable, str(HOOK)], cwd=self.root, env=environment,
                              capture_output=True, text=True)

    def close(self):
        self.directory.cleanup()


class HookFile(unittest.TestCase):
    def test_it_is_an_executable_python_script_with_the_licence_line(self):
        self.assertTrue(HOOK.is_file(), "scripts/crux-pin-hook does not exist")
        self.assertTrue(HOOK.stat().st_mode & stat.S_IXUSR, "the hook is not executable")
        lines = HOOK.read_text().splitlines()
        self.assertEqual("#!/usr/bin/env python3", lines[0])
        self.assertEqual("# SPDX-License-Identifier: Apache-2.0", lines[1])

    def test_it_uses_the_standard_library_only_and_nothing_under_github(self):
        text = HOOK.read_text()
        for word in ("import yaml", "from yaml", "import requests", ".github"):
            self.assertNotIn(word, text)

    def test_it_runs_directly_through_its_shebang(self):
        work = Workspace()
        self.addCleanup(work.close)
        environment = dict(os.environ, CRUX_PIN_OLD=OLD, CRUX_PIN_NEW=NEW)
        result = subprocess.run([str(HOOK)], cwd=work.root, env=environment,
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


class HookMovesThePin(unittest.TestCase):
    def setUp(self):
        self.work = Workspace()
        self.addCleanup(self.work.close)

    def test_every_quote_moves_to_the_new_commit(self):
        result = self.work.run()
        self.assertEqual(0, result.returncode, result.stderr)
        expected = fixture(NEW)
        for name, body in expected.items():
            if name == "CHANGELOG.md":
                continue
            self.assertEqual(body, self.work.read(name), name)

    def test_the_changelog_moves_only_the_current_pin_and_keeps_the_history(self):
        self.assertEqual(0, self.work.run().returncode)
        text = self.work.read("CHANGELOG.md")
        self.assertIn(f"at a pinned commit (`{NEW[:8]}`, which", text)
        self.assertIn("moved from `5fa99839` to `2c017f68`", text)

    def test_another_commit_in_the_same_file_is_kept(self):
        self.assertEqual(0, self.work.run().returncode)
        text = self.work.read("tests/tooling/test_s6.py")
        self.assertIn(f'NOTE_PIN = "{NOTE_PIN}"', text)
        self.assertIn(f'    PIN = "{NEW}"', text)
        self.assertIn("dccb09599635bdff17633fa7e9dab014b91dce90", self.work.read("docs/dependencies.md"))

    def test_findings_are_untouched(self):
        self.assertEqual(0, self.work.run().returncode)
        self.assertEqual(FINDINGS, self.work.read("docs/findings/README.md"))

    def test_west_yml_is_not_written_by_the_hook(self):
        before = self.work.read("west.yml")
        self.assertEqual(0, self.work.run().returncode)
        self.assertEqual(before, self.work.read("west.yml"))

    def test_it_names_the_files_it_changed(self):
        result = self.work.run()
        for name in ("RELEASE.md", "docs/dependencies.md", "tests/tooling/test_manifest.py"):
            self.assertIn(name, result.stdout)

    def test_a_rerun_is_a_no_op_with_exit_status_3(self):
        self.assertEqual(0, self.work.run().returncode)
        before = self.work.snapshot()
        again = self.work.run()
        self.assertEqual(3, again.returncode, again.stderr)
        self.assertEqual(before, self.work.snapshot())

    def test_the_file_mode_is_kept(self):
        path = self.work.root / "RELEASE.md"
        path.chmod(0o640)
        self.assertEqual(0, self.work.run().returncode)
        self.assertEqual(0o640, stat.S_IMODE(path.stat().st_mode))

    def test_line_endings_are_kept(self):
        path = self.work.root / "RELEASE.md"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(0, self.work.run().returncode)
        self.assertIn(f"`{NEW[:8]}`".encode() + b"](", path.read_bytes())
        self.assertTrue(path.read_bytes().endswith(b"\r\n"))


class HookWithoutChangelog(unittest.TestCase):
    def test_a_missing_changelog_is_skipped_silently(self):
        work = Workspace(changelog=False)
        self.addCleanup(work.close)
        result = work.run()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertFalse((work.root / "CHANGELOG.md").exists())


class HookRefuses(unittest.TestCase):
    def setUp(self):
        self.work = Workspace()
        self.addCleanup(self.work.close)

    def assert_nothing_written(self, result, status, fragment):
        before = self.work.snapshot()
        self.assertEqual(status, result.returncode, result.stdout + result.stderr)
        self.assertIn(fragment, result.stderr)
        self.assertEqual(before, self.work.snapshot())

    def test_a_missing_quote_fails_and_writes_nothing(self):
        self.work.write("tests/tooling/test_s5.py", "        pass\n")
        before = self.work.snapshot()
        result = self.work.run()
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("tests/tooling/test_s5.py", result.stderr)
        self.assertIn(f"revision: {OLD}", result.stderr)
        self.assertEqual(before, self.work.snapshot())

    def test_a_missing_required_file_fails_and_writes_nothing(self):
        (self.work.root / "RELEASE.md").unlink()
        before = self.work.snapshot()
        result = self.work.run()
        self.assertEqual(1, result.returncode)
        self.assertIn("RELEASE.md", result.stderr)
        self.assertEqual(before, self.work.snapshot())

    def test_a_west_yml_that_does_not_pin_the_new_commit_fails(self):
        self.work.write("west.yml", west_yml(OLD))
        before = self.work.snapshot()
        result = self.work.run()
        self.assertEqual(1, result.returncode)
        self.assertIn("west.yml", result.stderr)
        self.assertEqual(before, self.work.snapshot())

    def test_a_bad_sha_is_rejected(self):
        for old, new in ((OLD[:8], NEW), (OLD, NEW.upper()), (OLD, NEW + "0"), (OLD, "main"),
                         ("", NEW), (OLD, f"{NEW[:-1]}g"), (OLD, f"{NEW}\n")):
            before = self.work.snapshot()
            result = self.work.run(old=old, new=new)
            self.assertEqual(2, result.returncode, (old, new))
            self.assertIn("CRUX_PIN_", result.stderr)
            self.assertEqual(before, self.work.snapshot())

    def test_a_missing_variable_is_rejected(self):
        for old, new in ((None, NEW), (OLD, None)):
            result = self.work.run(old=old, new=new)
            self.assertEqual(2, result.returncode)
            self.assertIn("CRUX_PIN_", result.stderr)


class HookOnTheRealFiles(unittest.TestCase):
    """Runs the hook on a copy of this repository and then the tests that pin the commit."""

    TESTS = (
        "test_manifest.ManifestIsOptionA",
        "test_docs.Promises",
        "test_docs.Dependencies",
        "test_docs_navigation.AddingAStep",
        "test_s4.S4Findings.test_the_manifest_pins_the_approved_commit",
        "test_s5.S5Findings.test_the_manifest_pins_the_approved_commit",
        "test_s6.S6StepNote.test_west_yml_changed_in_comments_only",
    )

    @staticmethod
    def current_pin(text):
        lines = text.splitlines()
        start = lines.index("    - name: crux-pilot")
        for line in lines[start + 1:]:
            if line.strip().startswith("revision:"):
                return line.split(":", 1)[1].strip()
        raise AssertionError("west.yml has no crux-pilot revision")

    def test_the_real_files_move_and_the_pin_tests_pass_at_a_fake_new_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            copy = pathlib.Path(directory) / "crux-controller"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "build", "__pycache__"))
            west = copy / "west.yml"
            old = self.current_pin(west.read_text())
            notes = {p: p.read_bytes() for p in (copy / "docs" / "findings").rglob("*") if p.is_file()}

            def pin_tests():
                return subprocess.run([sys.executable, "-m", "unittest", *self.TESTS],
                                      cwd=copy / "tests" / "tooling", capture_output=True, text=True)

            # The Crux tool rewrites the revision line; the hook does the rest.
            west.write_text(west.read_text().replace(f"revision: {old}", f"revision: {NEW}"))
            # Negative control: without the hook the same tests fail, so they do check the pin.
            self.assertNotEqual(0, pin_tests().returncode)
            environment = dict(os.environ, CRUX_PIN_OLD=old, CRUX_PIN_NEW=NEW)
            result = subprocess.run([sys.executable, str(copy / "scripts" / "crux-pin-hook")],
                                    cwd=copy, env=environment, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            for path, body in notes.items():
                self.assertEqual(body, path.read_bytes(), path)
            tests = pin_tests()
            self.assertEqual(0, tests.returncode, tests.stdout + tests.stderr)
            again = subprocess.run([sys.executable, str(copy / "scripts" / "crux-pin-hook")],
                                   cwd=copy, env=environment, capture_output=True, text=True)
            self.assertEqual(3, again.returncode, again.stdout + again.stderr)


if __name__ == "__main__":
    unittest.main()
