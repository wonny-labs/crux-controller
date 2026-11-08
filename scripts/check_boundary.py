#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail when product source includes a header outside the public boundary.

Three trees are checked:

* ``app/src`` may include ISO C headers, the standard headers of the Crux Sockets
  profile, public ``<crux/NAME.h>`` headers, and headers of its own tree.
* ``workload/`` is portable code. It may include ISO C headers and headers of its
  own tree, and nothing else.
* ``app/compose/`` is the composition zone, the one place that mounts a file system and
  binds it to Crux. It may include ISO C headers, public ``<crux/NAME.h>`` headers, the
  composition interface ``<crux/file_zephyr.h>``, the explicit allow-list of Zephyr headers
  in ``COMPOSITION_ZEPHYR_HEADERS``, headers of its own tree and the headers of ``app/src``
  (header files only: the product-owned header that ``app/src`` declares and the zone
  implements). Such a header is scanned under the ``app/src`` rules, so a Sockets profile header
  or a ``workload`` header that it includes reaches the zone indirectly; the zone's own
  includes are what the rule restricts. It may not
  include the Sockets profile, a Crux private or port header, any other Zephyr header or a
  vendor or third-party header. ``app/src`` has no way into the zone: the composition
  interface and the allow-listed Zephyr headers fail there, and so does a quoted include of a
  zone header. See ``docs/composition-zone.md``.

Anything else fails: Zephyr, vendor and POSIX headers outside the profile, nested
or unknown ``<crux/...>`` paths, and quoted headers that do not resolve inside the
checked tree (a Crux port header reached through a private include directory is
the case this catches). The check reads every file under both trees, whatever its suffix, and every
``#include``, ``#include_next`` and ``#import`` directive, after joining lines that end in a
backslash (as C joins them, with nothing in between), reading CRLF line ends, the digraph
``%:`` and the trigraph ``??=`` as ``#``, and removing comments. An operand that is not a literal ``<name>`` or ``"name"``
(a macro, for example) fails, because it cannot be checked. The check does not see include
paths added by CMake, so the build must not add any; ``tests/tooling/test_boundary.py`` checks
``app/CMakeLists.txt`` for that.
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

# The composition zone's exact allow-list of Zephyr headers (docs/composition-zone.md justifies
# each one). There are no wildcards: a name is a header or it is not. Adding a name is a reviewed
# change of this file, of tests/tooling/test_boundary.py and of that document.
COMPOSITION_ZEPHYR_HEADERS = frozenset({"zephyr/fs/fs.h", "zephyr/devicetree.h"})

# The composition interfaces of Crux that the zone may include. A composition header is
# <crux/NAME.h> that names a provider; Crux publishes it under components/*/ports/*/include/crux,
# beside the public headers under components/*/include/crux. Any header of that kind is out of
# reach of app/src and of the workload, whether or not it is listed here.
COMPOSITION_CRUX_HEADERS = frozenset({"crux/file_zephyr.h"})

CRUX_PUBLIC = re.compile(r"^crux/[A-Za-z0-9_]+\.h$")
DIRECTIVE = re.compile(r"^[ \t\f\v]*#[ \t\f\v]*(include_next|include|import)\b(.*)$", re.DOTALL)
OPERAND = re.compile(r'^\s*(?:<([^>\n]+)>|"([^"\n]+)")')


@dataclasses.dataclass(frozen=True)
class Rule:
    directory: str
    allow_sockets: bool
    allow_crux: bool
    # Other trees of this repository whose headers a quoted include may name.
    extra_roots: tuple = ()
    # Zephyr headers this tree may include, by exact name. Empty: no Zephyr header.
    zephyr_allow: frozenset = frozenset()
    # Composition interfaces <crux/NAME.h> this tree may include, by exact name.
    composition_crux: frozenset = frozenset()
    # True: a quoted include may name only a header file (suffix .h) of an extra root.
    extra_roots_headers_only: bool = False


RULES = (
    # The application binds the workload, so its public headers are in reach.
    Rule("app/src", allow_sockets=True, allow_crux=True, extra_roots=("workload/include",)),
    Rule("workload", allow_sockets=False, allow_crux=False),
    # The composition zone. Its headers of its own tree are scanned like the rest. app/src
    # is an extra root so that the zone can implement the product-owned header that app/src
    # declares; that header is scanned under the rules of app/src, so it cannot carry a
    # Zephyr or composition include back into the application.
    Rule(
        "app/compose",
        allow_sockets=False,
        allow_crux=True,
        extra_roots=("app/src",),
        extra_roots_headers_only=True,
        zephyr_allow=COMPOSITION_ZEPHYR_HEADERS,
        composition_crux=COMPOSITION_CRUX_HEADERS,
    ),
)


