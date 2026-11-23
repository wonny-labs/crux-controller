# SPDX-License-Identifier: Apache-2.0
"""The editor tools of the Dev Container: clangd for C code navigation, and west Tab completion in bash.

clangd (the binary in the image and the VS Code extension) replaces the C/C++ extension, as in Crux's Dev
Container; it reads the compile database that the board build of the VS Code task writes. The west completion
script comes from the west of the virtual environment, which lives in the cache volume and not in the image, so
.devcontainer/setup.sh writes it on every run into bash-completion's user folder. Nothing here starts VS Code,
clangd or a container.
"""

import json
import pathlib
import re
import unittest

from test_devcontainer import SetupFixture

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEVCONTAINER = ROOT / ".devcontainer"
CLANG_VERSION = "1:18.1.3-1ubuntu1"


def apt_step(text):
    joined = re.sub(r"\\\n", " ", text)
    return next(line for line in joined.splitlines() if line.startswith("RUN apt-get update"))


class Clangd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dockerfile = (DEVCONTAINER / "Dockerfile").read_text()
        cls.config = json.loads((DEVCONTAINER / "devcontainer.json").read_text())
        cls.vscode = cls.config["customizations"]["vscode"]

    def test_the_image_installs_clangd_18_at_the_version_of_clang_tidy_and_names_it_clangd(self):
        step = apt_step(self.dockerfile)
        self.assertIn(f"clangd-18={CLANG_VERSION}", step)
        self.assertIn(f"clang-tidy-18={CLANG_VERSION}", step)
        self.assertIn("ln -sf /usr/bin/clangd-18 /usr/local/bin/clangd", step)
        self.assertLess(step.index("apt-get install"), step.index("ln -sf /usr/bin/clangd-18"))

    def test_the_clangd_extension_replaces_the_cpp_extension(self):
        extensions = self.vscode["extensions"]
        self.assertIn("llvm-vs-code-extensions.vscode-clangd", extensions)
        self.assertNotIn("ms-vscode.cpptools", extensions)
        self.assertFalse([key for key in self.vscode["settings"] if key.startswith("C_Cpp")])

    def test_clangd_asks_the_sdk_compiler_for_its_system_headers(self):
        arguments = self.vscode["settings"]["clangd.arguments"]
        self.assertIn("--query-driver=${env:ZEPHYR_SDK_INSTALL_DIR}/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc",
                      arguments)

    def test_c_files_are_formatted_by_clangd_with_the_repository_style(self):
        self.assertEqual("llvm-vs-code-extensions.vscode-clangd",
                         self.vscode["settings"]["[c]"]["editor.defaultFormatter"])
        self.assertTrue((ROOT / ".clang-format").is_file())

    def test_clangd_reads_the_compile_database_of_the_board_build_of_the_vscode_task(self):
        config = (ROOT / ".clangd").read_text()
        match = re.search(r"(?m)^  CompilationDatabase: (\S+)$", config)
        self.assertIsNotNone(match, config)
        self.assertIn("CompileFlags:", config)
        tasks = {t["label"]: t for t in json.loads((ROOT / ".vscode" / "tasks.json").read_text())["tasks"]}
        self.assertIn(f"-d crux-controller/{match.group(1)} ", tasks["Build firmware"]["command"])


class BashCompletion(unittest.TestCase):
    def test_the_image_has_the_bash_completion_package(self):
        self.assertRegex(apt_step((DEVCONTAINER / "Dockerfile").read_text()), r"\sbash-completion\s")

    def setUp(self):
        self.fixture = SetupFixture()
        self.addCleanup(self.fixture.close)
        self.target = self.fixture.home / ".local" / "share" / "bash-completion" / "completions" / "west"

    def run_setup(self, **env):
        result = self.fixture.run(**env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout, "setup.sh must keep the standard output clean")
        return result

    def test_setup_writes_the_west_completion_script_to_the_bash_completion_user_folder(self):
        self.run_setup()
        self.assertEqual("# west completion script for bash\n", self.target.read_text())
        self.assertIn("west completion bash", self.fixture.calls("west"))

    def test_it_is_written_again_on_every_run_after_the_tools_are_installed(self):
        self.run_setup()
        self.target.write_text("stale\n")
        self.run_setup()
        self.assertEqual("# west completion script for bash\n", self.target.read_text())
        log = self.fixture.calls()
        self.assertLess(next(i for i, line in enumerate(log) if line.startswith("python -m pip install")),
                        log.index("west completion bash"))

    def test_it_follows_xdg_data_home(self):
        data = self.fixture.base / "data"
        self.run_setup(XDG_DATA_HOME=str(data))
        self.assertTrue((data / "bash-completion" / "completions" / "west").is_file())

    def test_it_follows_bash_completion_user_dir(self):
        folder = self.fixture.base / "user-completions"
        self.run_setup(BASH_COMPLETION_USER_DIR=str(folder), XDG_DATA_HOME=str(self.fixture.base / "data"))
        self.assertTrue((folder / "completions" / "west").is_file())
        self.assertFalse((self.fixture.base / "data" / "bash-completion").exists())

    def test_a_failed_completion_warns_and_the_setup_goes_on_with_the_old_file_kept(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_text("previous\n")
        result = self.run_setup(FAKE_COMPLETION_FAIL="1")
        self.assertIn("warning", result.stderr)
        self.assertIn("west Tab completion", result.stderr)
        self.assertEqual("previous\n", self.target.read_text())
        self.assertEqual(["west completion bash"], [n for n in self.fixture.calls("west completion")])
        self.assertTrue(self.fixture.calls("west init"), "the later steps still run")
        self.assertTrue(self.fixture.sdk_installs())
        self.assertEqual(["west"], sorted(p.name for p in self.target.parent.iterdir()))

    def test_the_completion_step_has_a_name_of_its_own(self):
        self.assertIn('step "the west Tab completion"', (DEVCONTAINER / "setup.sh").read_text())

    def test_no_shell_start_file_is_edited(self):
        text = (DEVCONTAINER / "setup.sh").read_text()
        self.assertNotIn(".bashrc >>", text)
        self.assertNotRegex(text, r">>\s*\"?\$HOME/\.bashrc")


if __name__ == "__main__":
    unittest.main()
