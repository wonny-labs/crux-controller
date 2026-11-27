/* SPDX-License-Identifier: Apache-2.0 */

/* The controller state, the application lifecycle and the start decision of the controller
 * framework (specification sections 4.5 to 4.7; criterion 10). Plain C, no Crux or Zephyr include.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "controller_state.h"

static int failures;
static int checks;

#define CHECK(condition)                                                                           \
    do {                                                                                           \
        checks++;                                                                                  \
        if (!(condition)) {                                                                        \
            failures++;                                                                            \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition);                            \
        }                                                                                          \
    } while (0)

#define BIT(service) (1u << (service))

static controller_inputs_t healthy(void)
{
    controller_inputs_t inputs;

    memset(&inputs, 0, sizeof inputs);
    inputs.startup_done = true;
    inputs.watchdog_armed = true;
    for (int service = 0; service < SERVICE_COUNT; service++) {
        inputs.health[service] = SERVICE_HEALTHY;
    }
    return inputs;
}

static void test_the_controller_states(void)
{
    controller_inputs_t inputs = healthy();

    CHECK(controller_state_decide(&inputs) == CONTROLLER_OPERATIONAL);

    inputs.startup_done = false;
    CHECK(controller_state_decide(&inputs) == CONTROLLER_STARTING);

    inputs = healthy();
    inputs.safe_mode = true;
    inputs.watchdog_armed = false;
    CHECK(controller_state_decide(&inputs) == CONTROLLER_RECOVERY);
    inputs.startup_done = false;
    CHECK(controller_state_decide(&inputs) == CONTROLLER_RECOVERY);
}

static void test_only_a_required_service_degrades_the_controller(void)
{
    controller_inputs_t inputs = healthy();

    inputs.health[SERVICE_TIME] = SERVICE_DEGRADED;
    inputs.health[SERVICE_WEB] = SERVICE_FAILED;
    CHECK(controller_state_decide(&inputs) == CONTROLLER_OPERATIONAL);

    inputs.required = BIT(SERVICE_STORAGE) | BIT(SERVICE_TIME);
    CHECK(controller_state_decide(&inputs) == CONTROLLER_DEGRADED);

    inputs.health[SERVICE_TIME] = SERVICE_HEALTHY;
    CHECK(controller_state_decide(&inputs) == CONTROLLER_OPERATIONAL);

    inputs.health[SERVICE_STORAGE] = SERVICE_FAILED;
    CHECK(controller_state_decide(&inputs) == CONTROLLER_DEGRADED);

    inputs.health[SERVICE_STORAGE] = SERVICE_ABSENT;
    CHECK(controller_state_decide(&inputs) == CONTROLLER_DEGRADED);
}

static void test_a_watchdog_that_is_not_armed_degrades_unless_the_build_allows_it(void)
{
    controller_inputs_t inputs = healthy();

    inputs.watchdog_armed = false;
    CHECK(controller_state_decide(&inputs) == CONTROLLER_DEGRADED);
    inputs.watchdog_optional = true;
    CHECK(controller_state_decide(&inputs) == CONTROLLER_OPERATIONAL);
}

static void test_null_inputs_read_as_starting(void)
{
    CHECK(controller_state_decide(NULL) == CONTROLLER_STARTING);
}

/* Every pair of section 4.5 that the table has, and a sample of those it has not. */
static void test_the_application_transitions(void)
{
    app_state_t to = APP_ABSENT;

    CHECK(app_state_next(APP_NOT_INITIALISED, APP_EVENT_INIT_OK, APP_HOLD_NONE, &to));
    CHECK(to == APP_INITIALISED);
    CHECK(app_state_next(APP_NOT_INITIALISED, APP_EVENT_INIT_FAILED, APP_HOLD_NONE, &to));
    CHECK(to == APP_FAULT);
    CHECK(app_state_next(APP_NOT_INITIALISED, APP_EVENT_HOLD, APP_HOLD_SAFE_MODE, &to));
    CHECK(to == APP_HELD);
    CHECK(app_state_next(APP_INITIALISED, APP_EVENT_START_OK, APP_HOLD_NONE, &to));
    CHECK(to == APP_RUNNING);
    CHECK(app_state_next(APP_INITIALISED, APP_EVENT_START_FAILED, APP_HOLD_NONE, &to));
    CHECK(to == APP_FAULT);
    CHECK(app_state_next(APP_INITIALISED, APP_EVENT_HOLD, APP_HOLD_PREREQUISITE, &to));
    CHECK(to == APP_HELD);
    CHECK(app_state_next(APP_RUNNING, APP_EVENT_STOPPED, APP_HOLD_NONE, &to));
    CHECK(to == APP_STOPPED);
    CHECK(app_state_next(APP_RUNNING, APP_EVENT_FAULT, APP_HOLD_NONE, &to));
    CHECK(to == APP_FAULT);
    CHECK(app_state_next(APP_STOPPED, APP_EVENT_START_OK, APP_HOLD_NONE, &to));
    CHECK(to == APP_RUNNING);
    CHECK(app_state_next(APP_HELD, APP_EVENT_OPERATOR_START, APP_HOLD_PREREQUISITE, &to));
    CHECK(to == APP_RUNNING);

    to = APP_ABSENT;
    /* A hold for safe mode or the watchdog leaves only through a reset. */
    CHECK(!app_state_next(APP_HELD, APP_EVENT_OPERATOR_START, APP_HOLD_SAFE_MODE, &to));
    CHECK(!app_state_next(APP_HELD, APP_EVENT_OPERATOR_START, APP_HOLD_WATCHDOG, &to));
    /* A fault leaves only through a reset. */
    for (int event = APP_EVENT_INIT_OK; event <= APP_EVENT_OPERATOR_START; event++) {
        CHECK(!app_state_next(APP_FAULT, (app_event_t)event, APP_HOLD_PREREQUISITE, &to));
    }
    /* No application, no transition. */
    CHECK(!app_state_next(APP_ABSENT, APP_EVENT_INIT_OK, APP_HOLD_NONE, &to));
    /* init runs once per boot; start does not run from running. */
    CHECK(!app_state_next(APP_INITIALISED, APP_EVENT_INIT_OK, APP_HOLD_NONE, &to));
    CHECK(!app_state_next(APP_RUNNING, APP_EVENT_START_OK, APP_HOLD_NONE, &to));
    CHECK(!app_state_next(APP_STOPPED, APP_EVENT_FAULT, APP_HOLD_NONE, &to));
    CHECK(to == APP_ABSENT);
    CHECK(!app_state_next(APP_RUNNING, APP_EVENT_STOPPED, APP_HOLD_NONE, NULL));
}

