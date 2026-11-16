/* SPDX-License-Identifier: Apache-2.0 */
#ifndef MANAGEMENT_POLICY_H
#define MANAGEMENT_POLICY_H

/*
 * The product's policy for HTTPS management, as data and plain C with ISO C includes only, so the
 * host builds and tests it with no Crux or Zephyr header. Step S6 compiles management_policy.c into
 * its image, and the composition zone (app/compose/management_start.c) copies this data into the
 * Crux types.
 *
 * The permission names below are copies, because this file has no Crux include. What backs each
 * one: "access.manage"  CRUX_ACCESS_PERMISSION_MANAGE, defined in crux/access.h, which also defines
 *                    "access.self" (not listed here: every role holds it implicitly).
 *   "config.save"    named by the route table of docs/management-in-a-product.md. The macro that
 *                    carries it, CRUX_CONFIG_SERVICE_PERMISSION_SAVE in crux/config_service.h, was
 *                    read by the author only.
 *   "status.read"    CRUX_MGMT_STATUS_PERMISSION_READ in crux/management_status.h, read by the
 *                    author only; no second source states the value.
 * The two strings that rest on the author's reading are to be confirmed against the header by the
 * composition that passes this data to Crux. An earlier version of this comment asked that
 * composition to assert the equality at build time. It is a start-time refusal instead: the
 * composition passes the three Crux macros to management_permission_names_match() below and
 * refuses to start on a false answer. Two string literals cannot be compared by the preprocessor
 * or the compiler in ISO C, so no build-time check does it. The mismatch path of the function has a
 * host test; the composition's refusal on it has no test that runs without Zephyr.
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

/*
 * The longest version text that the status service accepts, without the terminator. Not verified
 * beyond the author's reading of the comment of crux/management_status.h, which says 63 bytes under
 * a character rule; no other source was checked.
 */
#define MANAGEMENT_VERSION_LENGTH_MAX 63u

/*
 * A role: a name and the exact list of its permissions. It has the same members as
 * crux_access_role_t of crux/access.h, in the same order. Nothing in this repository checks that
 * the two are equivalent beyond the copy itself: the composition copies member by member with
 * designated initializers, so that a member that Crux renames or retypes fails its compile, and
 * it does not rely on sizeof or offsetof of either type.
 */
typedef struct {
    const char *name;
    const char *const *permissions;
    size_t permission_count;
} management_role_t;

/*
 * The roles and the session limits. It has the same members as crux_access_policy_t of
 * crux/access.h, without the password rule hook. The same applies: nothing in this repository
 * checks the equivalence beyond the copy, which sets the hook to NULL for the reference rule.
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
 * Zephyr's HTTP server falls back to every address for a text that is not an address, so a
 * composition that wants one interface checks the text itself, and this is that check. This is
 * stated in docs/management-in-a-product.md and in a comment of
 * components/web/ports/zephyr/web_http_server.c at the pinned revision; the behaviour itself is
 * not verified here.
 */
bool management_address_valid(const char *text);

/*
 * The same check, and on success the four parts of the address in order, so that a composition can
 * name the address in a certificate without a parser of its own or a Zephyr header. The octets are
 * written only when the text is valid, and are left as they were otherwise. A null text or a null
 * destination is refused.
 */
bool management_address_parse(const char *text, uint8_t octets[4]);

/*
 * True when the three texts, which the composition reads from the Crux macros for the manage
 * permission of Access, the status read permission and the configuration save permission, are
 * exactly the product's three names above, in that order. A null pointer is a mismatch.
 */
bool management_permission_names_match(const char *access_manage, const char *status_read,
                                       const char *config_save);

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
