/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The fixture application (fixture.h). It reaches the framework only through <controller/NAME.h>,
 * calls Crux's public interfaces directly for logging, files and configuration, and Zephyr directly
 * for its threads, as an application does (specification section 3.2).
 */

#include "fixture.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include <controller/framework.h>
#include <controller/framework_management.h>
#include <crux/config_service.h>
#include <crux/configuration.h>
#include <crux/file.h>
#include <crux/logging.h>
#include <crux/management_status.h>
#include <crux/status.h>
#include <zephyr/kernel.h>

#define TAG "fixture"
#define RELOAD_MS 1000u
#define LOOP_MS 100
#define STALL_AFTER 10u
#define JOIN_MS 1000
/* The application band of the reference configuration (specification section 7.4). */
#define WORKER_PRIORITY 5
#define MONITOR_PRIORITY 6
#define STACK_BYTES 2048

static K_THREAD_STACK_DEFINE(worker_stack, STACK_BYTES);
static K_THREAD_STACK_DEFINE(monitor_stack, STACK_BYTES);
static struct k_thread worker_thread;
static struct k_thread monitor_thread;

static fixture_behaviour_t behaviour;
static controller_app_context_t *context;
static controller_app_channel_t worker_channel;
static controller_app_channel_t monitor_channel;
static atomic_t stop_requested;
static atomic_t fault_wanted;
static atomic_t counter;
static atomic_t inits;
static atomic_t starts;
static atomic_t stops;
static atomic_t safe_states;

static void say(crux_log_level_t level, const char *text)
{
    (void)crux_log_write(level, TAG, text);
}

/* The status item: the worker's loop count. It copies a value, as a source must. */
static crux_status_t read_counter(void *item_context, crux_mgmt_status_value_t *out)
{
    (void)item_context;
    out->type = CRUX_MGMT_STATUS_U32;
    out->data.u32 = (uint32_t)atomic_get(&counter);
    return CRUX_OK;
}

static const crux_mgmt_status_item_t items[] = {
    {"fixture.counter", CRUX_MGMT_STATUS_PERMISSION_READ, read_counter, NULL},
};

/* The parameter: the worker's period in milliseconds, read by the fixture and shown by the
 * configuration service. */
static const crux_config_spec_t period_spec = {
    .key = "fixture.period",
    .schema_version = 1u,
    .default_value = {.type = CRUX_CONFIG_U32, .data = {.u32 = 100u}},
    .validate = NULL,
    .validation_context = NULL,
};
static crux_config_param_t period;

static const crux_config_service_entry_t parameters[] = {
    {&period, CRUX_MGMT_STATUS_PERMISSION_READ, CRUX_CONFIG_SERVICE_PERMISSION_SAVE, false,
     CRUX_CONFIG_ACTIVATION_APPLICATION},
};

static void worker_run(void *unused0, void *unused1, void *unused2)
{
    ARG_UNUSED(unused0);
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    controller_framework_health_t seen = CONTROLLER_FRAMEWORK_HEALTH_HEALTHY;

    while (atomic_get(&stop_requested) == 0) {
        const uint32_t loops = (uint32_t)atomic_inc(&counter) + 1u;

        if (behaviour != FIXTURE_THREAD_STALLS || loops <= STALL_AFTER) {
            controller_app_channel_feed(context, worker_channel);
        } else if (loops == STALL_AFTER + 1u) {
            say(CRUX_LOG_WARN, "worker stops feeding its channel");
        }
        /* A runtime dependency is the application's to respond to (section 4.7): it logs. */
        const controller_framework_health_t health =
            controller_app_service_health(context, CONTROLLER_FRAMEWORK_SERVICE_CONFIGURATION);

        if (health != seen) {
            char text[64];

            seen = health;
            (void)snprintf(text, sizeof text, "configuration health %s, worker keeps running",
                           health == CONTROLLER_FRAMEWORK_HEALTH_HEALTHY ? "healthy"
                                                                         : "not healthy");
            say(CRUX_LOG_INFO, text);
        }
        if (atomic_cas(&fault_wanted, 1, 0)) {
            say(CRUX_LOG_WARN, "worker reports a fault");
            controller_app_report_fault(context);
        }
        k_msleep(LOOP_MS);
    }
}

static void monitor_run(void *unused0, void *unused1, void *unused2)
{
    ARG_UNUSED(unused0);
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    while (atomic_get(&stop_requested) == 0) {
        controller_app_channel_feed(context, monitor_channel);
        k_msleep(LOOP_MS);
    }
}

static int write_file(int root)
{
    static const char text[] = "written by the fixture application\n";
    crux_file_t *file = NULL;
    size_t written = 0u;

    if (root < 0 || crux_file_open_at((crux_file_root_t)root, "hello.txt", CRUX_FILE_CREATE_REPLACE,
                                      &file) != CRUX_FILE_OK) {
        return -1;
    }
    const crux_file_result_t result = crux_file_write(file, text, sizeof text - 1u, &written);

    (void)crux_file_close(&file);
    return result == CRUX_FILE_OK && written == sizeof text - 1u ? 0 : -1;
}

