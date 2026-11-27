/* SPDX-License-Identifier: Apache-2.0 */

/* The application contract of the controller framework (specification sections 3.3, 4.4, 4.5 and
 * 4.8; criteria 5, 10 and 22): registrations, the channel lifecycle and the order of the calls with
 * the clean-up of each failure. Fake entries and a fake channel port record every call in one log,
 * so a test reads the order as text. Plain C, no Crux or Zephyr include. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "app_contract.h"

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

/* What the fakes did, as words separated by spaces. */
static char trace[1024];

static void note(const char *word)
{
    const size_t length = strlen(trace);

    (void)snprintf(&trace[length], sizeof trace - length, "%s%s", length > 0u ? " " : "", word);
}

static void trace_clear(void)
{
    trace[0] = '\0';
}

/* The fake application. init registers what the plan says, then answers init_result. */
static struct {
    app_contract_t *contract;
    int init_result;
    int start_result;
    int stop_result;
    unsigned channels_in_init; /* channels init registers: "a", "b", ... */
    bool status_in_init;
    app_contract_status_t last_register;
    app_stop_reason_t last_reason;
    int safe_states;
} app;

static const int status_table[2] = {1, 2};
static const int parameter_table[3] = {1, 2, 3};
static const char *const channel_names[] = {"a", "b", "c", "d", "e", "f", "g", "h", "i"};

static int fake_init(void *argument)
{
    CHECK(argument == &app);
    note("init");
    for (unsigned index = 0; index < app.channels_in_init; index++) {
        size_t got = 99u;

        app.last_register = app_contract_register_channel(app.contract, channel_names[index], 100u,
                                                          &got);
        if (app.last_register == APP_CONTRACT_OK) {
            CHECK(got == index);
        }
    }
    if (app.status_in_init) {
        CHECK(app_contract_register_status(app.contract, status_table, 2u) == APP_CONTRACT_OK);
        CHECK(app_contract_register_parameters(app.contract, parameter_table, 3u) ==
              APP_CONTRACT_OK);
    }
    return app.init_result;
}

static int fake_start(void *argument)
{
    (void)argument;
    note("start");
    return app.start_result;
}

static int fake_stop(void *argument, app_stop_reason_t reason)
{
    (void)argument;
    app.last_reason = reason;
    note("stop");
    return app.stop_result;
}

static void fake_safe_state(void *argument)
{
    (void)argument;
    app.safe_states++;
    note("safe");
}

/* The fake task watchdog: handles count up from 10, so that a test can tell a handle from an index.
 */
static struct {
    int next_handle;
    int fail_at; /* the add with this number (from 1) fails; 0 for none */
    int adds;
    int active;
    int last_fed;
} port;

static int fake_add(void *context, const char *name, uint32_t reload_ms)
{
    char word[48];

    CHECK(context == &port);
    CHECK(reload_ms > 0u);
    port.adds++;
    if (port.adds == port.fail_at) {
        (void)snprintf(word, sizeof word, "add-%s-refused", name);
        note(word);
        return -1;
    }
    (void)snprintf(word, sizeof word, "add-%s", name);
    note(word);
    port.active++;
    return port.next_handle++;
}

static void fake_remove(void *context, int handle)
{
    char word[32];

    (void)context;
    (void)snprintf(word, sizeof word, "remove-%d", handle);
    note(word);
    port.active--;
}

static void fake_feed(void *context, int handle)
{
    (void)context;
    port.last_fed = handle;
}

static app_entries_t entries(void)
{
    return (app_entries_t){fake_init, fake_start, fake_stop, fake_safe_state, &app};
}

static const app_channel_port_t channel_port = {fake_add, fake_remove, fake_feed, &port};

static const app_start_conditions_t go = {false, true, true, false};

static void reset(app_contract_t *contract, size_t capacity)
{
    const app_entries_t given = entries();

    memset(&app, 0, sizeof app);
    memset(&port, 0, sizeof port);
    port.next_handle = 10;
    port.last_fed = -1;
    app.contract = contract;
    app.channels_in_init = 2u;
    app.status_in_init = true;
    trace_clear();
    app_contract_init(contract, &given, &channel_port, capacity);
}

