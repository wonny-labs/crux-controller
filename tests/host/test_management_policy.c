/* SPDX-License-Identifier: Apache-2.0 */

/* The address text of the management groundwork: plain C, no Crux or Zephyr include. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "management_policy.h"
#include "management_port.h"

static int failures;
static int checks;

#define CHECK(condition)                                                                           \
    do {                                                                                           \
        checks++;                                                                                  \
        if (!(condition)) {                                                                        \
            failures++;                                                                            \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition);                            \
        }                                                                                          \
    } while (0)

/* A check that a pointer can be used: when it fails, the test function ends, so the checks after it
 * never read through a null pointer. */
#define REQUIRE(condition)                                                                         \
    do {                                                                                           \
        checks++;                                                                                  \
        if (!(condition)) {                                                                        \
            failures++;                                                                            \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition);                            \
            return;                                                                                \
        }                                                                                          \
    } while (0)

static const char *const valid_text[] = {
    "0.0.0.0", "127.0.0.1", "192.168.77.2",  "255.255.255.255", "1.2.3.4",     "10.0.0.0",
    "0.0.0.1", "1.0.0.0",   "100.200.250.9", "9.99.199.249",    "255.0.255.0",
};

static const char *const invalid_text[] = {
    /* Nothing, or only space. */
    "",
    " ",
    /* Whitespace anywhere, including a trailing newline from a file. */
    " 1.2.3.4",
    "1.2.3.4 ",
    "1.2.3.4\n",
    "1.2.3.4\r\n",
    "1.2.3.4\t",
    "1. 2.3.4",
    "1.2 .3.4",
    /* Leading zeros: only a single "0" may start with zero. */
    "01.2.3.4",
    "1.02.3.4",
    "1.2.03.4",
    "1.2.3.04",
    "00.0.0.0",
    "0.0.0.00",
    "001.2.3.4",
    "0.0.0.000",
    /* Above 255, including three digits and four digits. */
    "256.1.1.1",
    "1.256.1.1",
    "1.1.256.1",
    "1.1.1.256",
    "999.1.1.1",
    "300.1.1.1",
    "1000.1.1.1",
    "1.1.1.1000",
    "2550.1.1.1",
    /* A long part: only the cap of three digits stops it from wrapping around to a small value
     * (4294967296 is 0 and 4294967551 is 255 in 32 bits). */
    "4294967296.1.1.1",
    "1.4294967296.1.1",
    "1.1.4294967296.1",
    "1.1.1.4294967296",
    "4294967295.1.1.1",
    "1.4294967295.1.1",
    "1.1.4294967295.1",
    "1.1.1.4294967295",
    "4294967551.1.1.1",
    "1.4294967551.1.1",
    "1.1.4294967551.1",
    "1.1.1.4294967551",
    "1000000000000.1.1.1",
    "1.1000000000000.1.1",
    "1.1.1000000000000.1",
    "1.1.1.1000000000000",
    /* Too few or too many parts, and empty parts. */
    "1",
    "1.2",
    "1.2.3",
    "1.2.3.",
    ".1.2.3",
    ".1.2.3.4",
    "1.2.3.4.",
    "1.2..3",
    "1..2.3.4",
    "1.2.3.4.5",
    "...",
    "....",
    /* Text after the address, and other characters. */
    "1.2.3.4x",
    "1.2.3.4/24",
    "1.2.3.4:443",
    "1.2.3.4,",
    "a.b.c.d",
    "1.2.3.a",
    "0x1.2.3.4",
    "0x7f.0.0.1",
    "1e1.2.3.4",
    "+1.2.3.4",
    "-1.2.3.4",
    "1.2.3.-4",
    "1,2,3,4",
    "1-2-3-4",
    /* Other forms of an address, and a name. */
    "::1",
    "[::1]",
    "localhost",
    "example.com",
    "2130706433",
    /* A digit that is not an ASCII digit (UTF-8 bytes). */
    "\xd9\xa3.1.1.1",
};

