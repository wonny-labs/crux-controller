/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The adapter zone of the application thread (framework/src/app_port.h): one Zephyr thread that
 * runs the start function's work function for each batch of requests, so that init, start and stop
 * of the application have one caller (specification section 3.3). The thread sits in the startup
 * band (priority 8, specification section 7.4), below the supervisor, so an application entry that
 * holds the CPU cannot starve supervision; its deadlines are the supervisor's.
 *
 * A request is a bit. app_port_post() adds the bits and wakes the thread; the thread takes every
 * bit that is set and runs the work function once for them, so requests posted during a batch run
 * in the next one. app_port_call() also asks for a completion, which the thread gives after the
 * batch that contained it. app_port_call() has one caller at a time: the start function during
 * startup, then the reboot thread before a planned reset.
 *
 * Status: built in CI for the board and run on native_sim; never run on a board.
 */

#include "../src/app_port.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <zephyr/kernel.h>

#define APP_THREAD_PRIORITY 8
/* The bit of a request that wants a completion; the work function never sees it. */
#define CALL_BIT 0x80000000u

static K_THREAD_STACK_DEFINE(app_stack, CONFIG_CRUX_CONTROLLER_APP_THREAD_STACK);
static struct k_thread app_thread;
static K_SEM_DEFINE(wake, 0, 1);
static K_SEM_DEFINE(done, 0, 1);
static atomic_t pending;
static app_port_work_t work_function;
static atomic_t started;

static void app_run(void *unused0, void *unused1, void *unused2)
{
    ARG_UNUSED(unused0);
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    for (;;) {
        (void)k_sem_take(&wake, K_FOREVER);
        const uint32_t requests = (uint32_t)atomic_clear(&pending);

        if ((requests & ~CALL_BIT) != 0u) {
            work_function(requests & ~CALL_BIT);
        }
        if ((requests & CALL_BIT) != 0u) {
            k_sem_give(&done);
        }
    }
}

int app_port_start(app_port_work_t work)
{
    if (work == NULL || !atomic_cas(&started, 0, 1)) {
        return -1;
    }
    work_function = work;
    (void)k_thread_create(&app_thread, app_stack, K_THREAD_STACK_SIZEOF(app_stack), app_run, NULL,
                          NULL, NULL, K_PRIO_PREEMPT(APP_THREAD_PRIORITY), 0, K_NO_WAIT);
    (void)k_thread_name_set(&app_thread, "application");
    return 0;
}

void app_port_post(uint32_t requests)
{
    if (requests == 0u || atomic_get(&started) == 0) {
        return;
    }
    (void)atomic_or(&pending, (atomic_val_t)(requests & ~CALL_BIT));
    k_sem_give(&wake);
}

void app_port_call(uint32_t requests)
{
    if (requests == 0u || atomic_get(&started) == 0) {
        return;
    }
    (void)atomic_or(&pending, (atomic_val_t)((requests & ~CALL_BIT) | CALL_BIT));
    k_sem_give(&wake);
    (void)k_sem_take(&done, K_FOREVER);
}
