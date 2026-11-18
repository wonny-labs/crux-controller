# SPDX-License-Identifier: Apache-2.0
"""The product must not define identifiers in the namespaces that belong to Crux and to Kconfig.

The platform's product code standard keeps product identifiers out of the ``crux_`` and ``CRUX_``
namespace, which is the platform's. These tests scan the tracked C and header files of the product
(``app/`` and ``workload/``) for definitions of such identifiers: a function, variable, type, tag,
enumerator or macro that the file introduces. A call of a Crux function, the use of a Crux type and
the include of a Crux header are not definitions and are not reported.

The ``CONFIG_`` namespace is Kconfig's. Zephyr's tooling reports every ``CONFIG_`` identifier in
the source that no Kconfig file declares, so a header guard, macro or enumerator of the product
that starts with ``CONFIG_`` looks like an undefined Kconfig symbol. No tracked C or header file,
tests included, may define such an identifier. Using one, in ``#if``, ``#ifdef``, ``IS_ENABLED``
or ``BUILD_ASSERT``, is how Kconfig values reach the source and is fine.

Only files that git tracks are scanned (``git ls-files``). A new file counts once it is added.

The scan reads tokens, not lines. It removes comments and string literals, takes the preprocessor
lines apart, and then reads each statement of the remaining text. It does not parse C. It finds the
declaration forms that this repository uses, and the tests below pin the forms that it must find
and the forms that it must leave alone.

Known limits, not scheduled to be fixed:

* An object that a macro defines, such as ``K_THREAD_STACK_DEFINE(crux_stack, 512)``, is not a
  declaration to the scanner, so its name is not reported.
* A tag in ``typedef struct crux_tag {...} name;`` is not reported, and neither is a declaration
  that starts with ``__attribute__`` or anything inside a macro body.
* The scan does not follow ``#if`` branches: it reads all of them.
"""

import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]

CRUX_PREFIX = re.compile(r"^(?:crux_|CRUX_)")
CRUX_TREES = ("app", "workload")
CONFIG_PREFIX = re.compile(r"^CONFIG_")

TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9][A-Za-z0-9_.]*|\S")
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
DEFINE = re.compile(r"^\s*#\s*(?:define|undef)\s+([A-Za-z_][A-Za-z0-9_]*)")
# A statement that starts with one of these words is not a declaration.
NOT_A_DECLARATION = frozenset({
    "return", "else", "goto", "case", "do", "if", "while", "for", "switch", "break", "continue",
    "default", "sizeof",
})


def blank_comments_and_literals(text):
    """The text with comments and the content of string and character literals replaced by
    spaces. Line breaks stay, so a position keeps its line number."""
    out = []
    i = 0
    size = len(text)
    while i < size:
        two = text[i:i + 2]
        if two == "/*":
            end = text.find("*/", i + 2)
            end = size if end < 0 else end + 2
            out.append(re.sub(r"[^\n]", " ", text[i:end]))
            i = end
        elif two == "//":
            end = text.find("\n", i)
            end = size if end < 0 else end
            out.append(" " * (end - i))
            i = end
        elif text[i] in "\"'":
            quote = text[i]
            j = i + 1
            while j < size and text[j] != quote and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, size)
            out.append(quote + re.sub(r"[^\n]", " ", text[i + 1:j - 1]) + (quote if j - 1 > i else ""))
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def split_preprocessor(code):
    """The macro names that the preprocessor lines define or undefine, as (name, line) pairs, and
    the code without its preprocessor lines (continuation lines included)."""
    macros = []
    kept = []
    lines = code.split("\n")
    number = 0
    while number < len(lines):
        line = lines[number]
        if line.lstrip().startswith("#"):
            match = DEFINE.match(line)
            if match:
                macros.append((match.group(1), number + 1))
            while lines[number].rstrip().endswith("\\") and number + 1 < len(lines):
                kept.append("")
                number += 1
            kept.append("")
        else:
            kept.append(line)
        number += 1
    return macros, "\n".join(kept)


