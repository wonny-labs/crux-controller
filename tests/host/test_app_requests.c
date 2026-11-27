/* SPDX-License-Identifier: Apache-2.0 */

/* The operator requests and the planned-reset gate of the application thread (specification
 * sections 3.3 and 4.8; criterion 21): plain C, no Crux or Zephyr include. */

#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

#include "app_requests.h"

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

/* Requests after startup supervision ended in step 12. */
static void after_startup(app_requests_t *requests)
{
    app_requests_init(requests);
    app_requests_startup_returned(requests, true);
}

static void test_operator_requests_wait_for_the_end_of_startup(void)
{
    app_requests_t requests;

    app_requests_init(&requests);
    CHECK(app_requests_post(&requests, APP_REQUEST_STOP) == APP_REQUEST_REFUSED_STARTING);
    CHECK(app_requests_post(&requests, APP_REQUEST_START) == APP_REQUEST_REFUSED_STARTING);
    CHECK(app_requests_take(&requests) == APP_REQUEST_NONE);

    /* A startup that stopped before step 12 ended keeps refusing them. */
    app_requests_startup_returned(&requests, false);
    CHECK(app_requests_post(&requests, APP_REQUEST_START) == APP_REQUEST_REFUSED_STARTING);

    after_startup(&requests);
    CHECK(app_requests_post(&requests, APP_REQUEST_STOP) == APP_REQUEST_ACCEPTED);
    CHECK(app_requests_take(&requests) == APP_REQUEST_STOP);
    CHECK(app_requests_take(&requests) == APP_REQUEST_NONE);
}

static void test_a_request_that_is_not_stop_or_start_is_invalid(void)
{
    app_requests_t requests;

    after_startup(&requests);
    CHECK(app_requests_post(&requests, APP_REQUEST_NONE) == APP_REQUEST_INVALID);
    CHECK(app_requests_post(NULL, APP_REQUEST_START) == APP_REQUEST_INVALID);
    CHECK(app_requests_take(&requests) == APP_REQUEST_NONE);
}

/* "start" then "stop" in one batch: the newer stop wins, so the application ends stopped. */
static void test_a_newer_stop_supersedes_an_older_start(void)
{
    app_requests_t requests;

    after_startup(&requests);
    CHECK(app_requests_post(&requests, APP_REQUEST_START) == APP_REQUEST_ACCEPTED);
    CHECK(app_requests_post(&requests, APP_REQUEST_STOP) == APP_REQUEST_ACCEPTED);
    CHECK(app_requests_take(&requests) == APP_REQUEST_STOP);
    CHECK(app_requests_take(&requests) == APP_REQUEST_NONE);
}

/* "stop" then "start" in one batch: the newer start wins. */
static void test_a_newer_start_supersedes_an_older_stop(void)
{
    app_requests_t requests;

    after_startup(&requests);
    CHECK(app_requests_post(&requests, APP_REQUEST_STOP) == APP_REQUEST_ACCEPTED);
    CHECK(app_requests_post(&requests, APP_REQUEST_START) == APP_REQUEST_ACCEPTED);
    CHECK(app_requests_take(&requests) == APP_REQUEST_START);
    CHECK(app_requests_take(&requests) == APP_REQUEST_NONE);
}

/* A planned reset is refused while the step table runs, because step 12 may still call start. */
static void test_a_planned_reset_waits_for_the_step_table(void)
{
    app_requests_t requests;

    app_requests_init(&requests);
    CHECK(!app_requests_reset_allowed(&requests));
    CHECK(!app_requests_plan_reset(&requests));

    /* Also after a startup that stopped: no step calls start any more. */
    app_requests_startup_returned(&requests, false);
    CHECK(app_requests_reset_allowed(&requests));
    CHECK(app_requests_plan_reset(&requests));

    after_startup(&requests);
    CHECK(app_requests_reset_allowed(&requests));
    CHECK(app_requests_plan_reset(&requests));
}

/* A start that waits when the reset is planned never runs, so the reset comes after stop and
 * safe_state. */
static void test_a_planned_reset_drops_a_pending_start(void)
{
    app_requests_t requests;

    after_startup(&requests);
    CHECK(app_requests_post(&requests, APP_REQUEST_START) == APP_REQUEST_ACCEPTED);
    CHECK(app_requests_plan_reset(&requests));
    CHECK(app_requests_take(&requests) == APP_REQUEST_NONE);
}

/* An operator request after the reset is planned is refused. */
static void test_a_planned_reset_refuses_later_requests(void)
{
    app_requests_t requests;

    after_startup(&requests);
    CHECK(app_requests_plan_reset(&requests));
    CHECK(app_requests_post(&requests, APP_REQUEST_START) == APP_REQUEST_REFUSED_RESET);
    CHECK(app_requests_post(&requests, APP_REQUEST_STOP) == APP_REQUEST_REFUSED_RESET);
    CHECK(app_requests_take(&requests) == APP_REQUEST_NONE);
}

/* A start stored by a thread that checked the gate just before the reset was planned is dropped
 * when the application thread takes it. */
static void test_a_start_stored_across_the_planned_reset_is_dropped(void)
{
    app_requests_t requests;

    after_startup(&requests);
    CHECK(app_requests_plan_reset(&requests));
    /* The store of the racing post, without its check. */
    atomic_store(&requests.pending, (int)APP_REQUEST_START);
    CHECK(app_requests_take(&requests) == APP_REQUEST_NONE);
}

/* When the reset did not happen, operator requests are accepted again. */
static void test_an_abandoned_reset_opens_the_gate_again(void)
{
    app_requests_t requests;

    after_startup(&requests);
    CHECK(app_requests_plan_reset(&requests));
    app_requests_reset_abandoned(&requests);
    CHECK(app_requests_post(&requests, APP_REQUEST_START) == APP_REQUEST_ACCEPTED);
    CHECK(app_requests_take(&requests) == APP_REQUEST_START);
}

static void test_null_is_refused(void)
{
    CHECK(app_requests_take(NULL) == APP_REQUEST_NONE);
    CHECK(!app_requests_reset_allowed(NULL));
    CHECK(!app_requests_plan_reset(NULL));
    app_requests_init(NULL);
    app_requests_startup_returned(NULL, true);
    app_requests_reset_abandoned(NULL);
}

int main(void)
{
    test_operator_requests_wait_for_the_end_of_startup();
    test_a_request_that_is_not_stop_or_start_is_invalid();
    test_a_newer_stop_supersedes_an_older_start();
    test_a_newer_start_supersedes_an_older_stop();
    test_a_planned_reset_waits_for_the_step_table();
    test_a_planned_reset_drops_a_pending_start();
    test_a_planned_reset_refuses_later_requests();
    test_a_start_stored_across_the_planned_reset_is_dropped();
    test_an_abandoned_reset_opens_the_gate_again();
    test_null_is_refused();
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
