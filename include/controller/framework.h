/* SPDX-License-Identifier: Apache-2.0 */
#ifndef CONTROLLER_FRAMEWORK_H
#define CONTROLLER_FRAMEWORK_H

/*
 * The controller framework: the start function that composes the Crux services of a networked
 * controller. A product's main() calls it once, from the main thread, after the Zephyr network
 * configuration has brought the interface up; the base image of this repository does the same.
 *
 * This version takes no application. It starts the services that the build turns on
 * (CONFIG_CRUX_CONTROLLER_FRAMEWORK_*), in the order of framework/src/framework.c, logs the name
 * and result of each phase through Crux Logging under the tag "framework", and returns. A service
 * that fails is reported and the controller runs without it; only a clock that does not answer
 * stops startup. The function creates no thread for an application.
 *
 * The interface has no stability promise yet: it changes when the application interface is added.
 */

typedef enum {
    CONTROLLER_FRAMEWORK_OK = 0,                   /* Startup ran; failed services were reported. */
    CONTROLLER_FRAMEWORK_ERR_ALREADY_STARTED = -1, /* A second call; nothing ran. */
    CONTROLLER_FRAMEWORK_ERR_STARTUP = -2, /* A required phase failed and startup stopped. */
} controller_framework_status_t;

controller_framework_status_t controller_framework_start(void);

#endif
