/* SPDX-License-Identifier: Apache-2.0 */

/* The health verdict and the trial deadline of a test image (specification section 6.1; criterion
 * 25), run against a fake image state port. Plain C, no Crux or Zephyr include.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "controller_state.h"
#include "image_state_port.h"
#include "image_trial.h"

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

/* Trial deadline and stable period of these tests, in milliseconds of the monotonic clock. */
#define DEADLINE_MS ((uint64_t)600000u)
#define STABLE_MS ((uint64_t)60000u)

/* --- the fake image state port --- */

static struct {
    image_state_t state;
    int reads;
    int confirms;
    int resets;
    bool confirm_fails;
    bool reset_fails;
} fake;

static void fake_reset(image_state_t state)
{
    memset(&fake, 0, sizeof fake);
    fake.state = state;
}

image_state_t image_state_port_read(void)
{
    fake.reads++;
    return fake.state;
}

bool image_state_port_confirm(void)
{
    fake.confirms++;
    if (fake.confirm_fails) {
        return false;
    }
    fake.state = IMAGE_STATE_CONFIRMED;
    return true;
}

bool image_state_port_request_reset(void)
{
    fake.resets++;
    return !fake.reset_fails;
}

/* --- helpers --- */

/* Every condition of the verdict holds, with the application running; both device management
 * services are in the build and started. */
static image_health_inputs_t healthy(void)
{
    image_health_inputs_t inputs;

    memset(&inputs, 0, sizeof inputs);
    inputs.controller = CONTROLLER_OPERATIONAL;
    for (int service = 0; service < SERVICE_COUNT; service++) {
        inputs.health[service] = SERVICE_HEALTHY;
    }
    inputs.application = APP_RUNNING;
    inputs.configuration_compatible = true;
    return inputs;
}

static image_trial_t trial_new(void)
{
    image_trial_t trial;
    const image_trial_config_t config = {.deadline_ms = DEADLINE_MS, .stable_period_ms = STABLE_MS};

    CHECK(image_trial_init(&trial, &config));
    return trial;
}

/* --- the verdict --- */

static void test_the_verdict_needs_the_stable_period_not_uptime_alone(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    CHECK(!image_trial_verdict(&trial, &inputs, 1000u));
    CHECK(!image_trial_verdict(&trial, &inputs, 1000u + STABLE_MS - 1u));
    CHECK(image_trial_verdict(&trial, &inputs, 1000u + STABLE_MS));
}

static void test_each_condition_keeps_the_verdict_not_healthy(void)
{
    image_health_inputs_t inputs;
    image_trial_t trial;

    /* The controller is not operational. */
    static const controller_state_t states[] = {CONTROLLER_STARTING, CONTROLLER_DEGRADED,
                                                CONTROLLER_RECOVERY};
    for (size_t i = 0; i < sizeof states / sizeof states[0]; i++) {
        trial = trial_new();
        inputs = healthy();
        inputs.controller = states[i];
        CHECK(!image_trial_verdict(&trial, &inputs, 0u));
        CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS * 2u));
    }

    /* A start prerequisite is not healthy. */
    static const service_health_t not_healthy[] = {SERVICE_DEGRADED, SERVICE_FAILED,
                                                   SERVICE_ABSENT};
    for (size_t i = 0; i < sizeof not_healthy / sizeof not_healthy[0]; i++) {
        trial = trial_new();
        inputs = healthy();
        inputs.prerequisites = BIT(SERVICE_STORAGE);
        inputs.health[SERVICE_STORAGE] = not_healthy[i];
        CHECK(!image_trial_verdict(&trial, &inputs, 0u));
        CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS * 2u));
    }

    /* A device management service of the build did not start. */
    static const service_id_t management[] = {SERVICE_WEB, SERVICE_COMMAND_LINE};
    for (size_t i = 0; i < sizeof management / sizeof management[0]; i++) {
        trial = trial_new();
        inputs = healthy();
        inputs.health[management[i]] = SERVICE_FAILED;
        CHECK(!image_trial_verdict(&trial, &inputs, 0u));
        CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS * 2u));
    }

    /* The configuration did not load with a compatible version. */
    trial = trial_new();
    inputs = healthy();
    inputs.configuration_compatible = false;
    CHECK(!image_trial_verdict(&trial, &inputs, 0u));
    CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS * 2u));

    /* The application is not running. */
    static const app_state_t applications[] = {APP_NOT_INITIALISED, APP_INITIALISED, APP_HELD,
                                               APP_STOPPED, APP_FAULT};
    for (size_t i = 0; i < sizeof applications / sizeof applications[0]; i++) {
        trial = trial_new();
        inputs = healthy();
        inputs.application = applications[i];
        CHECK(!image_trial_verdict(&trial, &inputs, 0u));
        CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS * 2u));
    }
}