def tokenize(code):
    tokens = []
    for number, line in enumerate(code.split("\n"), 1):
        for match in TOKEN.finditer(line):
            tokens.append((match.group(0), number))
    return tokens


def is_identifier(token):
    return bool(IDENTIFIER.match(token))


def lead_name(tokens):
    """The identifier that a declaration declares: the last identifier of its leading run of
    identifiers and stars, when the run holds a type before it. A call, an assignment and a
    statement that starts with a keyword such as return declare nothing."""
    run = []
    for token, line in tokens:
        if is_identifier(token) or token == "*":
            run.append((token, line))
        else:
            break
    words = [(token, line) for token, line in run if token != "*"]
    if len(words) < 2 or words[0][0] in NOT_A_DECLARATION:
        return None
    return words[-1]


def split_top_level(tokens, separator):
    pieces = [[]]
    depth = 0
    for token, line in tokens:
        if token in "([{":
            depth += 1
        elif token in ")]}":
            depth -= 1
        if depth == 0 and token == separator:
            pieces.append([])
        else:
            pieces[-1].append((token, line))
    return pieces


def declared_names(statement):
    """The names that one statement or statement head declares, as (name, line) pairs."""
    if not statement:
        return []
    names = []
    if statement[0][0] == "typedef":
        # The name is the identifier inside "(*name)" of a function pointer type, or else the
        # last identifier outside every bracket.
        tokens = [token for token, _ in statement]
        for position in range(len(tokens) - 2):
            if tokens[position] == "(" and tokens[position + 1] == "*":
                return [statement[position + 2]]
        depth = 0
        top = []
        for token, line in statement:
            if token in "([{":
                depth += 1
            elif token in ")]}":
                depth -= 1
            elif depth == 0 and is_identifier(token):
                top.append((token, line))
        return top[-1:]
    pieces = split_top_level(statement, ",")
    first = lead_name(pieces[0])
    if first:
        names.append(first)
        # The parameters of a function declaration or definition.
        for index, (token, _) in enumerate(pieces[0]):
            if token == "(":
                inner = []
                depth = 0
                for t, n in pieces[0][index:]:
                    if t == "(":
                        depth += 1
                        if depth == 1:
                            continue
                    elif t == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    inner.append((t, n))
                for parameter in split_top_level(inner, ","):
                    name = lead_name(parameter)
                    if name:
                        names.append(name)
                break
        # More declarators after a comma: "int a = 1, crux_b = 2;"
        for piece in pieces[1:]:
            if piece and (is_identifier(piece[0][0]) or piece[0][0] == "*"):
                words = [(t, n) for t, n in piece if is_identifier(t)]
                if words and words[0][0] not in NOT_A_DECLARATION:
                    names.append(words[0])
    return names


def statement_definitions(tokens):
    """Every name that the statements of the token stream declare, enumerators and the names
    after a closing brace included."""
    names = []
    statement = []
    paren = 0
    index = 0
    while index < len(tokens):
        token, line = tokens[index]
        if token == "(":
            paren += 1
        elif token == ")":
            paren -= 1
        if paren > 0 or token not in ";{}":
            statement.append((token, line))
            index += 1
            continue
        if token == ";":
            names.extend(declared_names(statement))
            statement = []
        elif token == "{":
            words = [t for t, _ in statement]
            if "typedef" not in words:
                names.extend(declared_names(statement))
            # The head of "enum tag {" or "typedef enum {": the body holds enumerators.
            # The head of "struct tag {" or of a function: the body holds declarations and
            # statements, and is scanned as the statements that it is.
            end = index
            depth = 0
            for end in range(index, len(tokens)):
                if tokens[end][0] == "{":
                    depth += 1
                elif tokens[end][0] == "}":
                    depth -= 1
                    if depth == 0:
                        break
            if "enum" in words and "(" not in words:
                body = tokens[index + 1:end]
                for piece in split_top_level(body, ","):
                    if piece and is_identifier(piece[0][0]):
                        names.append(piece[0])
                index = end + 1
                names.extend(after_brace(tokens, index))
                index = skip_to_semicolon(tokens, index)
                statement = []
                continue
            if "typedef" in words or "struct" in words or "union" in words:
                if "(" not in words:
                    names.extend(statement_definitions(tokens[index + 1:end]))
                    index = end + 1
                    names.extend(after_brace(tokens, index))
                    index = skip_to_semicolon(tokens, index)
                    statement = []
                    continue
            statement = []
        else:
            statement = []
        index += 1
    names.extend(declared_names(statement))
    return names


