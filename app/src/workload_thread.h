/* SPDX-License-Identifier: Apache-2.0 */
#ifndef WORKLOAD_THREAD_H
#define WORKLOAD_THREAD_H

#include <stdint.h>

#include "workload.h"

/* The value that a message carries for a cycle. Each message is logged as
 * "workload: cycle=<n> value=<v>", so a reader can check it. */
#define WORKLOAD_VALUE_OF(cycle) ((uint32_t)(cycle) ^ 0x5A5A5A5Au)

/*
 * Run the workload on Crux threads: one thread drives the cycle on the Crux monotonic clock
 * and queues a message every config->message_every cycles, another thread takes each message
 * from the queue and logs it through Crux Logging. Returns 0, or a negative crux_status_t.
 */
int workload_thread_start(const workload_config_t *config);

/* Stop both threads, after the queue is drained, and release the queue. Returns 0 or a negative crux_status_t. */
int workload_thread_stop(void);

#endif
