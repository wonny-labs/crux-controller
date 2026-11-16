/* SPDX-License-Identifier: Apache-2.0 */

/* The address text of the S6 management groundwork: plain C, no Crux or Zephyr include. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "management_policy.h"

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

int main(void)
{
    a_dotted_ipv4_address_is_valid();
    any_other_text_is_refused();
    no_text_at_all_is_refused();
    the_text_ends_at_the_first_nul_and_nothing_after_it_counts();
    the_boundaries_of_each_part_are_exact();

    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
