/* SPDX-License-Identifier: Apache-2.0 */

#include "image_trial.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "controller_state.h"
#include "image_state_port.h"

/* The device management services of section 4.7. */
static const service_id_t management_services[] = {SERVICE_WEB, SERVICE_COMMAND_LINE};

bool image_trial_init(image_trial_t *trial, const image_trial_config_t *config)
{
    if (trial == NULL || config == NULL) {
        return false;
    }
    memset(trial, 0, sizeof *trial);
    trial->config = *config;
    trial->phase = IMAGE_TRIAL_NONE;
    return true;
}

static bool prerequisites_healthy(const image_health_inputs_t *inputs)
{
    for (int service = 0; service < SERVICE_COUNT; service++) {
        if ((inputs->prerequisites & (1u << service)) != 0u &&
            inputs->health[service] != SERVICE_HEALTHY) {
            return false;
        }
    }
    return true;
}

static bool management_started(const image_health_inputs_t *inputs)
{
    for (size_t i = 0; i < sizeof management_services / sizeof management_services[0]; i++) {
        service_health_t health = inputs->health[management_services[i]];

        /* A service that the build leaves out has nothing to start. */
        if (health != SERVICE_ABSENT && health != SERVICE_HEALTHY && health != SERVICE_DEGRADED) {
            return false;
        }
    }
    return true;
}

/* Tracks the run of the application and answers whether it meets its condition now. */
static bool application_stable(image_trial_t *trial, const image_health_inputs_t *inputs,
                               uint64_t now_ms)
{
    app_state_t application = inputs->application;

    if (application == APP_ABSENT) {
        trial->running = false;
        return true;
    }
    if (application != APP_RUNNING) {
        trial->running = false;
        return false;
    }
    if (!trial->running) {
        trial->running = true;
        trial->running_since = now_ms;
    }
    /* A clock that reads earlier than the start of the run counts as no time passed. */
    return now_ms >= trial->running_since &&
           now_ms - trial->running_since >= trial->config.stable_period_ms;
}

bool image_trial_verdict(image_trial_t *trial, const image_health_inputs_t *inputs, uint64_t now_ms)
{
    if (trial == NULL || inputs == NULL) {
        return false;
    }
    /* The application's run is tracked first, so that every poll sees a stop. */
    bool stable = application_stable(trial, inputs, now_ms);

    return stable && inputs->controller == CONTROLLER_OPERATIONAL &&
           prerequisites_healthy(inputs) && management_started(inputs) &&
           inputs->configuration_compatible;
}

image_trial_phase_t image_trial_poll(image_trial_t *trial, const image_health_inputs_t *inputs,
                                     uint64_t now_ms)
{
    if (trial == NULL || inputs == NULL) {
        return IMAGE_TRIAL_NONE;
    }
    if (!trial->state_read) {
        trial->state_read = true;
        trial->phase =
            image_state_port_read() == IMAGE_STATE_TEST ? IMAGE_TRIAL_WAITING : IMAGE_TRIAL_NONE;
    }
    if (trial->phase != IMAGE_TRIAL_WAITING) {
        return trial->phase;
    }
    if (image_trial_verdict(trial, inputs, now_ms) && image_state_port_confirm()) {
        trial->phase = IMAGE_TRIAL_CONFIRMED;
    } else if (now_ms >= trial->config.deadline_ms && image_state_port_request_reset()) {
        trial->phase = IMAGE_TRIAL_RESET_REQUESTED;
    }
    return trial->phase;
}

const char *image_trial_phase_name(image_trial_phase_t phase)
{
    switch (phase) {
    case IMAGE_TRIAL_NONE:
        return "none";
    case IMAGE_TRIAL_WAITING:
        return "waiting";
    case IMAGE_TRIAL_CONFIRMED:
        return "confirmed";
    case IMAGE_TRIAL_RESET_REQUESTED:
        return "reset-requested";
    default:
        return "unknown";
    }
}
