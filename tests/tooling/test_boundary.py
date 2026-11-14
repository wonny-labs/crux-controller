"""Tests of scripts/check_boundary.py."""

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_boundary  # noqa: E402


class Repo:
    """A throwaway repository layout with files written from a dict."""

    def __init__(self, files):
        self._dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._dir.name)
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def close(self):
        self._dir.cleanup()


def run(files, crux_root=None):
    repo = Repo(files)
    try:
        return check_boundary.check(repo.root, crux_root)
    finally:
        repo.close()


def reasons(violations):
    return [v.include for v in violations]


class AppRules(unittest.TestCase):
    def test_clean_application_passes(self):
        files = {"app/src/main.c": "#include <crux/time.h>\n#include <stdint.h>\n"}
        self.assertEqual([], run(files))

    def test_zephyr_header_fails(self):
        files = {"app/src/main.c": "#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_zephyr_printk_header_fails(self):
        files = {"app/src/main.c": "#include <zephyr/sys/printk.h>\n"}
        self.assertEqual(["zephyr/sys/printk.h"], reasons(run(files)))

    def test_vendor_header_fails(self):
        files = {"app/src/main.c": "#include <fsl_enet.h>\n"}
        self.assertEqual(["fsl_enet.h"], reasons(run(files)))

    def test_crux_port_header_fails(self):
        # The file binding lives in a port header that no <crux/...> header
        # declares. A product reaches it only by a private include path.
        files = {"app/src/main.c": '#include "file_native.h"\n'}
        self.assertEqual(["file_native.h"], reasons(run(files)))

    def test_nested_crux_path_fails(self):
        files = {"app/src/main.c": "#include <crux/ports/zephyr/file_native.h>\n"}
        self.assertEqual(["crux/ports/zephyr/file_native.h"], reasons(run(files)))

    def test_socket_profile_headers_pass_in_the_application(self):
        names = [
            "sys/socket.h", "netinet/in.h", "arpa/inet.h", "poll.h",
            "fcntl.h", "unistd.h", "errno.h", "time.h",
        ]
        text = "".join(f"#include <{n}>\n" for n in names)
        self.assertEqual([], run({"app/src/net.c": text}))

    def test_other_posix_header_fails_in_the_application(self):
        files = {"app/src/main.c": "#include <pthread.h>\n"}
        self.assertEqual(["pthread.h"], reasons(run(files)))

    def test_local_quoted_header_passes(self):
        files = {
            "app/src/main.c": '#include "adapter.h"\n',
            "app/src/adapter.h": "#include <stdint.h>\n",
        }
        self.assertEqual([], run(files))

    def test_local_header_in_a_subdirectory_resolves(self):
        files = {
            "app/src/main.c": '#include "net/client.h"\n',
            "app/src/net/client.h": "",
        }
        self.assertEqual([], run(files))

    def test_commented_include_is_ignored(self):
        text = '/* #include <zephyr/kernel.h> */\n// #include <fsl_enet.h>\n'
        self.assertEqual([], run({"app/src/main.c": text}))

    def test_spaced_include_forms_are_found(self):
        files = {"app/src/main.c": "  #  include   <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_violation_names_file_and_line(self):
        files = {"app/src/main.c": "#include <stdint.h>\n#include <zephyr/kernel.h>\n"}
        (violation,) = run(files)
        self.assertEqual("app/src/main.c", violation.path)
        self.assertEqual(2, violation.line)

    def test_header_files_are_scanned_too(self):
        files = {"app/src/adapter.h": "#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))


class WorkloadRules(unittest.TestCase):
    def test_iso_c_only_passes(self):
        files = {"workload/cycle.c": "#include <stdint.h>\n#include <string.h>\n"}
        self.assertEqual([], run(files))

    def test_crux_header_fails_in_the_workload(self):
        files = {"workload/cycle.c": "#include <crux/time.h>\n"}
        self.assertEqual(["crux/time.h"], reasons(run(files)))

    def test_socket_header_fails_in_the_workload(self):
        files = {"workload/cycle.c": "#include <sys/socket.h>\n"}
        self.assertEqual(["sys/socket.h"], reasons(run(files)))

    def test_zephyr_header_fails_in_the_workload(self):
        files = {"workload/cycle.c": "#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_local_header_passes_in_the_workload(self):
        files = {
            "workload/cycle.c": '#include "workload/cycle.h"\n',
            "workload/include/workload/cycle.h": "",
        }
        self.assertEqual([], run(files))


class CruxPublicHeaders(unittest.TestCase):
    def crux_root(self, names):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = pathlib.Path(directory.name)
        for name in names:
            path = root / "components" / "x" / "include" / "crux" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        return root

    def test_known_public_header_passes(self):
        root = self.crux_root(["time.h"])
        files = {"app/src/main.c": "#include <crux/time.h>\n"}
        self.assertEqual([], run(files, crux_root=root))

    def test_unknown_crux_header_fails_when_the_public_set_is_known(self):
        root = self.crux_root(["time.h"])
        files = {"app/src/main.c": "#include <crux/secret.h>\n"}
        self.assertEqual(["crux/secret.h"], reasons(run(files, crux_root=root)))


class Scope(unittest.TestCase):
    def test_missing_directories_are_skipped(self):
        self.assertEqual([], run({"README.md": ""}))

    def test_files_outside_the_scanned_directories_are_not_checked(self):
        files = {"tests/host/test.c": "#include <zephyr/kernel.h>\n"}
        self.assertEqual([], run(files))


class Reviewed(unittest.TestCase):
    """Cases the independent review of Gate A asked for."""

    def test_crux_private_path_fails(self):
        files = {"app/src/main.c": '#include "../../crux-pilot/components/time/src/x.h"\n'}
        self.assertEqual(["../../crux-pilot/components/time/src/x.h"], reasons(run(files)))

    def test_private_path_fails_even_when_the_file_exists_outside_the_tree(self):
        files = {
            "app/src/main.c": '#include "../../crux-pilot/components/time/src/x.h"\n',
            "crux-pilot/components/time/src/x.h": "",
        }
        self.assertEqual(1, len(run(files)))

    def test_quoted_vendor_header_fails(self):
        files = {"app/src/main.c": '#include "fsl_enet.h"\n'}
        self.assertEqual(["fsl_enet.h"], reasons(run(files)))

    def test_other_posix_header_sys_stat_fails(self):
        files = {"app/src/main.c": "#include <sys/stat.h>\n"}
        self.assertEqual(["sys/stat.h"], reasons(run(files)))

    def test_every_file_is_scanned_whatever_its_suffix(self):
        for name in ("zeph.inc", "zeph.inl", "zeph.hh", "zeph.def", "zeph.cxx", "zeph"):
            files = {f"app/src/{name}": "#include <zephyr/kernel.h>\n"}
            self.assertEqual(["zephyr/kernel.h"], reasons(run(files)), name)

    def test_include_next_and_import_are_checked(self):
        files = {"app/src/a.c": "#include_next <zephyr/kernel.h>\n#import <fsl_enet.h>\n"}
        self.assertEqual(["zephyr/kernel.h", "fsl_enet.h"], reasons(run(files)))

    def test_a_macro_operand_is_a_violation(self):
        files = {"app/src/a.c": "#define H <zephyr/kernel.h>\n#include H\n"}
        (violation,) = run(files)
        self.assertEqual(2, violation.line)
        self.assertIn("literal", violation.reason)

    def test_a_directive_split_by_a_backslash_is_joined(self):
        files = {"app/src/a.c": "#include \\\n    <zephyr/kernel.h>\n"}
        (violation,) = run(files)
        self.assertEqual("zephyr/kernel.h", violation.include)
        self.assertEqual(1, violation.line)

    def test_line_numbers_survive_a_joined_directive(self):
        files = {"app/src/a.c": "#define X \\\n  1\n#include <zephyr/kernel.h>\n"}
        (violation,) = run(files)
        self.assertEqual(3, violation.line)

    def test_a_comment_marker_inside_a_string_does_not_hide_an_include(self):
        text = 'const char *s = "/*";\n#include <zephyr/kernel.h>\nconst char *t = "*/";\n'
        self.assertEqual(["zephyr/kernel.h"], reasons(run({"app/src/a.c": text})))

    def test_a_comment_marker_in_a_char_literal_does_not_hide_an_include(self):
        text = "char c = '\"';\n#include <zephyr/kernel.h>\n"
        self.assertEqual(["zephyr/kernel.h"], reasons(run({"app/src/a.c": text})))

    def test_the_application_may_include_the_workload_header(self):
        files = {
            "app/src/main.c": '#include "workload.h"\n',
            "workload/include/workload.h": "#include <stdint.h>\n",
        }
        self.assertEqual([], run(files))

    def test_the_workload_may_not_include_an_application_header(self):
        files = {
            "workload/src/a.c": '#include "../../app/src/adapter.h"\n',
            "app/src/adapter.h": "",
        }
        self.assertEqual(1, len(run(files)))


class Hardening(unittest.TestCase):
    """The non-blocking findings of the Gate A review."""

    def test_a_split_inside_the_keyword_is_joined_as_c_joins_it(self):
        files = {"app/src/a.c": "#inc\\\nlude <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_a_crlf_continuation_is_joined(self):
        files = {"app/src/a.c": "#include \\\r\n  <zephyr/kernel.h>\r\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_plain_crlf_directives_are_found(self):
        files = {"app/src/a.c": "#include <zephyr/kernel.h>\r\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_the_digraph_for_hash_is_found(self):
        files = {"app/src/a.c": "%:include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_the_trigraph_for_hash_is_found(self):
        files = {"app/src/a.c": "??=include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_a_form_feed_before_the_hash_is_allowed_for(self):
        files = {"app/src/a.c": "\f#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))


class CompositionZone(unittest.TestCase):
    """app/compose is the one place that may name the File composition interface and mount.

    It may include <crux/file_zephyr.h>, public <crux/NAME.h> headers, ISO C headers and an
    explicit allow-list of Zephyr headers. app/src keeps its rules and reaches the zone only
    through a product-owned header that lives in app/src.
    """

    ZONE = "app/compose/mount.c"

    def crux_root(self, composition=("file_zephyr.h",), public=("file.h", "time.h")):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = pathlib.Path(directory.name)
        for name in public:
            path = root / "components" / "x" / "include" / "crux" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        for name in composition:
            path = root / "components" / "file" / "ports" / "zephyr" / "include" / "crux" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        return root

    def in_zone(self, text, name="mount.c", **kwargs):
        return run({f"app/compose/{name}": text}, **kwargs)

    # What the zone may include.

    def test_the_zone_may_include_the_composition_interface(self):
        self.assertEqual([], self.in_zone("#include <crux/file_zephyr.h>\n"))

    def test_the_zone_may_include_the_composition_interface_when_crux_publishes_it(self):
        root = self.crux_root()
        self.assertEqual([], self.in_zone("#include <crux/file_zephyr.h>\n", crux_root=root))

    def test_the_zone_may_include_the_public_file_header_and_iso_c(self):
        text = "#include <crux/file.h>\n#include <stdint.h>\n#include <string.h>\n"
        self.assertEqual([], self.in_zone(text, crux_root=self.crux_root()))

    def test_the_zone_may_include_each_allow_listed_zephyr_header(self):
        for name in sorted(check_boundary.COMPOSITION_ZEPHYR_HEADERS):
            self.assertEqual([], self.in_zone(f"#include <{name}>\n"), name)

    def test_the_zone_may_include_its_own_headers(self):
        files = {
            "app/compose/mount.c": '#include "mount_private.h"\n',
            "app/compose/mount_private.h": "#include <zephyr/fs/fs.h>\n",
        }
        self.assertEqual([], run(files))

    def test_the_zone_may_include_the_product_owned_header_of_app_src(self):
        files = {
            "app/compose/mount.c": '#include "storage_port.h"\n#include "../src/storage_port.h"\n',
            "app/src/storage_port.h": "#include <crux/file.h>\n",
        }
        self.assertEqual([], run(files))

    def test_the_zone_may_include_only_header_files_of_app_src(self):
        # The port is a header. A source file of app/src is not part of it.
        files = {
            "app/compose/mount.c": '#include "../src/main.c"\n',
            "app/src/main.c": "",
        }
        self.assertEqual(["../src/main.c"], reasons(run(files)))
        for name in ("main.inc", "main.cc", "main"):
            files = {"app/compose/mount.c": f'#include "../src/{name}"\n', f"app/src/{name}": ""}
            self.assertEqual([f"../src/{name}"], reasons(run(files)), name)

    def test_app_src_keeps_its_rule_for_the_files_of_the_workload_include_root(self):
        # Unchanged: a quoted include that resolves inside workload/include passes, whatever the suffix.
        files = {"app/src/main.c": '#include "table.inc"\n', "workload/include/table.inc": ""}
        self.assertEqual([], run(files))

    def test_the_zone_has_no_direct_way_to_the_sockets_profile(self):
        # Direct includes fail. An app/src header that includes a Sockets profile header is legal
        # under the app/src rules, and the zone may include that header: the rule is about what the
        # zone writes, and docs/composition-zone.md says so.
        self.assertEqual(["sys/socket.h"], reasons(self.in_zone("#include <sys/socket.h>\n")))

    # What the zone may not include.

    def test_the_zone_may_not_include_a_crux_private_or_port_header(self):
        for text, name in (
            ('#include "file_native.h"\n', "file_native.h"),
            ("#include <file_native.h>\n", "file_native.h"),
            ("#include <crux/ports/zephyr/file_native.h>\n", "crux/ports/zephyr/file_native.h"),
            ('#include "../../crux-pilot/components/file/ports/zephyr/file_native.h"\n',
             "../../crux-pilot/components/file/ports/zephyr/file_native.h"),
        ):
            self.assertEqual([name], reasons(self.in_zone(text)), text)

    def test_a_private_header_fails_even_when_it_exists_outside_the_tree(self):
        files = {
            "app/compose/mount.c": '#include "../../crux-pilot/components/file/src/file_port.h"\n',
            "crux-pilot/components/file/src/file_port.h": "",
        }
        self.assertEqual(1, len(run(files)))

    def test_the_zone_may_not_include_a_zephyr_header_that_is_not_allow_listed(self):
        for name in (
            "zephyr/kernel.h",
            "zephyr/storage/disk_access.h",
            "zephyr/sys/printk.h",
            "zephyr/drivers/gpio.h",
            "zephyr/net/socket.h",
            "zephyr/fs/littlefs.h",
            "zephyr/fs/fs_sys.h",
            "zephyr/fs",
            "zephyr/fs/",
            "zephyr/fs/fs.h.in",
            "zephyr/fs/../kernel.h",
            "zephyr.h",
        ):
            self.assertEqual([name], reasons(self.in_zone(f"#include <{name}>\n")), name)

    def test_the_allow_list_has_no_wildcards_and_names_only_zephyr_headers(self):
        names = check_boundary.COMPOSITION_ZEPHYR_HEADERS
        self.assertIsInstance(names, frozenset)
        for name in names:
            self.assertRegex(name, r"^zephyr/[a-z0-9_/]+\.h$")
            self.assertNotIn("..", name)
            self.assertNotIn("*", name)

    def test_the_allow_list_is_the_reviewed_set(self):
        # Changing this set changes what the boundary lets through: it is a reviewed change
        # of this test, of docs/composition-zone.md and of the pull request that justifies it.
        self.assertEqual(
            {"zephyr/fs/fs.h", "zephyr/devicetree.h"},
            set(check_boundary.COMPOSITION_ZEPHYR_HEADERS),
        )

    def test_the_zone_may_not_include_a_vendor_or_third_party_header(self):
        for name in ("fsl_enet.h", "fsl_usdhc.h", "ff.h", "lfs.h", "wolfssl/ssl.h", "stm32_hal.h"):
            self.assertEqual([name], reasons(self.in_zone(f"#include <{name}>\n")), name)
            self.assertEqual([name], reasons(self.in_zone(f'#include "{name}"\n')), name)

    def test_the_zone_may_not_use_the_sockets_profile_or_other_posix_headers(self):
        for name in ("sys/socket.h", "unistd.h", "pthread.h", "sys/stat.h"):
            self.assertEqual([name], reasons(self.in_zone(f"#include <{name}>\n")), name)

    def test_the_zone_may_not_quote_an_allow_listed_zephyr_header_to_dodge_the_list(self):
        self.assertEqual(
            ["zephyr/fs/fs.h"], reasons(self.in_zone('#include "zephyr/fs/fs.h"\n'))
        )

    def test_the_zone_may_not_include_a_crux_header_that_is_not_public(self):
        root = self.crux_root()
        self.assertEqual(
            ["crux/secret.h"], reasons(self.in_zone("#include <crux/secret.h>\n", crux_root=root))
        )

    def test_the_zone_may_not_include_a_composition_interface_crux_does_not_publish(self):
        root = self.crux_root(composition=())
        self.assertEqual(
            ["crux/file_zephyr.h"],
            reasons(self.in_zone("#include <crux/file_zephyr.h>\n", crux_root=root)),
        )

    def test_the_zone_may_not_include_another_composition_interface(self):
        # A composition header that Crux publishes next to file_zephyr.h is not in the zone's
        # allow-list until a reviewed change adds it.
        root = self.crux_root(composition=("file_zephyr.h", "queue_linux.h"))
        self.assertEqual(
            ["crux/queue_linux.h"],
            reasons(self.in_zone("#include <crux/queue_linux.h>\n", crux_root=root)),
        )

    def test_the_composition_allow_list_names_only_file_zephyr(self):
        self.assertEqual(
            {"crux/file_zephyr.h"}, set(check_boundary.COMPOSITION_CRUX_HEADERS)
        )

    # app/src and the workload keep their rules.

    def test_app_src_may_not_include_the_composition_interface(self):
        files = {"app/src/main.c": "#include <crux/file_zephyr.h>\n"}
        self.assertEqual(["crux/file_zephyr.h"], reasons(run(files)))

    def test_app_src_may_not_include_the_composition_interface_when_crux_publishes_it(self):
        files = {"app/src/main.c": "#include <crux/file_zephyr.h>\n"}
        self.assertEqual(
            ["crux/file_zephyr.h"], reasons(run(files, crux_root=self.crux_root()))
        )

    def test_app_src_may_not_include_an_allow_listed_zephyr_header(self):
        for name in sorted(check_boundary.COMPOSITION_ZEPHYR_HEADERS):
            files = {"app/src/main.c": f"#include <{name}>\n"}
            self.assertEqual([name], reasons(run(files)), name)

    def test_app_src_may_not_include_another_zephyr_header(self):
        files = {"app/src/main.c": "#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_app_src_may_not_reach_a_header_of_the_zone(self):
        for text in (
            '#include "../compose/mount_private.h"\n',
            '#include "compose/mount_private.h"\n',
            '#include "mount_private.h"\n',
        ):
            files = {
                "app/src/main.c": text,
                "app/compose/mount_private.h": "#include <zephyr/fs/fs.h>\n",
            }
            self.assertEqual(1, len(run(files)), text)

    def test_a_zone_header_that_app_src_includes_by_a_scanned_path_cannot_hide_zephyr(self):
        # The product-owned header lives in app/src, so the app rules scan it.
        files = {
            "app/src/main.c": '#include "storage_port.h"\n',
            "app/src/storage_port.h": "#include <zephyr/fs/fs.h>\n",
        }
        self.assertEqual(["zephyr/fs/fs.h"], reasons(run(files)))

    def test_the_workload_may_not_include_the_composition_interface_or_a_zone_header(self):
        for text in ("#include <crux/file_zephyr.h>\n", "#include <zephyr/fs/fs.h>\n"):
            self.assertEqual(1, len(run({"workload/cycle.c": text})), text)
        files = {
            "workload/src/a.c": '#include "../../app/compose/mount_private.h"\n',
            "app/compose/mount_private.h": "",
        }
        self.assertEqual(1, len(run(files)))

    def test_a_violation_in_the_zone_names_file_and_line(self):
        text = "#include <crux/file_zephyr.h>\n#include <zephyr/kernel.h>\n"
        (violation,) = self.in_zone(text)
        self.assertEqual("app/compose/mount.c", violation.path)
        self.assertEqual(2, violation.line)

    # The scan forms that the hardening of the application rules covers, for the zone.

    def test_every_file_of_the_zone_is_scanned_whatever_its_suffix(self):
        for name in ("m.inc", "m.inl", "m.hh", "m.def", "m.cxx", "m", "m.h"):
            files = {f"app/compose/{name}": "#include <zephyr/kernel.h>\n"}
            self.assertEqual(["zephyr/kernel.h"], reasons(run(files)), name)

    def test_the_hardened_scan_forms_hold_in_the_zone(self):
        for text in (
            "#include \\\n    <zephyr/kernel.h>\n",
            "#inc\\\nlude <zephyr/kernel.h>\n",
            "#include \\\r\n  <zephyr/kernel.h>\r\n",
            "#include <zephyr/kernel.h>\r\n",
            "%:include <zephyr/kernel.h>\n",
            "??=include <zephyr/kernel.h>\n",
            "\f#include <zephyr/kernel.h>\n",
            "  #  include   <zephyr/kernel.h>\n",
            "#include_next <zephyr/kernel.h>\n",
            "#import <zephyr/kernel.h>\n",
            'const char *s = "/*";\n#include <zephyr/kernel.h>\nconst char *t = "*/";\n',
        ):
            self.assertEqual(["zephyr/kernel.h"], reasons(self.in_zone(text)), repr(text))

    def test_the_hardened_scan_forms_find_allow_listed_headers_too(self):
        # A macro operand cannot be checked, even when it would name an allowed header.
        text = "#define H <zephyr/fs/fs.h>\n#include H\n"
        (violation,) = self.in_zone(text)
        self.assertEqual(2, violation.line)
        self.assertIn("literal", violation.reason)

    def test_a_commented_include_in_the_zone_is_ignored(self):
        text = "/* #include <zephyr/kernel.h> */\n// #include <ff.h>\n"
        self.assertEqual([], self.in_zone(text))

    def test_the_zone_command_line_reports_a_violation(self):
        repo = Repo({"app/compose/mount.c": "#include <zephyr/kernel.h>\n"})
        self.addCleanup(repo.close)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", str(repo.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("app/compose/mount.c:1", result.stdout)

    def test_the_zone_is_listed_with_the_other_rules(self):
        directories = [rule.directory for rule in check_boundary.RULES]
        self.assertEqual(["app/src", "workload", "app/compose", "app/os"], directories)

    def test_the_rules_of_app_src_and_the_workload_are_unchanged(self):
        app, workload = check_boundary.RULES[:2]
        self.assertEqual(
            (True, True, frozenset(), frozenset(), ("workload/include",)),
            (app.allow_sockets, app.allow_crux, app.zephyr_allow, app.composition_crux,
             app.extra_roots),
        )
        self.assertEqual(
            (False, False, frozenset(), frozenset(), ()),
            (workload.allow_sockets, workload.allow_crux, workload.zephyr_allow,
             workload.composition_crux, workload.extra_roots),
        )


class OsAdapterZone(unittest.TestCase):
    """app/os is the adapter zone: OS facilities use Zephyr directly, product behaviour stays in app/src.

    It may include ISO C headers, public <crux/NAME.h> headers, its own tree, header files of
    app/src (the product-owned port header) and exactly one Zephyr header, zephyr/kernel.h.
    app/src, app/compose and the workload keep failing on that header, and none of them can reach
    a header of the adapter zone.
    """

    def crux_root(self, composition=("file_zephyr.h",), public=("file.h", "time.h")):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = pathlib.Path(directory.name)
        for name in public:
            path = root / "components" / "x" / "include" / "crux" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        for name in composition:
            path = root / "components" / "file" / "ports" / "zephyr" / "include" / "crux" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        return root

    def in_adapter(self, text, name="adapter.c", **kwargs):
        return run({f"app/os/{name}": text}, **kwargs)

    # What the adapter zone may include.

    def test_the_adapter_may_include_zephyr_kernel(self):
        self.assertEqual([], self.in_adapter("#include <zephyr/kernel.h>\n"))

    def test_the_adapter_may_include_each_allow_listed_zephyr_header(self):
        for name in sorted(check_boundary.OS_ADAPTER_ZEPHYR_HEADERS):
            self.assertEqual([], self.in_adapter(f"#include <{name}>\n"), name)

    def test_the_adapter_may_include_public_crux_headers_and_iso_c(self):
        text = "#include <crux/time.h>\n#include <stdint.h>\n#include <string.h>\n"
        self.assertEqual([], self.in_adapter(text, crux_root=self.crux_root()))

    def test_the_adapter_may_include_its_own_headers(self):
        files = {
            "app/os/adapter.c": '#include "adapter_private.h"\n',
            "app/os/adapter_private.h": "#include <zephyr/kernel.h>\n",
        }
        self.assertEqual([], run(files))

    def test_the_adapter_may_include_the_product_owned_header_of_app_src(self):
        files = {
            "app/os/adapter.c": '#include "workload_os.h"\n#include "../src/workload_os.h"\n',
            "app/src/workload_os.h": "#include <stdint.h>\n",
        }
        self.assertEqual([], run(files))

    def test_the_adapter_may_include_only_header_files_of_app_src(self):
        for name in ("main.c", "main.inc", "main.cc", "main"):
            files = {"app/os/adapter.c": f'#include "../src/{name}"\n', f"app/src/{name}": ""}
            self.assertEqual([f"../src/{name}"], reasons(run(files)), name)

    def test_a_header_of_app_src_is_scanned_under_the_app_src_rules(self):
        files = {
            "app/os/adapter.c": '#include "workload_os.h"\n',
            "app/src/workload_os.h": "#include <zephyr/kernel.h>\n",
        }
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    # What the adapter zone may not include.

    def test_the_adapter_may_not_include_another_zephyr_header(self):
        for name in (
            "zephyr/sys/printk.h",
            "zephyr/logging/log.h",
            "zephyr/drivers/gpio.h",
            "zephyr/drivers/uart.h",
            "zephyr/net/socket.h",
            "zephyr/fs/fs.h",
            "zephyr/devicetree.h",
            "zephyr/kernel/thread.h",
            "zephyr/kernel",
            "zephyr/kernel.h.in",
            "zephyr/../zephyr/kernel.h",
            "zephyr.h",
        ):
            self.assertEqual([name], reasons(self.in_adapter(f"#include <{name}>\n")), name)

    def test_the_adapter_may_not_include_a_vendor_or_third_party_header(self):
        for name in ("fsl_enet.h", "fsl_usdhc.h", "ff.h", "lfs.h", "wolfssl/ssl.h", "stm32_hal.h"):
            self.assertEqual([name], reasons(self.in_adapter(f"#include <{name}>\n")), name)
            self.assertEqual([name], reasons(self.in_adapter(f'#include "{name}"\n')), name)

    def test_the_adapter_may_not_use_the_sockets_profile_or_other_posix_headers(self):
        for name in ("sys/socket.h", "netinet/in.h", "unistd.h", "pthread.h", "sys/stat.h"):
            self.assertEqual([name], reasons(self.in_adapter(f"#include <{name}>\n")), name)

    def test_the_adapter_may_not_include_the_composition_interface(self):
        self.assertEqual(
            ["crux/file_zephyr.h"], reasons(self.in_adapter("#include <crux/file_zephyr.h>\n"))
        )
        root = self.crux_root()
        self.assertEqual(
            ["crux/file_zephyr.h"],
            reasons(self.in_adapter("#include <crux/file_zephyr.h>\n", crux_root=root)),
        )

    def test_the_adapter_may_not_include_another_composition_interface(self):
        root = self.crux_root(composition=("file_zephyr.h", "queue_linux.h"))
        self.assertEqual(
            ["crux/queue_linux.h"],
            reasons(self.in_adapter("#include <crux/queue_linux.h>\n", crux_root=root)),
        )

    def test_the_adapter_may_not_include_a_crux_private_or_port_header(self):
        for text, name in (
            ('#include "file_native.h"\n', "file_native.h"),
            ("#include <crux/ports/zephyr/file_native.h>\n", "crux/ports/zephyr/file_native.h"),
        ):
            self.assertEqual([name], reasons(self.in_adapter(text)), text)

    def test_the_adapter_may_not_include_a_crux_header_that_is_not_public(self):
        root = self.crux_root()
        self.assertEqual(
            ["crux/secret.h"],
            reasons(self.in_adapter("#include <crux/secret.h>\n", crux_root=root)),
        )

    def test_the_adapter_may_not_quote_zephyr_kernel_to_dodge_the_list(self):
        self.assertEqual(
            ["zephyr/kernel.h"], reasons(self.in_adapter('#include "zephyr/kernel.h"\n'))
        )

    def test_the_adapter_may_not_reach_a_header_of_the_composition_zone(self):
        files = {
            "app/os/adapter.c": '#include "../compose/mount_private.h"\n',
            "app/compose/mount_private.h": "#include <zephyr/fs/fs.h>\n",
        }
        self.assertEqual(["../compose/mount_private.h"], reasons(run(files)))

    # The allow-list is exact.

    def test_the_allow_list_has_no_wildcards_and_names_only_zephyr_headers(self):
        names = check_boundary.OS_ADAPTER_ZEPHYR_HEADERS
        self.assertIsInstance(names, frozenset)
        for name in names:
            self.assertRegex(name, r"^zephyr/[a-z0-9_/]+\.h$")
            self.assertNotIn("..", name)
            self.assertNotIn("*", name)

    def test_the_adapter_allow_list_is_the_reviewed_set(self):
        # Changing this set changes what the boundary lets through: it is a reviewed change
        # of this test, of docs/composition-zone.md and of the pull request that justifies it.
        self.assertEqual({"zephyr/kernel.h"}, set(check_boundary.OS_ADAPTER_ZEPHYR_HEADERS))

    def test_the_adapter_rule_is_the_reviewed_rule(self):
        adapter = next(r for r in check_boundary.RULES if r.directory == "app/os")
        self.assertEqual(
            (False, True, check_boundary.OS_ADAPTER_ZEPHYR_HEADERS, frozenset(),
             ("app/src",), True),
            (adapter.allow_sockets, adapter.allow_crux, adapter.zephyr_allow,
             adapter.composition_crux, adapter.extra_roots, adapter.extra_roots_headers_only),
        )

    def test_the_composition_zone_keeps_its_rule_and_its_allow_list(self):
        # zephyr/kernel.h stays off the composition zone's list.
        compose = next(r for r in check_boundary.RULES if r.directory == "app/compose")
        self.assertEqual(
            {"zephyr/fs/fs.h", "zephyr/devicetree.h"}, set(compose.zephyr_allow)
        )
        self.assertNotIn("zephyr/kernel.h", check_boundary.COMPOSITION_ZEPHYR_HEADERS)
        self.assertEqual(frozenset({"crux/file_zephyr.h"}), compose.composition_crux)
        self.assertEqual(
            ["zephyr/kernel.h"],
            reasons(run({"app/compose/mount.c": "#include <zephyr/kernel.h>\n"})),
        )

    # The other trees keep failing on zephyr/kernel.h, and cannot reach the adapter zone.

    def test_app_src_may_not_include_zephyr_kernel(self):
        files = {"app/src/main.c": "#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_the_workload_may_not_include_zephyr_kernel(self):
        files = {"workload/cycle.c": "#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_app_src_may_not_reach_a_header_of_the_adapter_zone(self):
        for text in (
            '#include "../os/adapter_private.h"\n',
            '#include "os/adapter_private.h"\n',
            '#include "adapter_private.h"\n',
        ):
            files = {
                "app/src/main.c": text,
                "app/os/adapter_private.h": "#include <zephyr/kernel.h>\n",
            }
            self.assertEqual(1, len(run(files)), text)

    def test_the_composition_zone_may_not_reach_a_header_of_the_adapter_zone(self):
        for text in (
            '#include "../os/adapter_private.h"\n',
            '#include "os/adapter_private.h"\n',
            '#include "adapter_private.h"\n',
        ):
            files = {
                "app/compose/mount.c": text,
                "app/os/adapter_private.h": "#include <zephyr/kernel.h>\n",
            }
            self.assertEqual(1, len(run(files)), text)

    def test_the_workload_may_not_reach_a_header_of_the_adapter_zone(self):
        files = {
            "workload/src/a.c": '#include "../../app/os/adapter_private.h"\n',
            "app/os/adapter_private.h": "",
        }
        self.assertEqual(1, len(run(files)))

    # Scan forms and reporting hold in the adapter zone.

    def test_a_violation_in_the_adapter_names_file_and_line(self):
        text = "#include <zephyr/kernel.h>\n#include <zephyr/sys/printk.h>\n"
        (violation,) = self.in_adapter(text)
        self.assertEqual("app/os/adapter.c", violation.path)
        self.assertEqual(2, violation.line)

    def test_every_file_of_the_adapter_is_scanned_whatever_its_suffix(self):
        for name in ("a.inc", "a.inl", "a.hh", "a.def", "a.cxx", "a", "a.h"):
            files = {f"app/os/{name}": "#include <zephyr/sys/printk.h>\n"}
            self.assertEqual(["zephyr/sys/printk.h"], reasons(run(files)), name)

    def test_the_hardened_scan_forms_hold_in_the_adapter(self):
        for text in (
            "#include \\\n    <zephyr/sys/printk.h>\n",
            "#inc\\\nlude <zephyr/sys/printk.h>\n",
            "#include <zephyr/sys/printk.h>\r\n",
            "%:include <zephyr/sys/printk.h>\n",
            "??=include <zephyr/sys/printk.h>\n",
            "#include_next <zephyr/sys/printk.h>\n",
            "#import <zephyr/sys/printk.h>\n",
        ):
            self.assertEqual(["zephyr/sys/printk.h"], reasons(self.in_adapter(text)), repr(text))

    def test_a_macro_operand_is_a_violation_even_for_the_allowed_header(self):
        text = "#define H <zephyr/kernel.h>\n#include H\n"
        (violation,) = self.in_adapter(text)
        self.assertEqual(2, violation.line)
        self.assertIn("literal", violation.reason)

    def test_a_commented_include_in_the_adapter_is_ignored(self):
        text = "/* #include <zephyr/sys/printk.h> */\n// #include <ff.h>\n"
        self.assertEqual([], self.in_adapter(text))

    def test_the_adapter_command_line_reports_a_violation(self):
        repo = Repo({"app/os/adapter.c": "#include <zephyr/sys/printk.h>\n"})
        self.addCleanup(repo.close)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", str(repo.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("app/os/adapter.c:1", result.stdout)

    def test_the_adapter_command_line_passes_for_the_one_allowed_header(self):
        repo = Repo({"app/os/adapter.c": "#include <zephyr/kernel.h>\n"})
        self.addCleanup(repo.close)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", str(repo.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout)

    def test_an_absent_adapter_tree_is_skipped(self):
        # main has no app/os yet, and the check must keep passing there.
        self.assertEqual([], run({"app/src/main.c": "#include <stdint.h>\n"}))


class BuildFiles(unittest.TestCase):
    """The check reads includes only, so the build files must not add include paths."""

    FORBIDDEN = (
        "include_directories",
        "zephyr_include_directories",
        "target_include_directories",
        "-include",
        "-I",
    )

    def test_app_cmake_adds_no_include_path(self):
        text = (ROOT / "app" / "CMakeLists.txt").read_text()
        for line in text.splitlines():
            code = line.split("#", 1)[0]
            for word in self.FORBIDDEN:
                self.assertNotIn(word, code, f"app/CMakeLists.txt: {line.strip()}")

    def test_app_cmake_takes_sources_from_app_src_only(self):
        text = (ROOT / "app" / "CMakeLists.txt").read_text()
        for line in text.splitlines():
            code = line.split("#", 1)[0]
            if "target_sources" in code:
                self.assertIn("src/", code)
                self.assertNotIn("..", code)


class CommandLine(unittest.TestCase):
    def invoke(self, files, *extra):
        repo = Repo(files)
        self.addCleanup(repo.close)
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", str(repo.root), *extra],
            capture_output=True,
            text=True,
        )

    def test_exit_zero_when_clean(self):
        result = self.invoke({"app/src/main.c": "#include <crux/time.h>\n"})
        self.assertEqual(0, result.returncode, result.stderr)

    def test_exit_one_and_report_when_violated(self):
        result = self.invoke({"app/src/main.c": "#include <zephyr/kernel.h>\n"})
        self.assertEqual(1, result.returncode)
        self.assertIn("app/src/main.c:1", result.stdout)
        self.assertIn("zephyr/kernel.h", result.stdout)

    def test_exit_two_for_a_missing_repository(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", "/nonexistent-dir"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, result.returncode)


class ThisRepository(unittest.TestCase):
    def test_repository_keeps_the_boundary(self):
        self.assertEqual([], check_boundary.check(ROOT, None))


if __name__ == "__main__":
    unittest.main()
