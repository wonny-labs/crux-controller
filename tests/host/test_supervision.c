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
        CHECK(supervision_poll(&state, now, &(supervision_channels_t){names, COUNT, 0u}) ==
              SUPERVISION_FEED);
    }
}

static void test_a_step_within_its_deadline_feeds(void)
{
    supervision_t state;

    supervision_init(&state);
    supervision_step_begin(&state, 100u, "web management", 5000u);
    CHECK(supervision_poll(&state, 5100u, &(supervision_channels_t){names, COUNT, 0u}) ==
          SUPERVISION_FEED);
    supervision_step_end(&state);
    CHECK(supervision_poll(&state, 999999u, &(supervision_channels_t){names, COUNT, 0u}) ==
          SUPERVISION_FEED);
}

static void test_a_step_past_its_deadline_latches_once_and_names_the_step(void)
{
    supervision_t state;

    supervision_init(&state);
    supervision_step_begin(&state, 100u, "command line", 5000u);
    CHECK(supervision_poll(&state, 5101u, &(supervision_channels_t){names, COUNT, 0u}) ==
          SUPERVISION_LATCH);
    CHECK(state.latched);
    CHECK(state.reason == BOOT_FAULT_DEADLINE);
    CHECK(strcmp(state.name, "command line") == 0);
    /* Feeding stays stopped, and the record is written once. */
    CHECK(supervision_poll(&state, 5102u, &(supervision_channels_t){names, COUNT, 0u}) ==
          SUPERVISION_STOPPED);
    supervision_step_end(&state);
    CHECK(supervision_poll(&state, 6000u, &(supervision_channels_t){names, COUNT, 0u}) ==
          SUPERVISION_STOPPED);
}

static void test_a_step_without_a_deadline_never_latches(void)
{
    supervision_t state;

    supervision_init(&state);
    supervision_step_begin(&state, 0u, "clock", 0u);
    CHECK(supervision_poll(&state, UINT64_C(1) << 40,
                           &(supervision_channels_t){names, COUNT, 0u}) == SUPERVISION_FEED);
}

static void test_an_expired_channel_latches_and_names_the_channel(void)
{
    supervision_t state;

    supervision_init(&state);
    CHECK(supervision_poll(&state, 10u, &(supervision_channels_t){names, COUNT, 1u << 1}) ==
          SUPERVISION_LATCH);
    CHECK(state.reason == BOOT_FAULT_CHANNEL);
    CHECK(strcmp(state.name, "reboot") == 0);
    CHECK(supervision_poll(&state, 20u, &(supervision_channels_t){names, COUNT, 1u << 1}) ==
          SUPERVISION_STOPPED);
}

static void test_the_lowest_expired_channel_is_named(void)
{
    supervision_t state;

    supervision_init(&state);
    CHECK(supervision_poll(&state, 10u,
                           &(supervision_channels_t){names, COUNT, (1u << 2) | (1u << 0)}) ==
          SUPERVISION_LATCH);
    CHECK(strcmp(state.name, "time") == 0);
}

static void test_a_step_deadline_wins_over_a_channel(void)
{
    supervision_t state;

    supervision_init(&state);
    supervision_step_begin(&state, 0u, "web management", 10u);
    CHECK(supervision_poll(&state, 11u, &(supervision_channels_t){names, COUNT, 1u}) ==
          SUPERVISION_LATCH);
    CHECK(state.reason == BOOT_FAULT_DEADLINE);
}

static void test_an_expired_bit_without_a_name_still_latches(void)
{
    supervision_t state;

    supervision_init(&state);
    CHECK(supervision_poll(&state, 10u, &(supervision_channels_t){names, COUNT, 1u << 5}) ==
          SUPERVISION_LATCH);
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
    CHECK(supervision_poll(&state, 10u, &(supervision_channels_t){names, COUNT, 0u}) ==
          SUPERVISION_STOPPED);
}

/* The supervisor learns of an outside latch once, so that it writes the record, calls safe_state and
 * resets (specification section 4.8: a stop that returns an error). A latch that a poll found is
 * reported by that poll, not again. */
static void test_an_outside_latch_is_reported_once(void)
{
    supervision_t state;
    boot_fault_reason_t reason = BOOT_FAULT_NONE;
    char name[BOOT_NAME_SIZE] = "";

    supervision_init(&state);
    CHECK(!supervision_take_report(&state, &reason, name));
    CHECK(supervision_latch(&state, BOOT_FAULT_STOP, "application"));
    CHECK(supervision_take_report(&state, &reason, name));
    CHECK(reason == BOOT_FAULT_STOP);
    CHECK(strcmp(name, "application") == 0);
    CHECK(!supervision_take_report(&state, &reason, name));

    supervision_init(&state);
    supervision_step_begin(&state, 0u, "application", 5u);
    CHECK(supervision_poll(&state, 6u, &(supervision_channels_t){names, COUNT, 0u}) ==
          SUPERVISION_LATCH);
    CHECK(!supervision_take_report(&state, &reason, name));
    CHECK(!supervision_take_report(NULL, &reason, name));
}

static void test_a_long_name_is_cut(void)
{
    supervision_t state;

    supervision_init(&state);
    supervision_step_begin(&state, 0u, "a step name much longer than the field", 1u);
    CHECK(supervision_poll(&state, 2u, &(supervision_channels_t){names, COUNT, 0u}) ==
          SUPERVISION_LATCH);
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
    supervision_step_begin(NULL, 0u, "x", 1u);
    supervision_step_end(NULL);
    CHECK(supervision_poll(NULL, 0u, &(supervision_channels_t){names, COUNT, 0u}) ==
          SUPERVISION_STOPPED);
    CHECK(!supervision_latch(NULL, BOOT_FAULT_STOP, "x"));

    supervision_t state;

    supervision_init(&state);
    CHECK(supervision_poll(&state, 0u, &(supervision_channels_t){NULL, 0u, 1u}) ==
          SUPERVISION_LATCH);
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
    test_an_outside_latch_is_reported_once();
    test_the_timing_rule();
    test_null_arguments_are_harmless();
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