static void a_dotted_ipv4_address_is_valid(void)
{
    for (size_t i = 0; i < sizeof valid_text / sizeof valid_text[0]; i++) {
        if (!management_address_valid(valid_text[i])) {
            printf("not accepted: \"%s\"\n", valid_text[i]);
        }
        CHECK(management_address_valid(valid_text[i]));
    }
}

static void any_other_text_is_refused(void)
{
    for (size_t i = 0; i < sizeof invalid_text / sizeof invalid_text[0]; i++) {
        if (management_address_valid(invalid_text[i])) {
            printf("accepted: \"%s\"\n", invalid_text[i]);
        }
        CHECK(!management_address_valid(invalid_text[i]));
    }
}

static void no_text_at_all_is_refused(void)
{
    CHECK(!management_address_valid(NULL));
}

static void the_text_ends_at_the_first_nul_and_nothing_after_it_counts(void)
{
    /* "1.2.3.4" then NUL then more bytes: the text is "1.2.3.4". */
    const char with_tail[] = "1.2.3.4\0junk";
    /* A NUL where a dot would have been: the text is "1.2.3". */
    const char cut_short[] = "1.2.3\0.4";
    /* A NUL at the start: the text is empty. */
    const char empty[] = "\0\x31.2.3.4";

    CHECK(sizeof with_tail > strlen(with_tail) + 1u);
    CHECK(management_address_valid(with_tail));
    CHECK(!management_address_valid(cut_short));
    CHECK(!management_address_valid(empty));
}

static void the_boundaries_of_each_part_are_exact(void)
{
    CHECK(management_address_valid("0.0.0.0"));
    CHECK(management_address_valid("255.255.255.255"));
    CHECK(!management_address_valid("256.255.255.255"));
    CHECK(!management_address_valid("255.256.255.255"));
    CHECK(!management_address_valid("255.255.256.255"));
    CHECK(!management_address_valid("255.255.255.256"));
    CHECK(!management_address_valid("255.255.255.2555"));
}

static void the_parser_gives_the_four_octets_of_each_valid_text(void)
{
    static const struct {
        const char *text;
        uint8_t octets[4];
    } cases[] = {
        {"0.0.0.0", {0, 0, 0, 0}},           {"255.255.255.255", {255, 255, 255, 255}},
        {"192.168.77.2", {192, 168, 77, 2}}, {"127.0.0.1", {127, 0, 0, 1}},
        {"1.2.3.4", {1, 2, 3, 4}},           {"100.200.250.9", {100, 200, 250, 9}},
    };

    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        uint8_t octets[4] = {0xAA, 0xAA, 0xAA, 0xAA};

        CHECK(management_address_parse(cases[i].text, octets));
        CHECK(memcmp(octets, cases[i].octets, sizeof octets) == 0);
    }
}

static void the_parser_refuses_what_the_validator_refuses_and_leaves_the_octets_alone(void)
{
    for (size_t i = 0; i < sizeof invalid_text / sizeof invalid_text[0]; i++) {
        uint8_t octets[4] = {0xAA, 0xBB, 0xCC, 0xDD};
        const uint8_t before[4] = {0xAA, 0xBB, 0xCC, 0xDD};

        CHECK(!management_address_parse(invalid_text[i], octets));
        CHECK(memcmp(octets, before, sizeof octets) == 0);
    }
}

static void the_parser_and_the_validator_agree_on_every_text_of_both_tables(void)
{
    for (size_t i = 0; i < sizeof valid_text / sizeof valid_text[0]; i++) {
        uint8_t octets[4];

        CHECK(management_address_parse(valid_text[i], octets) ==
              management_address_valid(valid_text[i]));
    }
    for (size_t i = 0; i < sizeof invalid_text / sizeof invalid_text[0]; i++) {
        uint8_t octets[4];

        CHECK(management_address_parse(invalid_text[i], octets) ==
              management_address_valid(invalid_text[i]));
    }
}

