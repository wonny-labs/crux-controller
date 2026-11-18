# SPDX-License-Identifier: Apache-2.0
"""Tests of scripts/check_spdx.py, the check that first-party files carry the licence identifier.

Every failure mode is shown on a throwaway Git repository: a check that no input can fail would
prove nothing. One test also mutates a copy of this repository's own tracked files.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_spdx.py"

C_HEADER = "/* SPDX-License-Identifier: Apache-2.0 */\n"
HASH_HEADER = "# SPDX-License-Identifier: Apache-2.0\n"

# One passing example for each kind of file that the check covers.
GOOD = {
    "src/a.c": C_HEADER + "int a;\n",
    "src/a.h": C_HEADER + "int a(void);\n",
    "tools/t.py": "#!/usr/bin/env python3\n" + HASH_HEADER + '"""Doc."""\n',
    "tools/u.py": HASH_HEADER + '"""Doc."""\n',
    "tools/s.sh": "#!/usr/bin/env bash\n" + HASH_HEADER + "set -e\n",
    "CMakeLists.txt": HASH_HEADER + "project(x)\n",
    "sub/CMakeLists.txt": HASH_HEADER + "add_library(y)\n",
    "sub/x.cmake": HASH_HEADER + "set(a 1)\n",
    "Kconfig": HASH_HEADER + "config X\n",
}


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def make_repo(files, track=True):
    directory = tempfile.TemporaryDirectory()
    repo = pathlib.Path(directory.name)
    git(repo, "init", "-q")
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    if track:
        git(repo, "add", "-A")
    return directory, repo


def run(repo, *extra):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), *extra],
        capture_output=True, text=True,
    )


class Passing(unittest.TestCase):
    def test_a_repository_with_every_header_passes(self):
        directory, repo = make_repo(GOOD)
        with directory:
            result = run(repo, "--allowlist", os.devnull)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(f"check_spdx: {len(GOOD)} files checked", result.stdout)

    def test_files_of_other_kinds_need_no_header(self):
        files = dict(GOOD)
        files.update({
            "README.md": "# Title\n", "data.json": "{}\n", "ci.yml": "name: x\n",
            "prj.conf": "CONFIG_X=y\n", "board.overlay": "/ { };\n", "notes.txt": "x\n",
            "site/page.js": "var x;\n", "site/page.css": "a {}\n", "site/index.html": "<p>\n",
            "LICENSE": "Apache\n",
        })
        directory, repo = make_repo(files)
        with directory:
            result = run(repo, "--allowlist", os.devnull)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(f"{len(GOOD)} files checked", result.stdout)

    def test_a_shebang_may_come_first(self):
        directory, repo = make_repo({"a.py": "#!/usr/bin/env python3\n" + HASH_HEADER})
        with directory:
            self.assertEqual(0, run(repo, "--allowlist", os.devnull).returncode)


class Failing(unittest.TestCase):
    def fails(self, files, fragment, track=True):
        directory, repo = make_repo(files, track=track)
        with directory:
            result = run(repo, "--allowlist", os.devnull)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(fragment, result.stderr)
        return result

    def test_each_covered_kind_fails_without_its_header(self):
        for name, text in GOOD.items():
            stripped = "".join(
                line for line in text.splitlines(keepends=True) if "SPDX" not in line
            )
            with self.subTest(name):
                self.fails({name: stripped}, name)

    def test_the_failure_names_every_offending_file_and_no_other(self):
        files = dict(GOOD)
        files["src/bad1.c"] = "int x;\n"
        files["src/bad2.h"] = "int y;\n"
        result = self.fails(files, "src/bad1.c")
        self.assertIn("src/bad2.h", result.stderr)
        self.assertNotIn("src/a.c", result.stderr)

    def test_another_licence_identifier_fails(self):
        self.fails({"a.c": "/* SPDX-License-Identifier: MIT */\n"}, "a.c")

    def test_the_identifier_must_match_exactly(self):
        for variant in ("Apache-2.0 OR MIT", "Apache-2.0+", "Apache-2.00", "apache-2.0"):
            with self.subTest(variant):
                self.fails({"a.c": f"/* SPDX-License-Identifier: {variant} */\n"}, "a.c")

    def test_the_comment_style_must_suit_the_file(self):
        self.fails({"a.c": HASH_HEADER}, "a.c")
        self.fails({"a.py": C_HEADER}, "a.py")

    def test_the_header_must_be_the_first_line_or_the_one_after_a_shebang(self):
        self.fails({"a.c": "int x;\n" + C_HEADER}, "a.c")
        self.fails({"a.c": "\n" + C_HEADER}, "a.c")
        self.fails({"a.py": "#!/usr/bin/env python3\n\n" + HASH_HEADER}, "a.py")
        self.fails({"a.py": "import os\n" + HASH_HEADER}, "a.py")

    def test_a_shebang_without_a_header_fails(self):
        self.fails({"a.sh": "#!/usr/bin/env bash\nset -e\n"}, "a.sh")

    def test_an_empty_covered_file_fails(self):
        self.fails({"a.c": ""}, "a.c")

    def test_a_file_that_is_not_utf8_fails_instead_of_crashing(self):
        directory, repo = make_repo({})
        with directory:
            (repo / "a.c").write_bytes(b"\xff\xfe\x00 binary\n")
            git(repo, "add", "-A")
            result = run(repo, "--allowlist", os.devnull)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("a.c", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_an_untracked_file_that_is_not_ignored_is_checked(self):
        directory, repo = make_repo(GOOD)
        with directory:
            (repo / "new.c").write_text("int z;\n")
            result = run(repo, "--allowlist", os.devnull)
        self.assertEqual(1, result.returncode)
        self.assertIn("new.c", result.stderr)

    def test_an_ignored_file_is_not_checked(self):
        directory, repo = make_repo(GOOD)
        with directory:
            (repo / ".gitignore").write_text("build/\n")
            (repo / "build").mkdir()
            (repo / "build" / "gen.c").write_text("int z;\n")
            result = run(repo, "--allowlist", os.devnull)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_a_file_deleted_but_still_listed_is_skipped(self):
        directory, repo = make_repo(GOOD)
        with directory:
            (repo / "src" / "a.c").unlink()
            result = run(repo, "--allowlist", os.devnull)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_a_repository_without_a_covered_file_is_an_error_not_a_pass(self):
        directory, repo = make_repo({"README.md": "x\n"})
        with directory:
            result = run(repo, "--allowlist", os.devnull)
        self.assertEqual(2, result.returncode)
        self.assertIn("no covered files", result.stderr)

    def test_a_directory_that_is_not_a_repository_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(directory, "--allowlist", os.devnull)
        self.assertEqual(2, result.returncode)


class Allowlist(unittest.TestCase):
    def allowlist(self, directory, *lines):
        path = pathlib.Path(directory) / "allow.txt"
        path.write_text("\n".join(lines) + "\n")
        return path

    def test_an_allowlisted_file_without_a_header_passes_and_is_counted(self):
        directory, repo = make_repo({**GOOD, "legacy.py": "print(1)\n"})
        with directory, tempfile.TemporaryDirectory() as other:
            allow = self.allowlist(other, "# a comment", "", "legacy.py")
            result = run(repo, "--allowlist", str(allow))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("1 allowlisted", result.stdout)

    def test_an_entry_for_a_file_that_now_has_a_header_fails(self):
        directory, repo = make_repo(GOOD)
        with directory, tempfile.TemporaryDirectory() as other:
            allow = self.allowlist(other, "src/a.c")
            result = run(repo, "--allowlist", str(allow))
        self.assertEqual(1, result.returncode)
        self.assertIn("src/a.c", result.stderr)
        self.assertIn("remove", result.stderr)

    def test_an_entry_for_a_file_that_does_not_exist_fails(self):
        directory, repo = make_repo(GOOD)
        with directory, tempfile.TemporaryDirectory() as other:
            allow = self.allowlist(other, "gone.py")
            result = run(repo, "--allowlist", str(allow))
        self.assertEqual(1, result.returncode)
        self.assertIn("gone.py", result.stderr)

    def test_an_entry_does_not_excuse_another_file(self):
        directory, repo = make_repo({**GOOD, "legacy.py": "x\n", "other.py": "y\n"})
        with directory, tempfile.TemporaryDirectory() as other:
            allow = self.allowlist(other, "legacy.py")
            result = run(repo, "--allowlist", str(allow))
        self.assertEqual(1, result.returncode)
        self.assertIn("other.py", result.stderr)
        self.assertNotIn("legacy.py", result.stderr)

    def test_a_wildcard_entry_is_refused(self):
        directory, repo = make_repo(GOOD)
        with directory, tempfile.TemporaryDirectory() as other:
            allow = self.allowlist(other, "src/*.c")
            result = run(repo, "--allowlist", str(allow))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("wildcard", result.stderr)

    def test_the_built_in_allowlist_names_only_scripts_that_cannot_be_edited_here(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import check_spdx
        finally:
            sys.path.pop(0)
        self.assertEqual(
            {"scripts/analyze_host.py", "scripts/check-format.sh"}, set(check_spdx.ALLOWLIST)
        )


class ThisRepository(unittest.TestCase):
    def test_the_tracked_tree_passes(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(ROOT)], capture_output=True, text=True
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("2 allowlisted", result.stdout)

    def test_removing_one_header_from_a_copy_of_the_tree_fails(self):
        listing = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True
        ).stdout.decode().split("\0")
        with tempfile.TemporaryDirectory() as directory:
            copy = pathlib.Path(directory)
            git(copy, "init", "-q")
            for name in filter(None, listing):
                source = ROOT / name
                if source.is_file():
                    (copy / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, copy / name)
            git(copy, "add", "-A")
            self.assertEqual(0, run(copy).returncode, "the copy must pass before the mutation")
            target = copy / "app" / "src" / "main.c"
            target.write_text(
                target.read_text().replace("/* SPDX-License-Identifier: Apache-2.0 */\n", "", 1)
            )
            result = run(copy)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("app/src/main.c", result.stderr)


if __name__ == "__main__":
    unittest.main()