static void test_a_descriptor_needs_every_entry(void)
{
    app_entries_t given = entries();

    CHECK(app_entries_complete(&given));
    CHECK(!app_entries_complete(NULL));
    given.init = NULL;
    CHECK(!app_entries_complete(&given));
    given = entries();
    given.start = NULL;
    CHECK(!app_entries_complete(&given));
    given = entries();
    given.stop = NULL;
    CHECK(!app_entries_complete(&given));
    given = entries();
    given.safe_state = NULL;
    CHECK(!app_entries_complete(&given));
}

static void test_no_descriptor_is_absent(void)
{
    app_contract_t contract;

    app_contract_init(&contract, NULL, &channel_port, 4u);
    CHECK(app_contract_state(&contract) == APP_ABSENT);
    CHECK(app_contract_run_init(&contract) == -1);
    CHECK(app_contract_start(&contract, &go, false) == APP_RUN_NOT_NOW);
    CHECK(app_contract_stop(&contract, APP_STOP_OPERATOR) == APP_STOP_NOT_NOW);
    CHECK(!app_contract_supervisor_safe_state(&contract));
    CHECK(!app_contract_items_available(&contract));
}

static void test_init_then_start_runs_in_order_and_activates_before_start(void)
{
    app_contract_t contract;
    size_t count = 0u;

    reset(&contract, 4u);
    CHECK(app_contract_state(&contract) == APP_NOT_INITIALISED);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_state(&contract) == APP_INITIALISED);
    /* Registration creates no channel. */
    CHECK(strcmp(trace, "init") == 0);
    CHECK(port.adds == 0);
    CHECK(app_contract_requirement_count(&contract) == 2u);
    CHECK(strcmp(app_contract_requirement_name(&contract, 1u), "b") == 0);
    CHECK(app_contract_requirement_name(&contract, 2u) == NULL);
    CHECK(app_contract_status_items(&contract, &count) == status_table && count == 2u);
    CHECK(app_contract_parameters(&contract, &count) == parameter_table && count == 3u);
    CHECK(app_contract_items_available(&contract));

    CHECK(app_contract_start(&contract, &go, false) == APP_RUN_STARTED);
    CHECK(strcmp(trace, "init add-a add-b start") == 0);
    CHECK(app_contract_state(&contract) == APP_RUNNING);
    /* A feed goes to the port's handle of that index. */
    app_contract_feed(&contract, 1u);
    CHECK(port.last_fed == 11);
    app_contract_feed(&contract, 7u);
    CHECK(port.last_fed == 11);
}

static void test_registration_is_closed_outside_init(void)
{
    app_contract_t contract;
    size_t index = 0u;

    reset(&contract, 4u);
    CHECK(app_contract_register_channel(&contract, "x", 10u, &index) == APP_CONTRACT_ERR_CLOSED);
    CHECK(app_contract_register_status(&contract, status_table, 2u) == APP_CONTRACT_ERR_CLOSED);
    CHECK(app_contract_register_parameters(&contract, parameter_table, 1u) ==
          APP_CONTRACT_ERR_CLOSED);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_register_channel(&contract, "x", 10u, &index) == APP_CONTRACT_ERR_CLOSED);
    CHECK(app_contract_requirement_count(&contract) == 2u);
}

/* Criterion 22, host part: a requirement beyond the capacity and a duplicate name are refused in
 * init, and init sees the error. */
static void test_capacity_and_duplicates_are_refused_in_init(void)
{
    app_contract_t contract;

    reset(&contract, 2u);
    app.channels_in_init = 3u;
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app.last_register == APP_CONTRACT_ERR_FULL);
    CHECK(app_contract_requirement_count(&contract) == 2u);

    reset(&contract, 0u);
    app.channels_in_init = 1u;
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app.last_register == APP_CONTRACT_ERR_FULL);

    /* The capacity is cut to the table. */
    reset(&contract, 100u);
    app.channels_in_init = APP_CONTRACT_CHANNELS_MAX + 1u;
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app.last_register == APP_CONTRACT_ERR_FULL);
    CHECK(app_contract_requirement_count(&contract) == APP_CONTRACT_CHANNELS_MAX);
}

static app_contract_t *registering;
static app_contract_status_t duplicate_result;
static app_contract_status_t zero_result;
static app_contract_status_t long_result;
static app_contract_status_t table_twice_result;
static app_contract_status_t empty_table_result;