static void test_a_degraded_management_service_has_started(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    /* Some command line transports started: the service has started (section 4.7). */
    inputs.health[SERVICE_COMMAND_LINE] = SERVICE_DEGRADED;
    CHECK(!image_trial_verdict(&trial, &inputs, 0u));
    CHECK(image_trial_verdict(&trial, &inputs, STABLE_MS));
}

static void test_a_service_that_is_not_a_prerequisite_does_not_count(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    /* Time is degraded and not a prerequisite; the controller is still operational. */
    inputs.health[SERVICE_TIME] = SERVICE_DEGRADED;
    CHECK(!image_trial_verdict(&trial, &inputs, 0u));
    CHECK(image_trial_verdict(&trial, &inputs, STABLE_MS));
}

static void test_the_base_image_needs_no_stable_period(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    inputs.application = APP_ABSENT;
    CHECK(image_trial_verdict(&trial, &inputs, 0u));
}

static void test_an_operator_stop_restarts_the_stable_period(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    CHECK(!image_trial_verdict(&trial, &inputs, 0u));
    CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS - 1000u));

    /* An operator stops the application: the verdict stays not healthy while it is stopped. */
    inputs.application = APP_STOPPED;
    CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS - 500u));
    CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS * 3u));

    /* Started again, it needs the whole stable period again. */
    inputs.application = APP_RUNNING;
    CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS * 4u));
    CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS * 5u - 1u));
    CHECK(image_trial_verdict(&trial, &inputs, STABLE_MS * 5u));
}

static void test_an_operator_stop_after_a_healthy_verdict_keeps_it_not_healthy(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    CHECK(!image_trial_verdict(&trial, &inputs, 0u));
    CHECK(image_trial_verdict(&trial, &inputs, STABLE_MS));
    inputs.application = APP_STOPPED;
    CHECK(!image_trial_verdict(&trial, &inputs, STABLE_MS + 1u));
}

static void test_the_verdict_refuses_a_null_argument(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();
    const image_trial_config_t config = {.deadline_ms = DEADLINE_MS, .stable_period_ms = STABLE_MS};

    CHECK(!image_trial_verdict(NULL, &inputs, STABLE_MS));
    CHECK(!image_trial_verdict(&trial, NULL, STABLE_MS));
    CHECK(!image_trial_init(NULL, &config));
    CHECK(!image_trial_init(&trial, NULL));
    CHECK(image_trial_poll(NULL, &inputs, 0u) == IMAGE_TRIAL_NONE);
    CHECK(image_trial_poll(&trial, NULL, 0u) == IMAGE_TRIAL_NONE);
}

/* --- the trial with the port --- */

static void test_a_healthy_verdict_leads_to_confirmation(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    fake_reset(IMAGE_STATE_TEST);
    CHECK(image_trial_poll(&trial, &inputs, 0u) == IMAGE_TRIAL_WAITING);
    CHECK(image_trial_poll(&trial, &inputs, STABLE_MS - 1u) == IMAGE_TRIAL_WAITING);
    CHECK(fake.confirms == 0);
    CHECK(image_trial_poll(&trial, &inputs, STABLE_MS) == IMAGE_TRIAL_CONFIRMED);
    CHECK(fake.confirms == 1);
    CHECK(fake.resets == 0);

    /* Confirmed once: later polls, even past the deadline or unhealthy, do nothing more. */
    inputs.controller = CONTROLLER_DEGRADED;
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS * 2u) == IMAGE_TRIAL_CONFIRMED);
    CHECK(fake.confirms == 1);
    CHECK(fake.resets == 0);
    CHECK(fake.reads == 1);
}

