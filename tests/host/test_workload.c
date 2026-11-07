/* SPDX-License-Identifier: Apache-2.0 */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "workload/config.h"
#include "workload/cycle.h"
#include "workload/message.h"

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

static workload_config_t good_config(void)
{
    workload_config_t config = {
        .period_ms = 100, .max_catch_up = 4, .payload_len = 8, .node_id = 7};
    return config;
}

static void test_config(void)
{
    workload_config_t config = good_config();

    CHECK(workload_config_validate(&config) == WORKLOAD_OK);
    CHECK(workload_config_validate(NULL) == WORKLOAD_ERR_NULL);

    config = good_config();
    config.period_ms = WORKLOAD_PERIOD_MIN_MS - 1;
    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);
    config.period_ms = WORKLOAD_PERIOD_MIN_MS;
    CHECK(workload_config_validate(&config) == WORKLOAD_OK);
    config.period_ms = WORKLOAD_PERIOD_MAX_MS;
    CHECK(workload_config_validate(&config) == WORKLOAD_OK);
    config.period_ms = WORKLOAD_PERIOD_MAX_MS + 1;
    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);

    config = good_config();
    config.max_catch_up = 0;
    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);
    config.max_catch_up = WORKLOAD_CATCH_UP_MAX;
    CHECK(workload_config_validate(&config) == WORKLOAD_OK);
    config.max_catch_up = WORKLOAD_CATCH_UP_MAX + 1;
    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);

    config = good_config();
    config.payload_len = WORKLOAD_PAYLOAD_MAX;
    CHECK(workload_config_validate(&config) == WORKLOAD_OK);
    config.payload_len = WORKLOAD_PAYLOAD_MAX + 1;
    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);

    config = good_config();
    config.node_id = 0;
    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);
    config.node_id = 1;
    CHECK(workload_config_validate(&config) == WORKLOAD_OK);
    config.node_id = WORKLOAD_NODE_ID_MAX;
    CHECK(workload_config_validate(&config) == WORKLOAD_OK);
    config.node_id = WORKLOAD_NODE_ID_MAX + 1;
    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);
}

static void test_cycle_basic(void)
{
    const workload_config_t config = good_config(); /* period 100, catch-up 4 */
    workload_cycle_t cycle;
    uint32_t due = 99;

    CHECK(workload_cycle_init(&cycle, &config, 1000) == WORKLOAD_OK);
    CHECK(workload_cycle_next_due(&cycle) == 1100);

    CHECK(workload_cycle_poll(&cycle, 1000, &due) == WORKLOAD_OK);
    CHECK(due == 0);
    CHECK(workload_cycle_poll(&cycle, 1099, &due) == WORKLOAD_OK);
    CHECK(due == 0);
    CHECK(workload_cycle_poll(&cycle, 1100, &due) == WORKLOAD_OK);
    CHECK(due == 1);
    CHECK(workload_cycle_next_due(&cycle) == 1200);
    CHECK(workload_cycle_poll(&cycle, 1100, &due) == WORKLOAD_OK);
    CHECK(due == 0);
    CHECK(workload_cycle_count(&cycle) == 1);
    CHECK(workload_cycle_skipped(&cycle) == 0);
}

static void test_cycle_catch_up(void)
{
    const workload_config_t config = good_config();
    workload_cycle_t cycle;
    uint32_t due = 0;

    CHECK(workload_cycle_init(&cycle, &config, 0) == WORKLOAD_OK);
    /* A stall of 350 ms leaves cycles at 100, 200 and 300 due. */
    CHECK(workload_cycle_poll(&cycle, 350, &due) == WORKLOAD_OK);
    CHECK(due == 3);
    CHECK(workload_cycle_next_due(&cycle) == 400);
    CHECK(workload_cycle_count(&cycle) == 3);
    CHECK(workload_cycle_skipped(&cycle) == 0);
}

