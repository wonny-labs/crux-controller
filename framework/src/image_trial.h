/* SPDX-License-Identifier: Apache-2.0 */
#ifndef IMAGE_TRIAL_H
#define IMAGE_TRIAL_H

/*
 * The trial of a test image (specification section 6.1, D7): the framework's health verdict, and
 * the confirmation or planned reset that the update component carries out on that verdict through
 * the image state port (image_state_port.h). Plain C with ISO C includes only
 * (tests/host/test_image_trial.c). No image builds it yet: Crux has no image state provider for
 * Zephyr (gap C10).
 *
 * Times are milliseconds of the monotonic clock since the start of the boot, which the caller
 * passes, so the trial deadline counts from the start of the boot. The verdict looks at the current
 * boot only: no input names the reset cause or the boot counter, because MCUboot reverts an
 * unconfirmed test image at its first reset.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "controller_state.h"

typedef struct {
    uint64_t deadline_ms;      /* the trial deadline, from the start of the boot (Kconfig) */
    uint64_t stable_period_ms; /* the stable period of section 5.2 (Kconfig) */
} image_trial_config_t;

/* What the verdict reads, at one moment of the boot. */
typedef struct {
    controller_state_t controller;
    uint32_t prerequisites; /* bit per service_id_t: the product's start prerequisites */
    /* The health of each service. The device management services are web management and the
     * command line; one that the build leaves out is SERVICE_ABSENT. */
    service_health_t health[SERVICE_COUNT];
    app_state_t application;       /* APP_ABSENT in the base image */
    bool configuration_compatible; /* the configuration loaded with a compatible version */
} image_health_inputs_t;

typedef enum {
    IMAGE_TRIAL_NONE = 0,        /* no trial: a confirmed image, or no image state */
    IMAGE_TRIAL_WAITING,         /* a test image whose verdict is not healthy yet */
    IMAGE_TRIAL_CONFIRMED,       /* the verdict was healthy and the image is confirmed */
    IMAGE_TRIAL_RESET_REQUESTED, /* the deadline passed and a planned reset was requested */
} image_trial_phase_t;

typedef struct {
    image_trial_config_t config;
    bool state_read; /* the image state was read in this boot */
    image_trial_phase_t phase;
    bool running;           /* the application was running at the last update */
    uint64_t running_since; /* when it began to run without interruption */
} image_trial_t;

/* A new trial for this boot. False for a NULL argument, with *trial untouched. */
bool image_trial_init(image_trial_t *trial, const image_trial_config_t *config);

/*
 * The health verdict at now_ms. Healthy when all of these hold, not uptime alone:
 * - the controller is operational;
 * - every start prerequisite is healthy;
 * - every device management service in the build has started (healthy or degraded);
 * - the application is absent, or has been running without interruption for the stable period; a
 *   stop, by an operator or otherwise, starts the period again when the application runs again;
 * - the configuration loaded with a compatible version.
 * Call it on every poll, so that it sees each stop. False for a NULL argument.
 */
bool image_trial_verdict(image_trial_t *trial, const image_health_inputs_t *inputs,
                         uint64_t now_ms);

/*
 * One poll of the trial: reads the image state through the port on the first poll of the boot,
 * then, for a test image, confirms it through the port when the verdict is healthy, or requests a
 * planned reset through the port when the verdict is not healthy at or after the deadline. A failed
 * confirmation or reset request is tried again on the next poll; an image that is still not
 * confirmed at the deadline requests the reset, so a test image does not keep running
 * unconfirmed. After a confirmation or an accepted reset request, a poll calls the port no more.
 * Returns the phase after the poll; IMAGE_TRIAL_NONE for a NULL argument.
 */
image_trial_phase_t image_trial_poll(image_trial_t *trial, const image_health_inputs_t *inputs,
                                     uint64_t now_ms);

/* "none", "waiting", "confirmed", "reset-requested"; "unknown" for a value out of range. */
const char *image_trial_phase_name(image_trial_phase_t phase);

#endif
