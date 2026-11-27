# SPDX-License-Identifier: Apache-2.0
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
    def test_a_single_missing_tree_is_skipped(self):
        self.assertEqual([], run({"app/src/main.c": "#include <stdio.h>\n"}))

    def test_no_checked_tree_at_all_is_an_error(self):
        with self.assertRaises(ValueError) as caught:
            run({"README.md": ""})
        self.assertIn("run from the repository root or pass --repo", str(caught.exception))

    def test_the_command_fails_with_exit_2_and_a_message_from_the_wrong_directory(self):
        repo = Repo({"README.md": ""})
        self.addCleanup(repo.close)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", str(repo.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertNotIn("boundary check passed", result.stdout)
        self.assertIn("no checked tree", result.stderr)

    def test_files_outside_the_scanned_directories_are_not_checked(self):
        # app/src is present so that the run has a checked tree; the file outside it is ignored.
        files = {"tests/host/test.c": "#include <zephyr/kernel.h>\n", "app/src/main.c": ""}
        self.assertEqual([], run(files))


class Reviewed(unittest.TestCase):
    """Cases that an independent review of the boundary check asked for."""

    def test_crux_private_path_fails(self):
        files = {"app/src/main.c": '#include "../../crux/components/time/src/x.h"\n'}
        self.assertEqual(["../../crux/components/time/src/x.h"], reasons(run(files)))

    def test_private_path_fails_even_when_the_file_exists_outside_the_tree(self):
        files = {
            "app/src/main.c": '#include "../../crux/components/time/src/x.h"\n',
            "crux/components/time/src/x.h": "",
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
    """The non-blocking findings of that review."""

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
            ('#include "../../crux/components/file/ports/zephyr/file_native.h"\n',
             "../../crux/components/file/ports/zephyr/file_native.h"),
        ):
            self.assertEqual([name], reasons(self.in_zone(text)), text)

    def test_a_private_header_fails_even_when_it_exists_outside_the_tree(self):
        files = {
            "app/compose/mount.c": '#include "../../crux/components/file/src/file_port.h"\n',
            "crux/components/file/src/file_port.h": "",
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
            {"zephyr/fs/fs.h", "zephyr/devicetree.h", "zephyr/net/tls_credentials.h"},
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

    def test_the_composition_allow_list_is_the_reviewed_set(self):
        self.assertEqual(
            {"crux/file_zephyr.h", "crux/web_zephyr.h", "crux/cli_zephyr.h"},
            set(check_boundary.COMPOSITION_CRUX_HEADERS),
        )

    # The serial command line: <crux/cli_zephyr.h>, which starts the Crux console on the UART of
    # the devicetree alias crux-serial0. Crux publishes it under components/cli/ports/zephyr.

    CLI_ZEPHYR = "crux/cli_zephyr.h"

    def cli_root(self, composition=("file_zephyr.h", "web_zephyr.h", "cli_zephyr.h")):
        return self.crux_root(composition=composition,
                              public=("file.h", "time.h", "cli.h", "access.h"))

    def test_the_zones_may_include_the_cli_composition_interface(self):
        for tree in ("app/compose", "framework/compose"):
            files = {f"{tree}/cli_start.c": f"#include <{self.CLI_ZEPHYR}>\n#include <crux/cli.h>\n"}
            for root in (None, self.cli_root()):
                self.assertEqual([], run(files, crux_root=root), (tree, root))

    def test_the_cli_interface_fails_outside_the_composition_zones(self):
        for root in (None, self.cli_root()):
            for tree in ("app/src", "app/os", "workload", "include", "framework/src", "framework/os"):
                files = {f"{tree}/x.c": f"#include <{self.CLI_ZEPHYR}>\n"}
                self.assertEqual([self.CLI_ZEPHYR], reasons(run(files, crux_root=root)), (tree, root))

    def test_the_cli_interface_fails_outside_the_zones_by_name_without_a_crux_root(self):
        (violation,) = run({"framework/src/core.c": f"#include <{self.CLI_ZEPHYR}>\n"})
        self.assertEqual("composition interface, for the composition zone only", violation.reason)

    def test_the_zone_may_not_include_the_cli_interface_crux_does_not_publish(self):
        root = self.cli_root(composition=("file_zephyr.h", "web_zephyr.h"))
        files = {"framework/compose/cli_start.c": f"#include <{self.CLI_ZEPHYR}>\n"}
        self.assertEqual([self.CLI_ZEPHYR], reasons(run(files, crux_root=root)))

    def test_the_portable_cli_header_stays_an_ordinary_public_header(self):
        root = self.cli_root()
        for tree in ("app/src/a.c", "framework/src/a.c", "framework/compose/a.c"):
            self.assertEqual([], run({tree: "#include <crux/cli.h>\n"}, crux_root=root), tree)

    def test_the_cli_change_adds_no_zephyr_header_and_unfreezes_nothing(self):
        self.assertEqual(
            {"zephyr/fs/fs.h", "zephyr/devicetree.h", "zephyr/net/tls_credentials.h"},
            set(check_boundary.COMPOSITION_ZEPHYR_HEADERS),
        )
        for name in sorted(check_boundary.FROZEN_CRUX_HEADERS):
            for tree in ("framework/src/a.c", "framework/os/a.c", "app/src/a.c"):
                self.assertEqual([name], reasons(run({tree: f"#include <{name}>\n"})), (name, tree))

    # The HTTPS management composition: <crux/web_zephyr.h> and <zephyr/net/tls_credentials.h>.

    WEB_ZEPHYR = "crux/web_zephyr.h"
    TLS_CREDENTIALS = "zephyr/net/tls_credentials.h"

    def web_root(self):
        return self.crux_root(
            composition=("file_zephyr.h", "web_zephyr.h"),
            public=("file.h", "time.h", "web.h", "web_session.h", "web_management.h",
                    "tls_certificate.h"),
        )

    def test_the_zone_may_include_the_web_composition_interface(self):
        self.assertEqual([], self.in_zone(f"#include <{self.WEB_ZEPHYR}>\n"))
        self.assertEqual(
            [], self.in_zone(f"#include <{self.WEB_ZEPHYR}>\n", crux_root=self.web_root())
        )

    def test_the_zone_may_include_the_tls_credentials_header(self):
        self.assertEqual([], self.in_zone(f"#include <{self.TLS_CREDENTIALS}>\n"))
        self.assertEqual(
            [], self.in_zone(f"#include <{self.TLS_CREDENTIALS}>\n", crux_root=self.web_root())
        )

    def test_the_zone_may_not_include_the_web_interface_crux_does_not_publish(self):
        root = self.crux_root()  # publishes file_zephyr.h only
        self.assertEqual(
            [self.WEB_ZEPHYR],
            reasons(self.in_zone(f"#include <{self.WEB_ZEPHYR}>\n", crux_root=root)),
        )

    def test_app_src_may_not_include_either_header(self):
        for root in (None, self.web_root()):
            for name in (self.WEB_ZEPHYR, self.TLS_CREDENTIALS):
                files = {"app/src/main.c": f"#include <{name}>\n"}
                self.assertEqual([name], reasons(run(files, crux_root=root)), (name, root))

    def test_the_adapter_zone_may_not_include_either_header(self):
        for root in (None, self.web_root()):
            for name in (self.WEB_ZEPHYR, self.TLS_CREDENTIALS):
                files = {"app/os/adapter.c": f"#include <{name}>\n"}
                self.assertEqual([name], reasons(run(files, crux_root=root)), (name, root))

    def test_the_workload_may_not_include_either_header(self):
        for root in (None, self.web_root()):
            for name in (self.WEB_ZEPHYR, self.TLS_CREDENTIALS):
                files = {"workload/cycle.c": f"#include <{name}>\n"}
                self.assertEqual([name], reasons(run(files, crux_root=root)), (name, root))

    def test_the_web_interface_fails_outside_the_zone_by_name_without_a_crux_root(self):
        # Without --crux-root the shape test cannot tell a composition interface from a public
        # header, so the name decides. This is the case that a local run without a Crux
        # checkout depends on.
        (violation,) = run({"app/src/main.c": f"#include <{self.WEB_ZEPHYR}>\n"})
        self.assertEqual("composition interface, for the composition zone only", violation.reason)

    def test_the_quoted_form_of_either_header_fails_in_the_zone(self):
        for name in (self.WEB_ZEPHYR, self.TLS_CREDENTIALS):
            self.assertEqual([name], reasons(self.in_zone(f'#include "{name}"\n')), name)

    def test_the_zone_still_may_not_include_other_zephyr_net_headers(self):
        for name in (
            "zephyr/net/socket.h",
            "zephyr/net/net_if.h",
            "zephyr/net/http/server.h",
            "zephyr/net/tls_credentials",
            "zephyr/net/tls_credentials.h.in",
            "zephyr/net/../kernel.h",
        ):
            self.assertEqual([name], reasons(self.in_zone(f"#include <{name}>\n")), name)

    def test_the_other_web_headers_are_ordinary_public_headers(self):
        # Only crux/web_zephyr.h became composition-only. The portable web headers keep the
        # rule of every public <crux/NAME.h> header: allowed in app/src, app/os and the zone,
        # and not in the workload.
        root = self.web_root()
        for name in ("crux/web.h", "crux/web_session.h", "crux/web_management.h",
                     "crux/tls_certificate.h"):
            for tree in ("app/src/a.c", "app/os/a.c", "app/compose/a.c"):
                self.assertEqual([], run({tree: f"#include <{name}>\n"}, crux_root=root), name)
            self.assertEqual(
                [name], reasons(run({"workload/a.c": f"#include <{name}>\n"}, crux_root=root))
            )

    def test_the_file_interface_and_the_frozen_headers_keep_their_rules(self):
        root = self.web_root()
        self.assertEqual(
            [], self.in_zone("#include <crux/file_zephyr.h>\n", crux_root=root)
        )
        for tree in ("app/src/a.c", "app/os/a.c", "workload/a.c"):
            self.assertEqual(
                ["crux/file_zephyr.h"],
                reasons(run({tree: "#include <crux/file_zephyr.h>\n"}, crux_root=root)),
            )
        for name in sorted(check_boundary.FROZEN_CRUX_HEADERS):
            for tree in ("app/src/a.c", "app/os/a.c"):
                self.assertEqual([name], reasons(run({tree: f"#include <{name}>\n"})), name)
            self.assertEqual([], self.in_zone(f"#include <{name}>\n"), name)

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
        self.assertEqual(
            ["app/src", "workload", "app/compose", "app/os",
             "include", "framework/src", "framework/compose", "framework/os"],
            directories,
        )

    def test_the_rules_of_app_src_and_the_workload_are_unchanged(self):
        # app/src gains the framework core as a root, so that the configurations built on the
        # workload reach the framework services they compose.
        app, workload = check_boundary.RULES[:2]
        self.assertEqual(
            (True, True, frozenset(), frozenset(), ("workload/include", "framework/src"), False),
            (app.allow_sockets, app.allow_crux, app.zephyr_allow, app.composition_crux,
             app.extra_roots, app.extra_roots_headers_only),
        )
        self.assertEqual(
            (False, False, frozenset(), frozenset(), ()),
            (workload.allow_sockets, workload.allow_crux, workload.zephyr_allow,
             workload.composition_crux, workload.extra_roots),
        )


class OsAdapterZone(unittest.TestCase):
    """app/os is the adapter zone: OS facilities use Zephyr directly, product behaviour stays in app/src.

    It may include ISO C headers, public <crux/NAME.h> headers, its own tree, header files of
    app/src (the product-owned port header) and exactly two Zephyr headers, zephyr/kernel.h and
    zephyr/net/sntp.h. app/src, app/compose and the workload keep failing on those headers, and
    none of them can reach a header of the adapter zone.
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

    def test_the_adapter_may_include_the_zephyr_sntp_header(self):
        # The SNTP library header is the second entry of the adapter allow-list. The adapter uses
        # its string-based query, so it includes no socket type or socket header itself.
        self.assertEqual([], self.in_adapter("#include <zephyr/net/sntp.h>\n"))
        self.assertEqual([], self.in_adapter("#include <zephyr/kernel.h>\n#include <zephyr/net/sntp.h>\n"))
        self.assertEqual([], self.in_adapter("#include <zephyr/net/sntp.h>\n", name="sntp_private.h"))

    def test_the_zephyr_sntp_header_still_fails_outside_the_adapter(self):
        for tree in ("app/src", "app/compose", "workload"):
            files = {f"{tree}/x.c": "#include <zephyr/net/sntp.h>\n"}
            self.assertEqual(["zephyr/net/sntp.h"], reasons(run(files)), tree)

    def test_the_adapter_still_fails_on_socket_headers_next_to_the_sntp_header(self):
        for name in (
            "zephyr/net/socket.h",
            "zephyr/net/socket_types.h",
            "sys/socket.h",
            "netinet/in.h",
            "arpa/inet.h",
            "poll.h",
            "fcntl.h",
            "unistd.h",
        ):
            text = f"#include <zephyr/net/sntp.h>\n#include <{name}>\n"
            self.assertEqual([name], reasons(self.in_adapter(text)), name)

    def test_the_adapter_still_fails_on_another_zephyr_net_header(self):
        for name in (
            "zephyr/net/net_if.h",
            "zephyr/net/net_ip.h",
            "zephyr/net/sntp",
            "zephyr/net/sntp.h.in",
            "zephyr/net/sntp_client.h",
            "zephyr/net/../net/sntp.h",
        ):
            self.assertEqual([name], reasons(self.in_adapter(f"#include <{name}>\n")), name)

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
        self.assertEqual(
            {"zephyr/kernel.h", "zephyr/net/sntp.h"}, set(check_boundary.OS_ADAPTER_ZEPHYR_HEADERS)
        )

    def test_the_adapter_rule_is_the_reviewed_rule(self):
        adapter = next(r for r in check_boundary.RULES if r.directory == "app/os")
        # The rule allows the SNTP header and no socket header: sockets stay off for the zone.
        self.assertEqual(
            frozenset({"zephyr/kernel.h", "zephyr/net/sntp.h"}), adapter.zephyr_allow
        )
        self.assertFalse(adapter.allow_sockets)
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
            {"zephyr/fs/fs.h", "zephyr/devicetree.h", "zephyr/net/tls_credentials.h"},
            set(compose.zephyr_allow),
        )
        self.assertNotIn("zephyr/kernel.h", check_boundary.COMPOSITION_ZEPHYR_HEADERS)
        self.assertEqual(
            frozenset({"crux/file_zephyr.h", "crux/web_zephyr.h", "crux/cli_zephyr.h"}),
            compose.composition_crux,
        )
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

    def assertRejectedAsQuotedHeader(self, files, source, include):
        """The reaching include is the one violation, and the rule that rejects it is the
        quoted-header rule, not a count that some other include could also produce."""
        (violation,) = run(files)
        self.assertEqual(source, violation.path, include)
        self.assertEqual(1, violation.line, include)
        self.assertEqual(include, violation.include)
        self.assertIn("quoted header is not in this tree", violation.reason, include)

    def test_app_src_may_not_reach_a_header_of_the_adapter_zone(self):
        for include in ("../os/adapter_private.h", "os/adapter_private.h", "adapter_private.h"):
            files = {
                "app/src/main.c": f'#include "{include}"\n',
                "app/os/adapter_private.h": "#include <zephyr/kernel.h>\n",
            }
            self.assertRejectedAsQuotedHeader(files, "app/src/main.c", include)

    def test_the_composition_zone_may_not_reach_a_header_of_the_adapter_zone(self):
        for include in ("../os/adapter_private.h", "os/adapter_private.h", "adapter_private.h"):
            files = {
                "app/compose/mount.c": f'#include "{include}"\n',
                "app/os/adapter_private.h": "#include <zephyr/kernel.h>\n",
            }
            self.assertRejectedAsQuotedHeader(files, "app/compose/mount.c", include)

    def test_the_workload_may_not_reach_a_header_of_the_adapter_zone(self):
        for include in ("../../app/os/adapter_private.h", "app/os/adapter_private.h"):
            files = {
                "workload/src/a.c": f'#include "{include}"\n',
                "app/os/adapter_private.h": "#include <zephyr/kernel.h>\n",
            }
            self.assertRejectedAsQuotedHeader(files, "workload/src/a.c", include)

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
            "#include \\\r\n  <zephyr/sys/printk.h>\r\n",
            "#include <zephyr/sys/printk.h>\r\n",
            "%:include <zephyr/sys/printk.h>\n",
            "??=include <zephyr/sys/printk.h>\n",
            "\f#include <zephyr/sys/printk.h>\n",
            "  #  include   <zephyr/sys/printk.h>\n",
            "#include_next <zephyr/sys/printk.h>\n",
            "#import <zephyr/sys/printk.h>\n",
            'const char *s = "/*";\n#include <zephyr/sys/printk.h>\nconst char *t = "*/";\n',
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

    def test_a_multi_line_block_comment_hides_an_include_in_the_adapter(self):
        text = "/*\n#include <zephyr/sys/printk.h>\n#include <ff.h>\n*/\n"
        self.assertEqual([], self.in_adapter(text))

    def test_a_comment_inside_a_directive_does_not_hide_the_include_in_the_adapter(self):
        for text in (
            "#/* c */include <zephyr/sys/printk.h>\n",
            "#include /* c */ <zephyr/sys/printk.h>\n",
            "#include <zephyr/sys/printk.h> // the next line is fine\n",
            "#include <zephyr/sys/printk.h> /* trailing */\n",
        ):
            (violation,) = self.in_adapter(text)
            self.assertEqual("zephyr/sys/printk.h", violation.include, repr(text))
            self.assertEqual(1, violation.line, repr(text))

    def test_a_comment_inside_the_keyword_does_not_form_an_include_in_the_adapter(self):
        # A comment is one space to the compiler, so "inc" and "lude" are two tokens.
        self.assertEqual([], self.in_adapter("#inc/* c */lude <zephyr/sys/printk.h>\n"))

    def test_an_include_in_a_disabled_conditional_block_is_still_checked_in_the_adapter(self):
        # The check does not evaluate #if, so a disabled block cannot hide an include. It fails
        # closed, and the allowed header stays allowed there.
        text = "#if 0\n#include <zephyr/sys/printk.h>\n#endif\n"
        (violation,) = self.in_adapter(text)
        self.assertEqual("zephyr/sys/printk.h", violation.include)
        self.assertEqual(2, violation.line)
        self.assertEqual([], self.in_adapter("#if 0\n#include <zephyr/kernel.h>\n#endif\n"))

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

    PRODUCT = {
        "app/src/main.c": "#include <stdint.h>\n",
        "workload/src/cycle.c": "#include <stdint.h>\n",
    }

    def test_an_absent_adapter_tree_is_skipped(self):
        # main has no app/os yet, and the check must keep passing there. A clean result alone
        # would also come from a rule that never ran, so the same layout with the tree present
        # must report the violation that the tree holds.
        with_tree = dict(self.PRODUCT, **{"app/os/adapter.c": "#include <zephyr/sys/printk.h>\n"})
        (violation,) = run(with_tree)
        self.assertEqual("app/os/adapter.c", violation.path)
        self.assertEqual("zephyr/sys/printk.h", violation.include)
        self.assertEqual([], run(self.PRODUCT))

    def test_an_absent_adapter_tree_is_not_an_error_on_the_command_line(self):
        repo = Repo(self.PRODUCT)
        self.addCleanup(repo.close)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", str(repo.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("boundary check passed\n", result.stdout)
        self.assertEqual("", result.stderr)

    def test_an_absent_tree_does_not_stop_the_scan_of_the_trees_after_it(self):
        # Each tree alone: every tree before it is absent, so a skip that ended the scan would
        # lose the violation of a later tree, and the adapter is the last one.
        for tree, name in (
            ("app/src", "main.c"),
            ("workload", "cycle.c"),
            ("app/compose", "mount.c"),
            ("app/os", "adapter.c"),
        ):
            files = {f"{tree}/{name}": "#include <zephyr/sys/printk.h>\n"}
            self.assertEqual([f"{tree}/{name}"], [v.path for v in run(files)], tree)

    def test_an_absent_adapter_tree_does_not_hide_the_violations_of_the_other_trees(self):
        files = {
            "app/src/main.c": "#include <zephyr/kernel.h>\n",
            "workload/src/cycle.c": "#include <crux/time.h>\n",
        }
        self.assertEqual(
            ["app/src/main.c", "workload/src/cycle.c"], sorted(v.path for v in run(files))
        )


class FrozenCruxHeaders(unittest.TestCase):
    """app/src and app/os may not include the three frozen Crux headers.

    OS facilities of the product use Zephyr directly in the adapter zone, so a later change must
    not bring Crux Thread, Sync or Serial back. The other public Crux headers stay allowed, and the
    rule does not touch the workload (which has no Crux header at all) or the composition zone.
    Crux Queue is not on the list because Crux no longer publishes <crux/queue.h>; RemovedCruxQueue
    below checks that the header still fails.
    """

    FROZEN = ("crux/thread.h", "crux/sync.h", "crux/serial.h")
    STILL_ALLOWED = ("crux/time.h", "crux/logging.h", "crux/status.h", "crux/file.h")

    def crux_root(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = pathlib.Path(directory.name)
        for name in self.FROZEN + self.STILL_ALLOWED:
            path = root / "components" / "x" / "include" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        return root

    def test_the_frozen_set_is_the_reviewed_set(self):
        self.assertEqual(frozenset(self.FROZEN), check_boundary.FROZEN_CRUX_HEADERS)

    def test_each_frozen_header_fails_in_app_src(self):
        for name in self.FROZEN:
            violations = run({"app/src/workload.c": f"#include <{name}>\n"})
            self.assertEqual([name], reasons(violations), name)
            self.assertIn("frozen", violations[0].reason, name)

    def test_each_frozen_header_fails_in_the_adapter_zone(self):
        for name in self.FROZEN:
            violations = run({"app/os/adapter.c": f"#include <{name}>\n"})
            self.assertEqual([name], reasons(violations), name)
            self.assertIn("frozen", violations[0].reason, name)

    def test_each_frozen_header_fails_when_crux_publishes_it(self):
        root = self.crux_root()
        for name in self.FROZEN:
            for path in ("app/src/a.c", "app/os/a.c"):
                self.assertEqual([name], reasons(run({path: f"#include <{name}>\n"}, root)), path)

    def test_the_message_names_the_header_and_the_way_out(self):
        (violation,) = run({"app/src/a.c": "#include <crux/thread.h>\n"})
        self.assertEqual("app/src/a.c", violation.path)
        self.assertEqual(1, violation.line)
        self.assertIn("frozen", violation.reason)
        self.assertIn("app/os", violation.reason)

    def test_the_other_public_headers_still_pass_in_both_trees(self):
        text = "".join(f"#include <{name}>\n" for name in self.STILL_ALLOWED)
        self.assertEqual([], run({"app/src/a.c": text}))
        self.assertEqual([], run({"app/os/a.c": text}))
        root = self.crux_root()
        self.assertEqual([], run({"app/src/a.c": text}, root))
        self.assertEqual([], run({"app/os/a.c": text}, root))

    def test_the_hardened_scan_forms_find_a_frozen_header(self):
        for text in (
            "  #  include   <crux/serial.h>\n",
            "%:include <crux/serial.h>\n",
            "??=include <crux/serial.h>\n",
            "#include \\\n<crux/serial.h>\n",
            "#include_next <crux/serial.h>\n",
            "#import <crux/serial.h>\n",
        ):
            for tree in ("app/src", "app/os"):
                self.assertEqual(["crux/serial.h"], reasons(run({f"{tree}/a.c": text})), (tree, text))

    def test_a_commented_frozen_include_is_ignored(self):
        text = "/* #include <crux/thread.h> */\n// #include <crux/serial.h>\n"
        self.assertEqual([], run({"app/src/a.c": text}))
        self.assertEqual([], run({"app/os/a.c": text}))

    def test_a_frozen_header_fails_in_a_header_file_too(self):
        self.assertEqual(["crux/sync.h"], reasons(run({"app/src/port.h": "#include <crux/sync.h>\n"})))
        self.assertEqual(["crux/sync.h"], reasons(run({"app/os/port.h": "#include <crux/sync.h>\n"})))

    def test_only_the_two_product_trees_carry_the_rule(self):
        denied = {r.directory: r.deny_crux for r in check_boundary.RULES}
        self.assertEqual(check_boundary.FROZEN_CRUX_HEADERS, denied["app/src"])
        self.assertEqual(check_boundary.FROZEN_CRUX_HEADERS, denied["app/os"])
        self.assertEqual(frozenset(), denied["workload"])
        self.assertEqual(frozenset(), denied["app/compose"])

    def test_the_workload_keeps_its_own_message(self):
        # The workload has no Crux header at all; the deny rule is not what stops it.
        (violation,) = run({"workload/cycle.c": "#include <crux/thread.h>\n"})
        self.assertEqual("Crux header in portable code", violation.reason)

    def test_the_composition_zone_is_not_changed_by_the_rule(self):
        compose = next(r for r in check_boundary.RULES if r.directory == "app/compose")
        self.assertEqual(frozenset(), compose.deny_crux)
        self.assertTrue(compose.allow_crux)

    def test_the_command_line_reports_a_frozen_header(self):
        repo = Repo({"app/os/adapter.c": "#include <crux/thread.h>\n"})
        self.addCleanup(repo.close)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", str(repo.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("app/os/adapter.c:1", result.stdout)
        self.assertIn("frozen", result.stdout)


class RemovedCruxQueue(unittest.TestCase):
    """Crux no longer publishes <crux/queue.h>, and product code still may not include it.

    The header left the frozen list because the pinned Crux removed it. The guarantee now comes from
    the list of public headers: with --crux-root (CI always passes it) a <crux/NAME.h> that the
    checkout does not publish fails in every tree, the composition zone included.
    """

    PUBLISHED = ("crux/thread.h", "crux/sync.h", "crux/serial.h", "crux/time.h", "crux/logging.h")

    def crux_root(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = pathlib.Path(directory.name)
        for name in self.PUBLISHED:
            path = root / "components" / "x" / "include" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        return root

    def test_the_queue_header_is_not_frozen_any_more(self):
        self.assertNotIn("crux/queue.h", check_boundary.FROZEN_CRUX_HEADERS)

    def test_the_queue_header_fails_in_every_product_tree_when_crux_does_not_publish_it(self):
        root = self.crux_root()
        for path in ("app/src/a.c", "app/os/a.c", "app/compose/a.c"):
            violations = run({path: "#include <crux/queue.h>\n"}, root)
            self.assertEqual(["crux/queue.h"], reasons(violations), path)
            self.assertEqual(
                "not a public Crux header at the pinned revision", violations[0].reason, path
            )

    def test_the_queue_header_fails_in_the_workload_as_any_crux_header_does(self):
        (violation,) = run({"workload/a.c": "#include <crux/queue.h>\n"}, self.crux_root())
        self.assertEqual("Crux header in portable code", violation.reason)

    def test_the_hardened_scan_forms_find_the_queue_header(self):
        root = self.crux_root()
        for text in (
            "%:include <crux/queue.h>\n",
            "#include \\\n<crux/queue.h>\n",
            "#import <crux/queue.h>\n",
        ):
            for tree in ("app/src", "app/os"):
                self.assertEqual(
                    ["crux/queue.h"], reasons(run({f"{tree}/a.c": text}, root)), (tree, text)
                )

    def test_the_command_line_with_a_crux_root_reports_the_queue_header(self):
        root = self.crux_root()
        repo = Repo({"app/src/main.c": "#include <crux/queue.h>\n"})
        self.addCleanup(repo.close)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_boundary.py"), "--repo", str(repo.root),
             "--crux-root", str(root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("app/src/main.c:1: crux/queue.h: not a public Crux header", result.stdout)


class FrameworkTrees(unittest.TestCase):
    """The trees of the controller framework module and of its interface header.

    include/ holds the interface header that a product includes. framework/src is the portable
    core: the rules of app/src without the Sockets profile and without the workload.
    framework/compose and framework/os are the composition and adapter zones of the module, with
    the same allow-lists as app/compose and app/os, and they reach the core through its header
    files only. A source file of the module that no rule covers fails the check.
    """

    API = "include/controller/framework.h"

    def test_the_framework_rules_are_the_reviewed_rules(self):
        rules = {rule.directory: rule for rule in check_boundary.RULES}
        frozen = check_boundary.FROZEN_CRUX_HEADERS
        expected = {
            "include": (False, True, frozenset(), frozenset(), (), False, frozen, True),
            "framework/src": (False, True, frozenset(), frozenset(), (), False, frozen, True),
            "framework/compose": (
                False, True, check_boundary.COMPOSITION_ZEPHYR_HEADERS,
                check_boundary.COMPOSITION_CRUX_HEADERS, ("framework/src",), True, frozenset(), False,
            ),
            "framework/os": (
                False, True, check_boundary.FRAMEWORK_OS_ZEPHYR_HEADERS, frozenset(),
                ("framework/src",), True, frozen, False,
            ),
        }
        for directory, values in expected.items():
            rule = rules[directory]
            self.assertEqual(
                values,
                (rule.allow_sockets, rule.allow_crux, rule.zephyr_allow, rule.composition_crux,
                 rule.extra_roots, rule.extra_roots_headers_only, rule.deny_crux,
                 rule.framework_api),
                directory,
            )

    def test_the_legacy_zones_keep_their_rules(self):
        rules = {rule.directory: rule for rule in check_boundary.RULES}
        self.assertFalse(rules["app/compose"].framework_api)
        self.assertFalse(rules["app/os"].framework_api)
        self.assertFalse(rules["workload"].framework_api)
        self.assertTrue(rules["app/src"].framework_api)

    # The portable core.

    def test_the_core_may_include_iso_c_public_crux_headers_and_its_own_headers(self):
        files = {
            "framework/src/startup.c": '#include "startup.h"\n#include <crux/time.h>\n#include <stdint.h>\n',
            "framework/src/startup.h": "#include <stddef.h>\n",
        }
        self.assertEqual([], run(files))

    def test_the_core_may_include_no_zephyr_header(self):
        for name in ("zephyr/kernel.h", "zephyr/fs/fs.h", "zephyr/net/sntp.h", "zephyr/devicetree.h"):
            files = {"framework/src/core.c": f"#include <{name}>\n"}
            self.assertEqual([name], reasons(run(files)), name)

    def test_the_core_may_not_use_the_sockets_profile(self):
        files = {"framework/src/core.c": "#include <sys/socket.h>\n"}
        self.assertEqual(["sys/socket.h"], reasons(run(files)))

    def test_the_core_may_not_include_a_composition_interface_or_a_frozen_header(self):
        for name in ("crux/file_zephyr.h", "crux/web_zephyr.h", "crux/thread.h", "crux/sync.h"):
            files = {"framework/src/core.c": f"#include <{name}>\n"}
            self.assertEqual([name], reasons(run(files)), name)

    def test_the_core_may_not_reach_the_workload_or_a_zone_header(self):
        files = {
            "framework/src/core.c": '#include "../../workload/include/workload.h"\n'
                                    '#include "../compose/mount.h"\n#include "../os/thread.h"\n',
            "workload/include/workload.h": "",
            "framework/compose/mount.h": "",
            "framework/os/thread.h": "",
        }
        self.assertEqual(
            ["../../workload/include/workload.h", "../compose/mount.h", "../os/thread.h"],
            reasons(run(files)),
        )

    # The zones of the module.

    def test_the_module_composition_zone_has_the_composition_allow_list(self):
        text = "".join(f"#include <{n}>\n" for n in sorted(check_boundary.COMPOSITION_ZEPHYR_HEADERS))
        text += "#include <crux/file_zephyr.h>\n#include <crux/web_zephyr.h>\n"
        files = {"framework/compose/mount.c": text + '#include "../src/storage_port.h"\n',
                 "framework/src/storage_port.h": "#include <stdint.h>\n"}
        self.assertEqual([], run(files))

    def test_the_module_composition_zone_fails_on_other_zephyr_headers(self):
        files = {"framework/compose/mount.c": "#include <zephyr/kernel.h>\n#include <zephyr/fs/littlefs.h>\n"}
        self.assertEqual(["zephyr/kernel.h", "zephyr/fs/littlefs.h"], reasons(run(files)))

    def test_the_module_adapter_zone_has_the_adapter_allow_list(self):
        files = {"framework/os/sntp.c": "#include <zephyr/kernel.h>\n#include <zephyr/net/sntp.h>\n"
                                        '#include "../src/time_sync_port.h"\n',
                 "framework/src/time_sync_port.h": "#include <stdint.h>\n"}
        self.assertEqual([], run(files))

    def test_the_module_adapter_zone_fails_on_other_headers(self):
        files = {"framework/os/sntp.c": "#include <zephyr/net/socket.h>\n#include <crux/file_zephyr.h>\n"
                                        "#include <crux/thread.h>\n#include <sys/socket.h>\n"}
        self.assertEqual(
            ["zephyr/net/socket.h", "crux/file_zephyr.h", "crux/thread.h", "sys/socket.h"],
            reasons(run(files)),
        )

    def test_the_module_adapter_zone_has_its_supervision_headers(self):
        text = "".join(f"#include <{n}>\n" for n in sorted(check_boundary.FRAMEWORK_OS_ZEPHYR_HEADERS))
        files = {"framework/os/supervisor.c": text + '#include "../src/supervisor_port.h"\n',
                 "framework/src/supervisor_port.h": "#include <stdint.h>\n"}
        self.assertEqual([], run(files))

    def test_the_zones_of_the_module_reach_header_files_of_the_core_only(self):
        for zone in ("framework/compose", "framework/os"):
            files = {f"{zone}/x.c": '#include "../src/core.c"\n', "framework/src/core.c": ""}
            self.assertEqual(["../src/core.c"], reasons(run(files)), zone)

    def test_the_zones_of_the_module_may_not_reach_app_src(self):
        for zone in ("framework/compose", "framework/os"):
            files = {f"{zone}/x.c": '#include "../../app/src/port.h"\n', "app/src/port.h": ""}
            self.assertEqual(["../../app/src/port.h"], reasons(run(files)), zone)

    def test_the_two_zones_of_the_module_may_not_reach_each_other(self):
        files = {
            "framework/compose/a.c": '#include "../os/b.h"\n',
            "framework/os/b.h": "",
            "framework/os/c.c": '#include "../compose/d.h"\n',
            "framework/compose/d.h": "",
        }
        self.assertEqual(["../os/b.h", "../compose/d.h"], reasons(run(files)))

    # The interface header.

    def test_the_interface_header_may_include_iso_c_and_public_crux_headers(self):
        files = {self.API: "#include <stdint.h>\n#include <crux/time.h>\n"}
        self.assertEqual([], run(files))

    def test_the_interface_header_may_include_no_zephyr_header_and_no_core_header(self):
        files = {self.API: '#include <zephyr/kernel.h>\n#include "../../framework/src/startup.h"\n',
                 "framework/src/startup.h": ""}
        self.assertEqual(["zephyr/kernel.h", "../../framework/src/startup.h"], reasons(run(files)))

    def test_the_interface_header_passes_by_name_where_the_rule_allows_it(self):
        text = "#include <controller/framework.h>\n"
        files = {self.API: "", "app/src/main.c": text, "framework/src/framework.c": text}
        self.assertEqual([], run(files))

    def test_the_interface_header_fails_in_the_zones_and_the_workload(self):
        text = "#include <controller/framework.h>\n"
        for tree in ("app/compose", "app/os", "framework/compose", "framework/os", "workload"):
            files = {self.API: "", f"{tree}/x.c": text}
            self.assertEqual(["controller/framework.h"], reasons(run(files)), tree)

    def test_an_interface_name_that_is_not_a_header_of_include_fails(self):
        files = {self.API: "", "app/src/main.c": "#include <controller/missing.h>\n"
                                                  "#include <controller/sub/framework.h>\n"}
        self.assertEqual(
            ["controller/missing.h", "controller/sub/framework.h"], reasons(run(files))
        )

    # Sources that no rule covers.

    def test_a_source_of_the_module_outside_every_tree_fails(self):
        for name in ("framework/extra/x.c", "framework/x.h", "app/extra/main.c",
                     "framework/tools/y.cpp", "app/management/z.inc", "zephyr/x.c", "zephyr/sub/y.h"):
            files = {"app/src/main.c": "", name: ""}
            violations = run(files)
            self.assertEqual([name], [v.path for v in violations], name)
            self.assertIn("no rule", violations[0].reason)

    def test_build_files_and_assets_outside_the_trees_pass(self):
        files = {
            "app/src/main.c": "",
            "framework/management/management.cmake": "",
            "framework/management/site/index.html": "",
            "framework/sources.cmake": "",
            "app/conf/base.conf": "",
            "app/boards/base.overlay": "",
            "zephyr/CMakeLists.txt": "",
            "zephyr/module.yml": "",
        }
        self.assertEqual([], run(files))

    def test_a_source_under_a_checked_tree_is_not_reported_twice(self):
        files = {"framework/src/core.c": "#include <zephyr/kernel.h>\n"}
        self.assertEqual(["zephyr/kernel.h"], reasons(run(files)))

    def test_the_module_trees_alone_are_a_checked_layout(self):
        self.assertEqual([], run({"framework/src/core.c": "#include <stdint.h>\n"}))


class FrameworkAdapterSupervision(unittest.TestCase):
    """The adapter zone of the module, framework/os, holds the health supervision of the framework.

    Its list is the list of app/os plus the Zephyr headers that the supervisor thread, the task
    watchdog, the retained region and the fatal error handler need (FRAMEWORK_OS_ZEPHYR_HEADERS).
    app/os keeps its two headers, and no other tree gains any of the new ones.
    """

    SUPERVISION = {
        "zephyr/task_wdt/task_wdt.h",
        "zephyr/retention/retention.h",
        "zephyr/fatal.h",
        "zephyr/device.h",
        "zephyr/devicetree.h",
    }

    def test_the_module_adapter_allow_list_is_the_reviewed_set(self):
        # Changing this set changes what the boundary lets through: it is a reviewed change of
        # this test, of docs/composition-zone.md and of the pull request that justifies it.
        self.assertEqual(
            {"zephyr/kernel.h", "zephyr/net/sntp.h"} | self.SUPERVISION,
            set(check_boundary.FRAMEWORK_OS_ZEPHYR_HEADERS),
        )
        self.assertIsInstance(check_boundary.FRAMEWORK_OS_ZEPHYR_HEADERS, frozenset)

    def test_the_list_of_app_os_is_unchanged(self):
        self.assertEqual(
            {"zephyr/kernel.h", "zephyr/net/sntp.h"}, set(check_boundary.OS_ADAPTER_ZEPHYR_HEADERS)
        )
        adapter = next(r for r in check_boundary.RULES if r.directory == "app/os")
        self.assertEqual(check_boundary.OS_ADAPTER_ZEPHYR_HEADERS, adapter.zephyr_allow)

    def test_each_supervision_header_passes_in_the_module_adapter_zone(self):
        for name in sorted(self.SUPERVISION):
            files = {"framework/os/supervisor.c": f"#include <{name}>\n"}
            self.assertEqual([], run(files), name)

    def test_each_supervision_header_fails_in_every_other_tree(self):
        for name in sorted(self.SUPERVISION):
            for tree in ("app/src", "app/os", "workload", "include", "framework/src"):
                files = {f"{tree}/x.c": f"#include <{name}>\n"}
                self.assertEqual([name], reasons(run(files)), (tree, name))

    def test_the_composition_zones_gain_only_the_devicetree_header_they_already_had(self):
        for name in sorted(self.SUPERVISION - {"zephyr/devicetree.h"}):
            for tree in ("app/compose", "framework/compose"):
                files = {f"{tree}/x.c": f"#include <{name}>\n"}
                self.assertEqual([name], reasons(run(files)), (tree, name))

    def test_the_retained_memory_driver_header_stays_out(self):
        # The framework uses the retention API, not the retained memory driver underneath it.
        for name in ("zephyr/drivers/retained_mem.h", "zephyr/drivers/watchdog.h",
                     "zephyr/drivers/hwinfo.h", "zephyr/sys/reboot.h", "zephyr/logging/log.h"):
            files = {"framework/os/supervisor.c": f"#include <{name}>\n"}
            self.assertEqual([name], reasons(run(files)), name)


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
