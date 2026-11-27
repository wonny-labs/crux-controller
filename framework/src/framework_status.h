/* SPDX-License-Identifier: Apache-2.0 */
#ifndef FRAMEWORK_STATUS_H
#define FRAMEWORK_STATUS_H

/*
 * What the framework shows through the status service (specification section 4.3, "Reporting"):
 * the controller state, the application state, safe mode, the boot counter and how the boot was
 * classified, the watchdog state, the last-fault record, the thread with the least unused stack and
 * the health of each service. The start function implements these (framework/src/framework.c); the
 * composition zone adds them to the status service as project items
 * (framework/compose/supervision_start.c). Each call copies a value that the framework keeps, does
 * not block and touches no storage, as a status item source must. The texts use lower-case words,
 * digits, spaces and hyphens only.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

void framework_status_controller(char *text, size_t size);
void framework_status_application(char *text, size_t size);
bool framework_status_safe_mode(void);
uint32_t framework_status_boot_counter(void);
void framework_status_boot(char *text, size_t size);
void framework_status_watchdog(char *text, size_t size);
void framework_status_last_fault(char *text, size_t size);
void framework_status_stack(char *text, size_t size);

/* The health of one service (service_id_t of controller_state.h) as the status service shows it:
 * absent, healthy, degraded or failed. */
void framework_status_health(int service, char *text, size_t size);

/* False once the application's registrations have been released, and with no application. */
bool framework_status_application_items(void);

#endif
