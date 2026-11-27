#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail when product source includes a header outside the public boundary.

Eight trees are checked: the four trees of the configurations built on the workload, and the
four trees of the controller framework module and its interface header.

* ``app/src`` may include ISO C headers, the standard headers of the Crux Sockets
  profile, public ``<crux/NAME.h>`` headers, and headers of its own tree.
* ``workload/`` is portable code. It may include ISO C headers and headers of its
  own tree, and nothing else.
* ``app/compose/`` is the composition zone of the configurations of ``app/``, which mounts a file
  system and binds it to Crux. It holds no source; ``framework/compose`` has the same rule and holds the sources. It may include ISO C headers, public ``<crux/NAME.h>`` headers, the
  composition interfaces ``<crux/file_zephyr.h>``, ``<crux/web_zephyr.h>`` and ``<crux/cli_zephyr.h>`` (``COMPOSITION_CRUX_HEADERS``),
  the explicit allow-list of Zephyr headers in ``COMPOSITION_ZEPHYR_HEADERS``, headers of its own tree and the headers of ``app/src``
  (header files only: the product-owned header that ``app/src`` declares and the zone
  implements). Such a header is scanned under the ``app/src`` rules, so a Sockets profile header
  or a ``workload`` header that it includes reaches the zone indirectly; the zone's own
  includes are what the rule restricts. It may not
  include the Sockets profile, a Crux private or port header, any other Zephyr header or a
  vendor or third-party header. ``app/src`` has no way into the zone: the composition
  interfaces and the allow-listed Zephyr headers fail there, and so does a quoted include of a
  zone header. See ``docs/composition-zone.md``.
* ``app/os/`` is the adapter zone, where OS facilities (threads, queues, sleeping) use Zephyr
  directly. It may include ISO C headers, public ``<crux/NAME.h>`` headers, headers of its own
  tree, the headers of ``app/src`` (header files only: the product-owned port that ``app/src``
  declares and the zone implements) and exactly two Zephyr headers, ``zephyr/kernel.h`` and
  ``zephyr/net/sntp.h`` (``OS_ADAPTER_ZEPHYR_HEADERS``). The SNTP header is allowed for the
  library's string-based query, so the zone includes no socket header itself. It may not
  include the Sockets profile or other POSIX headers, the composition interface
  ``<crux/file_zephyr.h>`` or any other composition interface, any other Zephyr header (the
  Zephyr socket headers included), or a vendor or third-party header. ``app/src``, ``app/compose``
  and ``workload`` keep failing on both Zephyr headers, and a quoted include of an adapter header
  fails in all three. The composition zone's list gains neither header. See
  ``docs/composition-zone.md``.

* ``include/`` holds the interface header of the framework, ``<controller/NAME.h>``, that a
  product includes. It may include ISO C headers, public ``<crux/NAME.h>`` headers and the
  interface headers of its own tree.
* ``framework/src`` is the portable core of the framework. It has the rules of ``app/src``
  without the Sockets profile and without the workload: ISO C headers, public ``<crux/NAME.h>``
  headers, the interface headers and headers of its own tree, and no Zephyr header.
* ``framework/compose`` and ``framework/os`` are the composition and adapter zones of the module.
  They have the allow-lists of ``app/compose`` and ``app/os`` and reach the core through its header
  files only. Neither reaches ``app/src``, the workload or the other zone.

``app/src`` may include the interface headers and the headers of ``framework/src``, because
the configurations built on the workload compose the framework services that moved into the
module. The other trees of ``app`` and the workload may include neither.

A C or C++ source or header file under ``app``, ``framework``, ``include`` or ``zephyr`` that no rule covers
fails, so a source of the module cannot escape the check by its place (``MODULE_TREES``).

``app/src`` and ``app/os`` also fail on the three frozen Crux headers, ``crux/thread.h``,
``crux/sync.h`` and ``crux/serial.h`` (``FROZEN_CRUX_HEADERS``), although they are public headers.
The product uses Zephyr directly for threads and queues, in ``app/os`` behind a port header of
``app/src``, so the check keeps a later change from bringing the Crux contracts back. The rule is a
field of the tree's ``Rule`` and does not apply to ``workload`` (which has no Crux header at all) or
to ``app/compose``; the trees of the module carry it except the composition zone. Crux no longer publishes ``crux/queue.h``, so it is not on the list: with
``--crux-root`` it fails in every tree as a name that is not a public Crux header.

