/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SCENARIO_H
#define SCENARIO_H

/*
 * Helpers of the native_sim scenarios that restart the simulated process: the number of the boot,
 * kept in the environment across restarts, a thread that copies what Crux Logging writes to its
 * emulated UART to standard output, where Twister's console harness reads it, and the typing at the
 * emulated UART of the serial console.
 */

#include <stdbool.h>

/* 1 at the first start, then one more at each restart of the process. Call once per boot. */
int scenario_boot_number(void);

/* Start the thread that copies the log UART (node label logging_test) to standard output. */
void scenario_forward_log(void);

/* Print a line for the console harness, after the log lines written before it. */
void scenario_say(const char *text);

/* Wait for the serial console (node label serial_test) to write text, and drop everything up to it.
 * False when it does not come in time. */
bool scenario_console_expect(const char *text);

/* Type a line at the serial console, ended by a carriage return. */
void scenario_console_type(const char *text);

#endif
