# SPDX-License-Identifier: Apache-2.0
"""Tests of scripts/ci/match-vulnerabilities.sh with stub commands (criterion 36).

curl, sha256sum and tar are stubs on PATH, and the stub tar puts a fake grype in place, so the
script runs without a download. The pinned hash check is tested as text.
"""

import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "match-vulnerabilities.sh"

FAKE_GRYPE = r"""#!/bin/bash
# Prints a table, or a JSON report when asked for --output json; FAIL_ON names a document to fail.
printf '%s\n' "$*" >> "$CALLS"
document="${1#sbom:}"
[[ -n "${FAIL_ON:-}" && "$(basename "$document")" == "$FAIL_ON" ]] && exit 1
if [[ " $* " == *" --output json "* ]]; then
  printf '{"matches": [], "source": "%s"}\n' "$(basename "$document")"
else
  printf 'NAME INSTALLED VULNERABILITY\n'
fi
"""


class MatchVulnerabilities(unittest.TestCase):
    def setUp(self):
        self.base = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(self.base)])
        self.bin = self.base / "bin"
        self.bin.mkdir()
        (self.base / "grype").write_text(FAKE_GRYPE)
        self.stub("curl", '#!/bin/bash\nwhile [[ $# -gt 0 ]]; do\n'
                          '  [[ $1 == --output ]] && { : > "$2"; shift; }\n  shift\ndone\n')
        self.stub("sha256sum", "#!/bin/bash\ncat > /dev/null\n")
        self.stub("tar", f'#!/bin/bash\nwhile [[ $# -gt 0 ]]; do\n'
                         f'  [[ $1 == -C ]] && {{ cp "{self.base}/grype" "$2/grype"; chmod +x "$2/grype"; }}\n'
                         f'  shift\ndone\n')
        self.spdx = self.base / "spdx"
        self.spdx.mkdir()
        for name in ("app.spdx", "zephyr.spdx"):
            (self.spdx / name).write_text("SPDXVersion: SPDX-2.3\n")
        self.calls = self.base / "calls.txt"

    def stub(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def run_script(self, *args, **env):
        environment = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
                       "CALLS": str(self.calls), **env}
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True,
                              env=environment)

    def test_the_default_mode_prints_a_table_per_document_and_only_reports(self):
        result = self.run_script(str(self.spdx))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("### app.spdx", result.stdout)
        self.assertIn("### zephyr.spdx", result.stdout)
        self.assertIn("Report only", result.stdout)
        self.assertIn("--output table", self.calls.read_text())

    def test_the_json_mode_writes_one_grype_report_per_document(self):
        out = self.base / "matches"
        result = self.run_script("--json", str(out), str(self.spdx))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["app.grype.json", "zephyr.grype.json"],
                         sorted(path.name for path in out.iterdir()))
        report = json.loads((out / "app.grype.json").read_text())
        self.assertEqual([], report["matches"])
        self.assertEqual("app.spdx", report["source"])
        self.assertNotIn("--output table", self.calls.read_text())
        self.assertIn("release/check_triage.py", result.stdout)

    def test_a_document_grype_cannot_read_fails_in_both_modes(self):
        for args in ((), ("--json", str(self.base / "out"))):
            with self.subTest(args=args):
                result = self.run_script(*args, str(self.spdx), FAIL_ON="zephyr.spdx")
                self.assertEqual(1, result.returncode)
                self.assertIn("zephyr.spdx", result.stderr)

    def test_wrong_arguments_exit_2(self):
        for args in ((), (str(self.base / "missing"),), ("--json",), ("--json", "out")):
            with self.subTest(args=args):
                self.assertEqual(2, self.run_script(*args).returncode)

    def test_a_folder_without_spdx_documents_exits_2(self):
        empty = self.base / "empty"
        empty.mkdir()
        self.assertEqual(2, self.run_script(str(empty)).returncode)

    def test_the_archive_is_checked_against_its_pinned_hash(self):
        text = SCRIPT.read_text()
        self.assertRegex(text, r"GRYPE_SHA256=[0-9a-f]{64}")
        self.assertIn("sha256sum --check --strict -", text)


if __name__ == "__main__":
    unittest.main()
