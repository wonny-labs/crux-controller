#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the application template folder, or a copy of it (specification section 7.5).

    check_template.py [--root DIR] [--check build|paths|all]

Two checks, both lexical:

* ``build`` (criterion 48): every build file of the folder (``CMakeLists.txt`` and ``*.cmake``) adds
  sources, subdirectories, included files and configured files from inside the folder only. An
  argument of such a command must be a relative path, or start with ``${CMAKE_CURRENT_SOURCE_DIR}``
  or ``${CMAKE_CURRENT_LIST_DIR}``, and must stay inside the folder; any other variable, a
  generator expression or an absolute path fails, because the check cannot see where it leads. An
  include path (``include_directories`` and its variants, ``-I``, ``-include``) and an extra Zephyr
  module (``EXTRA_ZEPHYR_MODULES``, ``ZEPHYR_EXTRA_MODULES``) fail too. The framework reaches the
  copy as a Zephyr module of its west workspace, through the target ``controller::framework``.
* ``paths`` (criterion 49): no text file of the folder holds an absolute path (``/a/b``, a drive
  path such as ``C:\\a``, ``~/``, ``file:/``) or a relative path (``../``) that leaves the folder.
  A URL such as ``https://host/a/b`` is not a path. The folders ``.git`` and ``build`` and files
  that are not UTF-8 text are not read.

``scripts/check_boundary.py`` checks the includes of the template sources; this script checks what
the boundary check cannot see. The default folder is ``template`` of this repository. Exit status:
0 when the checks pass, 1 when a check finds a problem, 2 for a usage error.
"""

import argparse
import os
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]

# The commands whose arguments name files that the build reads or adds.
FILE_COMMANDS = frozenset(
    """target_sources target_sources_ifdef target_sources_ifndef zephyr_sources zephyr_sources_ifdef
    zephyr_sources_ifndef zephyr_library_sources zephyr_library_sources_ifdef
    zephyr_library_sources_ifndef add_subdirectory include configure_file file aux_source_directory
    add_library add_executable""".split()
)
INCLUDE_PATH_COMMANDS = frozenset(
    """include_directories target_include_directories zephyr_include_directories
    zephyr_library_include_directories zephyr_system_include_directories""".split()
)
MODULE_VARIABLES = frozenset({"EXTRA_ZEPHYR_MODULES", "ZEPHYR_EXTRA_MODULES"})
# Keywords of the file commands, which are not paths.
KEYWORDS = frozenset(
    """PRIVATE PUBLIC INTERFACE STATIC SHARED OBJECT MODULE UNKNOWN IMPORTED ALIAS GLOBAL
    EXCLUDE_FROM_ALL SYSTEM GLOB GLOB_RECURSE RELATIVE CONFIGURE_DEPENDS LIST_DIRECTORIES
    FOLLOW_SYMLINKS COPYONLY ESCAPE_QUOTES @ONLY NEWLINE_STYLE UNIX DOS WIN32 LF CRLF OPTIONAL
    RESULT_VARIABLE NO_POLICY_SCOPE true false TRUE FALSE ON OFF""".split()
)
CONFIG_SYMBOL = re.compile(r"^CONFIG_[A-Za-z0-9_]+$")
FOLDER_VARIABLE = re.compile(r"^\$\{CMAKE_CURRENT_(?:SOURCE|LIST)_DIR\}(/[^$]*)?$")
COMMAND = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")

# An absolute POSIX path: a slash that no word, dot, colon, slash, brace or other path character
# precedes, followed by at least two named parts (/a/b). One part (/RAM:) and the devicetree
# directives (/delete-node/, / {) are not paths. A URL has a colon or a slash before its slashes.
ABSOLUTE = re.compile(r"(?<![\w.:/~$}\)\-@+])/[A-Za-z0-9._@+\-]+(?:/[A-Za-z0-9._@+\-]+)+")
DRIVE = re.compile(r"(?<![\w])[A-Za-z]:[\\/]\w")
HOME = re.compile(r"(?<![\w/])~/")
FILE_URL = re.compile(r"\bfile:/")
RELATIVE_UP = re.compile(r"(?<![\w.])(?:\.\.[/\\])+[^\s\"'<>()\[\]`]*")
SKIPPED_FOLDERS = frozenset({".git", "build"})


def strip_cmake_comments(text):
    """Blank out # comments outside quoted arguments; keep every newline."""
    out = []
    quoted = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and quoted:
            out.append(text[i : i + 2])
            i += 2
            continue
        if c == '"':
            quoted = not quoted
        elif c == "#" and not quoted:
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            out.append(" " * (end - i))
            i = end
            continue
        out.append(c)
        i += 1
    return "".join(out)


