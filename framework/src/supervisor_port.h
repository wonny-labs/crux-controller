/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SUPERVISOR_PORT_H
#define SUPERVISOR_PORT_H

/*
 * The port of the supervisor (specification sections 4.1 to 4.4), implemented in the adapter zone
 * (framework/os/supervisor_zephyr.c): one thread in the supervisor band that holds the single
 * crux_watchdog_t token, the Zephyr task watchdog with one channel per supervised framework thread
 * and no hardware fallback, and the step deadlines of startup. The decisions are those of
 * supervision.h.
 *
 * Once per period the thread asks supervision_poll(). It feeds the Crux watchdog only on
 * SUPERVISION_FEED. On SUPERVISION_LATCH it stops feeding first, then writes the fault record
 * (recovery_fault()), and, when the watchdog is not armed, requests a software reset with
 * crux_system_reset(); with an armed watchdog the unfed watchdog resets the device within T. While
 * nothing is latched it calls the tick function of the configuration, on its own thread.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Called once per period on the supervisor thread while no fault is latched. */
typedef void (*supervisor_port_tick_t)(uint64_t now_ms);

typedef struct {
    uint32_t timeout_ms; /* T: the one watchdog timeout of the boot */
    uint32_t period_ms;  /* the supervisor's period; T is at least twice as long */
    supervisor_port_tick_t tick;
} supervisor_port_config_t;

typedef enum {
    SUPERVISOR_PORT_ARMED = 0,     /* the thread runs and the hardware watchdog is armed */
    SUPERVISOR_PORT_NOT_ARMED = 1, /* the thread runs; Crux System did not arm the watchdog */
    SUPERVISOR_PORT_ERR = -1,      /* nothing started: a second start or an invalid configuration */
} supervisor_port_status_t;

/* Start the supervisor thread and arm the watchdog with T. *watchdog_status, when not NULL,
 * receives the crux_status_t of crux_watchdog_start(). */
supervisor_port_status_t supervisor_port_start(const supervisor_port_config_t *config,
                                               int *watchdog_status);

/* A startup step begins and ends; the deadline counts from the begin. Zero: no deadline. */
void supervisor_port_step_begin(const char *name, uint32_t deadline_ms);
void supervisor_port_step_end(void);

/*
 * Activate a task watchdog channel for the calling framework thread, fed now. The name is borrowed
 * for the program's life. Returns a handle of zero or more, or a negative value when the table or
 * the task watchdog is full.
 */
int supervisor_port_channel_add(const char *name, uint32_t reload_ms);

/* Feed the channel of a handle. */
void supervisor_port_channel_feed(int handle);

/*
 * The thread with the least unused stack, as the supervisor last measured it (about every ten
 * periods). False before the first measurement, or in an image without stack information.
 */
bool supervisor_port_stack_min(char *name, size_t size, uint32_t *unused_bytes);

/* Milliseconds since boot. */
uint64_t supervisor_port_uptime_ms(void);

/* Sleep for good: a stalled thread for a fault injection of the scenarios. */
void supervisor_port_stall(void);

/* Raise a fatal error on the calling thread, for a fault injection of the scenarios. */
void supervisor_port_fatal(void);

#endif
