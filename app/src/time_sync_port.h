/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TIME_SYNC_PORT_H
#define TIME_SYNC_PORT_H

/*
 * The product-owned port to the operating system for step S5. The application declares it and the
 * adapter zone (app/os/time_sync_zephyr.c) implements it with Zephyr kernel calls and the Zephyr
 * SNTP library, so app/src includes no Zephyr, socket or SNTP header: the link joins the two, no
 * include does. This header includes only ISO C and the policy header, which owns the types of an
 * instant and of a query result.
 *
 * The port has one thread, one query at a time and no handle. Calls are made from thread context.
 */

#include <stdint.h>

#include "time_sync_policy.h"

typedef enum {
    TIME_SYNC_PORT_OK = 0,
    TIME_SYNC_PORT_ERROR, /* the thread was started already, or an argument is NULL */
} time_sync_port_status_t;

/*
 * Ask the server for the time and wait about timeout_ms for the answer: the Zephyr query checks its
 * deadline between rounds, so a call can run past it by up to one round's wait (1600 ms at most),
 * or longer while it skips answers to earlier requests. The server is the text that Zephyr's
 * string-based query takes, an IPv4 address with an optional ":port" (port 123 when there is
 * none). Blocks the caller. On TIME_SYNC_SAMPLE_OK, *sample holds the time of the answer;
 * otherwise *sample is not changed. The result names the failure: no answer in time, a
 * kiss-o'-death, or anything else. Only one thread may call it at a time.
 */
time_sync_sample_result_t time_sync_port_query(const char *server, uint32_t timeout_ms,
                                               time_sync_instant_t *sample);

/* Suspend the calling thread for about ms milliseconds. */
void time_sync_port_sleep_ms(uint32_t ms);

/*
 * Create the one low-priority thread of the step, which runs entry once and ends when it returns.
 * TIME_SYNC_PORT_ERROR, with no thread started, when entry is NULL or a thread was started before.
 */
time_sync_port_status_t time_sync_port_start(void (*entry)(void));

#endif
