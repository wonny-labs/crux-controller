/* SPDX-License-Identifier: Apache-2.0 */

#include "workload/message.h"

#include <string.h>

#define MAGIC 0x57u
#define VERSION 1u
#define HEADER_LENGTH 10u
#define CRC_LENGTH 2u

uint16_t workload_crc16(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xFFFFu;

    for (size_t i = 0; i < length; i++) {
        crc ^= (uint16_t)((uint16_t)data[i] << 8);
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x8000u) != 0u ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

workload_status_t workload_message_encode(const workload_message_t *message, uint8_t *buffer,
                                          size_t capacity, size_t *written_out)
{
    if (message == NULL || buffer == NULL || written_out == NULL) {
        return WORKLOAD_ERR_NULL;
    }
    if (message->payload_len > WORKLOAD_PAYLOAD_MAX) {
        return WORKLOAD_ERR_RANGE;
    }
    const size_t total = HEADER_LENGTH + message->payload_len + CRC_LENGTH;
    if (capacity < total) {
        return WORKLOAD_ERR_SHORT_BUFFER;
    }
    buffer[0] = MAGIC;
    buffer[1] = VERSION;
    buffer[2] = message->node_id;
    buffer[3] = 0;
    buffer[4] = (uint8_t)(message->sequence >> 24);
    buffer[5] = (uint8_t)(message->sequence >> 16);
    buffer[6] = (uint8_t)(message->sequence >> 8);
    buffer[7] = (uint8_t)message->sequence;
    buffer[8] = (uint8_t)(message->payload_len >> 8);
    buffer[9] = (uint8_t)message->payload_len;
    memcpy(&buffer[HEADER_LENGTH], message->payload, message->payload_len);
    const uint16_t crc = workload_crc16(buffer, total - CRC_LENGTH);
    buffer[total - 2] = (uint8_t)(crc >> 8);
    buffer[total - 1] = (uint8_t)crc;
    *written_out = total;
    return WORKLOAD_OK;
}

workload_status_t workload_message_decode(const uint8_t *buffer, size_t length,
                                          workload_message_t *message_out, size_t *consumed_out)
{
    if (buffer == NULL || message_out == NULL || consumed_out == NULL) {
        return WORKLOAD_ERR_NULL;
    }
    /* Reject what is already wrong before waiting for more bytes. */
    if ((length >= 1u && buffer[0] != MAGIC) || (length >= 2u && buffer[1] != VERSION) ||
        (length >= 4u && buffer[3] != 0u)) {
        return WORKLOAD_ERR_FORMAT;
    }
    if (length < HEADER_LENGTH) {
        return WORKLOAD_ERR_TRUNCATED;
    }
    const size_t payload_len = ((size_t)buffer[8] << 8) | buffer[9];
    if (payload_len > WORKLOAD_PAYLOAD_MAX) {
        return WORKLOAD_ERR_FORMAT;
    }
    const size_t total = HEADER_LENGTH + payload_len + CRC_LENGTH;
    if (length < total) {
        return WORKLOAD_ERR_TRUNCATED;
    }
    const uint16_t expected = (uint16_t)(((uint16_t)buffer[total - 2] << 8) | buffer[total - 1]);
    if (workload_crc16(buffer, total - CRC_LENGTH) != expected) {
        return WORKLOAD_ERR_FORMAT;
    }
    memset(message_out, 0, sizeof *message_out);
    message_out->node_id = buffer[2];
    message_out->sequence = ((uint32_t)buffer[4] << 24) | ((uint32_t)buffer[5] << 16) |
                            ((uint32_t)buffer[6] << 8) | buffer[7];
    message_out->payload_len = (uint16_t)payload_len;
    memcpy(message_out->payload, &buffer[HEADER_LENGTH], payload_len);
    *consumed_out = total;
    return WORKLOAD_OK;
}