static void test_cycle_stall_beyond_the_catch_up_limit(void)
{
    const workload_config_t config = good_config(); /* limit 4 */
    workload_cycle_t cycle;
    uint32_t due = 0;

    CHECK(workload_cycle_init(&cycle, &config, 0) == WORKLOAD_OK);
    /* Cycles at 100 .. 1000 are due: ten. Four run, six are dropped. */
    CHECK(workload_cycle_poll(&cycle, 1050, &due) == WORKLOAD_OK);
    CHECK(due == 4);
    CHECK(workload_cycle_count(&cycle) == 4);
    CHECK(workload_cycle_skipped(&cycle) == 6);
    /* The schedule stays on the original grid. */
    CHECK(workload_cycle_next_due(&cycle) == 1100);
    CHECK(workload_cycle_poll(&cycle, 1100, &due) == WORKLOAD_OK);
    CHECK(due == 1);
}

static void test_cycle_time_going_backwards(void)
{
    const workload_config_t config = good_config();
    workload_cycle_t cycle;
    uint32_t due = 5;

    CHECK(workload_cycle_init(&cycle, &config, 5000) == WORKLOAD_OK);
    CHECK(workload_cycle_poll(&cycle, 5100, &due) == WORKLOAD_OK);
    CHECK(due == 1);
    CHECK(workload_cycle_poll(&cycle, 4000, &due) == WORKLOAD_OK);
    CHECK(due == 0);
    CHECK(workload_cycle_next_due(&cycle) == 5200);
}

static void test_cycle_near_the_end_of_64_bit_time(void)
{
    const workload_config_t config = good_config();
    workload_cycle_t cycle;
    uint32_t due = 0;
    const uint64_t last = WORKLOAD_TIME_LIMIT_MS;

    /* Just below the limit the arithmetic stays exact. */
    CHECK(workload_cycle_init(&cycle, &config, last - 1000) == WORKLOAD_OK);
    CHECK(workload_cycle_next_due(&cycle) == last - 900);
    CHECK(workload_cycle_poll(&cycle, last - 1, &due) == WORKLOAD_OK);
    CHECK(due == 4);
    CHECK(workload_cycle_skipped(&cycle) == 5);
    /* Nine cycles were due: four ran, five were dropped, and the grid moved on by nine. */
    CHECK(workload_cycle_next_due(&cycle) == last);

    /* Past the limit the module refuses instead of wrapping. */
    CHECK(workload_cycle_init(&cycle, &config, last + 1) == WORKLOAD_ERR_RANGE);
    CHECK(workload_cycle_init(&cycle, &config, UINT64_MAX) == WORKLOAD_ERR_RANGE);
    CHECK(workload_cycle_init(&cycle, &config, last - 1000) == WORKLOAD_OK);
    CHECK(workload_cycle_poll(&cycle, last + 1, &due) == WORKLOAD_ERR_RANGE);
    CHECK(workload_cycle_poll(&cycle, UINT64_MAX, &due) == WORKLOAD_ERR_RANGE);
}

static void test_cycle_arguments(void)
{
    workload_config_t config = good_config();
    workload_cycle_t cycle;
    uint32_t due = 0;

    CHECK(workload_cycle_init(NULL, &config, 0) == WORKLOAD_ERR_NULL);
    CHECK(workload_cycle_init(&cycle, NULL, 0) == WORKLOAD_ERR_NULL);
    config.period_ms = 1;
    CHECK(workload_cycle_init(&cycle, &config, 0) == WORKLOAD_ERR_RANGE);
    config = good_config();
    CHECK(workload_cycle_init(&cycle, &config, 0) == WORKLOAD_OK);
    CHECK(workload_cycle_poll(NULL, 0, &due) == WORKLOAD_ERR_NULL);
    CHECK(workload_cycle_poll(&cycle, 0, NULL) == WORKLOAD_ERR_NULL);
}

static void test_crc(void)
{
    const uint8_t check[] = "123456789";

    CHECK(workload_crc16(check, 9) == 0x29B1);
    CHECK(workload_crc16(NULL, 0) == 0xFFFF);
}

