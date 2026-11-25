# SPDX-License-Identifier: Apache-2.0
"""Checks of scripts/check_include_domains.py, the local run of the Crux product include check.

The Boundary check job of ci.yml downloads check_domain_includes.py and the style kit wrapper
check-includes.sh from a Crux commit and checks their SHA-256 before it runs them. A checkout
without the workflows or without access to that host has no such step. The script takes both files
from a local Crux checkout instead, checks the same hashes and runs them the way the workflow does.

Most tests build a fake Crux tree and a fake product tree in a temporary directory and run the
script as a separate process. They use no network.
"""

import ast
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_include_domains.py"
PINS = ROOT / "scripts" / "include-check-pins.json"
CI = ROOT / ".github" / "workflows" / "ci.yml"
CHECKER = "templates/product/check_domain_includes.py"
WRAPPER = "templates/product/style/check-includes.sh"

# A stand-in for check_domain_includes.py: it appends its arguments and working directory to
# include-check.log in the working directory, and reports a violation when a file VIOLATION exists.
FAKE_CHECKER = """\
import json, os, pathlib, sys
with open("include-check.log", "a") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\\n")
if pathlib.Path("VIOLATION").exists():
    print("app/src/x.c:1: forbidden include")
    sys.exit(1)
"""

# A stand-in for style/check-includes.sh with the layout of the kit: the checker sits beside the
# directory of the wrapper. It runs the checker on the working directory.
FAKE_WRAPPER = """\
#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
echo wrapper >> include-check.log
exec "${PYTHON:-python3}" "$here/../check_domain_includes.py" --product "$(pwd -P)" "$@"
"""

CI_SNIPPET = """\
jobs:
  boundary:
    steps:
      - name: Run the product include check
        env:
          CHECK_COMMIT: {commit}
          CHECK_SHA256: {checker}
      - name: Run the style kit include check script
        env:
          KIT_COMMIT: {kit_commit}
          CHECKER_SHA256: {checker2}
          WRAPPER_SHA256: {wrapper}
"""


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def load_script():
    spec = importlib.util.spec_from_file_location("check_include_domains", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ci_pins():
    """The pins of the two include check steps of ci.yml, read with a YAML parser."""
    steps = yaml.safe_load(CI.read_text())["jobs"]["boundary"]["steps"]
    env = {}
    for step in steps:
        env.update({k: str(v) for k, v in step.get("env", {}).items()})
    return env


class Workspace:
    """A temporary west workspace: the product repository and a Crux checkout side by side."""

    def __init__(self, test, crux_name="crux", checker=FAKE_CHECKER, wrapper=FAKE_WRAPPER):
        directory = tempfile.TemporaryDirectory()
        test.addCleanup(directory.cleanup)
        self.base = pathlib.Path(directory.name)
        self.repo = self.base / "crux-controller"
        (self.repo / "scripts").mkdir(parents=True)
        self.crux = self.base / crux_name
        self.write(CHECKER, checker)
        self.write(WRAPPER, wrapper)
        self.pin(checker=sha256(checker), wrapper=sha256(wrapper))

    def write(self, relative, text):
        path = self.crux / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def pin(self, checker, wrapper, commit="c" * 40):
        data = {"commit": commit, "files": {CHECKER: checker, WRAPPER: wrapper}}
        (self.repo / "scripts" / "include-check-pins.json").write_text(json.dumps(data))

    def run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *args],
            capture_output=True, text=True,
        )

    def log(self):
        path = self.repo / "include-check.log"
        return path.read_text().splitlines() if path.exists() else []


