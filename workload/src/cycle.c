/* SPDX-License-Identifier: Apache-2.0 */

#include "workload.h"

/* Differences of 64-bit times are taken modulo 2^64. A difference of 2^63 or more means
 * "behind", which is how a clock that wraps stays correct. */
#define HALF_RANGE (UINT64_C(1) << 63)

workload_status_t workload_cycle_init(workload_cycle_t *cycle, const workload_config_t *config,
                                      uint64_t now_ms)
{
    if (cycle == NULL || workload_config_validate(config) != WORKLOAD_OK) {
        return WORKLOAD_ERR_RANGE;
    }
    cycle->next_ms = now_ms + config->period_ms;
    cycle->cycle = 0;
    return WORKLOAD_OK;
}

workload_status_t workload_cycle_due(workload_cycle_t *cycle, const workload_config_t *config,
                                     uint64_t now_ms, uint32_t *cycles_elapsed)
{
    if (cycle == NULL || cycles_elapsed == NULL ||
        workload_config_validate(config) != WORKLOAD_OK) {
        return WORKLOAD_ERR_RANGE;
    }
    const uint64_t late_ms = now_ms - cycle->next_ms;
    if (late_ms >= HALF_RANGE) {
        *cycles_elapsed = 0;
        return WORKLOAD_OK;
    }
    const uint64_t due = late_ms / config->period_ms + 1u;
    if (due > UINT32_MAX) {
        return WORKLOAD_ERR_RANGE;
    }
    cycle->next_ms += due * config->period_ms;
    cycle->cycle += (uint32_t)due;
    *cycles_elapsed = (uint32_t)due;
    return WORKLOAD_OK;
}