def commands(text):
    """Yield (line, name, arguments) for each command call, arguments split as CMake splits them."""
    for match in COMMAND.finditer(text):
        depth, i = 1, match.end()
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        body = text[match.end() : i - 1]
        arguments = [quoted or bare for quoted, bare in re.findall(r'"((?:[^"\\]|\\.)*)"|([^\s()"]+)', body)]
        yield text.count("\n", 0, match.start()) + 1, match.group(1), arguments


def inside(path, root):
    try:
        pathlib.Path(os.path.normpath(path)).relative_to(root)
    except ValueError:
        return False
    return True


def argument_problem(argument, directory, root):
    """Why a path argument of a file command is not inside the folder, or None."""
    if argument in KEYWORDS or CONFIG_SYMBOL.match(argument):
        return None
    if "$" in argument:
        folder = FOLDER_VARIABLE.match(argument)
        if not folder:
            return "a variable or generator expression that the check cannot resolve"
        argument = "." + (folder.group(1) or "")
    if os.path.isabs(argument) or DRIVE.match(argument):
        return "an absolute path"
    if not inside(directory / argument, root):
        return "a path outside the template folder"
    return None


def build_file_problems(root):
    """Return 'path:line: problem' for each build file argument that reaches outside the folder."""
    root = pathlib.Path(os.path.abspath(root))
    problems = []
    files = sorted(p for p in root.rglob("*")
                   if p.is_file() and (p.name == "CMakeLists.txt" or p.suffix == ".cmake")
                   and not SKIPPED_FOLDERS & set(p.relative_to(root).parts[:-1]))
    for path in files:
        relative = path.relative_to(root).as_posix()
        text = strip_cmake_comments(path.read_text(errors="replace"))
        for line, name, arguments in commands(text):
            where = f"{relative}:{line}: {name}"
            if name in INCLUDE_PATH_COMMANDS:
                problems.append(f"{where}: adds an include path")
                continue
            for argument in arguments:
                if argument.startswith("-I") or argument == "-include":
                    problems.append(f"{where}: {argument}: adds an include path")
                elif argument in MODULE_VARIABLES:
                    problems.append(f"{where}: {argument}: adds a Zephyr module from outside the folder")
                elif name in FILE_COMMANDS:
                    reason = argument_problem(argument, path.parent, root)
                    if reason:
                        problems.append(f"{where}: {argument}: {reason}")
    return problems


def path_problems(root):
    """Return 'path:line: problem' for each absolute path, or relative path that leaves the folder."""
    root = pathlib.Path(os.path.abspath(root))
    problems = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        parts = path.relative_to(root).parts
        if SKIPPED_FOLDERS & set(parts[:-1]):
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(root).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            for pattern, what in ((ABSOLUTE, "an absolute path"), (DRIVE, "an absolute path"),
                                  (HOME, "a path in a home folder"), (FILE_URL, "a file URL")):
                for match in pattern.finditer(line):
                    problems.append(f"{relative}:{number}: {match.group(0)}: {what}")
            for match in RELATIVE_UP.finditer(line):
                if not inside(path.parent / match.group(0).replace("\\", "/"), root):
                    problems.append(f"{relative}:{number}: {match.group(0)}: a relative path that leaves the folder")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=pathlib.Path, default=REPO / "template",
                        help="the template folder or a copy (default: template of this repository)")
    parser.add_argument("--check", choices=("build", "paths", "all"), default="all")
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print(f"error: {args.root} is not a folder", file=sys.stderr)
        return 2
    problems = []
    if args.check in ("build", "all"):
        problems += build_file_problems(args.root)
    if args.check in ("paths", "all"):
        problems += path_problems(args.root)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} template problem(s). See template/README.md.")
        return 1
    print("template check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