static void test_a_verdict_not_healthy_by_the_deadline_requests_a_planned_reset(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    fake_reset(IMAGE_STATE_TEST);
    inputs.controller = CONTROLLER_DEGRADED;
    CHECK(image_trial_poll(&trial, &inputs, 0u) == IMAGE_TRIAL_WAITING);
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS - 1u) == IMAGE_TRIAL_WAITING);
    CHECK(fake.resets == 0);
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS) == IMAGE_TRIAL_RESET_REQUESTED);
    CHECK(fake.resets == 1);
    CHECK(fake.confirms == 0);

    /* Requested once; a later healthy verdict confirms nothing. */
    inputs = healthy();
    inputs.application = APP_ABSENT;
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS + 1u) == IMAGE_TRIAL_RESET_REQUESTED);
    CHECK(fake.resets == 1);
    CHECK(fake.confirms == 0);
}

static void test_a_healthy_verdict_at_the_deadline_confirms(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    fake_reset(IMAGE_STATE_TEST);
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS - STABLE_MS) == IMAGE_TRIAL_WAITING);
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS) == IMAGE_TRIAL_CONFIRMED);
    CHECK(fake.resets == 0);
}

static void test_an_operator_stopped_application_runs_into_the_deadline(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    fake_reset(IMAGE_STATE_TEST);
    CHECK(image_trial_poll(&trial, &inputs, 0u) == IMAGE_TRIAL_WAITING);
    inputs.application = APP_STOPPED;
    CHECK(image_trial_poll(&trial, &inputs, STABLE_MS) == IMAGE_TRIAL_WAITING);
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS - 1u) == IMAGE_TRIAL_WAITING);
    CHECK(fake.confirms == 0);
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS) == IMAGE_TRIAL_RESET_REQUESTED);
    CHECK(fake.confirms == 0);
    CHECK(fake.resets == 1);
}

static void test_a_build_without_web_management_is_confirmed_on_the_same_conditions(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    fake_reset(IMAGE_STATE_TEST);
    inputs.health[SERVICE_WEB] = SERVICE_ABSENT;
    CHECK(image_trial_poll(&trial, &inputs, 0u) == IMAGE_TRIAL_WAITING);
    CHECK(image_trial_poll(&trial, &inputs, STABLE_MS - 1u) == IMAGE_TRIAL_WAITING);
    CHECK(image_trial_poll(&trial, &inputs, STABLE_MS) == IMAGE_TRIAL_CONFIRMED);
    CHECK(fake.confirms == 1);

    /* Without web management, the same conditions still keep the verdict not healthy. */
    trial = trial_new();
    fake_reset(IMAGE_STATE_TEST);
    inputs.configuration_compatible = false;
    CHECK(image_trial_poll(&trial, &inputs, 0u) == IMAGE_TRIAL_WAITING);
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS) == IMAGE_TRIAL_RESET_REQUESTED);
    CHECK(fake.confirms == 0);

    /* Without any device management service as well. */
    trial = trial_new();
    fake_reset(IMAGE_STATE_TEST);
    inputs = healthy();
    inputs.health[SERVICE_WEB] = SERVICE_ABSENT;
    inputs.health[SERVICE_COMMAND_LINE] = SERVICE_ABSENT;
    CHECK(image_trial_poll(&trial, &inputs, 0u) == IMAGE_TRIAL_WAITING);
    CHECK(image_trial_poll(&trial, &inputs, STABLE_MS) == IMAGE_TRIAL_CONFIRMED);
}

static void test_a_confirmed_image_or_an_unknown_state_has_no_trial(void)
{
    static const image_state_t states[] = {IMAGE_STATE_CONFIRMED, IMAGE_STATE_UNKNOWN};

    for (size_t i = 0; i < sizeof states / sizeof states[0]; i++) {
        image_trial_t trial = trial_new();
        image_health_inputs_t inputs = healthy();

        fake_reset(states[i]);
        inputs.controller = CONTROLLER_DEGRADED;
        CHECK(image_trial_poll(&trial, &inputs, 0u) == IMAGE_TRIAL_NONE);
        CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS * 2u) == IMAGE_TRIAL_NONE);
        inputs = healthy();
        CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS * 3u) == IMAGE_TRIAL_NONE);
        CHECK(fake.confirms == 0);
        CHECK(fake.resets == 0);
        /* The state is read once per boot. */
        CHECK(fake.reads == 1);
    }
}

