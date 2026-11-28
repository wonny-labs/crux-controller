/* SPDX-License-Identifier: Apache-2.0 */
#ifndef CONTROLLER_FRAMEWORK_TEST_H
#define CONTROLLER_FRAMEWORK_TEST_H

/*
 * Fault injection for the native_sim scenarios of the controller framework. It exists only in an
 * image with CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION, which depends on native_sim, so no
 * board image can carry it. A scenario arms the first three before controller_framework_start(),
 * once per boot; the service and channel faults can be armed and changed at any time.
 */

typedef enum {
    CONTROLLER_FRAMEWORK_FAULT_NONE = 0,
    /* The startup step of that name stalls inside its deadline window and never returns. */
    CONTROLLER_FRAMEWORK_FAULT_STEP_STALL,
    /* The framework thread of that name ("time" or "reboot") stops feeding its channel, or the
     * reports of the Crux service thread of that name ("event drain", "web session", "web
     * management" or "console") stop feeding its channel (gap C8). */
    CONTROLLER_FRAMEWORK_FAULT_THREAD_STALL,
    /* The supervisor thread raises a fatal error once startup has ended. */
    CONTROLLER_FRAMEWORK_FAULT_FATAL,
    /* The service of that name ("network", "storage", "access", "configuration", "status", "time",
     * "web" or "command-line") reads as failed until CONTROLLER_FRAMEWORK_FAULT_SERVICE_UP. Kept
     * apart from the fault above: arming it changes no other fault. */
    CONTROLLER_FRAMEWORK_FAULT_SERVICE_DOWN,
    /* The service of that name reads its own health again. */
    CONTROLLER_FRAMEWORK_FAULT_SERVICE_UP,
    /* The activation of the application's channel of that name is refused (specification section
     * 4.4, partial activation). Kept apart from the faults above. */
    CONTROLLER_FRAMEWORK_FAULT_CHANNEL_REFUSED,
} controller_framework_fault_t;

/* Arm one fault. Returns 0, or -1 for an unknown fault or a missing or unknown name. Any thread. */
int controller_framework_inject(controller_framework_fault_t fault, const char *name);

#endif