static int init_with_bad_registrations(void *argument)
{
    size_t index = 0u;

    (void)argument;
    CHECK(app_contract_register_channel(registering, "same", 10u, &index) == APP_CONTRACT_OK);
    duplicate_result = app_contract_register_channel(registering, "same", 20u, &index);
    zero_result = app_contract_register_channel(registering, "zero", 0u, &index);
    long_result = app_contract_register_channel(
        registering, "a name that is longer than thirty-one bytes", 10u, &index);
    CHECK(app_contract_register_channel(registering, NULL, 10u, &index) ==
          APP_CONTRACT_ERR_INVALID);
    CHECK(app_contract_register_channel(registering, "", 10u, &index) == APP_CONTRACT_ERR_INVALID);
    CHECK(app_contract_register_channel(registering, "noindex", 10u, NULL) ==
          APP_CONTRACT_ERR_INVALID);
    CHECK(app_contract_register_status(registering, status_table, 2u) == APP_CONTRACT_OK);
    table_twice_result = app_contract_register_status(registering, status_table, 2u);
    empty_table_result = app_contract_register_parameters(registering, parameter_table, 0u);
    CHECK(app_contract_register_parameters(registering, NULL, 1u) == APP_CONTRACT_ERR_INVALID);
    return 0;
}

static void test_bad_registrations_are_refused(void)
{
    app_contract_t contract;
    app_entries_t given = entries();

    given.init = init_with_bad_registrations;
    registering = &contract;
    app_contract_init(&contract, &given, &channel_port, 4u);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(duplicate_result == APP_CONTRACT_ERR_DUPLICATE);
    CHECK(zero_result == APP_CONTRACT_ERR_INVALID);
    CHECK(long_result == APP_CONTRACT_ERR_INVALID);
    CHECK(table_twice_result == APP_CONTRACT_ERR_DUPLICATE);
    CHECK(empty_table_result == APP_CONTRACT_ERR_INVALID);
    CHECK(app_contract_requirement_count(&contract) == 1u);
}

/* Section 3.3, partial init failure: safe_state, the registrations released, fault, and neither
 * start nor stop afterwards. */
static void test_a_failed_init_cleans_up_and_enters_fault(void)
{
    app_contract_t contract;
    size_t count = 9u;

    reset(&contract, 4u);
    app.init_result = -5;
    CHECK(app_contract_run_init(&contract) == -5);
    CHECK(strcmp(trace, "init safe") == 0);
    CHECK(app_contract_state(&contract) == APP_FAULT);
    CHECK(app_contract_requirement_count(&contract) == 0u);
    CHECK(!app_contract_items_available(&contract));
    CHECK(app_contract_status_items(&contract, &count) == NULL && count == 0u);
    CHECK(app_contract_parameters(&contract, &count) == NULL && count == 0u);
    CHECK(app_contract_start(&contract, &go, false) == APP_RUN_NOT_NOW);
    CHECK(app_contract_start(&contract, &go, true) == APP_RUN_NOT_NOW);
    CHECK(app_contract_stop(&contract, APP_STOP_OPERATOR) == APP_STOP_NOT_NOW);
    CHECK(strcmp(trace, "init safe") == 0);
    /* init runs once per boot. */
    CHECK(app_contract_run_init(&contract) == -1);
}

/* Section 4.4, partial activation: start is not called, safe_state runs, the channels activated in
 * this step are deleted and the registrations released. */
static void test_a_failed_activation_deletes_what_it_activated(void)
{
    app_contract_t contract;

    reset(&contract, 4u);
    app.channels_in_init = 3u;
    port.fail_at = 3;
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_start(&contract, &go, false) == APP_RUN_FAILED);
    CHECK(strcmp(trace, "init add-a add-b add-c-refused safe remove-10 remove-11") == 0);
    CHECK(port.active == 0);
    CHECK(app_contract_state(&contract) == APP_FAULT);
    CHECK(app_contract_requirement_count(&contract) == 0u);
    CHECK(!app_contract_items_available(&contract));
}

/* Section 3.3, partial start failure: safe_state, the activated channels deleted, the registrations
 * released, fault; stop is not called. */
static void test_a_failed_start_cleans_up_and_enters_fault(void)
{
    app_contract_t contract;

    reset(&contract, 4u);
    app.start_result = -1;
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_start(&contract, &go, false) == APP_RUN_FAILED);
    CHECK(strcmp(trace, "init add-a add-b start safe remove-10 remove-11") == 0);
    CHECK(app_contract_state(&contract) == APP_FAULT);
    CHECK(app_contract_requirement_count(&contract) == 0u);
    CHECK(app_contract_stop(&contract, APP_STOP_OPERATOR) == APP_STOP_NOT_NOW);
}