def after_brace(tokens, index):
    """The declarators between a closing brace and its semicolon: "} crux_t, *crux_p;". An
    identifier is a declarator when it follows the brace, a comma or a star outside every bracket.
    An initialiser ("= {.level = CRUX_LOG_INFO}") and an array size ("[CRUX_COUNT]") are not."""
    names = []
    depth = 0
    previous = "}"
    while index < len(tokens) and not (tokens[index][0] == ";" and depth == 0):
        token, line = tokens[index]
        if token in "([{":
            depth += 1
        elif token in ")]}":
            depth -= 1
        elif depth == 0 and is_identifier(token) and previous in ("}", ",", "*"):
            names.append((token, line))
        previous = token
        index += 1
    return names


def skip_to_semicolon(tokens, index):
    while index < len(tokens) and tokens[index][0] != ";":
        index += 1
    return index + 1


def definitions(text):
    """Every identifier that the C text defines, as (name, line) pairs: macros, functions,
    variables, parameters, types, tags and enumerators."""
    macros, code = split_preprocessor(blank_comments_and_literals(text))
    return macros + statement_definitions(tokenize(code))


def tracked(root, trees, suffixes=(".c", ".h")):
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--", *trees],
        check=True, capture_output=True,
    )
    names = sorted(name.decode() for name in out.stdout.split(b"\0") if name)
    return [root / name for name in names
            if name.endswith(suffixes) and (root / name).is_file()]


def offenders(files, root, prefix):
    found = []
    for file in files:
        for name, line in definitions(file.read_text(errors="replace")):
            if prefix.match(name):
                found.append(f"{file.relative_to(root)}:{line}: defines {name}")
    return found


