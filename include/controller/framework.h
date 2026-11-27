/* SPDX-License-Identifier: Apache-2.0 */
#ifndef CONTROLLER_FRAMEWORK_H
#define CONTROLLER_FRAMEWORK_H

/*
 * The controller framework: the start function that composes the Crux services of a networked
 * controller, and the application interface of specification section 3. A product's main() calls
 * the start function once, from the main thread, after the Zephyr network configuration has
 * brought the interface up; the base image of this repository does the same with no application.
 *
 * The start function starts the services that the build turns on
 * (CONFIG_CRUX_CONTROLLER_FRAMEWORK_*) in the order of framework/src/framework.c, logs the name and
 * result of each step through Crux Logging under the tag "framework", and returns. A service that
 * fails is reported and the controller runs without it; only a clock that does not answer stops
 * startup. With health supervision (CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION) the function also
 * decides normal boot or safe mode, arms the watchdog and supervises its steps, and the framework
 * owns k_sys_fatal_error_handler(). Call it from a thread below the supervisor's priority (7), for
 * example the main thread with CONFIG_MAIN_THREAD_PRIORITY=8.
 *
 * The application interface needs health supervision. The framework runs no execution thread for
 * the application: init, start and stop are called from one framework thread ("application"), in
 * that order and never at the same time, and each returns within its deadline (Kconfig
 * CONFIG_CRUX_CONTROLLER_DEADLINE_*); a deadline that passes resets the device. The application
 * creates its own threads with Zephyr and calls Crux's public interfaces directly for logging,
 * time, sockets, files under its data root and configuration reads; the framework wraps none of
 * them. The application may not block a framework thread, take a framework lock or call device
 * management. Status items and the parameter table are registered through
 * <controller/framework_management.h>.
 *
 * Stability: the lowest tier (specification section 3.4). The interface changes until a first real
 * runtime consumer has validated it.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    CONTROLLER_FRAMEWORK_OK = 0,                   /* Startup ran; failed services were reported. */
    CONTROLLER_FRAMEWORK_ERR_ALREADY_STARTED = -1, /* A second call; nothing ran. */
    CONTROLLER_FRAMEWORK_ERR_STARTUP = -2, /* A required phase failed and startup stopped. */
    /* A descriptor without a mandatory entry, or an application in a build without health
     * supervision; nothing ran. */
    CONTROLLER_FRAMEWORK_ERR_INVALID_DESCRIPTOR = -3,
} controller_framework_status_t;

/* What the framework gives an entry: the handle of every call below. Owned by the framework. */
typedef struct controller_app_context controller_app_context_t;

typedef enum {
    CONTROLLER_APP_STOP_OPERATOR = 0,      /* an operator stop through device management */
    CONTROLLER_APP_STOP_PLANNED_RESET = 1, /* a reset that software requested */
    CONTROLLER_APP_STOP_FAULT = 2,         /* the application reported a fault */
} controller_app_stop_reason_t;

/*
 * The descriptor (section 3.1). Every entry is mandatory. Each is specified by the results it
 * guarantees and the time it may take:
 *   init        registers every channel requirement, status item and parameter table that the
 *               application needs; nothing is registered later. It may read its data root, and does
 *               not depend on configuration, time, web management or the command line, which start
 *               after it. On failure nothing that it started still runs.
 *   start       on success, the threads that feed the activated channels run and feed within
 *               their reload periods; on failure every thread that it created has ended before it
 *               returns.
 *   stop        on success every thread of the application has ended. An error return or a
 *               missed deadline is a hang: the device resets. A thread's last feed must come less
 *               than its reload period before stop returns, because the channel is deleted only
 *               then.
 *   safe_state  puts the outputs into the product's safe state and never blocks. It can run at
 *               the same time as the application's threads (from the supervisor before a reset),
 *               so it is idempotent, takes no lock, allocates nothing and logs nothing.
 * An entry returns 0 for success. The descriptor is borrowed for the program's life.
 */
typedef struct {
    int (*init)(controller_app_context_t *context);
    int (*start)(controller_app_context_t *context);
    int (*stop)(controller_app_context_t *context, controller_app_stop_reason_t reason);
    void (*safe_state)(controller_app_context_t *context);
    void *user_data; /* returned by controller_app_user_data() */
} controller_app_t;

