/* SPDX-License-Identifier: Apache-2.0 */

#include "workload.h"

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