class Definitions(unittest.TestCase):
    """What the scanner reports for the declaration forms of this repository."""

    def names(self, text):
        return [name for name, _ in definitions(text)]

    def test_a_static_function_definition_is_found(self):
        self.assertIn("crux_level", self.names(
            "static crux_log_level_t crux_level(health_log_level_t level)\n{\n    return 1;\n}\n"))

    def test_a_prototype_and_a_pointer_return_are_found(self):
        self.assertIn("crux_make", self.names("struct item *crux_make(void);"))
        self.assertIn("crux_size", self.names("size_t crux_size(const char *text);"))

    def test_a_macro_definition_and_an_undefinition_are_found(self):
        self.assertEqual(["CRUX_LIMIT", "crux_twice", "CRUX_GONE"], self.names(
            "#define CRUX_LIMIT 4\n#define crux_twice(x) \\\n    ((x) * 2)\n#undef CRUX_GONE\n"))

    def test_enumerators_and_a_typedef_name_are_found(self):
        names = self.names("typedef enum {\n    CRUX_A = 0,\n    CRUX_B = -1, /* note */\n} crux_kind_t;\n")
        self.assertEqual(["CRUX_A", "CRUX_B", "crux_kind_t"], names)

    def test_a_tag_a_variable_a_member_and_a_parameter_are_found(self):
        self.assertIn("crux_tag", self.names("enum crux_tag { ONE };"))
        self.assertIn("crux_state", self.names("static int crux_state = 3;"))
        self.assertIn("crux_member", self.names("struct s {\n    int crux_member;\n};\n"))
        self.assertIn("crux_arg", self.names("static void use(int crux_arg) {}"))
        self.assertIn("crux_second", self.names("static int first = 1, crux_second = 2;"))

    def test_an_initialiser_after_a_closing_brace_is_not_a_declarator(self):
        names = self.names("static struct {\n    int level;\n} state = {.level = CRUX_LOG_INFO};\n")
        self.assertEqual([], [n for n in names if CRUX_PREFIX.match(n)])
        self.assertIn("state", names)
        names = self.names("enum { ONE } value = CRUX_ONE;\nstruct { int a; } list[CRUX_COUNT], crux_second;\n")
        self.assertEqual(["crux_second"], [n for n in names if CRUX_PREFIX.match(n)])

    def test_a_function_pointer_typedef_is_found(self):
        self.assertEqual(["crux_handler_t"], self.names("typedef void (*crux_handler_t)(int);"))

    def test_a_definition_inside_a_function_body_is_found(self):
        self.assertIn("crux_local", self.names("void f(void)\n{\n    int crux_local = 0;\n    (void)crux_local;\n}\n"))

    def test_calls_and_uses_are_not_definitions(self):
        text = (
            '#include <crux/file.h>\n'
            '#include "crux_private.h"\n'
            "static void f(crux_log_level_t level, const crux_file_t *file)\n"
            "{\n"
            "    int result = crux_file_open(NAME, CRUX_FILE_READ, &file);\n"
            "    (void)crux_log_write(level, TAG, \"crux_text\");\n"
            "    if (crux_web_session_start_worker() != CRUX_WEB_OK) {\n"
            "        return crux_value(CRUX_X);\n"
            "    }\n"
            "    else crux_other();\n"
            "    crux_file_close(&file);\n"
            "    x = a * crux_b;\n"
            "    switch (result) { case CRUX_FILE_ERR_IO: break; default: break; }\n"
            "}\n"
            "#if defined(CONFIG_CRUX_WEB_MANAGEMENT) && IS_ENABLED(CONFIG_CRUX_TIME)\n"
            "#endif\n"
            "/* crux_comment() and CRUX_COMMENT are not code */\n"
            "// crux_line_comment() neither\n"
        )
        self.assertEqual([], [n for n in self.names(text) if CRUX_PREFIX.match(n)])

    def test_an_identifier_that_merely_contains_crux_is_not_in_the_namespace(self):
        self.assertEqual([], [n for n in self.names("static int my_crux_level(void);\n#define XCRUX_A 1\n")
                              if CRUX_PREFIX.match(n)])


class TrackedFiles(unittest.TestCase):
    def test_only_files_that_git_tracks_are_listed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            (root / "a.c").write_text("int a;\n")
            (root / "b.c").write_text("int b;\n")
            subprocess.run(["git", "-C", str(root), "add", "a.c"], check=True)
            self.assertEqual([root / "a.c"], tracked(root, (".",)))


class ProductTree(unittest.TestCase):
    def test_the_scan_covers_the_product_sources(self):
        files = [str(f.relative_to(ROOT)) for f in tracked(ROOT, CRUX_TREES)]
        self.assertIn("app/src/health.c", files)
        self.assertIn("app/src/time_sync.c", files)
        self.assertIn("workload/include/workload.h", files)

    def test_the_product_defines_nothing_in_the_crux_namespace(self):
        self.assertEqual([], offenders(tracked(ROOT, CRUX_TREES), ROOT, CRUX_PREFIX))

    def test_a_crux_definition_in_a_copy_of_a_product_file_is_found(self):
        original = (ROOT / "app/src/health.c").read_text()
        mutated = original + "\nstatic crux_log_level_t crux_added(health_log_level_t level)\n{\n    return 0;\n}\n"
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / "app/src/health.c"
            path.parent.mkdir(parents=True)
            path.write_text(mutated)
            found = offenders([path], root, CRUX_PREFIX)
        self.assertIn("app/src/health.c:%d: defines crux_added" % (original.count("\n") + 2), found)