static int fixture_init(controller_app_context_t *given)
{
    char text[CRUX_LOG_TEXT_MAX];

    (void)atomic_inc(&inits);
    context = given;
    const controller_app_result_t worker =
        controller_app_channel_register(given, "worker", RELOAD_MS, &worker_channel);
    const controller_app_result_t monitor =
        controller_app_channel_register(given, "monitor", RELOAD_MS, &monitor_channel);
    const controller_app_result_t status = controller_app_status_register(given, items, 1u);
    const crux_config_result_t initialised = crux_config_init(&period, &period_spec);
    /* No save provider in this image: a load gives the default (section 5.4, stage 4). */
    const crux_config_result_t loaded = crux_config_load(&period);
    const controller_app_result_t table = controller_app_parameters_register(given, parameters, 1u);
    const int root = controller_app_data_root(given);
    const int file = write_file(root);

    (void)snprintf(text, sizeof text,
                   "init channels=%d,%d status=%d parameter=%d,%d,%d root=%d file=%s", (int)worker,
                   (int)monitor, (int)status, (int)initialised, (int)loaded, (int)table, root,
                   file == 0 ? "hello.txt written" : "not written");
    say(CRUX_LOG_INFO, text);
    if (worker != CONTROLLER_APP_OK || monitor != CONTROLLER_APP_OK ||
        status != CONTROLLER_APP_OK || table != CONTROLLER_APP_OK || file != 0) {
        return -1;
    }
    if (behaviour == FIXTURE_INIT_FAILS) {
        say(CRUX_LOG_WARN, "init fails after its registrations");
        return -1;
    }
    return 0;
}

static int fixture_start(controller_app_context_t *given)
{
    (void)given;
    (void)atomic_inc(&starts);
    if (behaviour == FIXTURE_START_FAILS) {
        say(CRUX_LOG_WARN, "start fails before it creates a thread");
        return -1;
    }
    if (behaviour == FIXTURE_START_HANGS) {
        say(CRUX_LOG_WARN, "start hangs");
        for (;;) {
            k_sleep(K_FOREVER);
        }
    }
    atomic_set(&stop_requested, 0);
    (void)k_thread_create(&worker_thread, worker_stack, K_THREAD_STACK_SIZEOF(worker_stack),
                          worker_run, NULL, NULL, NULL, K_PRIO_PREEMPT(WORKER_PRIORITY), 0,
                          K_NO_WAIT);
    (void)k_thread_name_set(&worker_thread, "fixture worker");
    (void)k_thread_create(&monitor_thread, monitor_stack, K_THREAD_STACK_SIZEOF(monitor_stack),
                          monitor_run, NULL, NULL, NULL, K_PRIO_PREEMPT(MONITOR_PRIORITY), 0,
                          K_NO_WAIT);
    (void)k_thread_name_set(&monitor_thread, "fixture monitor");
    say(CRUX_LOG_INFO, "start: worker and monitor threads created with Zephyr");
    return 0;
}

static int fixture_stop(controller_app_context_t *given, controller_app_stop_reason_t reason)
{
    char text[64];

    (void)given;
    (void)atomic_inc(&stops);
    (void)snprintf(text, sizeof text, "stop reason=%s",
                   reason == CONTROLLER_APP_STOP_FAULT      ? "fault"
                   : reason == CONTROLLER_APP_STOP_OPERATOR ? "operator"
                                                            : "planned reset");
    say(CRUX_LOG_INFO, text);
    if (behaviour == FIXTURE_STOP_FAILS) {
        say(CRUX_LOG_WARN, "stop returns an error and ends nothing");
        return -1;
    }
    if (behaviour == FIXTURE_STOP_HANGS) {
        say(CRUX_LOG_WARN, "stop hangs");
        for (;;) {
            k_sleep(K_FOREVER);
        }
    }
    atomic_set(&stop_requested, 1);
    const int worker = k_thread_join(&worker_thread, K_MSEC(JOIN_MS));
    const int monitor = k_thread_join(&monitor_thread, K_MSEC(JOIN_MS));

    if (worker != 0 || monitor != 0) {
        return -1;
    }
    say(CRUX_LOG_INFO, "stop: both threads ended");
    return 0;
}

/* Never blocks, takes no lock, allocates nothing and logs nothing (section 3.3). */
static void fixture_safe_state(controller_app_context_t *given)
{
    (void)given;
    (void)atomic_inc(&safe_states);
}

static controller_app_t descriptor = {
    .init = fixture_init,
    .start = fixture_start,
    .stop = fixture_stop,
    .safe_state = fixture_safe_state,
    .user_data = NULL,
};

static const controller_app_t incomplete = {
    .init = fixture_init,
    .start = fixture_start,
    .stop = fixture_stop,
    .safe_state = NULL,
    .user_data = NULL,
};

const controller_app_t *fixture_descriptor(fixture_behaviour_t chosen)
{
    behaviour = chosen;
    return &descriptor;
}

const controller_app_t *fixture_incomplete_descriptor(void)
{
    return &incomplete;
}

void fixture_report_fault(void)
{
    atomic_set(&fault_wanted, 1);
}

unsigned fixture_inits(void)
{
    return (unsigned)atomic_get(&inits);
}

unsigned fixture_starts(void)
{
    return (unsigned)atomic_get(&starts);
}

unsigned fixture_stops(void)
{
    return (unsigned)atomic_get(&stops);
}

unsigned fixture_safe_states(void)
{
    return (unsigned)atomic_get(&safe_states);
}

uint32_t fixture_counter(void)
{
    return (uint32_t)atomic_get(&counter);
}

controller_framework_state_t fixture_controller_state(void)
{
    return controller_app_controller_state(context);
}

controller_framework_health_t fixture_health(controller_framework_service_t service)
{
    return controller_app_service_health(context, service);
}
