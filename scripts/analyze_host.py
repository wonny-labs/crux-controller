#!/usr/bin/env python3
"""Run clang-tidy over the sources that the host tests build, then list what it did not analyse.

The file list is not written by hand. It is every translation unit of this repository in the
compile database of the host tests (tests/host). Every tracked C or C++ source that is not in that
database, such as the sources that need Zephyr or Crux headers, is printed at the end, so a new
source cannot skip the analysis without showing up in the list. The check configuration is
.clang-tidy, where every finding is an error.

Usage: python3 scripts/analyze_host.py [--build-dir DIR] [--extra-arg ARG]...
Environment: CLANG_TIDY names the tool (default clang-tidy-18).
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

REQUIRED_MAJOR = "18"
SOURCE_PATTERNS = ("*.c", "*.cpp")


def repo_root():
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True
    )
    return pathlib.Path(out.stdout.strip()).resolve()


def tracked_sources(root):
    """Every C and C++ source that git lists, tracked or new but not ignored, that exists."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         "--", *SOURCE_PATTERNS],
        check=True, capture_output=True,
    )
    # -z keeps a path with a non-ASCII character as it is. Without it git quotes the path.
    names = (os.fsdecode(name) for name in out.stdout.split(b"\0") if name)
    paths = (root / name for name in names)
    return sorted({path for path in paths if path.is_file()})


def database_sources(database, root):
    """The sources of this repository in a compile database, each once and in order.

    Files outside the repository and files in a build directory are not this repository's sources.
    """
    root = pathlib.Path(root).resolve()
    found = set()
    for entry in json.loads(pathlib.Path(database).read_text()):
        path = pathlib.Path(entry["file"])
        if not path.is_absolute():
            path = pathlib.Path(entry["directory"]) / path
        path = pathlib.Path(os.path.normpath(path))
        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] == "build":
            continue
        found.add(root / relative)
    return sorted(found)


def not_analysed(tracked, analysed):
    analysed = set(analysed)
    return [path for path in tracked if path not in analysed]


def check_tool(tool):
    """Fail with a clear message unless the tool is clang-tidy of the required major version."""
    try:
        out = subprocess.run([tool, "--version"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        sys.exit(f"analyze_host: cannot run {tool}. Install clang-tidy-{REQUIRED_MAJOR}.")
    match = re.search(r"LLVM version (\S+)", out.stdout)
    version = match.group(1) if match else "unknown"
    if version.split(".")[0] != REQUIRED_MAJOR:
        sys.exit(
            f"analyze_host: {tool} is version {version}, but clang-tidy {REQUIRED_MAJOR} is "
            f"required (apt package clang-tidy-{REQUIRED_MAJOR})."
        )
    return version


def configure(root, build_dir):
    """Configure the host tests, without building them, to get their compile database.

    Returns the database path, or None when the configure step fails.
    """
    command = ["cmake", "-S", str(root / "tests/host"), "-B", str(build_dir), "-G", "Ninja",
               "-DWORKLOAD_SANITIZE=OFF", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]
    try:
        status = subprocess.run(command).returncode
    except OSError as error:
        print(f"analyze_host: cannot run cmake: {error}", file=sys.stderr)
        return None
    if status != 0:
        print(f"analyze_host: the cmake configure of tests/host failed (exit status {status}).",
              file=sys.stderr)
        return None
    return build_dir / "compile_commands.json"


def report_not_analysed(root, analysed):
    missing = not_analysed(tracked_sources(root), analysed)
    print(f"\nNot analysed ({len(missing)} tracked sources are not in the compile database):")
    for path in missing:
        print(f"  {path.relative_to(root).as_posix()}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--build-dir", type=pathlib.Path, help="default: build/analyze")
    parser.add_argument("--compile-commands", type=pathlib.Path,
                        help="use this compile database and skip the configure step")
    parser.add_argument("--extra-arg", action="append", default=[],
                        help="passed to clang-tidy as --extra-arg (for example a sysroot)")
    args = parser.parse_args(argv)

    root = repo_root()
    tool = os.environ.get("CLANG_TIDY", f"clang-tidy-{REQUIRED_MAJOR}")
    version = check_tool(tool)

    if args.compile_commands:
        database = args.compile_commands.resolve()
    else:
        database = configure(root, (args.build_dir or root / "build" / "analyze").resolve())
    # Without a usable database nothing is analysed, which is a failure. The list still shows
    # that every source was skipped.
    if database is None:
        report_not_analysed(root, [])
        return 1
    sources = database_sources(database, root)
    if not sources:
        print(f"analyze_host: no source of this repository in {database}.", file=sys.stderr)
        report_not_analysed(root, [])
        return 1

    print(f"analyze_host: clang-tidy {version}, {len(sources)} sources from {database}", flush=True)
    command = [tool, "-p", str(database.parent), "--quiet"]
    command += [f"--extra-arg={arg}" for arg in args.extra_arg]
    status = subprocess.run(command + [str(path) for path in sources]).returncode

    report_not_analysed(root, sources)
    print(f"analyze_host: clang-tidy exit status {status}", flush=True)
    return 1 if status else 0


if __name__ == "__main__":
    sys.exit(main())