class ConfigDefinitions(unittest.TestCase):
    """The CONFIG_ rule: definitions are reported, uses of Kconfig symbols are not."""

    def found(self, text):
        return [name for name, _ in definitions(text) if CONFIG_PREFIX.match(name)]

    def test_an_include_guard_is_a_definition(self):
        self.assertEqual(["CONFIG_STORE_H"], self.found("#ifndef CONFIG_STORE_H\n#define CONFIG_STORE_H\n#endif\n"))

    def test_a_macro_an_enumerator_and_a_typedef_name_are_definitions(self):
        text = (
            '#define CONFIG_STORE_FILE_NAME "config.rec"\n'
            "typedef enum {\n    CONFIG_STORE_OK = 0,\n    CONFIG_STORE_ERR = -1, /* note */\n} config_store_status_t;\n"
            "typedef int CONFIG_handle_t;\n"
            "static int CONFIG_counter;\n"
        )
        self.assertEqual(["CONFIG_STORE_FILE_NAME", "CONFIG_STORE_OK", "CONFIG_STORE_ERR",
                          "CONFIG_handle_t", "CONFIG_counter"], self.found(text))

    def test_the_use_of_kconfig_symbols_is_not_a_definition(self):
        text = (
            "#if defined(CONFIG_CRUX_WEB_MANAGEMENT) && CONFIG_NET_MAX_CONN > 2\n"
            "#endif\n"
            "#ifdef CONFIG_FILE_SYSTEM_MKFS\n"
            "#endif\n"
            "#ifndef CONFIG_SNTP\n"
            "#endif\n"
            'BUILD_ASSERT(CONFIG_NUM_PREEMPT_PRIORITIES > 6, "needs CONFIG_NUM_PREEMPT_PRIORITIES");\n'
            "BUILD_ASSERT(IS_ENABLED(CONFIG_TIMEOUT_64BIT), \"x\");\n"
            "_Static_assert(sizeof(CONFIG_CRUX_WEB_BIND_ADDRESS) > 1u, \"set it\");\n"
            "static void f(void)\n{\n"
            "    int result = tls_credential_add(CONFIG_CRUX_WEB_TLS_SEC_TAG, 1);\n"
            "    (void)result;\n"
            '    snprintf(text, sizeof text, "%s:%d", CONFIG_CRUX_WEB_BIND_ADDRESS, CONFIG_CRUX_WEB_PORT);\n'
            "}\n"
            "/* CONFIG_IN_A_COMMENT and #define CONFIG_NOT_CODE */\n"
        )
        self.assertEqual([], self.found(text))

    def test_a_neutral_prefix_is_not_a_definition_in_the_namespace(self):
        self.assertEqual([], self.found("#define CFGSTORE_OK 0\n#define MY_CONFIG_X 1\n#define CONFIGURED 1\n"))


class ConfigNamespace(unittest.TestCase):
    def test_the_scan_covers_headers_sources_and_tests(self):
        files = [str(f.relative_to(ROOT)) for f in tracked(ROOT, (".",))]
        for expected in ("app/src/config_store.h", "app/src/config_store.c",
                         "tests/host/test_net_client.c", "tests/native_sim/s3/src/test_s3.c"):
            self.assertIn(expected, files)

    def test_no_tracked_c_or_header_file_defines_a_config_identifier(self):
        self.assertEqual([], offenders(tracked(ROOT, (".",)), ROOT, CONFIG_PREFIX))

    def test_a_config_definition_in_a_copy_of_a_header_is_found(self):
        original = (ROOT / "app/src/net_client.h").read_text()
        mutated = original.replace("#define NET_CLIENT_H", "#define CONFIG_NET_CLIENT_H").replace(
            "#ifndef NET_CLIENT_H", "#ifndef CONFIG_NET_CLIENT_H")
        self.assertNotEqual(original, mutated)
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / "app/src/net_client.h"
            path.parent.mkdir(parents=True)
            path.write_text(mutated)
            found = offenders([path], root, CONFIG_PREFIX)
        self.assertEqual(["app/src/net_client.h:3: defines CONFIG_NET_CLIENT_H"], found)


if __name__ == "__main__":
    unittest.main()
