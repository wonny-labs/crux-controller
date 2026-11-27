# SPDX-License-Identifier: Apache-2.0
"""Tests of scripts/pin_framework.py, which pins the framework in a copy of the application template.

The rules held here:

- the revision of the project crux-controller becomes the full commit SHA that the given clone has
  checked out, and the first pin also records it as the template revision of the copy;
- a later pin moves the revision and keeps the recorded template revision;
- the rest of the file, its comments included, stays as it was;
- a manifest of another shape, or a folder that is not a Git clone, is refused and left alone.
"""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pin_framework.py"
TEMPLATE_MANIFEST = ROOT / "template" / "west.yml"

MANIFEST = """\
manifest:
  version: "1.2"
  remotes:
    - name: wonny-labs
      url-base: https://github.com/wonny-labs
  projects:
    # A comment that stays.
    - name: crux-controller
      remote: wonny-labs
      revision: main
      import: true
  self:
    path: product
    userdata:
      template-revision: none
"""

GIT_ENV = {"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@localhost",
           "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@localhost",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(*arguments, cwd):
    return subprocess.run(["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV}).stdout.strip()


class Workspace:
    """A temporary folder with a Git clone that has one or more commits, and a manifest file."""

    def __init__(self, text=MANIFEST):
        self._dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._dir.name)
        self.clone = self.root / "crux-controller"
        self.clone.mkdir()
        git("init", "--quiet", cwd=self.clone)
        self.commit()
        self.manifest = self.root / "west.yml"
        self.manifest.write_text(text)

    def commit(self):
        git("commit", "--quiet", "--allow-empty", "-m", "a commit", cwd=self.clone)
        return git("rev-parse", "HEAD", cwd=self.clone)

    def head(self):
        return git("rev-parse", "HEAD", cwd=self.clone)

    def pin(self, framework=None):
        return subprocess.run([sys.executable, str(SCRIPT), "--framework", str(framework or self.clone),
                               str(self.manifest)], capture_output=True, text=True)

    def close(self):
        self._dir.cleanup()


class Pin(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)

    def test_the_first_pin_sets_the_revision_and_records_the_template_revision(self):
        result = self.workspace.pin()
        self.assertEqual(0, result.returncode, result.stderr)
        sha = self.workspace.head()
        manifest = yaml.safe_load(self.workspace.manifest.read_text())["manifest"]
        self.assertEqual(sha, manifest["projects"][0]["revision"])
        self.assertIs(True, manifest["projects"][0]["import"])
        self.assertEqual(sha, manifest["self"]["userdata"]["template-revision"])
        self.assertIn(sha, result.stdout)

    def test_the_rest_of_the_file_stays_as_it_was(self):
        self.workspace.pin()
        sha = self.workspace.head()
        expected = MANIFEST.replace("revision: main", f"revision: {sha}").replace(
            "template-revision: none", f"template-revision: {sha}")
        self.assertEqual(expected, self.workspace.manifest.read_text())

    def test_a_later_pin_moves_the_revision_and_keeps_the_template_revision(self):
        self.workspace.pin()
        first = self.workspace.head()
        second = self.workspace.commit()
        result = self.workspace.pin()
        self.assertEqual(0, result.returncode, result.stderr)
        manifest = yaml.safe_load(self.workspace.manifest.read_text())["manifest"]
        self.assertEqual(second, manifest["projects"][0]["revision"])
        self.assertEqual(first, manifest["self"]["userdata"]["template-revision"])


class Refused(unittest.TestCase):
    def refused(self, text, status=1, framework=None):
        workspace = Workspace(text)
        try:
            result = workspace.pin(framework)
            self.assertEqual(status, result.returncode, result.stdout + result.stderr)
            self.assertEqual(text, workspace.manifest.read_text())
            return result.stderr
        finally:
            workspace.close()

    def test_a_manifest_without_the_project_is_refused(self):
        self.assertIn("crux-controller", self.refused(MANIFEST.replace("name: crux-controller", "name: other")))

    def test_a_project_that_does_not_import_the_manifest_is_refused(self):
        self.assertIn("import", self.refused(MANIFEST.replace("      import: true\n", "")))

    def test_a_project_without_one_revision_line_is_refused(self):
        self.refused(MANIFEST.replace("      revision: main\n", ""))
        self.refused(MANIFEST.replace("      revision: main\n", "      revision: main\n      revision: v1\n"))

    def test_a_manifest_without_the_template_revision_is_refused(self):
        self.assertIn("template-revision", self.refused(MANIFEST.replace("      template-revision: none\n", "")))

    def test_a_folder_that_is_not_a_clone_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            self.refused(MANIFEST, status=2, framework=pathlib.Path(directory))

    def test_a_missing_manifest_is_a_usage_error(self):
        workspace = Workspace()
        try:
            workspace.manifest.unlink()
            self.assertEqual(2, workspace.pin().returncode)
        finally:
            workspace.close()


class TemplateManifest(unittest.TestCase):
    def test_the_template_manifest_pins_as_the_joining_steps_say(self):
        workspace = Workspace(TEMPLATE_MANIFEST.read_text())
        try:
            result = workspace.pin()
            self.assertEqual(0, result.returncode, result.stderr)
            manifest = yaml.safe_load(workspace.manifest.read_text())["manifest"]
            sha = workspace.head()
            project = next(p for p in manifest["projects"] if p["name"] == "crux-controller")
            self.assertEqual(sha, project["revision"])
            self.assertEqual(sha, manifest["self"]["userdata"]["template-revision"])
        finally:
            workspace.close()


if __name__ == "__main__":
    unittest.main()