/* Section 4.4: an operator stop calls stop, then safe_state, then deletes the channels and keeps
 * the requirements; an operator start activates them again (new handles) without init. */
static void test_operator_stop_and_start(void)
{
    app_contract_t contract;

    reset(&contract, 4u);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_start(&contract, &go, false) == APP_RUN_STARTED);
    trace_clear();
    CHECK(app_contract_stop(&contract, APP_STOP_OPERATOR) == APP_STOPPED_OK);
    CHECK(app.last_reason == APP_STOP_OPERATOR);
    CHECK(strcmp(trace, "stop safe remove-10 remove-11") == 0);
    CHECK(app_contract_state(&contract) == APP_STOPPED);
    CHECK(app_contract_requirement_count(&contract) == 2u);
    CHECK(app_contract_items_available(&contract));
    /* A feed while stopped reaches no channel. */
    port.last_fed = -1;
    app_contract_feed(&contract, 0u);
    CHECK(port.last_fed == -1);

    trace_clear();
    CHECK(app_contract_start(&contract, &go, true) == APP_RUN_STARTED);
    CHECK(strcmp(trace, "add-a add-b start") == 0);
    CHECK(app_contract_state(&contract) == APP_RUNNING);
    app_contract_feed(&contract, 0u);
    CHECK(port.last_fed == 12);
    /* A second operator start while running is not a start. */
    CHECK(app_contract_start(&contract, &go, true) == APP_RUN_NOT_NOW);
}

/* An operator start from stopped with a start prerequisite that is not healthy does nothing. */
static void test_operator_start_checks_the_prerequisites(void)
{
    app_contract_t contract;
    const app_start_conditions_t unhealthy = {false, false, true, false};

    reset(&contract, 4u);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_start(&contract, &go, false) == APP_RUN_STARTED);
    CHECK(app_contract_stop(&contract, APP_STOP_OPERATOR) == APP_STOPPED_OK);
    trace_clear();
    CHECK(app_contract_start(&contract, &unhealthy, true) == APP_RUN_HELD);
    CHECK(strcmp(trace, "") == 0);
    CHECK(app_contract_state(&contract) == APP_STOPPED);
}

/* Step 12 holds for a start prerequisite; an operator start then runs once it is healthy. A hold
 * for safe mode or the watchdog leaves only through a reset. */
static void test_a_hold_and_the_operator_start_that_ends_it(void)
{
    app_contract_t contract;
    const app_start_conditions_t unhealthy = {false, false, true, false};
    const app_start_conditions_t no_watchdog = {false, true, false, false};

    reset(&contract, 4u);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_start(&contract, &unhealthy, false) == APP_RUN_HELD);
    CHECK(app_contract_state(&contract) == APP_HELD);
    CHECK(app_contract_hold(&contract) == APP_HOLD_PREREQUISITE);
    CHECK(app_contract_start(&contract, &unhealthy, true) == APP_RUN_HELD);
    CHECK(app_contract_state(&contract) == APP_HELD);
    CHECK(app_contract_start(&contract, &go, true) == APP_RUN_STARTED);
    CHECK(app_contract_state(&contract) == APP_RUNNING);
    CHECK(app_contract_hold(&contract) == APP_HOLD_NONE);

    reset(&contract, 4u);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_start(&contract, &no_watchdog, false) == APP_RUN_HELD);
    CHECK(app_contract_hold(&contract) == APP_HOLD_WATCHDOG);
    trace_clear();
    CHECK(app_contract_start(&contract, &go, true) == APP_RUN_NOT_NOW);
    CHECK(strcmp(trace, "") == 0);

    /* With the explicit option, a watchdog that is not armed does not hold (D14). */
    const app_start_conditions_t allowed = {false, true, false, true};

    reset(&contract, 4u);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_start(&contract, &allowed, false) == APP_RUN_STARTED);
}

/* A failed operator start from held enters fault with the clean-up of a partial start. */
static void test_a_failed_operator_start_from_held_enters_fault(void)
{
    app_contract_t contract;
    const app_start_conditions_t unhealthy = {false, false, true, false};

    reset(&contract, 4u);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_start(&contract, &unhealthy, false) == APP_RUN_HELD);
    app.start_result = -2;
    trace_clear();
    CHECK(app_contract_start(&contract, &go, true) == APP_RUN_FAILED);
    CHECK(strcmp(trace, "add-a add-b start safe remove-10 remove-11") == 0);
    CHECK(app_contract_state(&contract) == APP_FAULT);
}

