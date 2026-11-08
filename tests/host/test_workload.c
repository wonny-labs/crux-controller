/* SPDX-License-Identifier: Apache-2.0 */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "workload.h"

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

static workload_config_t config_with(uint32_t period_ms, uint32_t message_every)
{
    workload_config_t config = {.period_ms = period_ms, .message_every = message_every};
    return config;
}

static void config_default_is_valid(void)
{
    workload_config_t config;

    memset(&config, 0xAA, sizeof config);
    CHECK(workload_config_default(&config) == WORKLOAD_OK);
    CHECK(workload_config_validate(&config) == WORKLOAD_OK);
    CHECK(workload_config_default(NULL) == WORKLOAD_ERR_RANGE);
    CHECK(workload_config_validate(NULL) == WORKLOAD_ERR_RANGE);
}

static void config_period_9_rejected(void)
{
    const workload_config_t config = config_with(9, 10);

    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);
}

static void config_period_60001_rejected(void)
{
    const workload_config_t config = config_with(60001, 10);

    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);
}

static void config_message_every_0_rejected(void)
{
    const workload_config_t config = config_with(100, 0);

    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);
}

static void config_edges_are_accepted_and_one_beyond_is_not(void)
{
    workload_config_t config = config_with(10, 1);

    CHECK(workload_config_validate(&config) == WORKLOAD_OK);
    config = config_with(60000, 1000);
    CHECK(workload_config_validate(&config) == WORKLOAD_OK);
    config = config_with(100, 1001);
    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);
    config = config_with(UINT32_MAX, 1);
    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);
}