Anything else fails: Zephyr, vendor and POSIX headers outside the profile, nested
or unknown ``<crux/...>`` paths, and quoted headers that do not resolve inside the
checked tree (a Crux port header reached through a private include directory is
the case this catches). The check reads every file under each tree, whatever its suffix, and every
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
COMPOSITION_ZEPHYR_HEADERS = frozenset(
    {"zephyr/fs/fs.h", "zephyr/devicetree.h", "zephyr/net/tls_credentials.h"}
)

# The adapter zone's exact allow-list of Zephyr headers (docs/composition-zone.md justifies it).
# There are no wildcards: a name is a header or it is not. Adding a name is a reviewed change of
# this file, of tests/tooling/test_boundary.py and of that document.
OS_ADAPTER_ZEPHYR_HEADERS = frozenset({"zephyr/kernel.h", "zephyr/net/sntp.h"})

# The public Crux headers that the product no longer uses. Threads and queues come from Zephyr
# directly, in app/os behind a port header of app/src (ADR-0002 of crux-pilot), so app/src and
# app/os fail on these headers and the migration cannot be undone silently. Crux removed
# crux/queue.h, so it is not listed: --crux-root refuses it as a name that Crux does not publish.
# Adding or removing a name is a reviewed change of this file and of tests/tooling/test_boundary.py.
FROZEN_CRUX_HEADERS = frozenset({"crux/thread.h", "crux/sync.h", "crux/serial.h"})

# The composition interfaces of Crux that the zone may include. A composition header is
# <crux/NAME.h> that names a provider; Crux publishes it under components/*/ports/*/include/crux,
# beside the public headers under components/*/include/crux. Any header of that kind is out of
# reach of app/src and of the workload, whether or not it is listed here. A name listed here is
# denied outside the zone by name even without --crux-root, when the check cannot see which
# headers Crux publishes as composition interfaces: file_zephyr.h binds the File root,
# web_zephyr.h binds the Web server for the HTTPS management composition, and cli_zephyr.h starts
# the serial console with its first-account setup on the UART of the alias crux-serial0.
COMPOSITION_CRUX_HEADERS = frozenset(
    {"crux/file_zephyr.h", "crux/web_zephyr.h", "crux/cli_zephyr.h"}
)

CRUX_PUBLIC = re.compile(r"^crux/[A-Za-z0-9_]+\.h$")

# The interface headers of the framework: <controller/NAME.h>, one level, each a file of
# include/controller in this repository. A rule names whether its tree may include them.
FRAMEWORK_API_ROOT = "include"
FRAMEWORK_API = re.compile(r"^controller/[A-Za-z0-9_]+\.h$")

# The top-level trees whose C and C++ sources and headers must each sit in a checked tree. A
# source of the module, the base image or the configurations of app that no rule covers fails.
MODULE_TREES = ("app", "framework", FRAMEWORK_API_ROOT, "zephyr")
SOURCE_SUFFIXES = frozenset(
    ".c .h .inc .cc .cpp .cxx .hh .hpp .hxx .s .S".split()
)
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
    # Public <crux/NAME.h> headers this tree may not include, by exact name.
    deny_crux: frozenset = frozenset()
    # True: the tree may include the interface headers of the framework, <controller/NAME.h>.
    framework_api: bool = False


