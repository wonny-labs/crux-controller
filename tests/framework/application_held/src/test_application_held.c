/* SPDX-License-Identifier: Apache-2.0 */

/* The held-application scenario (criterion 19, application part): in the production watchdog
 * configuration, with no watchdog behind the alias crux-watchdog0, the framework initialises the
 * fixture application and holds it in step 12 (decision D14): start is not called, and the
 * controller is degraded. */

#include <stdbool.h>
#include <stdio.h>

#include <controller/framework.h>
#include <zephyr/kernel.h>

#include "fixture.h"
#include "scenario.h"

#define WAIT_STEP_MS 100
#define WAIT_STEPS 100

int main(void)
{
    scenario_forward_log();
    scenario_say("held scenario start");
    if (controller_framework_start(fixture_descriptor(FIXTURE_NORMAL)) != CONTROLLER_FRAMEWORK_OK) {
        scenario_say("held scenario FAILED: the start function");
        return 0;
    }
    bool degraded = false;

    for (int step = 0; step < WAIT_STEPS && !degraded; step++) {
        degraded = fixture_controller_state() == CONTROLLER_FRAMEWORK_STATE_DEGRADED;
        k_msleep(WAIT_STEP_MS);
    }
    k_msleep(1000);
    if (degraded && fixture_inits() == 1u && fixture_starts() == 0u) {
        scenario_say("held scenario: initialised, not started, controller degraded");
    } else {
        scenario_say("held scenario FAILED: the hold");
    }
    for (;;) {
        k_sleep(K_FOREVER);
    }
    return 0;
}
