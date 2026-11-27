#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run clang-tidy over this repository's sources in a native_sim compile database.

The host analysis (scripts/analyze_host.py) covers the sources that the host tests build. The
sources that need Zephyr (the framework's adapter and composition zones, the fixture application and
the scenarios) are compiled only in a Zephyr build, so this script reads the compile database of a
native_sim build (CMake writes compile_commands.json in every Zephyr build directory) and analyses
every source of this repository in it with the checks of .clang-tidy, where every finding is an error.

native_sim compiles with the host's GCC, whose command lines carry options that clang does not accept.
The script therefore writes a copy of the database in which each command keeps only what the
analysis needs: the defines, the include paths, the forced includes (-include and -imacros, which
carry the Kconfig values), the language standard and the word size, with clang as the compiler.
Files outside the repository (Zephyr, Crux, generated files) are left out, as analyze_host.py leaves
them out. The tracked sources that the database does not hold are printed at the end.

Usage: python3 scripts/analyze_zephyr.py --database BUILD/compile_commands.json [--extra-arg ARG]...
Environment: CLANG_TIDY names the tool (default clang-tidy-18).
"""

import argparse
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import analyze_host  # noqa: E402

# Options followed by a separate value that the analysis keeps.
KEPT_WITH_VALUE = ("-I", "-isystem", "-iquote", "-idirafter", "-include", "-imacros", "-D", "-U")
# Options whose value is joined to them that the analysis keeps.
KEPT_PREFIXES = ("-I", "-D", "-U", "-std=", "-isystem", "-iquote", "-idirafter")
KEPT_EXACT = frozenset({"-m32", "-m64", "-nostdinc"})


def arguments_of(entry):
    """The argument list of a compile database entry, from "arguments" or "command"."""
    if "arguments" in entry:
        return list(entry["arguments"])
    return shlex.split(entry["command"])


def kept_arguments(arguments):
    """The options of one command that the analysis keeps, in their order, without the compiler,
    the output and the source file."""
    kept = []
    index = 1
    while index < len(arguments):
        argument = arguments[index]
        if argument in KEPT_WITH_VALUE and index + 1 < len(arguments):
            kept += [argument, arguments[index + 1]]
            index += 2
            continue
        if argument in KEPT_EXACT or argument.startswith(KEPT_PREFIXES):
            kept.append(argument)
        index += 1
    return kept


def rewrite(entries, sources):
    """The entries of the given sources, with clang and the kept options only."""
    sources = set(sources)
    rewritten = []
    for entry in entries:
        path = pathlib.Path(entry["file"])
        if not path.is_absolute():
            path = pathlib.Path(entry["directory"]) / path
        path = pathlib.Path(os.path.normpath(path)).resolve()
        if path not in sources:
            continue
        arguments = ["clang", *kept_arguments(arguments_of(entry)), "-c", str(path)]
        rewritten.append({"directory": entry["directory"], "file": str(path), "arguments": arguments})
    return rewritten


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", type=pathlib.Path, required=True,
                        help="compile_commands.json of a native_sim build")
    parser.add_argument("--extra-arg", action="append", default=[],
                        help="passed to clang-tidy as --extra-arg")
    args = parser.parse_args(argv)

    # The repository of this script, wherever it runs from (CI runs it from the workspace folder).
    root = pathlib.Path(__file__).resolve().parents[1]
    tool = os.environ.get("CLANG_TIDY", f"clang-tidy-{analyze_host.REQUIRED_MAJOR}")
    version = analyze_host.check_tool(tool)
    try:
        entries = json.loads(args.database.read_text())
        ours = analyze_host.database_sources(args.database, root)
    except (OSError, ValueError, KeyError) as error:
        print(f"analyze_zephyr: cannot read {args.database}: {error}", file=sys.stderr)
        return 1
    rewritten = rewrite(entries, ours)
    if not rewritten:
        print(f"analyze_zephyr: no source of this repository in {args.database}.", file=sys.stderr)
        return 1
    sources = sorted({pathlib.Path(entry["file"]) for entry in rewritten})
    with tempfile.TemporaryDirectory() as directory:
        database = pathlib.Path(directory) / "compile_commands.json"
        database.write_text(json.dumps(rewritten, indent=1))
        print(f"analyze_zephyr: clang-tidy {version}, {len(sources)} sources from {args.database}",
              flush=True)
        for path in sources:
            print(f"  {path.relative_to(root).as_posix()}")
        command = [tool, "-p", directory, "--quiet"]
        command += [f"--extra-arg={arg}" for arg in args.extra_arg]
        status = subprocess.run(command + [str(path) for path in sources]).returncode
    missing = analyze_host.not_analysed(analyze_host.tracked_sources(root), sources)
    print(f"\nNot in this database ({len(missing)} tracked sources):")
    for path in missing:
        print(f"  {path.relative_to(root).as_posix()}")
    print(f"analyze_zephyr: clang-tidy exit status {status}", flush=True)
    return 1 if status else 0


if __name__ == "__main__":
    sys.exit(main())
