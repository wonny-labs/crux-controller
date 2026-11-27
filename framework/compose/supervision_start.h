/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SUPERVISION_START_H
#define SUPERVISION_START_H

/*
 * The framework's command table of the serial command line, which framework/compose/cli_start.c
 * passes to the Crux registry. A header of the composition zone: it names a Crux type.
 */

#include <stddef.h>

#include <crux/cli.h>

/* The table and its length, borrowed for the program's life. */
const crux_cli_command_t *supervision_commands(size_t *count);

#endif
