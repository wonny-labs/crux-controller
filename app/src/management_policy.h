/* SPDX-License-Identifier: Apache-2.0 */
#ifndef MANAGEMENT_POLICY_H
#define MANAGEMENT_POLICY_H

/*
 * The product's policy for HTTPS management, as data and plain C with ISO C includes only, so the
 * host builds and tests it with no Crux or Zephyr header. No firmware image compiles this file
 * yet: it is groundwork, and the composition that would use it is a later change.
 *
 * The names below are copies of what Crux defines, because this file has no Crux include:
 *   "access.manage"  CRUX_ACCESS_PERMISSION_MANAGE   (crux/access.h)
 *   "status.read"    CRUX_MGMT_STATUS_PERMISSION_READ (crux/management_status.h)
 *   "config.save"    CRUX_CONFIG_SERVICE_PERMISSION_SAVE (crux/config_service.h)
 * The composition that passes this data to Crux must assert at build time that each copy equals
 * the Crux value, as time_sync.c does for the time range. "access.self" is not listed: every role
 * holds it implicitly (crux/access.h).
 *
 * Only the permissions that the web routes of step S6 would check are granted: the status and the
 * configuration save. Nothing else is granted, because no other route is planned.
 *
 * The password rule is not set here. A missing rule selects the Crux Access reference rule, which
 * is the intent. Setting one later is a product decision of its own.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define MANAGEMENT_ROLE_ADMINISTRATOR "administrator"
#define MANAGEMENT_ROLE_READ_ONLY "read-only"

#define MANAGEMENT_PERMISSION_ACCESS_MANAGE "access.manage"
#define MANAGEMENT_PERMISSION_STATUS_READ "status.read"
#define MANAGEMENT_PERMISSION_CONFIG_SAVE "config.save"

/* A session ends after 15 minutes without activity, and at the latest 8 hours after its start. */
#define MANAGEMENT_SESSION_IDLE_LIMIT_S (15u * 60u)
#define MANAGEMENT_SESSION_ABSOLUTE_LIMIT_S (8u * 3600u)

/* The longest version text that the status service accepts, without the terminator. */
#define MANAGEMENT_VERSION_LENGTH_MAX 63u

/* A role: a name and the exact list of its permissions. The layout of crux_access_role_t. */
typedef struct {
    const char *name;
    const char *const *permissions;
    size_t permission_count;
} management_role_t;

/* The roles and the session limits. The layout of crux_access_policy_t without the password rule.
 */
typedef struct {
    const management_role_t *roles;
    size_t role_count;
    uint32_t session_idle_limit_s;
    uint32_t session_absolute_limit_s;
} management_policy_t;

/*
 * True when text is a strict dotted IPv4 address: four decimal parts separated by single dots,
 * each part 0 to 255, written with one to three digits and no leading zero (a part that starts
 * with zero is exactly "0"). No sign, no space, no other character and no text after the last
 * part. A null pointer and the empty text are refused. The text ends at its first NUL, so bytes
 * after a NUL are not seen.
 *
 * The Zephyr web server treats a bind text that is not an address as "every address", so a
 * composition that wants one interface has to refuse such a text itself, and this is the check.
 */
bool management_address_valid(const char *text);

/* The product's policy: the administrator role and the read-only role, and the session limits. */
const management_policy_t *management_policy_get(void);

/*
 * True when the policy meets the rules that crux_access_init() documents and applies (read in
 * crux/access.h and components/access/src/access.c at the pinned revision): at least one role, a
 * role name of 1 to 31 bytes, a permission of 1 to 63 bytes, no duplicate role name, no duplicate
 * permission inside one role, both session limits above zero, the idle limit not above the
 * absolute limit, and at least one role that holds "access.manage". A role with no permissions is
 * allowed. A null policy is refused. This is a host-side check of the data, not a replacement for
 * what Crux does at start.
 */
bool management_policy_valid(const management_policy_t *policy);

/*
 * True when text is one to MANAGEMENT_VERSION_LENGTH_MAX bytes of printable ASCII (0x20 to 0x7E).
 * That is a subset of what the status service accepts, which also allows other well-formed UTF-8
 * but no control character. The subset keeps the version out of terminal and log trouble.
 */
bool management_version_valid(const char *text);

#endif