class MatchingFiles(unittest.TestCase):
    def test_matching_hashes_run_the_checker_then_the_wrapper_and_pass(self):
        ws = Workspace(self)
        result = ws.run("--crux-root", str(ws.crux))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        log = ws.log()
        self.assertEqual(3, len(log), log)
        first = json.loads(log[0])
        self.assertEqual(["--product", "."], first["argv"])
        self.assertEqual(ws.repo.resolve(), pathlib.Path(first["cwd"]).resolve())
        self.assertEqual("wrapper", log[1])
        second = json.loads(log[2])
        self.assertEqual("--product", second["argv"][0])
        self.assertEqual(ws.repo.resolve(), pathlib.Path(second["argv"][1]).resolve())

    def test_a_violation_of_the_checker_fails_the_run(self):
        ws = Workspace(self)
        (ws.repo / "VIOLATION").write_text("")
        result = ws.run("--crux-root", str(ws.crux))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("forbidden include", result.stdout + result.stderr)
        self.assertNotIn("wrapper", ws.log(), "the wrapper ran after a failed check")


class WrongFiles(unittest.TestCase):
    def test_a_checker_with_another_hash_fails_before_anything_runs(self):
        ws = Workspace(self)
        ws.write(CHECKER, FAKE_CHECKER + "# changed\n")
        result = ws.run("--crux-root", str(ws.crux))
        self.assertEqual(2, result.returncode)
        self.assertIn("SHA-256", result.stderr)
        self.assertIn("check_domain_includes.py", result.stderr)
        self.assertEqual([], ws.log())

    def test_a_wrapper_with_another_hash_fails_before_anything_runs(self):
        ws = Workspace(self)
        ws.write(WRAPPER, FAKE_WRAPPER + "# changed\n")
        result = ws.run("--crux-root", str(ws.crux))
        self.assertEqual(2, result.returncode)
        self.assertIn("check-includes.sh", result.stderr)
        self.assertEqual([], ws.log())

    def test_a_missing_checker_fails_with_its_path(self):
        ws = Workspace(self)
        (ws.crux / CHECKER).unlink()
        result = ws.run("--crux-root", str(ws.crux))
        self.assertEqual(2, result.returncode)
        self.assertIn("not found", result.stderr)
        self.assertIn(CHECKER, result.stderr)

    def test_a_crux_root_that_does_not_exist_fails(self):
        ws = Workspace(self)
        result = ws.run("--crux-root", str(ws.base / "nowhere"))
        self.assertEqual(2, result.returncode)
        self.assertIn("nowhere", result.stderr)


class DefaultCruxRoot(unittest.TestCase):
    def test_a_checkout_named_crux_beside_the_repository_is_found(self):
        ws = Workspace(self, crux_name="crux")
        result = ws.run()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(str(ws.crux.resolve()), result.stdout)

    def test_a_checkout_named_for_the_west_project_is_found(self):
        ws = Workspace(self, crux_name="crux-pilot")
        result = ws.run()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(str(ws.crux.resolve()), result.stdout)

    def test_crux_is_preferred_when_both_exist(self):
        ws = Workspace(self, crux_name="crux")
        (ws.base / "crux-pilot").mkdir()
        result = ws.run()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(str(ws.crux.resolve()), result.stdout)

    def test_no_checkout_beside_the_repository_fails_and_names_both_folders(self):
        ws = Workspace(self, crux_name="elsewhere")
        result = ws.run()
        self.assertEqual(2, result.returncode)
        self.assertIn("crux", result.stderr)
        self.assertIn("crux-pilot", result.stderr)
        self.assertIn("--crux-root", result.stderr)


