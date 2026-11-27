/* SPDX-License-Identifier: Apache-2.0 */
#ifndef CONTROLLER_FRAMEWORK_TEST_H
#define CONTROLLER_FRAMEWORK_TEST_H

/*
 * Fault injection for the native_sim scenarios of the controller framework. It exists only in an
 * image with CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION, which depends on native_sim, so no
 * board image can carry it. A scenario calls it before controller_framework_start(), once per boot.
 */

typedef enum {
    CONTROLLER_FRAMEWORK_FAULT_NONE = 0,
    /* The startup step of that name stalls inside its deadline window and never returns. */
    CONTROLLER_FRAMEWORK_FAULT_STEP_STALL,
    /* The framework thread of that name ("time" or "reboot") stops feeding its channel. */
    CONTROLLER_FRAMEWORK_FAULT_THREAD_STALL,
    /* The supervisor thread raises a fatal error once startup has ended. */
    CONTROLLER_FRAMEWORK_FAULT_FATAL,
} controller_framework_fault_t;

/* Arm one fault. Returns 0, or -1 for an unknown fault or a missing name. */
int controller_framework_inject(controller_framework_fault_t fault, const char *name);

#endif
