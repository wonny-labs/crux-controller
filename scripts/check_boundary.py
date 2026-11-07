#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail when product source includes a header outside the public boundary.

Two trees are checked:

* ``app/src`` may include ISO C headers, the standard headers of the Crux Sockets
  profile, public ``<crux/NAME.h>`` headers, and headers of its own tree.
* ``workload/`` is portable code. It may include ISO C headers and headers of its
  own tree, and nothing else.

Anything else fails: Zephyr, vendor and POSIX headers outside the profile, nested
or unknown ``<crux/...>`` paths, and quoted headers that do not resolve inside the
checked tree (a Crux port header reached through a private include directory is
the case this catches). The check reads include lines only. It does not see
include paths added by CMake, so the build must not add any.
"""

import argparse
import dataclasses
import pathlib
import re
import sys

ISO_C = frozenset(
    "assert.h complex.h ctype.h errno.h fenv.h float.h inttypes.h iso646.h limits.h "
    "locale.h math.h setjmp.h signal.h stdalign.h stdarg.h stdatomic.h stdbool.h "
    "stddef.h stdint.h stdio.h stdlib.h stdnoreturn.h string.h tgmath.h threads.h "
    "time.h uchar.h wchar.h wctype.h".split()
)

# The headers that docs/networking-contract.md of crux-pilot lists for the profile,
# besides ISO C.
SOCKET_PROFILE = frozenset(
    "sys/socket.h netinet/in.h arpa/inet.h poll.h fcntl.h unistd.h errno.h time.h".split()
)

SOURCE_SUFFIXES = (".c", ".h", ".cc", ".cpp", ".hpp")
CRUX_PUBLIC = re.compile(r"^crux/[A-Za-z0-9_]+\.h$")
INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*(?:<([^>\n]+)>|"([^"\n]+)")', re.MULTILINE)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT = re.compile(r"//[^\n]*")


@dataclasses.dataclass(frozen=True)
class Rule:
    directory: str
    allow_sockets: bool
    allow_crux: bool


RULES = (
    Rule("app/src", allow_sockets=True, allow_crux=True),
    Rule("workload", allow_sockets=False, allow_crux=False),
)


@dataclasses.dataclass(frozen=True)
class Violation:
    path: str
    line: int
    include: str
    reason: str


def strip_comments(text):
    """Blank out comments and keep every newline, so line numbers stay true."""

    def blank(match):
        return re.sub(r"[^\n]", " ", match.group(0))

    return LINE_COMMENT.sub(blank, BLOCK_COMMENT.sub(blank, text))


def public_crux_headers(crux_root):
    names = {
        f"crux/{path.name}"
        for path in pathlib.Path(crux_root).glob("components/*/include/crux/*.h")
    }
    if not names:
        raise ValueError(f"no public Crux headers found under {crux_root}")
    return names


def resolves_locally(include, source, tree):
    for base in (source.parent, tree, tree / "include"):
        candidate = (base / include).resolve()
        try:
            candidate.relative_to(tree.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return True
    return False


def classify(include, angle, source, tree, rule, crux_headers):
    """Return a reason when the include is not allowed, otherwise None."""
    if not angle:
        if resolves_locally(include, source, tree):
            return None
        return "quoted header is not in this tree (private or port header?)"
    if include.startswith("zephyr/") or include == "zephyr.h":
        return "Zephyr header"
    if include in ISO_C:
        return None
    if include.startswith("crux/"):
        if not rule.allow_crux:
            return "Crux header in portable code"
        if not CRUX_PUBLIC.match(include):
            return "nested Crux path, not a public <crux/NAME.h> header"
        if crux_headers is not None and include not in crux_headers:
            return "not a public Crux header at the pinned revision"
        return None
    if include in SOCKET_PROFILE:
        if rule.allow_sockets:
            return None
        return "Sockets profile header in portable code"
    return "not an ISO C, Sockets profile or public Crux header"


def check(repo, crux_root=None):
    repo = pathlib.Path(repo)
    crux_headers = public_crux_headers(crux_root) if crux_root else None
    violations = []
    for rule in RULES:
        tree = repo / rule.directory
        if not tree.is_dir():
            continue
        for source in sorted(p for p in tree.rglob("*") if p.suffix in SOURCE_SUFFIXES):
            text = strip_comments(source.read_text(errors="replace"))
            for match in INCLUDE.finditer(text):
                angle, quoted = match.group(1), match.group(2)
                include = angle if angle is not None else quoted
                reason = classify(include, angle is not None, source, tree, rule, crux_headers)
                if reason:
                    violations.append(
                        Violation(
                            path=source.relative_to(repo).as_posix(),
                            line=text.count("\n", 0, match.start()) + 1,
                            include=include,
                            reason=reason,
                        )
                    )
    return violations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo", default=".", help="repository root (default: current directory)")
    parser.add_argument(
        "--crux-root",
        help="crux-pilot checkout; when given, <crux/NAME.h> must be one of its public headers",
    )
    args = parser.parse_args(argv)
    repo = pathlib.Path(args.repo)
    if not repo.is_dir():
        print(f"error: {repo} is not a directory", file=sys.stderr)
        return 2
    try:
        violations = check(repo, args.crux_root)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for v in violations:
        print(f"{v.path}:{v.line}: {v.include}: {v.reason}")
    if violations:
        print(f"{len(violations)} boundary violation(s)")
        return 1
    print("boundary check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
