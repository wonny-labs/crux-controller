# SPDX-License-Identifier: Apache-2.0
"""Criterion 49: follow the joining steps of template/README.md with local repositories.

The test copies this repository's template folder and pin script into a local stand-in of the
framework repository, makes a clone of it as a product team has one, and runs the commands of the
README section "Start a product" as written, in a new folder. Git's url.<base>.insteadOf (in a Git
configuration of the test only) sends the remote of the copy's west.yml to the local repositories,
so the copy's files stay as the steps leave them and nothing is fetched from the network. The
stand-in framework's manifest names a stand-in Crux, so the import of the copy resolves too.

It then checks that west update resolved the framework at the full commit that the steps pinned,
that the copy records that commit as its template revision, and that no file of the copy holds an
absolute path or a relative path that leaves the copy (scripts/check_template.py).

The test needs west and Git. Without west it skips with that reason, unless
CRUX_TEMPLATE_REQUIRE_WEST=1 is set, as in the nightly check template-joining-steps of
scripts/ci/checks.toml: there a missing west fails the test.
"""

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_template  # noqa: E402

REMOTE_BASE = "https://github.com/wonny-labs/"
REQUIRE = os.environ.get("CRUX_TEMPLATE_REQUIRE_WEST") == "1"
WEST = shutil.which("west")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def joining_steps():
    """The commands of the README section "Start a product", as written."""
    text = (ROOT / "template" / "README.md").read_text()
    section = text.split("\n## Start a product\n", 1)[1].split("\n## ", 1)[0]
    return re.search(r"```sh\n(.*?)\n```", section, re.DOTALL).group(1).splitlines()


class JoiningSteps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if WEST is None:
            if REQUIRE:
                raise AssertionError("west is not installed, and CRUX_TEMPLATE_REQUIRE_WEST=1 requires it")
            raise unittest.SkipTest("west is not installed; the nightly check template-joining-steps runs this test")
        cls._dir = tempfile.TemporaryDirectory()
        cls.root = pathlib.Path(cls._dir.name)
        cls.env = cls.environment()
        cls.crux_sha = cls.make_remote("crux", {"README": "a stand-in for Crux\n"})
        cls.framework_sha = cls.make_framework()
        cls.work = cls.root / "work"
        cls.work.mkdir()
        cls.git("clone", "--quiet", str(cls.root / "remotes" / "crux-controller"), str(cls.work / "crux-controller"))
        script = cls.root / "steps.sh"
        script.write_text("set -euo pipefail\n" + "\n".join(joining_steps()) + "\n")
        cls.result = subprocess.run(["bash", str(script)], cwd=cls.work, env=cls.env, capture_output=True, text=True)
        cls.workspace = cls.work / "product-workspace"
        cls.copy = cls.workspace / "product"

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    @classmethod
    def environment(cls):
        home = cls.root / "home"
        shims = cls.root / "bin"
        home.mkdir()
        shims.mkdir()
        # The steps call python3; it is this interpreter, which has PyYAML. A script, not a link: a
        # link to a virtual environment's interpreter would lose the environment.
        shim = shims / "python3"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        shim.chmod(0o755)
        config = cls.root / "gitconfig"
        config.write_text(f'[url "file://{cls.root / "remotes"}/"]\n\tinsteadOf = {REMOTE_BASE}\n'
                          "[user]\n\tname = template test\n\temail = template-test@localhost\n"
                          "[init]\n\tdefaultBranch = main\n[protocol \"file\"]\n\tallow = always\n")
        env = {key: value for key, value in os.environ.items() if not key.startswith(("GIT_", "ZEPHYR_", "WEST_"))}
        env.update({"HOME": str(home), "GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1",
                    "PATH": f"{shims}{os.pathsep}{env.get('PATH', '')}"})
        return env

    @classmethod
    def git(cls, *arguments, cwd=None):
        return subprocess.run(["git", *arguments], cwd=cwd, env=cls.env, check=True, capture_output=True,
                              text=True).stdout.strip()

    @classmethod
    def make_remote(cls, name, files):
        """A local repository with one commit of the files; return its commit."""
        path = cls.root / "remotes" / name
        path.mkdir(parents=True)
        for relative, text in files.items():
            target = path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        cls.git("init", "--quiet", cwd=path)
        cls.git("add", "-A", cwd=path)
        cls.git("commit", "--quiet", "-m", f"{name} for the joining test", cwd=path)
        return cls.git("rev-parse", "HEAD", cwd=path)

    @classmethod
    def make_framework(cls):
        """The stand-in framework: this repository's template and pin script, and a manifest that
        names the stand-in Crux at its commit, as the framework's west.yml names Crux."""
        manifest = {"manifest": {"version": "1.2",
                                 "remotes": [{"name": "crux", "url-base": REMOTE_BASE.rstrip("/")}],
                                 "projects": [{"name": "crux", "remote": "crux", "revision": cls.crux_sha}],
                                 "self": {"path": "crux-controller"}}}
        files = {"west.yml": yaml.safe_dump(manifest, sort_keys=False),
                 "scripts/pin_framework.py": (ROOT / "scripts" / "pin_framework.py").read_text()}
        for path in sorted((ROOT / "template").rglob("*")):
            if path.is_file():
                files[f"template/{path.relative_to(ROOT / 'template').as_posix()}"] = path.read_text()
        return cls.make_remote("crux-controller", files)

    def west(self, *arguments):
        return subprocess.run([WEST, *arguments], cwd=self.workspace, env=self.env, check=True, capture_output=True,
                              text=True).stdout.strip()

    def test_the_steps_run_without_an_error(self):
        self.assertEqual(0, self.result.returncode, self.result.stdout + self.result.stderr)

    def test_the_copy_pins_the_framework_at_the_full_commit_of_the_clone(self):
        manifest = yaml.safe_load((self.copy / "west.yml").read_text())["manifest"]
        project = next(p for p in manifest["projects"] if p["name"] == "crux-controller")
        self.assertRegex(project["revision"], FULL_SHA)
        self.assertEqual(self.framework_sha, project["revision"])
        self.assertEqual(self.framework_sha, manifest["self"]["userdata"]["template-revision"])

    def test_west_update_resolves_the_framework_at_that_commit(self):
        self.assertEqual(self.framework_sha, self.git("rev-parse", "HEAD", cwd=self.workspace / "crux-controller"))
        self.assertEqual(self.framework_sha, self.west("list", "crux-controller", "-f", "{sha}"))

    def test_the_import_brings_crux_at_the_commit_of_the_framework(self):
        self.assertEqual(self.crux_sha, self.west("list", "crux", "-f", "{sha}"))
        self.assertTrue((self.workspace / "crux" / "README").is_file())

    def test_the_copy_is_a_repository_of_its_own_with_one_commit(self):
        self.assertEqual("1", self.git("rev-list", "--count", "HEAD", cwd=self.copy))
        self.assertEqual("", self.git("status", "--porcelain", cwd=self.copy))

    def test_no_file_of_the_copy_holds_an_absolute_path_or_leaves_the_copy(self):
        self.assertEqual([], check_template.path_problems(self.copy))
        self.assertEqual([], check_template.build_file_problems(self.copy))


if __name__ == "__main__":
    unittest.main()