RULES = (
    # The application binds the workload, so its public headers are in reach. It also binds the
    # framework services that its configurations compose, through the header files of the core
    # and the interface header of the framework.
    Rule(
        "app/src",
        allow_sockets=True,
        allow_crux=True,
        extra_roots=("workload/include", "framework/src"),
        deny_crux=FROZEN_CRUX_HEADERS,
        framework_api=True,
    ),
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
    # The adapter zone. Threads, queues and sleeping use Zephyr directly here, while product
    # behaviour stays plain C in app/src. app/src is an extra root, headers only, so that the zone
    # can implement the product-owned port that app/src declares; that header is scanned under the
    # rules of app/src, so it cannot carry a Zephyr include back into the application. No
    # composition interface and no Sockets profile.
    Rule(
        "app/os",
        allow_sockets=False,
        allow_crux=True,
        extra_roots=("app/src",),
        extra_roots_headers_only=True,
        zephyr_allow=OS_ADAPTER_ZEPHYR_HEADERS,
        deny_crux=FROZEN_CRUX_HEADERS,
    ),
    # The interface header of the framework, which a product includes: ISO C and public Crux
    # headers, and no Zephyr, Sockets profile or framework source header.
    Rule(
        FRAMEWORK_API_ROOT,
        allow_sockets=False,
        allow_crux=True,
        deny_crux=FROZEN_CRUX_HEADERS,
        framework_api=True,
    ),
    # The portable core of the framework: the rules of app/src without the Sockets profile and
    # without the workload. It implements the interface header.
    Rule(
        "framework/src",
        allow_sockets=False,
        allow_crux=True,
        deny_crux=FROZEN_CRUX_HEADERS,
        framework_api=True,
    ),
    # The composition zone of the module: the allow-lists of app/compose, and the header files of
    # the core in place of those of app/src.
    Rule(
        "framework/compose",
        allow_sockets=False,
        allow_crux=True,
        extra_roots=("framework/src",),
        extra_roots_headers_only=True,
        zephyr_allow=COMPOSITION_ZEPHYR_HEADERS,
        composition_crux=COMPOSITION_CRUX_HEADERS,
    ),
    # The adapter zone of the module: the allow-list of app/os, and the header files of the core
    # in place of those of app/src.
    Rule(
        "framework/os",
        allow_sockets=False,
        allow_crux=True,
        extra_roots=("framework/src",),
        extra_roots_headers_only=True,
        zephyr_allow=OS_ADAPTER_ZEPHYR_HEADERS,
        deny_crux=FROZEN_CRUX_HEADERS,
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


def classify(
    include, angle, source, tree, extra_roots, rule, crux_headers, composition_headers=None, repo=None
):
    """Return a reason when the include is not allowed, otherwise None."""
    if not angle:
        if resolves_locally(include, source, tree, extra_roots, rule.extra_roots_headers_only):
            return None
        return "quoted header is not in this tree (private or port header?)"
    if include in rule.zephyr_allow:
        return None
    if include.startswith("zephyr/") or include == "zephyr.h":
        if rule.zephyr_allow:
            return "Zephyr header that is not on this zone's allow-list"
        return "Zephyr header"
    if include in ISO_C:
        return None
    if include.startswith("controller/"):
        if not rule.framework_api:
            return "framework interface header, outside the trees that may include it"
        if not FRAMEWORK_API.match(include):
            return "nested framework path, not an interface header <controller/NAME.h>"
        root = pathlib.Path(repo) if repo is not None else tree.parent
        if not (root / FRAMEWORK_API_ROOT / include).is_file():
            return "not an interface header of include/controller"
        return None
    if include.startswith("crux/"):
        if not rule.allow_crux:
            return "Crux header in portable code"
        if include in rule.deny_crux:
            return (
                "frozen Crux header (Thread, Sync and Serial are not used by the product): "
                "use Zephyr directly in app/os behind a port header of app/src"
            )
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
    if not any((repo / rule.directory).is_dir() for rule in RULES):
        raise ValueError(
            f"no checked tree under {repo.resolve()}; run from the repository root or pass --repo"
        )
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
                    include, angle, source, tree, extra_roots, rule, crux_headers,
                    composition_headers, repo,
                )
                if reason:
                    violations.append(Violation(relative, line, include, reason))
    violations.extend(uncovered_sources(repo))
    return violations


def uncovered_sources(repo):
    """A violation for each C or C++ source or header of MODULE_TREES that no rule covers."""
    checked = [repo / rule.directory for rule in RULES]
    found = []
    for name in MODULE_TREES:
        top = repo / name
        if not top.is_dir():
            continue
        for path in sorted(p for p in top.rglob("*") if p.is_file()):
            if path.suffix not in SOURCE_SUFFIXES:
                continue
            if any(path.is_relative_to(tree) for tree in checked):
                continue
            found.append(
                Violation(
                    path.relative_to(repo).as_posix(),
                    1,
                    "(source file)",
                    "source of the module in no checked tree: no rule covers it",
                )
            )
    return found


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
