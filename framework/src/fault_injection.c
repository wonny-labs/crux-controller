/* SPDX-License-Identifier: Apache-2.0 */

/* Fault injection for the native_sim scenarios (<controller/framework_test.h>). Built only with
 * CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION, which depends on native_sim. */

#include <controller/framework_test.h>

#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "fault_injection.h"

#ifndef CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION
#error "fault_injection.c is built only with CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION"
#endif

#define NAME_SIZE 32u

static controller_framework_fault_t armed;
static char armed_name[NAME_SIZE];
static atomic_bool fatal_taken;

int controller_framework_inject(controller_framework_fault_t fault, const char *name)
{
    switch (fault) {
    case CONTROLLER_FRAMEWORK_FAULT_STEP_STALL:
    case CONTROLLER_FRAMEWORK_FAULT_THREAD_STALL:
        if (name == NULL || name[0] == '\0' || strlen(name) >= NAME_SIZE) {
            return -1;
        }
        (void)strcpy(armed_name, name);
        break;
    case CONTROLLER_FRAMEWORK_FAULT_FATAL:
    case CONTROLLER_FRAMEWORK_FAULT_NONE:
        armed_name[0] = '\0';
        break;
    default:
        return -1;
    }
    armed = fault;
    return 0;
}

bool fault_injection_step_stalls(const char *step)
{
    return armed == CONTROLLER_FRAMEWORK_FAULT_STEP_STALL && step != NULL &&
           strcmp(step, armed_name) == 0;
}

bool fault_injection_thread_stalls(const char *thread)
{
    return armed == CONTROLLER_FRAMEWORK_FAULT_THREAD_STALL && thread != NULL &&
           strcmp(thread, armed_name) == 0;
}

bool fault_injection_fatal_due(void)
{
    return armed == CONTROLLER_FRAMEWORK_FAULT_FATAL && !atomic_exchange(&fatal_taken, true);
}