static void the_parser_refuses_a_null_text_and_a_null_destination(void)
{
    uint8_t octets[4] = {1, 2, 3, 4};

    CHECK(!management_address_parse(NULL, octets));
    CHECK(octets[0] == 1u && octets[3] == 4u);
    CHECK(!management_address_parse("1.2.3.4", NULL));
}

static void the_parser_stops_at_the_first_nul(void)
{
    const char with_tail[] = "1.2.3.4\0junk";
    const char cut_short[] = "1.2.3\0.4";
    uint8_t octets[4] = {0, 0, 0, 0};

    CHECK(management_address_parse(with_tail, octets));
    CHECK(octets[0] == 1u && octets[1] == 2u && octets[2] == 3u && octets[3] == 4u);
    CHECK(!management_address_parse(cut_short, octets));
}

static void the_permission_names_match_only_when_all_three_are_the_policys(void)
{
    CHECK(management_permission_names_match("access.manage", "status.read", "config.save"));
    /* One name different at a time, in each position, and the empty and null cases. */
    CHECK(!management_permission_names_match("access.manag", "status.read", "config.save"));
    CHECK(!management_permission_names_match("access.manage", "status.reed", "config.save"));
    CHECK(!management_permission_names_match("access.manage", "status.read", "config.savee"));
    CHECK(!management_permission_names_match("status.read", "access.manage", "config.save"));
    CHECK(!management_permission_names_match("", "status.read", "config.save"));
    CHECK(!management_permission_names_match("access.manage", NULL, "config.save"));
    CHECK(!management_permission_names_match(NULL, NULL, NULL));
}

/* Copies of the limits that crux_access_init() enforces (crux/access.h at the pinned revision). */
#define ACCESS_NAME_MAX 31u       /* CRUX_ACCESS_NAME_SIZE (32) without the terminator. */
#define ACCESS_PERMISSION_MAX 63u /* CRUX_ACCESS_PERMISSION_MAX. */

static bool has_permission(const management_role_t *role, const char *permission)
{
    for (size_t i = 0; i < role->permission_count; i++) {
        if (strcmp(role->permissions[i], permission) == 0) {
            return true;
        }
    }
    return false;
}

static const management_role_t *role_named(const management_policy_t *policy, const char *name)
{
    for (size_t i = 0; i < policy->role_count; i++) {
        if (strcmp(policy->roles[i].name, name) == 0) {
            return &policy->roles[i];
        }
    }
    return NULL;
}

static void the_policy_has_exactly_an_administrator_and_a_read_only_role(void)
{
    const management_policy_t *policy = management_policy_get();

    REQUIRE(policy != NULL);
    CHECK(policy->role_count == 2u);
    CHECK(role_named(policy, "administrator") != NULL);
    CHECK(role_named(policy, "read-only") != NULL);
    CHECK(strcmp(MANAGEMENT_ROLE_ADMINISTRATOR, "administrator") == 0);
    CHECK(strcmp(MANAGEMENT_ROLE_READ_ONLY, "read-only") == 0);
}

static void the_administrator_holds_exactly_manage_status_read_and_config_save(void)
{
    const management_role_t *role = role_named(management_policy_get(), "administrator");

    REQUIRE(role != NULL);
    CHECK(role->permission_count == 3u);
    CHECK(has_permission(role, "access.manage"));
    CHECK(has_permission(role, "status.read"));
    CHECK(has_permission(role, "config.save"));
}

static void the_read_only_role_holds_status_read_and_nothing_else(void)
{
    const management_role_t *role = role_named(management_policy_get(), "read-only");

    REQUIRE(role != NULL);
    CHECK(role->permission_count == 1u);
    CHECK(has_permission(role, "status.read"));
    CHECK(!has_permission(role, "access.manage"));
    CHECK(!has_permission(role, "config.save"));
    CHECK(!has_permission(role, "access.self"));
}