/*
 * Start the framework once. app is the product's descriptor, or NULL for no application (the base
 * image). A second call, and a descriptor without a mandatory entry, are refused.
 */
controller_framework_status_t controller_framework_start(const controller_app_t *app);

typedef enum {
    CONTROLLER_APP_OK = 0,
    CONTROLLER_APP_ERR_INVALID = -1,   /* a missing argument, a reload period of zero, a bad name */
    CONTROLLER_APP_ERR_CLOSED = -2,    /* outside init */
    CONTROLLER_APP_ERR_DUPLICATE = -3, /* the name or the table is registered already */
    CONTROLLER_APP_ERR_FULL = -4,      /* beyond the free capacity */
} controller_app_result_t;

/* The user data of the descriptor. */
void *controller_app_user_data(const controller_app_context_t *context);

/* The handle that feeds one channel; its value stays the same across operator stops and starts. */
typedef struct {
    size_t index;
} controller_app_channel_t;

/*
 * Register a task watchdog channel requirement, inside init (section 4.4): a name of 1 to 31 bytes,
 * borrowed for the program's life, and a reload period above zero. No channel exists yet; the
 * framework activates it immediately before start, which feeds it once, and deletes it after a
 * successful stop. The capacity is CONFIG_TASK_WDT_CHANNELS less the framework's own channels.
 */
controller_app_result_t controller_app_channel_register(controller_app_context_t *context,
                                                        const char *name, uint32_t reload_ms,
                                                        controller_app_channel_t *channel);

/* Feed a channel from the thread that it supervises. Does nothing while it is not active. */
void controller_app_channel_feed(controller_app_context_t *context,
                                 controller_app_channel_t channel);

/*
 * The Crux File root (a crux_file_root_t value, for crux_file_open_at() and the other calls of
 * <crux/file.h> that take a root) that holds the application's data, or -1 when the build has no
 * storage or the volume did not mount. Valid from init on.
 */
int controller_app_data_root(const controller_app_context_t *context);

typedef enum {
    CONTROLLER_FRAMEWORK_STATE_STARTING = 0,
    CONTROLLER_FRAMEWORK_STATE_OPERATIONAL,
    CONTROLLER_FRAMEWORK_STATE_DEGRADED,
    CONTROLLER_FRAMEWORK_STATE_RECOVERY,
} controller_framework_state_t;

typedef enum {
    CONTROLLER_FRAMEWORK_SERVICE_NETWORK = 0,
    CONTROLLER_FRAMEWORK_SERVICE_STORAGE,
    CONTROLLER_FRAMEWORK_SERVICE_ACCESS,
    CONTROLLER_FRAMEWORK_SERVICE_CONFIGURATION,
    CONTROLLER_FRAMEWORK_SERVICE_STATUS,
    CONTROLLER_FRAMEWORK_SERVICE_TIME,
    CONTROLLER_FRAMEWORK_SERVICE_WEB,
    CONTROLLER_FRAMEWORK_SERVICE_COMMAND_LINE,
    CONTROLLER_FRAMEWORK_SERVICE_COUNT,
} controller_framework_service_t;

typedef enum {
    CONTROLLER_FRAMEWORK_HEALTH_ABSENT = 0, /* left out at build time */
    CONTROLLER_FRAMEWORK_HEALTH_HEALTHY,
    CONTROLLER_FRAMEWORK_HEALTH_DEGRADED, /* running with a reported failure */
    CONTROLLER_FRAMEWORK_HEALTH_FAILED,   /* start failed or stopped */
} controller_framework_health_t;

/* Read-only views (sections 4.6 and 4.7), from any thread. A runtime dependency that changes its
 * health is reported here and through the status service; the application decides its response. */
controller_framework_state_t
controller_app_controller_state(const controller_app_context_t *context);
controller_framework_health_t controller_app_service_health(const controller_app_context_t *context,
                                                            controller_framework_service_t service);

/*
 * Report a fault of the running application, from any of its threads. The framework handles it on
 * its own thread (section 4.8): stop with the reason CONTROLLER_APP_STOP_FAULT, then safe_state,
 * then the channels and registrations are released, and the application stays in fault until a
 * reset. A report while the application is not running is dropped.
 */
void controller_app_report_fault(controller_app_context_t *context);

#endif
