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

/* The supervised steps: each step's begin and end go to the hooks, around the step, with its
 * deadline, and a step that its skip function leaves out is reported to the hooks and not run. */
static struct {
    const char *events[MAX_EVENTS];
    uint32_t deadlines[MAX_EVENTS];
    size_t count;
} hooked;

static void hooked_add(const char *event, uint32_t deadline)
{
    if (hooked.count < MAX_EVENTS) {
        hooked.events[hooked.count] = event;
        hooked.deadlines[hooked.count] = deadline;
        hooked.count++;
    }
}

static void hook_begin(const char *name, uint32_t deadline_ms)
{
    (void)name;
    hooked_add("begin", deadline_ms);
}

static void hook_end(const char *name)
{
    (void)name;
    hooked_add("end", 0u);
}

static void hook_skipped(const char *name)
{
    (void)name;
    hooked_add("skipped", 0u);
}

static const startup_hooks_t hooks = {hook_begin, hook_end, hook_skipped};

static bool always_skip(void)
{
    return true;
}

static bool never_skip(void)
{
    return false;
}

static void reset_hooked(void)
{
    memset(&hooked, 0, sizeof hooked);
}

static void test_supervised_steps_run_between_their_hooks_in_order(void)
{
    const startup_step_t steps[] = {
        {{"clock", clock_ok, true}, 0u, NULL},
        {{"web", web_ok, false}, 5000u, never_skip},
        {{"time", time_ok, false}, 700u, NULL},
    };
    startup_summary_t summary = {0};

    reset();
    reset_hooked();
    CHECK(startup_run_steps(steps, 3u, report, &hooks, &summary) == STARTUP_OK);
    CHECK(seen.ran_count == 3u);
    CHECK(seen.reported_count == 3u);
    CHECK(hooked.count == 6u);
    CHECK(strcmp(hooked.events[0], "begin") == 0 && hooked.deadlines[0] == 0u);
    CHECK(strcmp(hooked.events[1], "end") == 0);
    CHECK(strcmp(hooked.events[2], "begin") == 0 && hooked.deadlines[2] == 5000u);
    CHECK(strcmp(hooked.events[4], "begin") == 0 && hooked.deadlines[4] == 700u);
    CHECK(strcmp(hooked.events[5], "end") == 0);
    CHECK(summary.completed == 3u && summary.failed == 0u);
}

static void test_a_skipped_step_does_not_run_and_is_not_reported_as_a_result(void)
{
    const startup_step_t steps[] = {
        {{"clock", clock_ok, true}, 0u, NULL},
        {{"time", time_ok, false}, 700u, always_skip},
    };
    startup_summary_t summary = {0};

    reset();
    reset_hooked();
    CHECK(startup_run_steps(steps, 2u, report, &hooks, &summary) == STARTUP_OK);
    CHECK(seen.ran_count == 1u);
    CHECK(seen.reported_count == 1u);
    CHECK(hooked.count == 3u);
    CHECK(strcmp(hooked.events[2], "skipped") == 0);
    CHECK(summary.completed == 1u);
}

static void test_a_failed_required_step_ends_its_hook_and_stops(void)
{
    const startup_step_t steps[] = {
        {{"clock", clock_fails, true}, 10u, NULL},
        {{"web", web_ok, false}, 0u, NULL},
    };
    startup_summary_t summary = {0};

    reset();
    reset_hooked();
    CHECK(startup_run_steps(steps, 2u, report, &hooks, &summary) == STARTUP_ERR_REQUIRED_PHASE);
    CHECK(seen.ran_count == 1u);
    CHECK(hooked.count == 2u);
    CHECK(strcmp(hooked.events[1], "end") == 0);
    CHECK(summary.failed == 1u);
}

static void test_supervised_steps_check_their_table_and_hooks(void)
{
    const startup_step_t no_run[] = {{{"clock", NULL, true}, 0u, NULL}};
    const startup_step_t one[] = {{{"clock", clock_ok, true}, 0u, NULL}};
    const startup_hooks_t partial = {hook_begin, NULL, hook_skipped};

    reset();
    reset_hooked();
    CHECK(startup_run_steps(no_run, 1u, report, &hooks, NULL) == STARTUP_ERR_INVALID_ARGUMENT);
    CHECK(startup_run_steps(one, 1u, report, &partial, NULL) == STARTUP_ERR_INVALID_ARGUMENT);
    CHECK(startup_run_steps(NULL, 1u, report, &hooks, NULL) == STARTUP_ERR_INVALID_ARGUMENT);
    CHECK(startup_run_steps(one, 1u, NULL, &hooks, NULL) == STARTUP_ERR_INVALID_ARGUMENT);
    CHECK(seen.ran_count == 0u && hooked.count == 0u);
    /* Without hooks the steps run as phases do. */
    CHECK(startup_run_steps(one, 1u, report, NULL, NULL) == STARTUP_OK);
    CHECK(seen.ran_count == 1u && hooked.count == 0u);
}

int main(void)
{
    test_every_phase_runs_once_in_order_and_is_reported();
    test_a_failed_required_phase_stops_startup();
    test_a_failed_phase_that_is_not_required_degrades_and_continues();
    test_any_result_other_than_zero_is_a_failure();
    test_an_invalid_table_runs_nothing();
    test_an_empty_table_and_no_summary_are_accepted();
    test_supervised_steps_run_between_their_hooks_in_order();
    test_a_skipped_step_does_not_run_and_is_not_reported_as_a_result();
    test_a_failed_required_step_ends_its_hook_and_stops();
    test_supervised_steps_check_their_table_and_hooks();
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
