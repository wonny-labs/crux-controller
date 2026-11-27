/* SPDX-License-Identifier: Apache-2.0 */
#ifndef CONTROLLER_STATE_H
#define CONTROLLER_STATE_H

/*
 * The states of the controller framework (specification sections 4.5 to 4.7): the health of each
 * framework service, the controller state built from it, the application lifecycle and the decision
 * whether the framework starts the application. Plain C with ISO C includes only
 * (tests/host/test_controller_state.c).
 *
 * The application contract (app_contract.h) moves the application along these transitions; the
 * base image has no application (APP_ABSENT).
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    SERVICE_ABSENT = 0, /* left out at build time */
    SERVICE_HEALTHY,
    SERVICE_DEGRADED, /* running with a reported failure */
    SERVICE_FAILED,   /* start failed or stopped */
} service_health_t;

typedef enum {
    SERVICE_NETWORK = 0,
    SERVICE_STORAGE,
    SERVICE_ACCESS,
    SERVICE_CONFIGURATION,
    SERVICE_STATUS,
    SERVICE_TIME,
    SERVICE_WEB,
    SERVICE_COMMAND_LINE,
    SERVICE_COUNT,
} service_id_t;

typedef enum {
    CONTROLLER_STARTING = 0,
    CONTROLLER_OPERATIONAL,
    CONTROLLER_DEGRADED,
    CONTROLLER_RECOVERY,
} controller_state_t;

typedef struct {
    bool startup_done;      /* startup supervision has ended */
    bool safe_mode;         /* this boot is in safe mode */
    bool watchdog_armed;    /* the hardware watchdog is armed */
    bool watchdog_optional; /* the build allows operation without it (D14) */
    uint32_t required;      /* bit per service_id_t that the product requires */
    service_health_t health[SERVICE_COUNT];
} controller_inputs_t;

/*
 * Recovery in safe mode, whatever else holds; starting until startup supervision ends; degraded
 * when a required service is degraded or failed, or when the watchdog is not armed in a build that
 * refuses that; operational otherwise. A service that is not required does not change the state,
 * and neither does the application state. A required service that the build left out is a build
 * error elsewhere (section 7.1) and reads as failed here.
 */
controller_state_t controller_state_decide(const controller_inputs_t *inputs);

typedef enum {
    APP_ABSENT = 0,
    APP_NOT_INITIALISED,
    APP_INITIALISED,
    APP_HELD,
    APP_RUNNING,
    APP_STOPPED,
    APP_FAULT,
} app_state_t;

typedef enum {
    APP_EVENT_INIT_OK,        /* init succeeded */
    APP_EVENT_INIT_FAILED,    /* init failed */
    APP_EVENT_START_OK,       /* activation and start succeeded */
    APP_EVENT_START_FAILED,   /* activation or start failed */
    APP_EVENT_HOLD,           /* the framework decided not to start it */
    APP_EVENT_STOPPED,        /* an operator stop's or a planned reset's stop succeeded */
    APP_EVENT_FAULT,          /* the application reported a fault and its stop succeeded */
    APP_EVENT_OPERATOR_START, /* an operator start that app_start_decide() allowed */
} app_event_t;

typedef enum {
    APP_HOLD_NONE = 0,
    APP_HOLD_SAFE_MODE,
    APP_HOLD_PREREQUISITE,
    APP_HOLD_WATCHDOG,
} app_hold_t;

/*
 * The transitions of section 4.5. True, with *to set, for a transition that the table has; false,
 * with *to untouched, for any other pair (a fault leaves only through a reset). hold is the reason
 * of a hold that is being entered or left: an operator start leaves held only when the reason was
 * a start prerequisite.
 */
bool app_state_next(app_state_t from, app_event_t event, app_hold_t hold, app_state_t *to);

typedef enum {
    APP_START_GO = 0,  /* activate the channels and call start */
    APP_START_HOLD,    /* do not start; hold with the reason given */
    APP_START_NOT_NOW, /* not a state from which the application starts */
} app_start_t;

typedef struct {
    app_state_t state;
    bool safe_mode;
    bool prerequisites_healthy;
    bool watchdog_armed;
    bool start_without_watchdog; /* the explicit build option of D14 */
} app_start_inputs_t;

/*
 * Whether the framework calls start (step 12 and every operator start). From initialised, stopped
 * and held: safe mode holds, a start prerequisite that is not healthy holds, and a watchdog that
 * is not armed holds unless the build has the explicit option; otherwise go. Any other state is
 * not a state to start from. *hold receives the reason of a hold and APP_HOLD_NONE otherwise; it
 * may be NULL.
 */
app_start_t app_start_decide(const app_start_inputs_t *inputs, app_hold_t *hold);

/*
 * The conditions of a successful boot (section 5.2), which must hold for the stable period before
 * the boot counter is cleared: the controller is operational and the application is neither in
 * fault nor held. An absent application (the base image) does not stop it.
 */
bool controller_successful_boot_conditions(controller_state_t state, app_state_t application);

/* Lower-case words for the log and the status service; "unknown" for a value out of range. */
const char *controller_state_name(controller_state_t state);
const char *app_state_name(app_state_t state);
const char *service_health_name(service_health_t health);

/* The service's name in the log, the status items and the fault injection of the scenarios:
 * "network", "storage", "access", "configuration", "status", "time", "web", "command-line";
 * "unknown" for a value out of range. */
const char *service_id_name(service_id_t service);

#endif
