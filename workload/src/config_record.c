/* SPDX-License-Identifier: Apache-2.0 */

#include "workload.h"

#include <string.h>

static const uint8_t record_tag[4] = {'W', 'C', 'R', '1'};

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

workload_status_t workload_config_default(workload_config_t *out)
{
    if (out == NULL) {
        return WORKLOAD_ERR_RANGE;
    }
    out->period_ms = 100u;
    out->message_every = 10u;
    return WORKLOAD_OK;
}

workload_status_t workload_config_validate(const workload_config_t *config)
{
    if (config == NULL || config->period_ms < WORKLOAD_PERIOD_MIN_MS ||
        config->period_ms > WORKLOAD_PERIOD_MAX_MS ||
        config->message_every < WORKLOAD_MESSAGE_EVERY_MIN ||
        config->message_every > WORKLOAD_MESSAGE_EVERY_MAX) {
        return WORKLOAD_ERR_RANGE;
    }
    return WORKLOAD_OK;
}

workload_status_t workload_config_encode(const workload_config_t *config, uint8_t *buffer,
                                         size_t capacity, size_t *length)
{
    if (config == NULL || buffer == NULL || length == NULL ||
        workload_config_validate(config) != WORKLOAD_OK) {
        return WORKLOAD_ERR_RANGE;
    }
    if (capacity < WORKLOAD_CONFIG_RECORD_SIZE) {
        return WORKLOAD_ERR_SIZE;
    }
    memcpy(buffer, record_tag, sizeof record_tag);
    put_u32(buffer + 4, config->period_ms);
    put_u32(buffer + 8, config->message_every);
    *length = WORKLOAD_CONFIG_RECORD_SIZE;
    return WORKLOAD_OK;
}

workload_status_t workload_config_decode(const uint8_t *buffer, size_t length,
                                         workload_config_t *config)
{
    workload_config_t decoded;

    if (buffer == NULL || config == NULL) {
        return WORKLOAD_ERR_RANGE;
    }
    if (length != WORKLOAD_CONFIG_RECORD_SIZE || memcmp(buffer, record_tag, sizeof record_tag) != 0) {
        return WORKLOAD_ERR_FORMAT;
    }
    decoded.period_ms = get_u32(buffer + 4);
    decoded.message_every = get_u32(buffer + 8);
    if (workload_config_validate(&decoded) != WORKLOAD_OK) {
        return WORKLOAD_ERR_RANGE;
    }
    *config = decoded;
    return WORKLOAD_OK;
}
