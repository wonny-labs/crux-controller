/* SPDX-License-Identifier: Apache-2.0 */
#ifndef WORKLOAD_CONFIG_H
#define WORKLOAD_CONFIG_H

#include <stdint.h>

#include "workload/status.h"

#ifdef __cplusplus
extern "C" {
#endif

#define WORKLOAD_PERIOD_MIN_MS 10u
#define WORKLOAD_PERIOD_MAX_MS 60000u
#define WORKLOAD_CATCH_UP_MAX 16u
#define WORKLOAD_PAYLOAD_MAX 64u
#define WORKLOAD_NODE_ID_MAX 250u

/** Largest time, in milliseconds, that the cycle accepts. Half of the 64-bit range keeps
 *  every schedule computation free of wrap-around. */
#define WORKLOAD_TIME_LIMIT_MS ((uint64_t)UINT64_MAX / 2u)

/** The configuration record of the synthetic workload. */
typedef struct {
    uint32_t period_ms;    /**< Cycle period, WORKLOAD_PERIOD_MIN_MS to WORKLOAD_PERIOD_MAX_MS. */
    uint32_t max_catch_up; /**< Cycles run per poll after a stall, 1 to WORKLOAD_CATCH_UP_MAX. */
    uint16_t payload_len;  /**< Bytes of payload per message, 0 to WORKLOAD_PAYLOAD_MAX. */
    uint8_t node_id;       /**< Sender identity, 1 to WORKLOAD_NODE_ID_MAX. */
} workload_config_t;

/** Check every field against its range. */
workload_status_t workload_config_validate(const workload_config_t *config);

#ifdef __cplusplus
}
#endif

#endif
