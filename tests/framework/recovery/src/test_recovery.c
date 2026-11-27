/* SPDX-License-Identifier: Apache-2.0 */

/* The recovery scenario of the controller framework on native_sim. One run, six boots: the
 * simulated watchdog of Crux System restarts the simulated process after a missed feed, which
 * then reads the reset cause SOFTWARE (gap C11), and the retained region over the test-only
 * retained memory of ../common survives the restart. Each boot arms one fault, starts the framework
 * and prints what the console harness of testcase.yaml matches, in order:
 *
 *   1. A startup step stalls past its deadline: the supervisor stops feeding and the simulated
 *      watchdog restarts the image (criterion 7).
 *   2. The record names the step and the reset counts (counter 1). The supervisor thread raises a
 *      fatal error: the handler writes the minimal record and restarts the image (criterion 16).
 *   3. The record names the fatal error and the reset counts (counter 2). The time synchronisation
 *      thread stops feeding its channel: the expiry is recorded and the image restarts.
 *   4. Counter 3 = N: safe mode, with no time synchronisation and no application. The framework's
 *      reboot thread, a safe-mode service, stalls: the image restarts (criterion 17).
 *   5. Safe mode again, the counter saturated. Device management answers: first-account setup and
 *      a login over the serial command line, and the status command shows the recovery state; the
 *      recovery exit command clears the counter and restarts through Crux Reboot with the operator
 *      reset marker (criterion 11).
 *   6. A normal boot: the marker makes the reset a planned one, and the counter is zero.
 *
 * The base image has no application, so "the application is not initialised" of criterion 11 shows
 * as "no application: safe mode"; the fixture application of delivery stage 3 shows the rest. */

#include <stdbool.h>
#include <stdio.h>

#include <controller/framework.h>
#include <controller/framework_test.h>
#include <zephyr/kernel.h>

#include "scenario.h"

#define USER "operator"
#define PASSWORD "recovery scenario password"

static void fail(const char *what)
{
    char text[160];

    (void)snprintf(text, sizeof text, "recovery scenario FAILED: %s", what);
    scenario_say(text);
}

static bool expect(const char *text)
{
    if (!scenario_console_expect(text)) {
        fail(text);
        return false;
    }
    return true;
}

/* Boot 5: set up the first account, log in, check the status and leave safe mode. */
static void leave_safe_mode(void)
{
    if (!expect("login: ")) {
        return;
    }
    scenario_console_type("!setup");
    if (!expect("new user: ")) {
        return;
    }
    scenario_console_type(USER);
    if (!expect("password: ")) {
        return;
    }
    scenario_console_type(PASSWORD);
    if (!expect("repeat: ")) {
        return;
    }
    scenario_console_type(PASSWORD);
    if (!expect("account created") || !expect("login: ")) {
        return;
    }
    scenario_console_type(USER);
    if (!expect("password: ")) {
        return;
    }
    scenario_console_type(PASSWORD);
    if (!expect("> ")) {
        return;
    }
    scenario_console_type("status");
    if (!expect("{\"name\":\"controller.state\",\"status\":\"ok\",\"type\":\"text\","
                "\"value\":\"recovery\"}") ||
        !expect("{\"name\":\"controller.safe_mode\",\"status\":\"ok\",\"type\":\"bool\","
                "\"value\":true}") ||
        !expect("{\"name\":\"controller.boot_counter\",\"status\":\"ok\",\"type\":\"u32\","
                "\"value\":3}") ||
        !expect("> ")) {
        return;
    }
    scenario_say("recovery scenario: status shows safe mode");
    scenario_console_type("recovery exit");
    if (!expect("restart requested")) {
        return;
    }
    scenario_say("recovery scenario: restart requested");
}

int main(void)
{
    char text[64];
    const int boot = scenario_boot_number();

    scenario_forward_log();
    (void)snprintf(text, sizeof text, "recovery scenario boot %d", boot);
    scenario_say(text);

    switch (boot) {
    case 1:
        (void)controller_framework_inject(CONTROLLER_FRAMEWORK_FAULT_STEP_STALL, "command line");
        break;
    case 2:
        (void)controller_framework_inject(CONTROLLER_FRAMEWORK_FAULT_FATAL, NULL);
        break;
    case 3:
        (void)controller_framework_inject(CONTROLLER_FRAMEWORK_FAULT_THREAD_STALL, "time");
        break;
    case 4:
        (void)controller_framework_inject(CONTROLLER_FRAMEWORK_FAULT_THREAD_STALL, "reboot");
        break;
    default:
        break;
    }
    if (controller_framework_start() != CONTROLLER_FRAMEWORK_OK) {
        fail("the start function");
    }
    if (boot == 5) {
        leave_safe_mode();
    } else if (boot == 6) {
        scenario_say("recovery scenario done");
    } else if (boot > 6) {
        fail("more boots than planned");
    }
    for (;;) {
        k_sleep(K_FOREVER);
    }
    return 0;
}
