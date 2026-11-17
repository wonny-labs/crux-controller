#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail when a first-party file lacks the licence identifier line that this repository uses.

The convention is the one the existing files follow: the first line of the file, or the second
when the first is a shebang, is exactly

    /* SPDX-License-Identifier: Apache-2.0 */     C and C++ sources and headers
    # SPDX-License-Identifier: Apache-2.0         everything else that is covered

Covered files are the tracked and the untracked, not ignored, files named CMakeLists.txt or
Kconfig, and the files with the suffix .c, .h, .py, .sh or .cmake. Configuration (.conf), device
tree overlays, documents, JSON, YAML and the web assets of the management page are not covered:
none of them carries a header today, so a rule for them would be a new convention and not the
enforcement of this one.

ALLOWLIST holds the files that predate the check and still lack the header. An entry is an exact
path, never a pattern. An entry for a file that is gone or that now has the header is an error, so
the list can only get shorter.

Usage: python3 scripts/check_spdx.py [--repo DIR] [--allowlist FILE]
Exit status: 0 all covered files pass, 1 findings, 2 the check could not run.
"""

import argparse
import os
import pathlib
import subprocess
import sys

IDENTIFIER = "SPDX-License-Identifier: Apache-2.0"
C_HEADER = f"/* {IDENTIFIER} */"
HASH_HEADER = f"# {IDENTIFIER}"

C_SUFFIXES = (".c", ".h")
HASH_SUFFIXES = (".py", ".sh", ".cmake")
COVERED_NAMES = ("CMakeLists.txt", "Kconfig")

# Files that predate the check. Both are existing check scripts, and changing one needs the
# project owner's approval of a protected path, so they are listed here and not edited.
ALLOWLIST = (
    "scripts/analyze_host.py",
    "scripts/check-format.sh",
)


def expected_header(path):
    """The header line that `path` needs, or None when the check does not cover it."""
    name = os.path.basename(path)
    if name.endswith(C_SUFFIXES):
        return C_HEADER
    if name in COVERED_NAMES or name.endswith(HASH_SUFFIXES):
        return HASH_HEADER
    return None


def list_files(repo):
    """Tracked and untracked, not ignored, files of the repository that still exist."""
    try:
        output = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            check=True, capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", b"") or str(error).encode()
        raise SystemExit(
            f"check_spdx: cannot list the files of {repo}: {detail.decode(errors='replace').strip()}"
        ) from None
    names = sorted({n for n in output.decode("utf-8", errors="surrogateescape").split("\0") if n})
    # Git still lists the old path of a file that was deleted and not yet staged.
    return [n for n in names if os.path.isfile(os.path.join(repo, n))]


def has_header(path, wanted):
    """True when line 1, or line 2 after a shebang, is exactly the wanted header."""
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            lines = handle.read(4096).splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    return bool(lines) and lines[0] == wanted


def read_allowlist(path):
    entries = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if any(ch in line for ch in "*?[]"):
                raise SystemExit(f"check_spdx: the allowlist takes exact paths, not a wildcard: {line}")
            entries.append(line)
    return tuple(entries)


def check(repo, allowlist):
    """Returns (problems, checked, allowlisted); raises ValueError when nothing is covered."""
    covered = {n: h for n in list_files(repo) if (h := expected_header(n)) is not None}
    if not covered:
        raise ValueError("no covered files in the repository")
    problems = []
    used = 0
    for name in sorted(covered):
        ok = has_header(os.path.join(repo, name), covered[name])
        if name in allowlist:
            used += 1
            if ok:
                problems.append(f"{name}: has the header now, remove it from the allowlist")
        elif not ok:
            problems.append(f"{name}: needs the first line {covered[name]}")
    for name in allowlist:
        if name not in covered:
            problems.append(f"{name}: allowlisted but not a covered file of the repository")
    return problems, len(covered), used


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo", default=".", help="the Git repository to check (default: .)")
    parser.add_argument(
        "--allowlist", help="a file of exact paths, one per line, in place of the built-in list"
    )
    args = parser.parse_args(argv)
    repo = pathlib.Path(args.repo)
    try:
        allowlist = read_allowlist(args.allowlist) if args.allowlist else ALLOWLIST
        problems, checked, used = check(repo, allowlist)
    except ValueError as error:
        print(f"check_spdx: {error}", file=sys.stderr)
        return 2
    except (OSError, SystemExit) as error:
        message = error.code if isinstance(error, SystemExit) else f"check_spdx: {error}"
        print(message, file=sys.stderr)
        return 2
    for problem in problems:
        print(f"check_spdx: {problem}", file=sys.stderr)
    if problems:
        print(f"check_spdx: {len(problems)} problem(s) in {checked} covered files", file=sys.stderr)
        return 1
    print(f"check_spdx: {checked} files checked, {used} allowlisted, all carry {IDENTIFIER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