static void cycle_not_due_before_period(void)
{
    const workload_config_t config = config_with(100, 10);
    workload_cycle_t cycle;
    uint32_t elapsed = 99;

    CHECK(workload_cycle_init(&cycle, &config, 1000) == WORKLOAD_OK);
    CHECK(workload_cycle_due(&cycle, &config, 1000, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 0);
    CHECK(workload_cycle_due(&cycle, &config, 1099, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 0);
    CHECK(cycle.cycle == 0);
    CHECK(cycle.next_ms == 1100);
}

static void cycle_due_once_at_period(void)
{
    const workload_config_t config = config_with(100, 10);
    workload_cycle_t cycle;
    uint32_t elapsed = 0;

    CHECK(workload_cycle_init(&cycle, &config, 1000) == WORKLOAD_OK);
    CHECK(workload_cycle_due(&cycle, &config, 1100, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 1);
    CHECK(cycle.cycle == 1);
    CHECK(cycle.next_ms == 1200);
    CHECK(workload_cycle_due(&cycle, &config, 1100, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 0);
}

static void cycle_catches_up_after_stall(void)
{
    const workload_config_t config = config_with(100, 10);
    workload_cycle_t cycle;
    uint32_t elapsed = 0;

    CHECK(workload_cycle_init(&cycle, &config, 0) == WORKLOAD_OK);
    /* A stall of 3.5 periods leaves the cycles at 100, 200 and 300 due. */
    CHECK(workload_cycle_due(&cycle, &config, 350, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 3);
    CHECK(cycle.cycle == 3);
    CHECK(cycle.next_ms == 400); /* still on the original grid */
    CHECK(workload_cycle_due(&cycle, &config, 400, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 1);
}

static void cycle_survives_64bit_time_near_wrap(void)
{
    const workload_config_t config = config_with(10, 1);
    workload_cycle_t cycle;
    uint32_t elapsed = 99;
    const uint64_t start = UINT64_MAX - 5;

    CHECK(workload_cycle_init(&cycle, &config, start) == WORKLOAD_OK);
    CHECK(cycle.next_ms == 4); /* start + 10 wraps past zero */
    CHECK(workload_cycle_due(&cycle, &config, start, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 0);
    CHECK(workload_cycle_due(&cycle, &config, UINT64_MAX, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 0);
    CHECK(workload_cycle_due(&cycle, &config, 3, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 0);
    CHECK(workload_cycle_due(&cycle, &config, 4, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 1);
    CHECK(cycle.next_ms == 14);

    /* A stall across the wrap counts the same as one away from it. */
    CHECK(workload_cycle_init(&cycle, &config, start) == WORKLOAD_OK);
    CHECK(workload_cycle_due(&cycle, &config, 25, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 3); /* due at 4, 14 and 24 */
    CHECK(cycle.next_ms == 34);
}

static void cycle_time_going_backwards_is_not_due(void)
{
    const workload_config_t config = config_with(100, 10);
    workload_cycle_t cycle;
    uint32_t elapsed = 5;

    CHECK(workload_cycle_init(&cycle, &config, 5000) == WORKLOAD_OK);
    CHECK(workload_cycle_due(&cycle, &config, 5100, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 1);
    CHECK(workload_cycle_due(&cycle, &config, 4000, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == 0);
    CHECK(cycle.next_ms == 5200);
}

static void cycle_rejects_a_stall_it_cannot_count(void)
{
    const workload_config_t config = config_with(10, 1);
    workload_cycle_t cycle;
    uint32_t elapsed = 7;
    /* 2^32 cycles are due, one more than the count can report. */
    const uint64_t now = 10u + 10u * (uint64_t)UINT32_MAX;

    CHECK(workload_cycle_init(&cycle, &config, 0) == WORKLOAD_OK);
    CHECK(workload_cycle_due(&cycle, &config, now, &elapsed) == WORKLOAD_ERR_RANGE);
    CHECK(elapsed == 7);
    CHECK(cycle.next_ms == 10);
    CHECK(cycle.cycle == 0);
    /* One cycle fewer fits. */
    CHECK(workload_cycle_due(&cycle, &config, now - 10, &elapsed) == WORKLOAD_OK);
    CHECK(elapsed == UINT32_MAX);
}

static void cycle_rejects_bad_arguments(void)
{
    const workload_config_t good = config_with(100, 10);
    const workload_config_t bad = config_with(1, 10);
    workload_cycle_t cycle;
    uint32_t elapsed = 0;

    CHECK(workload_cycle_init(NULL, &good, 0) == WORKLOAD_ERR_RANGE);
    CHECK(workload_cycle_init(&cycle, NULL, 0) == WORKLOAD_ERR_RANGE);
    CHECK(workload_cycle_init(&cycle, &bad, 0) == WORKLOAD_ERR_RANGE);
    CHECK(workload_cycle_init(&cycle, &good, 0) == WORKLOAD_OK);
    CHECK(workload_cycle_due(NULL, &good, 0, &elapsed) == WORKLOAD_ERR_RANGE);
    CHECK(workload_cycle_due(&cycle, NULL, 0, &elapsed) == WORKLOAD_ERR_RANGE);
    CHECK(workload_cycle_due(&cycle, &bad, 0, &elapsed) == WORKLOAD_ERR_RANGE);
    CHECK(workload_cycle_due(&cycle, &good, 0, NULL) == WORKLOAD_ERR_RANGE);
}

static void message_round_trip(void)
{
    const workload_message_t in = {.cycle = 0x01020304u, .value = 0xA0B0C0D0u};
    workload_message_t out = {0, 0};
    uint8_t buffer[WORKLOAD_MESSAGE_SIZE];
    size_t length = 0;

    CHECK(workload_message_encode(&in, buffer, sizeof buffer, &length) == WORKLOAD_OK);
    CHECK(length == WORKLOAD_MESSAGE_SIZE);
    CHECK(workload_message_decode(buffer, length, &out) == WORKLOAD_OK);
    CHECK(out.cycle == in.cycle);
    CHECK(out.value == in.value);
}

static void message_wire_form_is_big_endian_cycle_then_value(void)
{
    const workload_message_t in = {.cycle = 0x01020304u, .value = 0xA0B0C0D0u};
    const uint8_t expected[8] = {0x01, 0x02, 0x03, 0x04, 0xA0, 0xB0, 0xC0, 0xD0};
    uint8_t buffer[16];
    size_t length = 0;

    memset(buffer, 0xEE, sizeof buffer);
    CHECK(workload_message_encode(&in, buffer, sizeof buffer, &length) == WORKLOAD_OK);
    CHECK(memcmp(buffer, expected, 8) == 0);
    CHECK(buffer[8] == 0xEE); /* nothing written past the message */
}

static void message_encode_small_buffer(void)
{
    const workload_message_t in = {.cycle = 1, .value = 2};

    for (size_t capacity = 0; capacity < WORKLOAD_MESSAGE_SIZE; capacity++) {
        uint8_t buffer[WORKLOAD_MESSAGE_SIZE];
        size_t length = 77;

        memset(buffer, 0xEE, sizeof buffer);
        CHECK(workload_message_encode(&in, buffer, capacity, &length) == WORKLOAD_ERR_SIZE);
        CHECK(length == 77);
        for (size_t i = 0; i < sizeof buffer; i++) {
            CHECK(buffer[i] == 0xEE);
        }
    }
}

static void message_encode_rejects_null(void)
{
    const workload_message_t in = {.cycle = 1, .value = 2};
    uint8_t buffer[WORKLOAD_MESSAGE_SIZE];
    size_t length = 0;

    CHECK(workload_message_encode(NULL, buffer, sizeof buffer, &length) == WORKLOAD_ERR_RANGE);
    CHECK(workload_message_encode(&in, NULL, sizeof buffer, &length) == WORKLOAD_ERR_RANGE);
    CHECK(workload_message_encode(&in, buffer, sizeof buffer, NULL) == WORKLOAD_ERR_RANGE);
}

static void message_decode_truncated(void)
{
    const uint8_t buffer[WORKLOAD_MESSAGE_SIZE] = {0, 0, 0, 1, 0, 0, 0, 2};

    for (size_t length = 0; length < WORKLOAD_MESSAGE_SIZE; length++) {
        workload_message_t out = {0xAAAAAAAAu, 0xBBBBBBBBu};

        CHECK(workload_message_decode(buffer, length, &out) == WORKLOAD_ERR_FORMAT);
        CHECK(out.cycle == 0xAAAAAAAAu);
        CHECK(out.value == 0xBBBBBBBBu);
    }
}

static void message_decode_wrong_length_is_rejected(void)
{
    const uint8_t buffer[WORKLOAD_MESSAGE_SIZE + 1] = {0, 0, 0, 1, 0, 0, 0, 2, 0};
    workload_message_t out = {0xAAAAAAAAu, 0xBBBBBBBBu};

    CHECK(workload_message_decode(buffer, sizeof buffer, &out) == WORKLOAD_ERR_FORMAT);
    CHECK(out.cycle == 0xAAAAAAAAu);
}

static void message_decode_rejects_null(void)
{
    const uint8_t buffer[WORKLOAD_MESSAGE_SIZE] = {0};
    workload_message_t out;

    CHECK(workload_message_decode(NULL, sizeof buffer, &out) == WORKLOAD_ERR_RANGE);
    CHECK(workload_message_decode(buffer, sizeof buffer, NULL) == WORKLOAD_ERR_RANGE);
}

int main(void)
{
    config_default_is_valid();
    config_period_9_rejected();
    config_period_60001_rejected();
    config_message_every_0_rejected();
    config_edges_are_accepted_and_one_beyond_is_not();
    cycle_not_due_before_period();
    cycle_due_once_at_period();
    cycle_catches_up_after_stall();
    cycle_survives_64bit_time_near_wrap();
    cycle_time_going_backwards_is_not_due();
    cycle_rejects_a_stall_it_cannot_count();
    cycle_rejects_bad_arguments();
    message_round_trip();
    message_wire_form_is_big_endian_cycle_then_value();
    message_encode_small_buffer();
    message_encode_rejects_null();
    message_decode_truncated();
    message_decode_wrong_length_is_rejected();
    message_decode_rejects_null();

    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
