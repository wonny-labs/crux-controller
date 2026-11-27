/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The start function of the controller framework: the phase table of the services that the build
 * turns on, run by the portable startup sequence (startup.h). Each service is reached through its
 * port, whose implementation is in the composition zone (framework/compose) or the adapter zone
 * (framework/os) of the module, so this file includes no Zephyr header.
 *
 * Order:
 *   1. clock: the Crux monotonic clock answers. Required: without it nothing can be timed.
 *   2. management: storage mount and the two roots of the credential store, security events,
 *      the credential store and Access, the configuration service, the status service with the
 *      reset cause it reads once, the TLS certificate, sessions and web management, then the
 *      HTTPS listener (management_port.h has the order inside the phase).
 *   3. command line: the framework's command tables to the Crux registry, then the Crux serial
 *      console on the UART of the alias crux-serial0, with its first-account setup. It needs
 *      Access, so it runs only when web management started (cli_port.h).
 *   4. time synchronisation: the SNTP thread that sets the Crux Time realtime clock.
 * The network interface is up before main() (the Zephyr network configuration library), and
 * Crux Logging needs no start. A phase after the clock that fails is reported and the controller
 * runs without that service.
 */

#include <controller/framework.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

#include <crux/logging.h>
#include <crux/status.h>
#include <crux/time.h>

#include "startup.h"

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
#include "management_policy.h"
#include "management_port.h"

/* The versions that the status service reports come from the build (zephyr/CMakeLists.txt), and a
 * build without them stops here, because the port refuses a start without a valid text. */
#ifndef CONTROLLER_PLATFORM_VERSION
#error "web management needs CONTROLLER_PLATFORM_VERSION from zephyr/CMakeLists.txt"
#endif
#ifndef CONTROLLER_PROJECT_VERSION
#error "web management needs CONTROLLER_PROJECT_VERSION from zephyr/CMakeLists.txt"
#endif
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
#include "cli_port.h"
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC
#include "time_sync.h"
#endif

#define LOG_TAG "framework"

static int phase_clock(void)
{
    crux_monotonic_time_t now;

    return crux_monotonic_now(&now) == CRUX_OK ? 0 : -1;
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
/* True once web management started, and with it Access, which the command line needs. */
static bool management_started;

static int phase_management(void)
{
    const management_port_config_t config = {
        .policy = management_policy_get(),
        .platform_version = CONTROLLER_PLATFORM_VERSION,
        .project_version = CONTROLLER_PROJECT_VERSION,
    };
    const management_port_status_t status = management_port_start(&config);

    management_started = status == MANAGEMENT_PORT_OK;
    return (int)status;
}
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
/* The phase result when web management, and so Access, did not start. */
#define PHASE_COMMAND_LINE_NO_ACCESS (-100)

static int phase_command_line(void)
{
    /* The first account gets the role of the management policy that manages accounts. */
    static const cli_port_config_t config = {.setup_role = MANAGEMENT_ROLE_ADMINISTRATOR};

    if (!management_started) {
        return PHASE_COMMAND_LINE_NO_ACCESS;
    }
    return (int)cli_port_start(&config);
}
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC
static int phase_time_sync(void)
{
    return time_sync_start();
}
#endif

static const startup_phase_t phases[] = {
    {"clock", phase_clock, true},
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
    {"web management", phase_management, false},
#endif
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
    {"command line", phase_command_line, false},
#endif
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC
    {"time synchronisation", phase_time_sync, false},
#endif
};

static void report(const char *name, int result)
{
    char text[CRUX_LOG_TEXT_MAX];

    if (result == 0) {
        (void)snprintf(text, sizeof text, "phase %s ok", name);
        (void)crux_log_write(CRUX_LOG_INFO, LOG_TAG, text);
    } else {
        (void)snprintf(text, sizeof text, "phase %s failed result=%d", name, result);
        (void)crux_log_write(CRUX_LOG_ERROR, LOG_TAG, text);
    }
}

controller_framework_status_t controller_framework_start(void)
{
    static bool started;
    startup_summary_t summary = {0u, 0u};
    char text[CRUX_LOG_TEXT_MAX];

    if (started) {
        return CONTROLLER_FRAMEWORK_ERR_ALREADY_STARTED;
    }
    started = true;

    const startup_status_t status =
        startup_run(phases, sizeof phases / sizeof phases[0], report, &summary);

    if (status != STARTUP_OK) {
        (void)crux_log_write(CRUX_LOG_ERROR, LOG_TAG, "startup stopped");
        return CONTROLLER_FRAMEWORK_ERR_STARTUP;
    }
    (void)snprintf(text, sizeof text, "startup done phases=%u failed=%u",
                   (unsigned)summary.completed, (unsigned)summary.failed);
    (void)crux_log_write(summary.failed == 0u ? CRUX_LOG_INFO : CRUX_LOG_WARN, LOG_TAG, text);
    return CONTROLLER_FRAMEWORK_OK;
}
