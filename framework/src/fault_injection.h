/* SPDX-License-Identifier: Apache-2.0 */
#ifndef FAULT_INJECTION_H
#define FAULT_INJECTION_H

/*
 * The queries behind <controller/framework_test.h>. Without
 * CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION every query answers false, as inline functions,
 * so the framework calls them unconditionally and a board image compiles them away.
 */

#include <stdbool.h>

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION
bool fault_injection_step_stalls(const char *step);
bool fault_injection_thread_stalls(const char *thread);
/* True once, when the fatal error is armed. */
bool fault_injection_fatal_due(void);
#else
static inline bool fault_injection_step_stalls(const char *step)
{
    (void)step;
    return false;
}
static inline bool fault_injection_thread_stalls(const char *thread)
{
    (void)thread;
    return false;
}
static inline bool fault_injection_fatal_due(void)
{
    return false;
}
#endif

#endif
