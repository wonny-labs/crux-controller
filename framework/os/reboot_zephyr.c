/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The framework's reboot thread (specification section 5.1, gap C14): it carries out a restart that
 * an operator requested through Crux Reboot, in place of a Crux reboot worker, which the framework
 * does not start. A composition with no worker calls crux_reboot_work_once() itself, as
 * <crux/reboot.h> documents, so the second policy check of a request runs on this thread just
 * before the reset, and only that check writes the operator reset marker (reboot_policy.h).
 *
 * The thread has a task watchdog channel and feeds it before and after each call. One call can wait
 * for Crux Reboot's lock, its delay and its settle wait (1 s, 1 s and 15 s at their defaults), plus
 * its polls, the policy call and its event, so the reload period is longer than that bound.
 *
 * Status: built in CI for the board and run on native_sim; never run on a board.
 */

#include "../src/fault_injection.h"
#include "../src/reboot_policy.h"
#include "../src/reboot_port.h"
#include "../src/recovery.h"
#include "../src/supervisor_port.h"

#include <crux/reboot.h>

#include <stdbool.h>
#include <stddef.h>

#include <zephyr/kernel.h>

/* The device management band of the reference configuration (specification section 7.4). */
#define REBOOT_PRIORITY 12
#define REBOOT_STACK_BYTES 2048
/* The pause between two calls when no request waits. */
#define REBOOT_IDLE_MS 500
/* Longer than one call of crux_reboot_work_once() at Crux's defaults (17 s) plus its polls. */
#define REBOOT_RELOAD_MS 30000u

static K_THREAD_STACK_DEFINE(reboot_stack, REBOOT_STACK_BYTES);
static struct k_thread reboot_thread;
static bool started;

static bool on_reboot_thread(void)
{
    return k_current_get() == &reboot_thread;
}

/* The base image has no application to ask; delivery stage 3 adds the application's judgement. */
static bool restart_allowed(void)
{
    return true;
}

static void marker_write(bool set)
{
    recovery_marker(set);
}

static bool work_once(void)
{
    return crux_reboot_work_once();
}

static const reboot_policy_port_t port = {on_reboot_thread, restart_allowed, marker_write,
                                          work_once};

const reboot_policy_port_t *reboot_policy_port(void)
{
    return &port;
}

static void reboot_run(void *unused0, void *unused1, void *unused2)
{
    ARG_UNUSED(unused0);
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    const int channel = supervisor_port_channel_add("reboot", REBOOT_RELOAD_MS);

    for (;;) {
        supervisor_port_channel_feed(channel);
        if (fault_injection_thread_stalls("reboot")) {
            supervisor_port_stall();
        }
        k_msleep(REBOOT_IDLE_MS);
        supervisor_port_channel_feed(channel);
        reboot_policy_pass(&port);
    }
}

int reboot_port_start(void)
{
    if (started) {
        return -1;
    }
    started = true;
    (void)k_thread_create(&reboot_thread, reboot_stack, K_THREAD_STACK_SIZEOF(reboot_stack),
                          reboot_run, NULL, NULL, NULL, K_PRIO_PREEMPT(REBOOT_PRIORITY), 0,
                          K_NO_WAIT);
    (void)k_thread_name_set(&reboot_thread, "reboot");
    return 0;
}
