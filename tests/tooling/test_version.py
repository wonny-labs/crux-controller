# SPDX-License-Identifier: Apache-2.0
"""Tests of the framework version: <controller/version.h>, the one place the number is kept.

The header follows Crux's <crux/version.h> (Crux ADR-0008): Semantic Versioning 2.0.0, and on
main the next planned release with the pre-release identifier "dev". It is the version of the
framework, not of an image: an image's Zephyr VERSION file is separate. The compile case skips
when no C compiler is found.
"""

import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
INCLUDE = ROOT / "include"
HEADER = INCLUDE / "controller" / "version.h"
PARTS = ("MAJOR", "MINOR", "PATCH", "PRERELEASE", "STRING")
PRERELEASE = re.compile(r"(|dev|rc\.(0|[1-9][0-9]*))")


def macros():
    """The CONTROLLER_VERSION_* macros of the header, name to value text."""
    found = {}
    for name, value in re.findall(
        r"(?m)^#define\s+(CONTROLLER_VERSION_\w+)\s+(.+?)\s*$", HEADER.read_text()
    ):
        found[name] = value
    return found


def parts():
    values = macros()
    numbers = [int(values[f"CONTROLLER_VERSION_{part}"]) for part in ("MAJOR", "MINOR", "PATCH")]
    prerelease = re.fullmatch(r'"([^"]*)"', values["CONTROLLER_VERSION_PRERELEASE"]).group(1)
    return numbers, prerelease


def expected_string():
    numbers, prerelease = parts()
    text = ".".join(str(number) for number in numbers)
    return f"{text}-{prerelease}" if prerelease else text


def compiler():
    for name in ("cc", "gcc", "clang"):
        path = shutil.which(name)
        if path:
            return path
    return None


class VersionHeaderTest(unittest.TestCase):
    def test_header_defines_each_part_once(self):
        text = HEADER.read_text()
        for name in PARTS:
            with self.subTest(name=name):
                self.assertEqual(
                    1, len(re.findall(rf"(?m)^#define\s+CONTROLLER_VERSION_{name}\s", text))
                )

    def test_numeric_parts_are_decimal_integers(self):
        values = macros()
        for part in ("MAJOR", "MINOR", "PATCH"):
            with self.subTest(part=part):
                self.assertRegex(values[f"CONTROLLER_VERSION_{part}"], r"^(0|[1-9][0-9]*)$")

    def test_prerelease_is_empty_dev_or_a_release_candidate(self):
        self.assertRegex(parts()[1], PRERELEASE)

    def test_string_equals_the_parts(self):
        self.assertEqual(f'"{expected_string()}"', macros()["CONTROLLER_VERSION_STRING"])

    def test_main_carries_the_approved_development_version(self):
        # No release and no tag exist, so main names the next planned release with "dev".
        self.assertEqual("0.1.0-dev", expected_string())

    def test_no_version_number_macro_before_1_0(self):
        # Before 1.0 the numbers name the target release, so a number cannot tell a snapshot of
        # main from the release. As in Crux, version-number feature checks are not supported.
        self.assertNotIn("CONTROLLER_VERSION_NUMBER", HEADER.read_text())

    @unittest.skipUnless(compiler(), "no C compiler")
    def test_header_compiles_alone_and_gives_the_string(self):
        probe = (
            "#include <controller/version.h>\n"
            "#include <stdio.h>\n"
            "_Static_assert(CONTROLLER_VERSION_MAJOR >= 0 && CONTROLLER_VERSION_MINOR >= 0 &&\n"
            "               CONTROLLER_VERSION_PATCH >= 0, \"numeric parts\");\n"
            "int main(void)\n{\n"
            "    printf(\"%d.%d.%d|%s|%s\\n\", CONTROLLER_VERSION_MAJOR, CONTROLLER_VERSION_MINOR,\n"
            "           CONTROLLER_VERSION_PATCH, CONTROLLER_VERSION_PRERELEASE,\n"
            "           CONTROLLER_VERSION_STRING);\n"
            "    return 0;\n}\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            source = pathlib.Path(temporary) / "probe.c"
            program = pathlib.Path(temporary) / "probe"
            source.write_text(probe)
            subprocess.run(
                [compiler(), "-std=c17", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                 "-I", str(INCLUDE), str(source), "-o", str(program)],
                check=True,
            )
            output = subprocess.run(
                [str(program)], check=True, capture_output=True, text=True
            ).stdout
        numbers, prerelease = parts()
        self.assertEqual(
            f"{'.'.join(map(str, numbers))}|{prerelease}|{expected_string()}", output.strip()
        )


if __name__ == "__main__":
    unittest.main()