static void test_a_failed_confirmation_is_retried_until_the_deadline(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    fake_reset(IMAGE_STATE_TEST);
    fake.confirm_fails = true;
    CHECK(image_trial_poll(&trial, &inputs, 0u) == IMAGE_TRIAL_WAITING);
    CHECK(image_trial_poll(&trial, &inputs, STABLE_MS) == IMAGE_TRIAL_WAITING);
    CHECK(fake.confirms == 1);
    CHECK(image_trial_poll(&trial, &inputs, STABLE_MS + 1000u) == IMAGE_TRIAL_WAITING);
    CHECK(fake.confirms == 2);

    /* An image that is still not confirmed at the deadline is not kept running unconfirmed. */
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS) == IMAGE_TRIAL_RESET_REQUESTED);
    CHECK(fake.resets == 1);

    /* A confirmation that succeeds on a retry ends the trial. */
    trial = trial_new();
    fake_reset(IMAGE_STATE_TEST);
    fake.confirm_fails = true;
    CHECK(image_trial_poll(&trial, &inputs, 0u) == IMAGE_TRIAL_WAITING);
    CHECK(image_trial_poll(&trial, &inputs, STABLE_MS) == IMAGE_TRIAL_WAITING);
    fake.confirm_fails = false;
    CHECK(image_trial_poll(&trial, &inputs, STABLE_MS + 1000u) == IMAGE_TRIAL_CONFIRMED);
    CHECK(fake.confirms == 2);
}

static void test_a_failed_reset_request_is_retried(void)
{
    image_trial_t trial = trial_new();
    image_health_inputs_t inputs = healthy();

    fake_reset(IMAGE_STATE_TEST);
    fake.reset_fails = true;
    inputs.configuration_compatible = false;
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS) == IMAGE_TRIAL_WAITING);
    CHECK(fake.resets == 1);
    fake.reset_fails = false;
    CHECK(image_trial_poll(&trial, &inputs, DEADLINE_MS + 1000u) == IMAGE_TRIAL_RESET_REQUESTED);
    CHECK(fake.resets == 2);
    CHECK(fake.confirms == 0);
}

static void test_the_phase_names(void)
{
    CHECK(strcmp(image_trial_phase_name(IMAGE_TRIAL_NONE), "none") == 0);
    CHECK(strcmp(image_trial_phase_name(IMAGE_TRIAL_WAITING), "waiting") == 0);
    CHECK(strcmp(image_trial_phase_name(IMAGE_TRIAL_CONFIRMED), "confirmed") == 0);
    CHECK(strcmp(image_trial_phase_name(IMAGE_TRIAL_RESET_REQUESTED), "reset-requested") == 0);
    // NOLINTNEXTLINE(clang-analyzer-optin.core.EnumCastOutOfRange): deliberate out-of-range value
    CHECK(strcmp(image_trial_phase_name((image_trial_phase_t)99), "unknown") == 0);
}

int main(void)
{
    test_the_verdict_needs_the_stable_period_not_uptime_alone();
    test_each_condition_keeps_the_verdict_not_healthy();
    test_a_degraded_management_service_has_started();
    test_a_service_that_is_not_a_prerequisite_does_not_count();
    test_the_base_image_needs_no_stable_period();
    test_an_operator_stop_restarts_the_stable_period();
    test_an_operator_stop_after_a_healthy_verdict_keeps_it_not_healthy();
    test_the_verdict_refuses_a_null_argument();
    test_a_healthy_verdict_leads_to_confirmation();
    test_a_verdict_not_healthy_by_the_deadline_requests_a_planned_reset();
    test_a_healthy_verdict_at_the_deadline_confirms();
    test_an_operator_stopped_application_runs_into_the_deadline();
    test_a_build_without_web_management_is_confirmed_on_the_same_conditions();
    test_a_confirmed_image_or_an_unknown_state_has_no_trial();
    test_a_failed_confirmation_is_retried_until_the_deadline();
    test_a_failed_reset_request_is_retried();
    test_the_phase_names();

    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