static void the_session_limits_are_fifteen_minutes_idle_and_eight_hours_absolute(void)
{
    const management_policy_t *policy = management_policy_get();

    REQUIRE(policy != NULL);
    CHECK(policy->session_idle_limit_s == 15u * 60u);
    CHECK(policy->session_absolute_limit_s == 8u * 3600u);
    CHECK(MANAGEMENT_SESSION_IDLE_LIMIT_S == 900u);
    CHECK(MANAGEMENT_SESSION_ABSOLUTE_LIMIT_S == 28800u);
}

static void the_shipped_policy_meets_the_rules_that_access_enforces(void)
{
    CHECK(management_policy_valid(management_policy_get()));
}

static management_policy_t policy_with(const management_role_t *roles, size_t count)
{
    management_policy_t policy = {.roles = roles,
                                  .role_count = count,
                                  .session_idle_limit_s = 60u,
                                  .session_absolute_limit_s = 120u};

    return policy;
}

static void a_policy_that_access_would_refuse_is_refused(void)
{
    static const char *const manage[] = {"access.manage"};
    static const char *const status[] = {"status.read"};
    static const char *const twice[] = {"status.read", "status.read"};
    static const char *const empty_name[] = {""};
    static const char *const null_name[] = {NULL};
    static const char long_permission[ACCESS_PERMISSION_MAX + 2u] =
        "0123456789012345678901234567890123456789012345678901234567890123";
    static const char *const long_permissions[] = {long_permission};
    static const char *const exact_permissions[] = {"0123456789012345678901234567890123456789"
                                                    "01234567890123456789012"};
    static const char long_name[ACCESS_NAME_MAX + 2u] = "01234567890123456789012345678901";
    static const management_role_t good[] = {{"a", manage, 1u}, {"b", status, 1u}};
    static const management_role_t no_manager[] = {{"b", status, 1u}};
    static const management_role_t dup_role[] = {{"a", manage, 1u}, {"a", status, 1u}};
    static const management_role_t dup_permission[] = {{"a", manage, 1u}, {"b", twice, 2u}};
    static const management_role_t no_name[] = {{"", manage, 1u}};
    static const management_role_t null_role_name[] = {{NULL, manage, 1u}};
    static const management_role_t over_long_name[] = {{long_name, manage, 1u}};
    static const management_role_t exact_name[] = {{"0123456789012345678901234567890", manage, 1u}};
    static const management_role_t empty_permission[] = {{"a", manage, 1u}, {"b", empty_name, 1u}};
    static const management_role_t null_permission[] = {{"a", manage, 1u}, {"b", null_name, 1u}};
    static const management_role_t over_long_permission[] = {{"a", manage, 1u},
                                                             {"b", long_permissions, 1u}};
    static const management_role_t exact_permission[] = {{"a", manage, 1u},
                                                         {"b", exact_permissions, 1u}};
    static const management_role_t no_permission_list[] = {{"a", manage, 1u}, {"b", NULL, 1u}};
    static const management_role_t empty_list[] = {{"a", manage, 1u}, {"b", NULL, 0u}};
    management_policy_t policy;

    CHECK(strlen(long_permission) == ACCESS_PERMISSION_MAX + 1u);
    CHECK(strlen(exact_permissions[0]) == ACCESS_PERMISSION_MAX);
    CHECK(strlen(long_name) == ACCESS_NAME_MAX + 1u);
    CHECK(strlen(exact_name[0].name) == ACCESS_NAME_MAX);

    policy = policy_with(good, 2u);
    CHECK(management_policy_valid(&policy));
    CHECK(!management_policy_valid(NULL));

    policy = policy_with(NULL, 0u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(NULL, 1u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(good, 0u);
    CHECK(!management_policy_valid(&policy));

    policy = policy_with(no_manager, 1u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(dup_role, 2u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(dup_permission, 2u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(no_name, 1u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(null_role_name, 1u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(over_long_name, 1u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(exact_name, 1u);
    CHECK(management_policy_valid(&policy));
    policy = policy_with(empty_permission, 2u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(null_permission, 2u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(over_long_permission, 2u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(exact_permission, 2u);
    CHECK(management_policy_valid(&policy));
    policy = policy_with(no_permission_list, 2u);
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(empty_list, 2u);
    CHECK(management_policy_valid(&policy));

    policy = policy_with(good, 2u);
    policy.session_idle_limit_s = 0u;
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(good, 2u);
    policy.session_absolute_limit_s = 0u;
    CHECK(!management_policy_valid(&policy));
    policy = policy_with(good, 2u);
    policy.session_idle_limit_s = 121u;
    CHECK(!management_policy_valid(&policy));
    policy.session_idle_limit_s = 120u;
    CHECK(management_policy_valid(&policy));
}

static void a_version_text_is_one_to_sixty_three_printable_ascii_bytes(void)
{
    static const char sixty_three[] =
        "012345678901234567890123456789012345678901234567890123456789012";
    static const char sixty_four[] =
        "0123456789012345678901234567890123456789012345678901234567890123";

    CHECK(strlen(sixty_three) == 63u);
    CHECK(strlen(sixty_four) == 64u);
    CHECK(MANAGEMENT_VERSION_LENGTH_MAX == 63u);

    CHECK(management_version_valid("1"));
    CHECK(management_version_valid("0.1.0"));
    CHECK(management_version_valid("v1.2.3-rc1+build.5 (debug)"));
    CHECK(management_version_valid(sixty_three));
    CHECK(management_version_valid(" ~"));

    CHECK(!management_version_valid(NULL));
    CHECK(!management_version_valid(""));
    CHECK(!management_version_valid(sixty_four));
    CHECK(!management_version_valid("1.0\n"));
    CHECK(!management_version_valid("1.0\t"));
    CHECK(!management_version_valid("1.0\x7f"));
    CHECK(!management_version_valid("1.0\x1b[0m"));
    CHECK(!management_version_valid("1.0\xc3\xa9"));
    CHECK(!management_version_valid("\x80"));
}

static void the_port_configuration_carries_the_policy_and_two_versions(void)
{
    const management_port_config_t config = {
        .policy = management_policy_get(),
        .platform_version = "platform 1",
        .project_version = "project 1",
    };

    CHECK(management_policy_valid(config.policy));
    CHECK(management_version_valid(config.platform_version));
    CHECK(management_version_valid(config.project_version));
    CHECK(MANAGEMENT_PORT_OK == 0);
    CHECK(MANAGEMENT_PORT_ERR_INVALID_ARGUMENT < 0);
    CHECK(MANAGEMENT_PORT_ERR_ALREADY_STARTED < 0);
    CHECK(MANAGEMENT_PORT_ERR_STEP_FAILED < 0);
}

int main(void)
{
    a_dotted_ipv4_address_is_valid();
    any_other_text_is_refused();
    no_text_at_all_is_refused();
    the_text_ends_at_the_first_nul_and_nothing_after_it_counts();
    the_boundaries_of_each_part_are_exact();
    the_parser_gives_the_four_octets_of_each_valid_text();
    the_parser_refuses_what_the_validator_refuses_and_leaves_the_octets_alone();
    the_parser_and_the_validator_agree_on_every_text_of_both_tables();
    the_parser_refuses_a_null_text_and_a_null_destination();
    the_parser_stops_at_the_first_nul();
    the_permission_names_match_only_when_all_three_are_the_policys();
    the_policy_has_exactly_an_administrator_and_a_read_only_role();
    the_administrator_holds_exactly_manage_status_read_and_config_save();
    the_read_only_role_holds_status_read_and_nothing_else();
    the_session_limits_are_fifteen_minutes_idle_and_eight_hours_absolute();
    the_shipped_policy_meets_the_rules_that_access_enforces();
    a_policy_that_access_would_refuse_is_refused();
    a_version_text_is_one_to_sixty_three_printable_ascii_bytes();
    the_port_configuration_carries_the_policy_and_two_versions();

    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