static workload_message_t sample_message(uint16_t length)
{
    workload_message_t message;

    memset(&message, 0, sizeof message);
    message.node_id = 9;
    message.sequence = 0x01020304u;
    message.payload_len = length;
    for (uint16_t i = 0; i < length; i++) {
        message.payload[i] = (uint8_t)(i * 3 + 1);
    }
    return message;
}

static void test_message_round_trip(void)
{
    const uint16_t lengths[] = {0, 1, 8, WORKLOAD_PAYLOAD_MAX};

    for (size_t i = 0; i < sizeof lengths / sizeof lengths[0]; i++) {
        const workload_message_t in = sample_message(lengths[i]);
        workload_message_t out;
        uint8_t frame[WORKLOAD_FRAME_MAX];
        size_t written = 0;
        size_t consumed = 0;

        memset(&out, 0xAA, sizeof out);
        CHECK(workload_message_encode(&in, frame, sizeof frame, &written) == WORKLOAD_OK);
        CHECK(written == (size_t)WORKLOAD_FRAME_OVERHEAD + lengths[i]);
        CHECK(workload_message_decode(frame, written, &out, &consumed) == WORKLOAD_OK);
        CHECK(consumed == written);
        CHECK(out.node_id == in.node_id);
        CHECK(out.sequence == in.sequence);
        CHECK(out.payload_len == in.payload_len);
        CHECK(memcmp(out.payload, in.payload, lengths[i]) == 0);
    }
}

static void test_message_wire_form(void)
{
    const workload_message_t in = sample_message(2); /* payload 01 04 */
    uint8_t frame[WORKLOAD_FRAME_MAX];
    size_t written = 0;

    CHECK(workload_message_encode(&in, frame, sizeof frame, &written) == WORKLOAD_OK);
    CHECK(written == 14);
    CHECK(frame[0] == 0x57); /* magic 'W' */
    CHECK(frame[1] == 1);    /* version */
    CHECK(frame[2] == 9);    /* node id */
    CHECK(frame[3] == 0);    /* flags */
    CHECK(frame[4] == 0x01 && frame[5] == 0x02 && frame[6] == 0x03 && frame[7] == 0x04);
    CHECK(frame[8] == 0x00 && frame[9] == 0x02);
    CHECK(frame[10] == 0x01 && frame[11] == 0x04);
    CHECK((uint16_t)((frame[12] << 8) | frame[13]) == workload_crc16(frame, 12));
}

static void test_message_encode_errors(void)
{
    const workload_message_t in = sample_message(8);
    uint8_t frame[WORKLOAD_FRAME_MAX];
    size_t written = 77;

    /* Every capacity below the frame size is a short buffer, and writes nothing. */
    for (size_t capacity = 0; capacity < (size_t)WORKLOAD_FRAME_OVERHEAD + 8; capacity++) {
        memset(frame, 0xEE, sizeof frame);
        written = 77;
        CHECK(workload_message_encode(&in, frame, capacity, &written) ==
              WORKLOAD_ERR_SHORT_BUFFER);
        CHECK(written == 77);
        CHECK(frame[0] == 0xEE);
    }
    CHECK(workload_message_encode(&in, frame, (size_t)WORKLOAD_FRAME_OVERHEAD + 8, &written) ==
          WORKLOAD_OK);

    {
        workload_message_t bad = in;
        bad.payload_len = WORKLOAD_PAYLOAD_MAX + 1;
        CHECK(workload_message_encode(&bad, frame, sizeof frame, &written) ==
              WORKLOAD_ERR_RANGE);
    }
    CHECK(workload_message_encode(NULL, frame, sizeof frame, &written) == WORKLOAD_ERR_NULL);
    CHECK(workload_message_encode(&in, NULL, sizeof frame, &written) == WORKLOAD_ERR_NULL);
    CHECK(workload_message_encode(&in, frame, sizeof frame, NULL) == WORKLOAD_ERR_NULL);
}

