/* SPDX-License-Identifier: Apache-2.0 */
#ifndef REBOOT_POLICY_H
#define REBOOT_POLICY_H

/*
 * The framework's policy for Crux Reboot and the operator reset marker (specification section 5.1,
 * gap C14). Plain C with ISO C includes only (tests/host/test_reboot_policy.c).
 *
 * The framework starts no Crux reboot worker. Its own reboot thread calls crux_reboot_work_once(),
 * which carries out an accepted request on the calling thread and asks the policy a second time
 * just before the reset. So a policy call that allows the restart on the reboot thread is the last
 * step before the reset, and only that call writes the marker. When crux_reboot_work_once()
 * returns, no reset happened, and the reboot thread clears a marker that the call left.
 *
 * The port is implemented in the adapter zone (framework/os/reboot_zephyr.c), which knows the
 * reboot thread and writes the retained region; the composition zone registers
 * reboot_policy_allow() as the Crux Reboot policy callback (framework/compose/supervision_start.c).
 * Documented but optional: <crux/reboot.h> says that a composition with no worker thread calls
 * crux_reboot_work_once() itself.
 */

#include <stdbool.h>

typedef struct {
    /* True when the caller is the framework's reboot thread. */
    bool (*on_reboot_thread)(void);
    /* The framework's judgement of the restart: true allows it. */
    bool (*restart_allowed)(void);
    /* Set or clear the operator reset marker in the retained region. */
    void (*marker_write)(bool set);
    /* One crux_reboot_work_once(): true when a request ended in a refusal or a failure. */
    bool (*work_once)(void);
} reboot_policy_port_t;

/*
 * The body of the Crux Reboot policy callback: the framework's judgement, and the marker when the
 * restart is allowed on the reboot thread. False for a NULL or incomplete port.
 */
bool reboot_policy_allow(const reboot_policy_port_t *port);

/* One pass of the reboot thread: crux_reboot_work_once(), then clear a marker that it left. */
void reboot_policy_pass(const reboot_policy_port_t *port);

/* The port of this image (framework/os/reboot_zephyr.c). */
const reboot_policy_port_t *reboot_policy_port(void);

#endif
