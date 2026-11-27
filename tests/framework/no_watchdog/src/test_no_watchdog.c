/* SPDX-License-Identifier: Apache-2.0 */

/* The scenario of the controller framework with no watchdog (criterion 7, second part). One run,
 * two boots. In the first, the application step, step 12, stalls past its deadline: the supervisor
 * latches the fault, writes the record and, with no armed watchdog, requests a software reset with
 * crux_system_reset(), which restarts the simulated process. The second boot reads the record,
 * which names the step, counts the reset as a fault reset, and, because the build allows operation
 * without a watchdog (D14), the controller is operational. */

#include <stdio.h>

#include <controller/framework.h>
#include <controller/framework_test.h>
#include <zephyr/kernel.h>

#include "scenario.h"

int main(void)
{
    char text[64];
    const int boot = scenario_boot_number();

    scenario_forward_log();
    (void)snprintf(text, sizeof text, "no watchdog scenario boot %d", boot);
    scenario_say(text);
    if (boot == 1) {
        (void)controller_framework_inject(CONTROLLER_FRAMEWORK_FAULT_STEP_STALL, "application");
    }
    if (controller_framework_start() != CONTROLLER_FRAMEWORK_OK) {
        scenario_say("no watchdog scenario FAILED: the start function");
    }
    if (boot == 2) {
        /* The controller state follows on the supervisor's next periods. */
        k_msleep(2000);
        scenario_say("no watchdog scenario done");
    }
    for (;;) {
        k_sleep(K_FOREVER);
    }
    return 0;
}