static void test_message_truncated_input(void)
{
    const workload_message_t in = sample_message(8);
    uint8_t frame[WORKLOAD_FRAME_MAX];
    size_t written = 0;

    CHECK(workload_message_encode(&in, frame, sizeof frame, &written) == WORKLOAD_OK);
    for (size_t length = 0; length < written; length++) {
        workload_message_t out;
        size_t consumed = 55;

        memset(&out, 0xAA, sizeof out);
        CHECK(workload_message_decode(frame, length, &out, &consumed) == WORKLOAD_ERR_TRUNCATED);
        CHECK(consumed == 55);
        CHECK(out.node_id == 0xAA);
    }
}

static void fix_crc(uint8_t *frame, size_t length)
{
    const uint16_t crc = workload_crc16(frame, length - 2);

    frame[length - 2] = (uint8_t)(crc >> 8);
    frame[length - 1] = (uint8_t)crc;
}

static void test_message_malformed_input(void)
{
    const workload_message_t in = sample_message(8);
    uint8_t original[WORKLOAD_FRAME_MAX];
    size_t length = 0;

    CHECK(workload_message_encode(&in, original, sizeof original, &length) == WORKLOAD_OK);

    for (int mutation = 0; mutation < 6; mutation++) {
        uint8_t frame[WORKLOAD_FRAME_MAX];
        workload_message_t out;
        size_t consumed = 55;

        memcpy(frame, original, length);
        switch (mutation) {
        case 0: frame[0] ^= 0xFF; break;          /* magic */
        case 1: frame[1] = 2; fix_crc(frame, length); break;     /* version */
        case 2: frame[3] = 1; fix_crc(frame, length); break;     /* reserved flags */
        case 3: frame[length - 1] ^= 0x01; break; /* checksum */
        case 4: frame[5] ^= 0x01; break;          /* sequence changed, checksum stale */
        default:
            /* payload length field above the maximum, with a matching checksum */
            frame[8] = 0x00;
            frame[9] = WORKLOAD_PAYLOAD_MAX + 1;
            fix_crc(frame, length);
            break;
        }
        memset(&out, 0xAA, sizeof out);
        CHECK(workload_message_decode(frame, length, &out, &consumed) == WORKLOAD_ERR_FORMAT);
        CHECK(consumed == 55);
        CHECK(out.node_id == 0xAA);
    }
}

static void test_message_trailing_bytes_are_left_alone(void)
{
    const workload_message_t in = sample_message(3);
    uint8_t frame[WORKLOAD_FRAME_MAX + 5];
    workload_message_t out;
    size_t written = 0;
    size_t consumed = 0;

    CHECK(workload_message_encode(&in, frame, sizeof frame, &written) == WORKLOAD_OK);
    memset(frame + written, 0x5A, 5);
    CHECK(workload_message_decode(frame, written + 5, &out, &consumed) == WORKLOAD_OK);
    CHECK(consumed == written);
}

static void test_message_decode_arguments(void)
{
    const workload_message_t in = sample_message(1);
    uint8_t frame[WORKLOAD_FRAME_MAX];
    workload_message_t out;
    size_t written = 0;
    size_t consumed = 0;

    CHECK(workload_message_encode(&in, frame, sizeof frame, &written) == WORKLOAD_OK);
    CHECK(workload_message_decode(NULL, written, &out, &consumed) == WORKLOAD_ERR_NULL);
    CHECK(workload_message_decode(frame, written, NULL, &consumed) == WORKLOAD_ERR_NULL);
    CHECK(workload_message_decode(frame, written, &out, NULL) == WORKLOAD_ERR_NULL);
}

int main(void)
{
    test_config();
    test_cycle_basic();
    test_cycle_catch_up();
    test_cycle_stall_beyond_the_catch_up_limit();
    test_cycle_time_going_backwards();
    test_cycle_near_the_end_of_64_bit_time();
    test_cycle_arguments();
    test_crc();
    test_message_round_trip();
    test_message_wire_form();
    test_message_encode_errors();
    test_message_truncated_input();
    test_message_malformed_input();
    test_message_trailing_bytes_are_left_alone();
    test_message_decode_arguments();

    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
