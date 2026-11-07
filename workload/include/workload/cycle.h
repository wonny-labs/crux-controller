/* SPDX-License-Identifier: Apache-2.0 */
#ifndef WORKLOAD_CYCLE_H
#define WORKLOAD_CYCLE_H

#include <stdint.h>

#include "workload/config.h"

#ifdef __cplusplus
extern "C" {
#endif

/** A periodic schedule on a caller-supplied millisecond clock. The caller owns the state. */
typedef struct {
    uint32_t period_ms;
    uint32_t max_catch_up;
    uint64_t next_due_ms;
    uint64_t count;
    uint64_t skipped;
} workload_cycle_t;

/**
 * Start a schedule. The first cycle is due one period after now_ms.
 * Returns WORKLOAD_ERR_RANGE for an invalid configuration or for now_ms above
 * WORKLOAD_TIME_LIMIT_MS.
 */
workload_status_t workload_cycle_init(workload_cycle_t *cycle, const workload_config_t *config,
                                      uint64_t now_ms);

/**
 * Report how many cycles to run now. After a stall, up to max_catch_up cycles are returned
 * and the rest are dropped and counted as skipped. The schedule stays on its original grid.
 * A now_ms earlier than a previous call counts as no elapsed time. A now_ms above
 * WORKLOAD_TIME_LIMIT_MS returns WORKLOAD_ERR_RANGE and changes nothing.
 */
workload_status_t workload_cycle_poll(workload_cycle_t *cycle, uint64_t now_ms,
                                      uint32_t *due_out);

uint64_t workload_cycle_next_due(const workload_cycle_t *cycle);
uint64_t workload_cycle_count(const workload_cycle_t *cycle);   /**< Cycles returned so far. */
uint64_t workload_cycle_skipped(const workload_cycle_t *cycle); /**< Cycles dropped so far. */

#ifdef __cplusplus
}
#endif

#endif
