/* SPDX-License-Identifier: Apache-2.0 */
#ifndef STORAGE_WORKER_PORT_H
#define STORAGE_WORKER_PORT_H

/*
 * The framework's storage worker (specification sections 4.3 and 4.7): one thread in the framework
 * services band (section 7.4) that calls the tick function once per period, so that storage work,
 * such as listing the application data root to see whether it reached its size limit (gap C15),
 * never runs on the supervisor or on a thread of device management. The thread feeds its own task
 * watchdog channel "storage" before and after each tick, so a tick that hangs ends in a reset
 * (section 4.4). Implemented in the adapter zone (framework/os/storage_worker_zephyr.c).
 */

#include <stdint.h>

/* Start the worker once. reload_ms must exceed period_ms plus the longest tick. Returns 0, or -1
 * for a second start, a missing tick or a zero period. */
int storage_worker_port_start(void (*tick)(void), uint32_t period_ms, uint32_t reload_ms);

#endif
