/* SPDX-License-Identifier: Apache-2.0 */

/* The framework's storage worker (storage_worker_port.h), with a Zephyr thread. */

#include "../src/storage_worker_port.h"

#include "../src/fault_injection.h"
#include "../src/supervisor_port.h"

#include <stdbool.h>
#include <stdint.h>

#include <zephyr/kernel.h>

/* The framework services band (specification section 7.4), with time synchronisation. */
#define STORAGE_WORKER_PRIORITY 10
#define STORAGE_WORKER_STACK_BYTES 2048

BUILD_ASSERT(CONFIG_NUM_PREEMPT_PRIORITIES > STORAGE_WORKER_PRIORITY,
             "the storage worker's priority must be a preemptive priority");

static K_THREAD_STACK_DEFINE(storage_worker_stack, STORAGE_WORKER_STACK_BYTES);
static struct k_thread storage_worker_thread;
static bool started;
static void (*worker_tick)(void);
static uint32_t worker_period_ms;
static uint32_t worker_reload_ms;

static void storage_worker_run(void *unused0, void *unused1, void *unused2)
{
    ARG_UNUSED(unused0);
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    const int channel = supervisor_port_channel_add("storage", worker_reload_ms);

    for (;;) {
        supervisor_port_channel_feed(channel);
        if (fault_injection_thread_stalls("storage")) {
            supervisor_port_stall();
        }
        worker_tick();
        supervisor_port_channel_feed(channel);
        k_msleep((int32_t)worker_period_ms);
    }
}

int storage_worker_port_start(void (*tick)(void), uint32_t period_ms, uint32_t reload_ms)
{
    if (started || tick == NULL || period_ms == 0u || reload_ms <= period_ms) {
        return -1;
    }
    started = true;
    worker_tick = tick;
    worker_period_ms = period_ms;
    worker_reload_ms = reload_ms;
    (void)k_thread_create(&storage_worker_thread, storage_worker_stack,
                          K_THREAD_STACK_SIZEOF(storage_worker_stack), storage_worker_run, NULL,
                          NULL, NULL, K_PRIO_PREEMPT(STORAGE_WORKER_PRIORITY), 0, K_NO_WAIT);
    (void)k_thread_name_set(&storage_worker_thread, "storage");
    return 0;
}
