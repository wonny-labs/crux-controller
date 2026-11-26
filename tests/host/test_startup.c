/* SPDX-License-Identifier: Apache-2.0 */

/* The startup sequence of the controller framework: plain C, no Crux or Zephyr include. */

#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "startup.h"

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

#define MAX_EVENTS 16

/* What the phases and the report saw, in order. */
static struct {
    const char *ran[MAX_EVENTS];
    size_t ran_count;
    const char *reported[MAX_EVENTS];
    int results[MAX_EVENTS];
    size_t reported_count;
} seen;

static void reset(void)
{
    memset(&seen, 0, sizeof seen);
}

static void ran(const char *name)
{
    if (seen.ran_count < MAX_EVENTS) {
        seen.ran[seen.ran_count++] = name;
    }
}

static int clock_ok(void)
{
    ran("clock");
    return 0;
}

static int clock_fails(void)
{
    ran("clock");
    return -7;
}

static int storage_fails(void)
{
    ran("storage");
    return -3;
}

static int storage_fails_positive(void)
{
    ran("storage");
    return 5;
}

static int web_ok(void)
{
    ran("web");
    return 0;
}

static int time_ok(void)
{
    ran("time");
    return 0;
}

static void report(const char *name, int result)
{
    if (seen.reported_count < MAX_EVENTS) {
        seen.reported[seen.reported_count] = name;
        seen.results[seen.reported_count] = result;
        seen.reported_count++;
    }
}

static void test_every_phase_runs_once_in_order_and_is_reported(void)
{
    const startup_phase_t phases[] = {
        {"clock", clock_ok, true},
        {"web", web_ok, false},
        {"time", time_ok, false},
    };
    startup_summary_t summary = {0};

    reset();
    CHECK(startup_run(phases, 3u, report, &summary) == STARTUP_OK);
    CHECK(seen.ran_count == 3u);
    CHECK(strcmp(seen.ran[0], "clock") == 0);
    CHECK(strcmp(seen.ran[1], "web") == 0);
    CHECK(strcmp(seen.ran[2], "time") == 0);
    CHECK(seen.reported_count == 3u);
    CHECK(strcmp(seen.reported[0], "clock") == 0 && seen.results[0] == 0);
    CHECK(strcmp(seen.reported[2], "time") == 0 && seen.results[2] == 0);
    CHECK(summary.completed == 3u);
    CHECK(summary.failed == 0u);
}

static void test_a_failed_required_phase_stops_startup(void)
{
    const startup_phase_t phases[] = {
        {"clock", clock_fails, true},
        {"web", web_ok, false},
    };
    startup_summary_t summary = {0};

    reset();
    CHECK(startup_run(phases, 2u, report, &summary) == STARTUP_ERR_REQUIRED_PHASE);
    CHECK(seen.ran_count == 1u);
    CHECK(seen.reported_count == 1u);
    CHECK(strcmp(seen.reported[0], "clock") == 0 && seen.results[0] == -7);
    CHECK(summary.completed == 1u);
    CHECK(summary.failed == 1u);
}

static void test_a_failed_phase_that_is_not_required_degrades_and_continues(void)
{
    const startup_phase_t phases[] = {
        {"clock", clock_ok, true},
        {"storage", storage_fails, false},
        {"time", time_ok, false},
    };
    startup_summary_t summary = {0};

    reset();
    CHECK(startup_run(phases, 3u, report, &summary) == STARTUP_OK);
    CHECK(seen.ran_count == 3u);
    CHECK(strcmp(seen.reported[1], "storage") == 0 && seen.results[1] == -3);
    CHECK(summary.completed == 3u);
    CHECK(summary.failed == 1u);
}

static void test_any_result_other_than_zero_is_a_failure(void)
{
    const startup_phase_t phases[] = {
        {"storage", storage_fails_positive, true},
        {"time", time_ok, false},
    };
    startup_summary_t summary = {0};

    reset();
    CHECK(startup_run(phases, 2u, report, &summary) == STARTUP_ERR_REQUIRED_PHASE);
    CHECK(seen.ran_count == 1u);
    CHECK(seen.results[0] == 5);
    CHECK(summary.failed == 1u);
}

static void test_an_invalid_table_runs_nothing(void)
{
    const startup_phase_t no_name[] = {{"clock", clock_ok, true}, {NULL, web_ok, false}};
    const startup_phase_t no_run[] = {{"clock", clock_ok, true}, {"web", NULL, false}};
    startup_summary_t summary = {.completed = 9u, .failed = 9u};

    reset();
    CHECK(startup_run(NULL, 1u, report, &summary) == STARTUP_ERR_INVALID_ARGUMENT);
    CHECK(startup_run(no_name, 2u, report, &summary) == STARTUP_ERR_INVALID_ARGUMENT);
    CHECK(startup_run(no_run, 2u, report, &summary) == STARTUP_ERR_INVALID_ARGUMENT);
    CHECK(startup_run(no_run, 1u, NULL, &summary) == STARTUP_ERR_INVALID_ARGUMENT);
    CHECK(seen.ran_count == 0u);
    CHECK(seen.reported_count == 0u);
    CHECK(summary.completed == 0u && summary.failed == 0u);
}

static void test_an_empty_table_and_no_summary_are_accepted(void)
{
    const startup_phase_t phases[] = {{"clock", clock_ok, true}};

    reset();
    CHECK(startup_run(NULL, 0u, report, NULL) == STARTUP_OK);
    CHECK(startup_run(phases, 1u, report, NULL) == STARTUP_OK);
    CHECK(seen.ran_count == 1u);
}

int main(void)
{
    test_every_phase_runs_once_in_order_and_is_reported();
    test_a_failed_required_phase_stops_startup();
    test_a_failed_phase_that_is_not_required_degrades_and_continues();
    test_any_result_other_than_zero_is_a_failure();
    test_an_invalid_table_runs_nothing();
    test_an_empty_table_and_no_summary_are_accepted();
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
