/* SPDX-License-Identifier: Apache-2.0 */

/* Fault injection for the native_sim scenarios (<controller/framework_test.h>). Built only with
 * CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION, which depends on native_sim. */

#include <controller/framework_test.h>

#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "controller_state.h"
#include "fault_injection.h"

#ifndef CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION
#error "fault_injection.c is built only with CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION"
#endif

#define NAME_SIZE 32u

static controller_framework_fault_t armed;
static char armed_name[NAME_SIZE];
static atomic_bool fatal_taken;
/* One bit per service_id_t that reads as failed. */
static atomic_uint services_down;
/* The application channel whose activation is refused; empty for none. Written before the
 * activation that reads it, by the scenario's thread. */
static char refused_channel[NAME_SIZE];

static int service_of(const char *name)
{
    if (name == NULL) {
        return -1;
    }
    for (int service = 0; service < SERVICE_COUNT; service++) {
        if (strcmp(name, service_id_name((service_id_t)service)) == 0) {
            return service;
        }
    }
    return -1;
}

static int inject_apart(controller_framework_fault_t fault, const char *name)
{
    if (fault == CONTROLLER_FRAMEWORK_FAULT_CHANNEL_REFUSED) {
        if (name == NULL || name[0] == '\0' || strlen(name) >= NAME_SIZE) {
            return -1;
        }
        (void)strcpy(refused_channel, name);
        return 0;
    }
    const int service = service_of(name);

    if (service < 0) {
        return -1;
    }
    if (fault == CONTROLLER_FRAMEWORK_FAULT_SERVICE_DOWN) {
        (void)atomic_fetch_or(&services_down, 1u << (unsigned)service);
    } else {
        (void)atomic_fetch_and(&services_down, ~(1u << (unsigned)service));
    }
    return 0;
}

int controller_framework_inject(controller_framework_fault_t fault, const char *name)
{
    switch (fault) {
    case CONTROLLER_FRAMEWORK_FAULT_SERVICE_DOWN:
    case CONTROLLER_FRAMEWORK_FAULT_SERVICE_UP:
    case CONTROLLER_FRAMEWORK_FAULT_CHANNEL_REFUSED:
        return inject_apart(fault, name);
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

bool fault_injection_service_down(int service)
{
    return service >= 0 && service < SERVICE_COUNT &&
           (atomic_load(&services_down) & (1u << (unsigned)service)) != 0u;
}

bool fault_injection_channel_refused(const char *name)
{
    return name != NULL && refused_channel[0] != '\0' && strcmp(name, refused_channel) == 0;
}
