/* SPDX-License-Identifier: Apache-2.0 */

#include "composition.h"

#include <crux/status.h>
#include <crux/time.h>

#ifdef CONFIG_CRUX_THREAD
#include "workload.h"
#include "workload_thread.h"
#endif

int composition_start(void)
{
    crux_monotonic_time_t now;

    /* S0: the clock answers. */
    const crux_status_t clock = crux_monotonic_now(&now);
    if (clock != CRUX_OK) {
        return clock;
    }
#ifdef CONFIG_CRUX_THREAD
    /* S1: the workload runs on Crux threads and reports through Crux Logging. */
    workload_config_t config;

    if (workload_config_default(&config) != WORKLOAD_OK) {
        return CRUX_ERR_INVALID_ARGUMENT;
    }
    return workload_thread_start(&config);
#else
    return 0;
#endif
}
