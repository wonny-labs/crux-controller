/* SPDX-License-Identifier: Apache-2.0 */

#include "workload.h"

static void put_u32(uint8_t *out, uint32_t value)
{
    out[0] = (uint8_t)(value >> 24);
    out[1] = (uint8_t)(value >> 16);
    out[2] = (uint8_t)(value >> 8);
    out[3] = (uint8_t)value;
}

static uint32_t get_u32(const uint8_t *in)
{
    return ((uint32_t)in[0] << 24) | ((uint32_t)in[1] << 16) | ((uint32_t)in[2] << 8) | in[3];
}

workload_status_t workload_message_encode(const workload_message_t *message, uint8_t *buffer,
                                          size_t capacity, size_t *length)
{
    if (message == NULL || buffer == NULL || length == NULL) {
        return WORKLOAD_ERR_RANGE;
    }
    if (capacity < WORKLOAD_MESSAGE_SIZE) {
        return WORKLOAD_ERR_SIZE;
    }
    put_u32(buffer, message->cycle);
    put_u32(buffer + 4, message->value);
    *length = WORKLOAD_MESSAGE_SIZE;
    return WORKLOAD_OK;
}

workload_status_t workload_message_decode(const uint8_t *buffer, size_t length,
                                          workload_message_t *message)
{
    if (buffer == NULL || message == NULL) {
        return WORKLOAD_ERR_RANGE;
    }
    if (length != WORKLOAD_MESSAGE_SIZE) {
        return WORKLOAD_ERR_FORMAT;
    }
    message->cycle = get_u32(buffer);
    message->value = get_u32(buffer + 4);
    return WORKLOAD_OK;
}