class PinSource(unittest.TestCase):
    def write_ci(self, ws, **values):
        (ws.repo / ".github" / "workflows").mkdir(parents=True)
        (ws.repo / ".github" / "workflows" / "ci.yml").write_text(CI_SNIPPET.format(**values))

    def test_the_workflow_pins_win_over_the_data_file_when_the_workflow_exists(self):
        ws = Workspace(self)
        good_checker, good_wrapper = sha256(FAKE_CHECKER), sha256(FAKE_WRAPPER)
        ws.pin(checker="0" * 64, wrapper="0" * 64)
        self.write_ci(ws, commit="a" * 40, kit_commit="a" * 40, checker=good_checker,
                      checker2=good_checker, wrapper=good_wrapper)
        result = ws.run("--crux-root", str(ws.crux))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("ci.yml", result.stdout)

    def test_a_wrong_hash_in_the_workflow_fails_even_with_a_good_data_file(self):
        ws = Workspace(self)
        self.write_ci(ws, commit="a" * 40, kit_commit="a" * 40, checker="0" * 64,
                      checker2="0" * 64, wrapper=sha256(FAKE_WRAPPER))
        result = ws.run("--crux-root", str(ws.crux))
        self.assertEqual(2, result.returncode)

    def test_two_different_checker_hashes_in_the_workflow_fail(self):
        ws = Workspace(self)
        self.write_ci(ws, commit="a" * 40, kit_commit="a" * 40, checker=sha256(FAKE_CHECKER),
                      checker2="1" * 64, wrapper=sha256(FAKE_WRAPPER))
        result = ws.run("--crux-root", str(ws.crux))
        self.assertEqual(2, result.returncode)
        self.assertIn("CHECKER_SHA256", result.stderr)

    def test_without_the_workflow_the_data_file_is_used(self):
        ws = Workspace(self)
        result = ws.run("--crux-root", str(ws.crux))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("include-check-pins.json", result.stdout)

    def test_without_the_workflow_and_the_data_file_the_run_fails(self):
        ws = Workspace(self)
        (ws.repo / "scripts" / "include-check-pins.json").unlink()
        result = ws.run("--crux-root", str(ws.crux))
        self.assertEqual(2, result.returncode)
        self.assertIn("include-check-pins.json", result.stderr)


@unittest.skipUnless(CI.is_file(), "no .github/workflows/ci.yml in this checkout")
class DataFileFollowsTheWorkflow(unittest.TestCase):
    """While ci.yml exists it is the source; the data file is its copy for checkouts without it."""

    def test_the_data_file_holds_the_hashes_and_the_commit_of_ci_yml(self):
        env = ci_pins()
        data = json.loads(PINS.read_text())
        self.assertEqual(env["CHECK_SHA256"], env["CHECKER_SHA256"])
        self.assertEqual(env["CHECK_COMMIT"], env["KIT_COMMIT"])
        self.assertEqual(
            {"commit": env["CHECK_COMMIT"],
             "files": {CHECKER: env["CHECK_SHA256"], WRAPPER: env["WRAPPER_SHA256"]}},
            data,
        )

    def test_the_script_reads_the_same_pins_from_ci_yml_as_a_yaml_parser(self):
        env = ci_pins()
        pins = load_script().read_workflow_pins(CI)
        self.assertEqual(env["CHECK_COMMIT"], pins["commit"])
        self.assertEqual({CHECKER: env["CHECK_SHA256"], WRAPPER: env["WRAPPER_SHA256"]},
                         pins["files"])


class ScriptRules(unittest.TestCase):
    def test_the_script_uses_no_network_module(self):
        text = SCRIPT.read_text()
        for module in ("urllib", "http.client", "socket", "requests", "curl"):
            self.assertNotIn(module, text, module)

    def test_the_script_imports_no_third_party_module(self):
        names = set()
        for node in ast.walk(ast.parse(SCRIPT.read_text())):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module.split(".")[0])
        stdlib = {"argparse", "hashlib", "json", "os", "pathlib", "re", "subprocess", "sys"}
        self.assertTrue(names)
        self.assertEqual(set(), names - stdlib, "import outside the reviewed standard modules")


def sibling_crux():
    for name in ("crux", "crux-pilot"):
        if (ROOT.parent / name / CHECKER).is_file():
            return ROOT.parent / name
    return None


@unittest.skipIf(sibling_crux() is None, "no Crux checkout named crux or crux-pilot beside this repository")
class RealCheckout(unittest.TestCase):
    """In a west workspace (the dev container, a local workspace) the real check runs."""

    def test_the_check_passes_on_this_repository(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                                cwd=ROOT, env=dict(os.environ))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
