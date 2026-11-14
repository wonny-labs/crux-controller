/* SPDX-License-Identifier: Apache-2.0 */
#ifndef WORKLOAD_THREAD_H
#define WORKLOAD_THREAD_H

#include <stdint.h>

#include "workload.h"

/* The value that a message carries for a cycle. Each message is logged as
 * "workload: cycle=<n> value=<v>", so a reader can check it. */
#define WORKLOAD_VALUE_OF(cycle) ((uint32_t)(cycle) ^ 0x5A5A5A5Au)

/* Called on the consumer thread after each message is logged. */
typedef void (*workload_sink_t)(const workload_message_t *message);

/* Set before workload_thread_start. NULL, the default, means no sink. */
void workload_thread_set_sink(workload_sink_t sink);

/* Called on the producer thread. */
typedef void (*workload_cycle_hook_t)(void);

/*
 * Set before workload_thread_start. NULL, the default, means no hook. The producer calls it once for
 * each pass that finds one or more cycles due, before it queues their messages, so a stall that is
 * made up in one pass counts once. Step S4 feeds its watchdog from it. It must not block.
 */
void workload_thread_set_cycle_hook(workload_cycle_hook_t hook);

/*
 * Run the workload on two threads that the adapter zone (app/os) creates through the port
 * workload_os.h: one thread drives the cycle on the Crux monotonic clock and queues a message
 * every config->message_every cycles, another thread takes each message from the queue and logs
 * it through Crux Logging. Returns 0, or a negative crux_status_t.
 */
int workload_thread_start(const workload_config_t *config);

/* Stop both threads, after the queue is drained, and release the queue. Returns 0 or a negative crux_status_t. */
int workload_thread_stop(void);

#endif
