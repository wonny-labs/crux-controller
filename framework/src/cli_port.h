/* SPDX-License-Identifier: Apache-2.0 */
#ifndef CLI_PORT_H
#define CLI_PORT_H

/*
 * The port of the serial command line. framework/src declares it and the composition zone
 * (framework/compose/cli_start.c) implements it with the console composition interface of Crux,
 * so this header names no Crux, Zephyr or composition header and is read and tested without them.
 *
 * cli_port_start() passes the framework's command tables to the Crux registry and then starts the
 * Crux serial console on the UART of the devicetree alias crux-serial0, once, from thread context.
 * Access must have started before the call: web management starts it (management_port.h), and the
 * start function calls this port only after that phase succeeded. The console's first-account
 * setup gives the first account the role named in the configuration, which must exist in the
 * Access policy and hold the permission that manages accounts.
 */

typedef enum {
    CLI_PORT_OK = 0,
    CLI_PORT_ERR_INVALID_ARGUMENT = -1,
    CLI_PORT_ERR_ALREADY_STARTED = -2, /* A second start; nothing changed. */
    CLI_PORT_ERR_STEP_FAILED = -3,     /* The registry or the console refused; no console runs. */
} cli_port_status_t;

typedef struct {
    /* The role of the first account, borrowed for the program's life. */
    const char *setup_role;
} cli_port_config_t;

/* Start the serial command line, or refuse and leave it off. */
cli_port_status_t cli_port_start(const cli_port_config_t *config);

#endif
