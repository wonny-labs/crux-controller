/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TIME_SYNC_H
#define TIME_SYNC_H

/*
 * Step S5: set the realtime clock of Crux Time from an SNTP server. This is the one file pair of
 * the product that calls the Crux Time authority (<crux/time_authority.h>), and nothing else in the
 * image sets the native clock: Crux Time takes its authority calls and the native setters outside
 * Crux are not synchronised with it. What the product decides is in time_sync_policy.h, and the
 * query and the thread are behind the port time_sync_port.h.
 *
 * Call from thread context, after Crux Logging is up. Each decision is reported once through Crux
 * Logging under the tag "time".
 */

/*
 * Prepare the realtime provider of Crux Time (crux_realtime_init, once) and start the clock for
 * the staleness age. Writes no time. Returns 0, or a negative crux_status_t when the provider
 * cannot be prepared; the service is then not ready and time_sync_poll() does nothing.
 */
int time_sync_init(void);

/*
 * One round: query the server, read a Crux Time snapshot, ask the policy and carry out its
 * decision, then report it. A failed query at boot sets nothing. Normally called by the thread
 * that time_sync_start() creates; the native_sim scenario calls it directly.
 */
void time_sync_poll(void);

/*
 * time_sync_init(), then start the low-priority thread that polls: once shortly after the start and
 * then every CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S seconds. Returns 0, or a negative
 * crux_status_t. A failure leaves the product running without time synchronisation.
 */
int time_sync_start(void);

#endif
