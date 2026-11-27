/* SPDX-License-Identifier: Apache-2.0 */

/* The supervisor's decisions (specification sections 4.1 to 4.4): step deadlines, channel expiry
 * and the latch. Plain C, no Crux or Zephyr include. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "supervision.h"

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

static const char *const names[] = {"time", "reboot", "app"};
#define COUNT (sizeof names / sizeof names[0])

static void test_nothing_to_supervise_feeds(void)
{
    supervision_t state;

    supervision_init(&state);
    for (uint64_t now = 0; now < 10000u; now += 1000u) {
        CHECK(supervision_poll(&state, now, 0u, names, COUNT) == SUPERVISION_FEED);
    }
}

static void test_a_step_within_its_deadline_feeds(void)
{
    supervision_t state;

    supervision_init(&state);
    supervision_step_begin(&state, "web management", 5000u, 100u);
    CHECK(supervision_poll(&state, 5100u, 0u, names, COUNT) == SUPERVISION_FEED);
    supervision_step_end(&state);
    CHECK(supervision_poll(&state, 999999u, 0u, names, COUNT) == SUPERVISION_FEED);
}

static void test_a_step_past_its_deadline_latches_once_and_names_the_step(void)
{
    supervision_t state;

    supervision_init(&state);
    supervision_step_begin(&state, "command line", 5000u, 100u);
    CHECK(supervision_poll(&state, 5101u, 0u, names, COUNT) == SUPERVISION_LATCH);
    CHECK(state.latched);
    CHECK(state.reason == BOOT_FAULT_DEADLINE);
    CHECK(strcmp(state.name, "command line") == 0);
    /* Feeding stays stopped, and the record is written once. */
    CHECK(supervision_poll(&state, 5102u, 0u, names, COUNT) == SUPERVISION_STOPPED);
    supervision_step_end(&state);
    CHECK(supervision_poll(&state, 6000u, 0u, names, COUNT) == SUPERVISION_STOPPED);
}

static void test_a_step_without_a_deadline_never_latches(void)
{
    supervision_t state;

    supervision_init(&state);
    supervision_step_begin(&state, "clock", 0u, 0u);
    CHECK(supervision_poll(&state, UINT64_C(1) << 40, 0u, names, COUNT) == SUPERVISION_FEED);
}

static void test_an_expired_channel_latches_and_names_the_channel(void)
{
    supervision_t state;

    supervision_init(&state);
    CHECK(supervision_poll(&state, 10u, 1u << 1, names, COUNT) == SUPERVISION_LATCH);
    CHECK(state.reason == BOOT_FAULT_CHANNEL);
    CHECK(strcmp(state.name, "reboot") == 0);
    CHECK(supervision_poll(&state, 20u, 1u << 1, names, COUNT) == SUPERVISION_STOPPED);
}

static void test_the_lowest_expired_channel_is_named(void)
{
    supervision_t state;

    supervision_init(&state);
    CHECK(supervision_poll(&state, 10u, (1u << 2) | (1u << 0), names, COUNT) == SUPERVISION_LATCH);
    CHECK(strcmp(state.name, "time") == 0);
}

static void test_a_step_deadline_wins_over_a_channel(void)
{
    supervision_t state;

    supervision_init(&state);
    supervision_step_begin(&state, "web management", 10u, 0u);
    CHECK(supervision_poll(&state, 11u, 1u, names, COUNT) == SUPERVISION_LATCH);
    CHECK(state.reason == BOOT_FAULT_DEADLINE);
}

static void test_an_expired_bit_without_a_name_still_latches(void)
{
    supervision_t state;

    supervision_init(&state);
    CHECK(supervision_poll(&state, 10u, 1u << 5, names, COUNT) == SUPERVISION_LATCH);
    CHECK(state.reason == BOOT_FAULT_CHANNEL);
    CHECK(strcmp(state.name, "channel 5") == 0);
}

static void test_an_outside_latch_stops_feeding_once(void)
{
    supervision_t state;

    supervision_init(&state);
    CHECK(supervision_latch(&state, BOOT_FAULT_STOP, "application"));
    CHECK(!supervision_latch(&state, BOOT_FAULT_FATAL, "other"));
    CHECK(state.reason == BOOT_FAULT_STOP);
    CHECK(supervision_poll(&state, 10u, 0u, names, COUNT) == SUPERVISION_STOPPED);
}

static void test_a_long_name_is_cut(void)
{
    supervision_t state;

    supervision_init(&state);
    supervision_step_begin(&state, "a step name much longer than the field", 1u, 0u);
    CHECK(supervision_poll(&state, 2u, 0u, names, COUNT) == SUPERVISION_LATCH);
    CHECK(strlen(state.name) == BOOT_NAME_SIZE - 1u);
}

static void test_the_timing_rule(void)
{
    CHECK(supervision_timing_valid(8000u, 1000u));
    CHECK(supervision_timing_valid(2000u, 1000u));
    CHECK(!supervision_timing_valid(1999u, 1000u));
    CHECK(!supervision_timing_valid(0u, 1000u));
    CHECK(!supervision_timing_valid(8000u, 0u));
}

static void test_null_arguments_are_harmless(void)
{
    supervision_init(NULL);
    supervision_step_begin(NULL, "x", 1u, 0u);
    supervision_step_end(NULL);
    CHECK(supervision_poll(NULL, 0u, 0u, names, COUNT) == SUPERVISION_STOPPED);
    CHECK(!supervision_latch(NULL, BOOT_FAULT_STOP, "x"));

    supervision_t state;

    supervision_init(&state);
    CHECK(supervision_poll(&state, 0u, 1u, NULL, 0u) == SUPERVISION_LATCH);
}

int main(void)
{
    test_nothing_to_supervise_feeds();
    test_a_step_within_its_deadline_feeds();
    test_a_step_past_its_deadline_latches_once_and_names_the_step();
    test_a_step_without_a_deadline_never_latches();
    test_an_expired_channel_latches_and_names_the_channel();
    test_the_lowest_expired_channel_is_named();
    test_a_step_deadline_wins_over_a_channel();
    test_an_expired_bit_without_a_name_still_latches();
    test_an_outside_latch_stops_feeding_once();
    test_a_long_name_is_cut();
    test_the_timing_rule();
    test_null_arguments_are_harmless();
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
