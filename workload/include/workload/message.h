/* SPDX-License-Identifier: Apache-2.0 */
#ifndef WORKLOAD_MESSAGE_H
#define WORKLOAD_MESSAGE_H

#include <stddef.h>
#include <stdint.h>

#include "workload/config.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Wire form, all multi-byte fields big-endian:
 *
 *   0       magic 0x57
 *   1       version 1
 *   2       node id
 *   3       flags, reserved, must be 0
 *   4..7    sequence
 *   8..9    payload length, at most WORKLOAD_PAYLOAD_MAX
 *   10..    payload
 *   then    CRC-16/CCITT-FALSE of every byte before it
 */
#define WORKLOAD_FRAME_OVERHEAD 12u
#define WORKLOAD_FRAME_MAX (WORKLOAD_FRAME_OVERHEAD + WORKLOAD_PAYLOAD_MAX)

typedef struct {
    uint8_t node_id;
    uint32_t sequence;
    uint16_t payload_len;
    uint8_t payload[WORKLOAD_PAYLOAD_MAX];
} workload_message_t;

/** CRC-16/CCITT-FALSE: polynomial 0x1021, initial value 0xFFFF, no reflection. */
uint16_t workload_crc16(const uint8_t *data, size_t length);

/**
 * Write one frame. WORKLOAD_ERR_SHORT_BUFFER, WORKLOAD_ERR_RANGE (payload too long) and
 * WORKLOAD_ERR_NULL leave the buffer and *written_out untouched.
 */
workload_status_t workload_message_encode(const workload_message_t *message, uint8_t *buffer,
                                          size_t capacity, size_t *written_out);

/**
 * Read one frame from the start of the buffer. Bytes after the frame are left alone and
 * *consumed_out gives the frame length. WORKLOAD_ERR_TRUNCATED means more bytes may complete
 * the frame; WORKLOAD_ERR_FORMAT means no extra bytes can. Failures leave both outputs untouched.
 */
workload_status_t workload_message_decode(const uint8_t *buffer, size_t length,
                                          workload_message_t *message_out, size_t *consumed_out);

#ifdef __cplusplus
}
#endif

#endif
