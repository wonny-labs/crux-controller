/* SPDX-License-Identifier: Apache-2.0 */
#ifndef APP_PORT_H
#define APP_PORT_H

/*
 * The port of the application thread (specification section 3.3, "One caller"), implemented in the
 * adapter zone (framework/os/app_zephyr.c): one framework thread, named "application", in the
 * startup band (priority 8, below the supervisor), that runs the work function of the start
 * function for each batch of requests. It calls init, start and stop of the application through the
 * application contract (app_contract.h), so those calls never run at the same time. Requests are
 * bits; requests posted while the work function runs wait for the next batch.
 */

#include <stdint.h>

typedef void (*app_port_work_t)(uint32_t requests);

/* Start the thread once. Returns 0, or -1 for a second start or a missing work function. */
int app_port_start(app_port_work_t work);

/* Ask for the requests and return at once, from any thread. */
void app_port_post(uint32_t requests);

/* Ask for the requests and wait until the work function has run them. One caller at a time: the
 * start function during startup, and after startup the reboot thread before a planned reset. */
void app_port_call(uint32_t requests);

#endif
