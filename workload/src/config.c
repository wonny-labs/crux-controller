/* SPDX-License-Identifier: Apache-2.0 */

#include "workload/config.h"

#include <stddef.h>

workload_status_t workload_config_validate(const workload_config_t *config)
{
    if (config == NULL) {
        return WORKLOAD_ERR_NULL;
    }
    if (config->period_ms < WORKLOAD_PERIOD_MIN_MS || config->period_ms > WORKLOAD_PERIOD_MAX_MS ||
        config->max_catch_up < 1u || config->max_catch_up > WORKLOAD_CATCH_UP_MAX ||
        config->payload_len > WORKLOAD_PAYLOAD_MAX || config->node_id < 1u ||
        config->node_id > WORKLOAD_NODE_ID_MAX) {
        return WORKLOAD_ERR_RANGE;
    }
    return WORKLOAD_OK;
}