static app_start_inputs_t ready(app_state_t state)
{
    return (app_start_inputs_t){
        .state = state,
        .safe_mode = false,
        .prerequisites_healthy = true,
        .watchdog_armed = true,
        .start_without_watchdog = false,
    };
}

static void test_the_start_decision(void)
{
    app_hold_t hold = APP_HOLD_WATCHDOG;
    app_start_inputs_t inputs = ready(APP_INITIALISED);

    CHECK(app_start_decide(&inputs, &hold) == APP_START_GO);
    CHECK(hold == APP_HOLD_NONE);

    inputs.safe_mode = true;
    CHECK(app_start_decide(&inputs, &hold) == APP_START_HOLD);
    CHECK(hold == APP_HOLD_SAFE_MODE);

    inputs = ready(APP_STOPPED);
    inputs.prerequisites_healthy = false;
    CHECK(app_start_decide(&inputs, &hold) == APP_START_HOLD);
    CHECK(hold == APP_HOLD_PREREQUISITE);

    inputs = ready(APP_HELD);
    CHECK(app_start_decide(&inputs, &hold) == APP_START_GO);

    for (int state = APP_ABSENT; state <= APP_FAULT; state++) {
        if (state == APP_INITIALISED || state == APP_STOPPED || state == APP_HELD) {
            continue;
        }
        inputs = ready((app_state_t)state);
        CHECK(app_start_decide(&inputs, &hold) == APP_START_NOT_NOW);
        CHECK(hold == APP_HOLD_NONE);
    }
    CHECK(app_start_decide(NULL, &hold) == APP_START_NOT_NOW);
    inputs = ready(APP_INITIALISED);
    CHECK(app_start_decide(&inputs, NULL) == APP_START_GO);
}

