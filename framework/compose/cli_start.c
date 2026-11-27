/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The composition zone of the serial command line: the one place that starts the Crux serial
 * console. It implements the port that framework/src declares (cli_port.h) with the public header
 * <crux/cli.h> and the console composition interface <crux/cli_zephyr.h>, which binds the console
 * to the UART of the devicetree alias crux-serial0. No Zephyr header is needed: the devicetree
 * chooses the UART, and Crux opens it.
 *
 * The registry holds the built-in commands of Crux (help, logout, passwd and account list) and,
 * when the configuration asks for them, the framework's command table of health supervision
 * (supervision_start.h). The console makes the first account itself when a person types !setup at
 * the login prompt and no account exists; this file makes no account and holds no password.
 */

#include "../src/cli_port.h"

#include <crux/cli.h>
#include <crux/cli_zephyr.h>
#include <crux/logging.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
#include "supervision_start.h"
#endif

#define LOG_TAG "cli"

/* One start per program: the registry is made ready once and the console thread never ends. */
static bool started;

/* The settings that the console borrows for the program's life. */
static crux_cli_serial_config_t console;

static cli_port_status_t failed(const char *step, int result)
{
    char text[CRUX_LOG_TEXT_MAX];

    (void)snprintf(text, sizeof text, "command line start refused at %s result=%d", step, result);
    (void)crux_log_write(CRUX_LOG_ERROR, LOG_TAG, text);
    return CLI_PORT_ERR_STEP_FAILED;
}

cli_port_status_t cli_port_start(const cli_port_config_t *config)
{
    if (started) {
        return CLI_PORT_ERR_ALREADY_STARTED;
    }
    if (config == NULL || config->setup_role == NULL || config->setup_role[0] == '\0') {
        return CLI_PORT_ERR_INVALID_ARGUMENT;
    }
    started = true;

    static const crux_cli_command_t *tables[1];
    static size_t counts[1];
    size_t table_count = 0u;

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    if (config->framework_commands) {
        tables[0] = supervision_commands(&counts[0]);
        table_count = 1u;
    }
#endif
    const crux_cli_result_t registry = crux_cli_init(table_count > 0u ? tables : NULL,
                                                     table_count > 0u ? counts : NULL, table_count);
    if (registry != CRUX_CLI_OK) {
        return failed("command tables", (int)registry);
    }
    console.setup_role = config->setup_role;
    const crux_cli_result_t serial = crux_cli_serial_start(&console);
    if (serial != CRUX_CLI_OK) {
        return failed("serial console", (int)serial);
    }
    (void)crux_log_write(CRUX_LOG_INFO, LOG_TAG, "serial command line started on crux-serial0");
    return CLI_PORT_OK;
}
