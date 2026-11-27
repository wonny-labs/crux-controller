/* SPDX-License-Identifier: Apache-2.0 */

#include "controller_state.h"

static bool service_ok(service_health_t health)
{
    return health == SERVICE_HEALTHY;
}

controller_state_t controller_state_decide(const controller_inputs_t *inputs)
{
    if (inputs == NULL) {
        return CONTROLLER_STARTING;
    }
    if (inputs->safe_mode) {
        return CONTROLLER_RECOVERY;
    }
    if (!inputs->startup_done) {
        return CONTROLLER_STARTING;
    }
    if (!inputs->watchdog_armed && !inputs->watchdog_optional) {
        return CONTROLLER_DEGRADED;
    }
    for (int service = 0; service < SERVICE_COUNT; service++) {
        if ((inputs->required & (1u << service)) != 0u && !service_ok(inputs->health[service])) {
            return CONTROLLER_DEGRADED;
        }
    }
    return CONTROLLER_OPERATIONAL;
}

static bool next_state(app_state_t from, app_event_t event, app_hold_t hold, app_state_t *to)
{
    switch (from) {
    case APP_NOT_INITIALISED:
        if (event == APP_EVENT_INIT_OK) {
            *to = APP_INITIALISED;
        } else if (event == APP_EVENT_INIT_FAILED) {
            *to = APP_FAULT;
        } else if (event == APP_EVENT_HOLD && hold == APP_HOLD_SAFE_MODE) {
            *to = APP_HELD;
        } else {
            return false;
        }
        return true;
    case APP_INITIALISED:
        if (event == APP_EVENT_START_OK) {
            *to = APP_RUNNING;
        } else if (event == APP_EVENT_START_FAILED) {
            *to = APP_FAULT;
        } else if (event == APP_EVENT_HOLD && hold != APP_HOLD_NONE) {
            *to = APP_HELD;
        } else {
            return false;
        }
        return true;
    case APP_HELD:
        /* Only a hold for a start prerequisite ends on an operator start; the others need a reset.
         */
        if (event == APP_EVENT_OPERATOR_START && hold == APP_HOLD_PREREQUISITE) {
            *to = APP_RUNNING;
            return true;
        }
        return false;
    case APP_RUNNING:
        if (event == APP_EVENT_STOPPED) {
            *to = APP_STOPPED;
        } else if (event == APP_EVENT_FAULT) {
            *to = APP_FAULT;
        } else {
            return false;
        }
        return true;
    case APP_STOPPED:
        if (event == APP_EVENT_START_OK || event == APP_EVENT_OPERATOR_START) {
            *to = APP_RUNNING;
        } else if (event == APP_EVENT_START_FAILED) {
            *to = APP_FAULT;
        } else {
            return false;
        }
        return true;
    case APP_ABSENT:
    case APP_FAULT:
    default:
        return false;
    }
}

bool app_state_next(app_state_t from, app_event_t event, app_hold_t hold, app_state_t *to)
{
    app_state_t next = from;

    if (to == NULL || !next_state(from, event, hold, &next)) {
        return false;
    }
    *to = next;
    return true;
}

app_start_t app_start_decide(const app_start_inputs_t *inputs, app_hold_t *hold)
{
    app_hold_t reason = APP_HOLD_NONE;
    app_start_t decision = APP_START_NOT_NOW;

    if (inputs != NULL && (inputs->state == APP_INITIALISED || inputs->state == APP_STOPPED ||
                           inputs->state == APP_HELD)) {
        if (inputs->safe_mode) {
            reason = APP_HOLD_SAFE_MODE;
        } else if (!inputs->prerequisites_healthy) {
            reason = APP_HOLD_PREREQUISITE;
        } else if (!inputs->watchdog_armed && !inputs->start_without_watchdog) {
            reason = APP_HOLD_WATCHDOG;
        }
        decision = reason == APP_HOLD_NONE ? APP_START_GO : APP_START_HOLD;
    }
    if (hold != NULL) {
        *hold = reason;
    }
    return decision;
}

const char *controller_state_name(controller_state_t state)
{
    switch (state) {
    case CONTROLLER_STARTING:
        return "starting";
    case CONTROLLER_OPERATIONAL:
        return "operational";
    case CONTROLLER_DEGRADED:
        return "degraded";
    case CONTROLLER_RECOVERY:
        return "recovery";
    default:
        return "unknown";
    }
}

const char *app_state_name(app_state_t state)
{
    switch (state) {
    case APP_ABSENT:
        return "absent";
    case APP_NOT_INITIALISED:
        return "not-initialised";
    case APP_INITIALISED:
        return "initialised";
    case APP_HELD:
        return "held";
    case APP_RUNNING:
        return "running";
    case APP_STOPPED:
        return "stopped";
    case APP_FAULT:
        return "fault";
    default:
        return "unknown";
    }
}

const char *service_health_name(service_health_t health)
{
    switch (health) {
    case SERVICE_ABSENT:
        return "absent";
    case SERVICE_HEALTHY:
        return "healthy";
    case SERVICE_DEGRADED:
        return "degraded";
    case SERVICE_FAILED:
        return "failed";
    default:
        return "unknown";
    }
}