@dataclasses.dataclass(frozen=True)
class Violation:
    path: str
    line: int
    include: str
    reason: str


def strip_comments(text):
    """Blank out comments, keep string and character literals, and keep every newline."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        pair = text[i : i + 2]
        if pair == "//":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
        elif pair == "/*":
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append("".join("\n" if ch == "\n" else " " for ch in text[i:end]))
            i = end
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def normalise(text):
    """Line ends as LF, and the digraph and trigraph for # as #, before any other reading."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("??=", "#").replace("%:", "#")


def logical_lines(text):
    """Yield (first line number, text) with backslash-continued lines joined, as C joins them."""
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        first = index
        joined = lines[index]
        while joined.endswith("\\") and index + 1 < len(lines):
            index += 1
            joined = joined[:-1] + lines[index]
        yield first + 1, joined
        index += 1


def public_crux_headers(crux_root):
    names = {
        f"crux/{path.name}"
        for path in pathlib.Path(crux_root).glob("components/*/include/crux/*.h")
    }
    if not names:
        raise ValueError(f"no public Crux headers found under {crux_root}")
    return names


def composition_crux_headers(crux_root):
    """The <crux/NAME.h> composition interfaces that Crux publishes at this revision."""
    return {
        f"crux/{path.name}"
        for path in pathlib.Path(crux_root).glob("components/*/ports/*/include/crux/*.h")
    }


def resolves_locally(include, source, tree, extra_roots, headers_only=False):
    """True when the quoted header is a file inside the tree, or inside an allowed extra root.

    With headers_only, an extra root counts only for a file whose suffix is .h.
    """
    pairs = [(source.parent, tree, False), (tree, tree, False), (tree / "include", tree, False)]
    pairs += [(root, root, headers_only) for root in extra_roots]
    for base, root, only_headers in pairs:
        candidate = (base / include).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            continue
        if candidate.is_file() and (not only_headers or candidate.suffix == ".h"):
            return True
    return False


def classify(include, angle, source, tree, extra_roots, rule, crux_headers, composition_headers=None):
    """Return a reason when the include is not allowed, otherwise None."""
    if not angle:
        if resolves_locally(include, source, tree, extra_roots, rule.extra_roots_headers_only):
            return None
        return "quoted header is not in this tree (private or port header?)"
    if include in rule.zephyr_allow:
        return None
    if include.startswith("zephyr/") or include == "zephyr.h":
        if rule.zephyr_allow:
            return "Zephyr header that is not on the composition allow-list"
        return "Zephyr header"
    if include in ISO_C:
        return None
    if include.startswith("crux/"):
        if not rule.allow_crux:
            return "Crux header in portable code"
        known_composition = COMPOSITION_CRUX_HEADERS | (composition_headers or set())
        if include in known_composition:
            if include not in rule.composition_crux:
                if rule.composition_crux:
                    return "composition interface that is not on the composition allow-list"
                return "composition interface, for the composition zone only"
            if composition_headers is not None and include not in composition_headers:
                return "not a composition interface that Crux publishes at the pinned revision"
            return None
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
    composition_headers = composition_crux_headers(crux_root) if crux_root else None
    violations = []
    for rule in RULES:
        tree = repo / rule.directory
        if not tree.is_dir():
            continue
        extra_roots = [repo / name for name in rule.extra_roots]
        for source in sorted(p for p in tree.rglob("*") if p.is_file()):
            relative = source.relative_to(repo).as_posix()
            text = strip_comments(normalise(source.read_bytes().decode("utf-8", errors="replace")))
            for line, logical in logical_lines(text):
                directive = DIRECTIVE.match(logical)
                if not directive:
                    continue
                operand = OPERAND.match(directive.group(2))
                if not operand:
                    violations.append(
                        Violation(
                            relative,
                            line,
                            directive.group(2).strip() or "(empty)",
                            "include operand is not a literal <name> or \"name\", so it cannot be checked",
                        )
                    )
                    continue
                angle = operand.group(1) is not None
                include = operand.group(1) if angle else operand.group(2)
                reason = classify(
                    include, angle, source, tree, extra_roots, rule, crux_headers, composition_headers
                )
                if reason:
                    violations.append(Violation(relative, line, include, reason))
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
