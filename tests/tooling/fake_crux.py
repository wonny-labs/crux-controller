# SPDX-License-Identifier: Apache-2.0
"""A temporary tree that publishes the headers of a Crux checkout, for the boundary check.

``check_boundary.check(repo, crux_root)`` asks which ``<crux/NAME.h>`` headers Crux publishes: the
public ones under ``components/*/include/crux`` and the composition interfaces under
``components/*/ports/*/include/crux``. Several tests build such a tree for the product as it is, and
the composition zone includes more headers once the management capability exists, so the list lives here once.
"""

import pathlib

# Public headers that the product includes, as the pinned revision of Crux publishes them.
PUBLIC_HEADERS = (
    "access.h", "config_service.h", "credential_store.h", "file.h", "logging.h",
    "management_status.h", "security_event.h", "status.h", "system.h", "time.h", "time_authority.h",
    "tls_certificate.h", "tls_certificate_start.h", "web.h", "web_management.h", "web_session.h",
    "cli.h", "reboot.h", "netif.h", "configuration.h",
)

# Composition interfaces, as (component, header): the zone of framework/compose may include these.
COMPOSITION_HEADERS = (("file", "file_zephyr.h"), ("web", "web_zephyr.h"), ("cli", "cli_zephyr.h"),
                       ("service_priority", "service_priority_zephyr.h"),
                       ("credential", "credential_store_zephyr.h"))


def publish(directory, public=PUBLIC_HEADERS, composition=COMPOSITION_HEADERS):
    """Write empty headers under ``directory`` the way Crux lays them out, and return the path."""
    root = pathlib.Path(directory)
    for name in public:
        header = root / "components" / "x" / "include" / "crux" / name
        header.parent.mkdir(parents=True, exist_ok=True)
        header.write_text("")
    for component, name in composition:
        header = root / "components" / component / "ports" / "zephyr" / "include" / "crux" / name
        header.parent.mkdir(parents=True, exist_ok=True)
        header.write_text("")
    return root
