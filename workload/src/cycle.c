/* SPDX-License-Identifier: Apache-2.0 */

#include "workload/cycle.h"

#include <stddef.h>

workload_status_t workload_cycle_init(workload_cycle_t *cycle, const workload_config_t *config,
                                      uint64_t now_ms)
{
    if (cycle == NULL || config == NULL) {
        return WORKLOAD_ERR_NULL;
    }
    const workload_status_t valid = workload_config_validate(config);
    if (valid != WORKLOAD_OK) {
        return valid;
    }
    if (now_ms > WORKLOAD_TIME_LIMIT_MS) {
        return WORKLOAD_ERR_RANGE;
    }
    cycle->period_ms = config->period_ms;
    cycle->max_catch_up = config->max_catch_up;
    cycle->next_due_ms = now_ms + config->period_ms;
    cycle->count = 0;
    cycle->skipped = 0;
    return WORKLOAD_OK;
}

workload_status_t workload_cycle_poll(workload_cycle_t *cycle, uint64_t now_ms,
                                      uint32_t *due_out)
{
    if (cycle == NULL || due_out == NULL) {
        return WORKLOAD_ERR_NULL;
    }
    if (now_ms > WORKLOAD_TIME_LIMIT_MS) {
        return WORKLOAD_ERR_RANGE;
    }
    if (now_ms < cycle->next_due_ms) {
        *due_out = 0;
        return WORKLOAD_OK;
    }
    /* now_ms is not above the limit, so next_due_ms stays far from 64-bit wrap-around. */
    const uint64_t due = (now_ms - cycle->next_due_ms) / cycle->period_ms + 1u;
    const uint64_t run = due > cycle->max_catch_up ? cycle->max_catch_up : due;

    cycle->count += run;
    cycle->skipped += due - run;
    cycle->next_due_ms += due * cycle->period_ms;
    *due_out = (uint32_t)run;
    return WORKLOAD_OK;
}

uint64_t workload_cycle_next_due(const workload_cycle_t *cycle)
{
    return cycle->next_due_ms;
}

uint64_t workload_cycle_count(const workload_cycle_t *cycle)
{
    return cycle->count;
}

uint64_t workload_cycle_skipped(const workload_cycle_t *cycle)
{
    return cycle->skipped;
}
