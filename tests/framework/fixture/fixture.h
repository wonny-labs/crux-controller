/* SPDX-License-Identifier: Apache-2.0 */
#ifndef FIXTURE_H
#define FIXTURE_H

/*
 * The fixture application of the controller framework (specification sections 3 and 8.1): a
 * test-only application that exercises the application interface in the native_sim scenarios. It is
 * no example and no image: it has no board build and no Budget row.
 *
 * It has the four entries of the descriptor. init registers two channel requirements ("worker" and
 * "monitor", 3 s each, longer than the scenarios' start deadline, so a start that hangs is named
 * by its deadline and not by a channel that nobody feeds yet), one status item (fixture.counter)
 * and one parameter (fixture.period), and writes a file (hello.txt) under its data root. start
 * creates two Zephyr threads, each feeding its own channel; stop ends both and joins them;
 * safe_state counts its calls and does nothing else. A behaviour chosen before the start function
 * makes one entry fail or hang, or the worker stop feeding, for the scenarios of faults. The
 * fixture logs through Crux Logging under the tag "fixture"; safe_state logs nothing (section 3.3).
 */

#include <stdbool.h>
#include <stdint.h>

#include <controller/framework.h>

typedef enum {
    FIXTURE_NORMAL = 0,
    FIXTURE_INIT_FAILS,    /* init registers everything, then returns an error */
    FIXTURE_START_FAILS,   /* start creates no thread and returns an error */
    FIXTURE_START_HANGS,   /* start never returns */
    FIXTURE_STOP_FAILS,    /* stop ends nothing and returns an error */
    FIXTURE_STOP_HANGS,    /* stop never returns */
    FIXTURE_THREAD_STALLS, /* the worker stops feeding its channel after a second and stays */
} fixture_behaviour_t;

/* The descriptor, with the behaviour for this boot. */
const controller_app_t *fixture_descriptor(fixture_behaviour_t behaviour);

/* A descriptor without safe_state, which the start function refuses (criterion 5). */
const controller_app_t *fixture_incomplete_descriptor(void);

/* Ask the worker thread to report a fault of the application (section 4.8). */
void fixture_report_fault(void);

/* Counts of the entries' calls in this boot. */
unsigned fixture_inits(void);
unsigned fixture_starts(void);
unsigned fixture_stops(void);
unsigned fixture_safe_states(void);

/*
 * Wait for the next stop that succeeds. fixture_expect_stop() forgets earlier stops; then
 * fixture_wait_for_stop() returns true once a stop has ended both threads, before stop returns, so
 * a waiting thread of the application thread's priority runs right after that stop and its
 * safe_state, and before a lower-priority thread such as the reboot thread goes on.
 */
void fixture_expect_stop(void);
bool fixture_wait_for_stop(int32_t timeout_ms);

/* The reason of the last stop, or -1 before any. */
int fixture_last_stop_reason(void);

/* The worker's loop count; it grows while the worker runs. */
uint32_t fixture_counter(void);

/* The controller state and a service's health, as the fixture reads them through its context. */
controller_framework_state_t fixture_controller_state(void);
controller_framework_health_t fixture_health(controller_framework_service_t service);

#endif