/* R5: a watchdog that does not arm holds the application in a product build, and not with the
 * explicit option. */
static void test_a_watchdog_that_does_not_arm_holds_the_application_in_a_product_build(void)
{
    app_hold_t hold = APP_HOLD_NONE;
    app_start_inputs_t inputs = ready(APP_INITIALISED);

    inputs.watchdog_armed = false;
    CHECK(app_start_decide(&inputs, &hold) == APP_START_HOLD);
    CHECK(hold == APP_HOLD_WATCHDOG);
    inputs.start_without_watchdog = true;
    CHECK(app_start_decide(&inputs, &hold) == APP_START_GO);
}

/* Criterion 10: the counter does not clear while the application is in fault or held, nor while the
 * controller is not operational. */
static void test_the_successful_boot_conditions(void)
{
    CHECK(controller_successful_boot_conditions(CONTROLLER_OPERATIONAL, APP_ABSENT));
    CHECK(controller_successful_boot_conditions(CONTROLLER_OPERATIONAL, APP_RUNNING));
    CHECK(controller_successful_boot_conditions(CONTROLLER_OPERATIONAL, APP_STOPPED));
    CHECK(!controller_successful_boot_conditions(CONTROLLER_OPERATIONAL, APP_FAULT));
    CHECK(!controller_successful_boot_conditions(CONTROLLER_OPERATIONAL, APP_HELD));
    for (int state = CONTROLLER_STARTING; state <= CONTROLLER_RECOVERY; state++) {
        if (state != CONTROLLER_OPERATIONAL) {
            CHECK(!controller_successful_boot_conditions((controller_state_t)state, APP_RUNNING));
            CHECK(!controller_successful_boot_conditions((controller_state_t)state, APP_ABSENT));
        }
    }
}

static void test_the_names(void)
{
    CHECK(strcmp(controller_state_name(CONTROLLER_STARTING), "starting") == 0);
    CHECK(strcmp(controller_state_name(CONTROLLER_OPERATIONAL), "operational") == 0);
    CHECK(strcmp(controller_state_name(CONTROLLER_DEGRADED), "degraded") == 0);
    CHECK(strcmp(controller_state_name(CONTROLLER_RECOVERY), "recovery") == 0);
    CHECK(strcmp(controller_state_name((controller_state_t)9), "unknown") == 0);
    CHECK(strcmp(app_state_name(APP_ABSENT), "absent") == 0);
    CHECK(strcmp(app_state_name(APP_NOT_INITIALISED), "not-initialised") == 0);
    CHECK(strcmp(app_state_name(APP_HELD), "held") == 0);
    CHECK(strcmp(app_state_name(APP_FAULT), "fault") == 0);
    CHECK(strcmp(app_state_name((app_state_t)99), "unknown") == 0);
    CHECK(strcmp(service_health_name(SERVICE_HEALTHY), "healthy") == 0);
    CHECK(strcmp(service_health_name(SERVICE_ABSENT), "absent") == 0);
    CHECK(strcmp(service_health_name((service_health_t)9), "unknown") == 0);
}

int main(void)
{
    test_the_controller_states();
    test_only_a_required_service_degrades_the_controller();
    test_a_watchdog_that_is_not_armed_degrades_unless_the_build_allows_it();
    test_null_inputs_read_as_starting();
    test_the_application_transitions();
    test_the_start_decision();
    test_a_watchdog_that_does_not_arm_holds_the_application_in_a_product_build();
    test_the_successful_boot_conditions();
    test_the_names();
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