static void test_safe_mode_holds_without_init(void)
{
    app_contract_t contract;

    reset(&contract, 4u);
    app_contract_hold_safe_mode(&contract);
    CHECK(app_contract_state(&contract) == APP_HELD);
    CHECK(app_contract_hold(&contract) == APP_HOLD_SAFE_MODE);
    CHECK(strcmp(trace, "") == 0);
    CHECK(app_contract_run_init(&contract) == -1);
    CHECK(app_contract_start(&contract, &go, true) == APP_RUN_NOT_NOW);
    /* Not initialised: the supervisor calls no safe_state. */
    CHECK(!app_contract_supervisor_safe_state(&contract));
}

/* Section 4.8: a reported fault is taken once by the framework thread, then stop runs with the
 * reason application fault, then safe_state, then the channels go and the registrations are
 * released. */
static void test_a_reported_fault_stops_and_releases(void)
{
    app_contract_t contract;

    reset(&contract, 4u);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_start(&contract, &go, false) == APP_RUN_STARTED);
    CHECK(!app_contract_take_fault(&contract));
    app_contract_report_fault(&contract);
    app_contract_report_fault(&contract);
    CHECK(app_contract_take_fault(&contract));
    CHECK(!app_contract_take_fault(&contract));
    trace_clear();
    CHECK(app_contract_stop(&contract, APP_STOP_FAULT) == APP_STOPPED_OK);
    CHECK(app.last_reason == APP_STOP_FAULT);
    CHECK(strcmp(trace, "stop safe remove-10 remove-11") == 0);
    CHECK(app_contract_state(&contract) == APP_FAULT);
    CHECK(app_contract_requirement_count(&contract) == 0u);
    CHECK(!app_contract_items_available(&contract));
    /* A fault leaves only through a reset. */
    CHECK(app_contract_start(&contract, &go, true) == APP_RUN_NOT_NOW);
}

/* A stop that returns an error is a hang: nothing more runs here, and the state stays running. */
static void test_a_stop_error_is_a_hang(void)
{
    app_contract_t contract;

    reset(&contract, 4u);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_start(&contract, &go, false) == APP_RUN_STARTED);
    app.stop_result = -1;
    trace_clear();
    CHECK(app_contract_stop(&contract, APP_STOP_OPERATOR) == APP_STOP_HANG);
    CHECK(strcmp(trace, "stop") == 0);
    CHECK(app_contract_state(&contract) == APP_RUNNING);
    CHECK(port.active == 2);
    /* The supervisor then calls safe_state, because init succeeded. */
    CHECK(app_contract_supervisor_safe_state(&contract));
    CHECK(strcmp(trace, "stop safe") == 0);
}

static void test_the_supervisor_calls_safe_state_only_after_init(void)
{
    app_contract_t contract;

    reset(&contract, 4u);
    CHECK(!app_contract_supervisor_safe_state(&contract));
    CHECK(app.safe_states == 0);
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_supervisor_safe_state(&contract));
    CHECK(app.safe_states == 1);
}

/* The status and parameter tables are one each and only from init. */
static void test_the_tables_stay_until_released(void)
{
    app_contract_t contract;
    size_t count = 0u;

    reset(&contract, 4u);
    app.status_in_init = false;
    CHECK(app_contract_run_init(&contract) == 0);
    CHECK(app_contract_status_items(&contract, &count) == NULL && count == 0u);
    CHECK(app_contract_parameters(&contract, NULL) == NULL);
}

int main(void)
{
    test_a_descriptor_needs_every_entry();
    test_no_descriptor_is_absent();
    test_init_then_start_runs_in_order_and_activates_before_start();
    test_registration_is_closed_outside_init();
    test_capacity_and_duplicates_are_refused_in_init();
    test_bad_registrations_are_refused();
    test_a_failed_init_cleans_up_and_enters_fault();
    test_a_failed_activation_deletes_what_it_activated();
    test_a_failed_start_cleans_up_and_enters_fault();
    test_operator_stop_and_start();
    test_operator_start_checks_the_prerequisites();
    test_a_hold_and_the_operator_start_that_ends_it();
    test_a_failed_operator_start_from_held_enters_fault();
    test_safe_mode_holds_without_init();
    test_a_reported_fault_stops_and_releases();
    test_a_stop_error_is_a_hang();
    test_the_supervisor_calls_safe_state_only_after_init();
    test_the_tables_stay_until_released();
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
