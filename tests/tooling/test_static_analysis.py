"""Checks of the format and static-analysis setup: the criteria files, the two scripts and the CI
job that runs them. The criteria are the ones that the Crux repository applies to its own code."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read(name):
    return (ROOT / name).read_text()


def mapping(name):
    """Top-level `key: value` pairs of a flat YAML file such as .clang-format."""
    pairs = {}
    for line in read(name).splitlines():
        match = re.match(r"^([A-Za-z]+):\s*(.*?)\s*$", line)
        if match and not line.startswith("#"):
            pairs[match.group(1)] = match.group(2)
    return pairs


class FormatCriteria(unittest.TestCase):
    def test_the_format_style_is_the_crux_style(self):
        self.assertEqual(
            {
                "BasedOnStyle": "LLVM",
                "BreakBeforeBraces": "Linux",
                "IndentWidth": "4",
                "ColumnLimit": "100",
                "SortIncludes": "CaseSensitive",
                "AllowShortFunctionsOnASingleLine": "None",
                "AllowShortBlocksOnASingleLine": "Never",
                "IndentExternBlock": "NoIndent",
            },
            mapping(".clang-format"),
        )


class TidyCriteria(unittest.TestCase):
    def setUp(self):
        self.text = read(".clang-tidy")

    def checks(self):
        block = re.search(r"^Checks:\s*>-\n((?:  .*\n)+)", self.text, re.MULTILINE)
        self.assertIsNotNone(block, "no Checks block")
        return [item.strip() for item in block.group(1).replace("\n", " ").split(",") if item.strip()]

    def test_the_checks_are_the_crux_checks(self):
        self.assertEqual(
            [
                "-*",
                "bugprone-*",
                "clang-analyzer-*",
                "-clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling",
                "performance-*",
                "-performance-enum-size",
                "portability-*",
                "readability-identifier-naming",
            ],
            self.checks(),
        )

    def test_every_finding_is_an_error(self):
        self.assertRegex(self.text, r"(?m)^WarningsAsErrors: '\*'$")

    def test_the_format_style_is_read_from_the_format_file(self):
        self.assertRegex(self.text, r"(?m)^FormatStyle: file$")

    def test_the_header_filter_covers_only_the_directories_of_this_repository(self):
        match = re.search(r"(?m)^HeaderFilterRegex: '(.*)'$", self.text)
        self.assertIsNotNone(match, "no HeaderFilterRegex")
        pattern = re.compile(match.group(1))
        for path in ("/w/repo/workload/include/workload.h", "/w/repo/app/src/net_client.h",
                     "/w/repo/tests/host/test_workload.c"):
            self.assertTrue(pattern.fullmatch(path), path)
        for path in ("/w/crux/components/time/include/crux/time.h",
                     "/w/zephyr/include/zephyr/kernel.h", "/usr/include/stdio.h"):
            self.assertFalse(pattern.fullmatch(path), path)

    def test_the_header_filter_says_why_it_is_narrow(self):
        lines = self.text.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("HeaderFilterRegex"))
        self.assertTrue(lines[index - 1].startswith("#"), "no comment above HeaderFilterRegex")


if __name__ == "__main__":
    unittest.main()
