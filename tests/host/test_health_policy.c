/* SPDX-License-Identifier: Apache-2.0 */

/* The reset-cause and watchdog policy of step S4: plain C, no Crux or Zephyr include. */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "health_policy.h"

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

/* The flag values are Crux's; the glue asserts them against <crux/system.h> at build time. */
static void flag_values_are_the_documented_bits(void)
{
    CHECK(HEALTH_CAUSE_POR == (1u << 0));
    CHECK(HEALTH_CAUSE_PIN == (1u << 1));
    CHECK(HEALTH_CAUSE_SOFTWARE == (1u << 2));
    CHECK(HEALTH_CAUSE_WATCHDOG == (1u << 3));
    CHECK(HEALTH_CAUSE_DEBUG == (1u << 4));
    CHECK(HEALTH_CAUSE_CPU_LOCKUP == (1u << 5));
    CHECK(HEALTH_CAUSE_HARDWARE == (1u << 6));
    CHECK(HEALTH_CAUSE_SECURITY == (1u << 7));
    CHECK(HEALTH_CAUSE_USER == (1u << 8));
    CHECK(HEALTH_CAUSE_TEMPERATURE == (1u << 9));
    CHECK(HEALTH_CAUSE_OTHER == (1u << 10));
}

static void causes_that_someone_asked_for_are_normal(void)
{
    const uint32_t normal[] = {HEALTH_CAUSE_POR,      HEALTH_CAUSE_PIN,  HEALTH_CAUSE_SOFTWARE,
                               HEALTH_CAUSE_DEBUG,    HEALTH_CAUSE_USER, HEALTH_CAUSE_HARDWARE,
                               HEALTH_CAUSE_POR | HEALTH_CAUSE_PIN};

    for (size_t i = 0; i < sizeof normal / sizeof normal[0]; i++) {
        CHECK(health_cause_classify(normal[i]) == HEALTH_CLASS_NORMAL);
    }
}

static void a_watchdog_reset_is_its_own_class(void)
{
    CHECK(health_cause_classify(HEALTH_CAUSE_WATCHDOG) == HEALTH_CLASS_WATCHDOG);
    /* Flags can accumulate: the watchdog outranks the ordinary ones. */
    CHECK(health_cause_classify(HEALTH_CAUSE_POR | HEALTH_CAUSE_WATCHDOG) == HEALTH_CLASS_WATCHDOG);
}

static void a_lockup_a_security_or_a_temperature_reset_is_a_fault(void)
{
    CHECK(health_cause_classify(HEALTH_CAUSE_CPU_LOCKUP) == HEALTH_CLASS_FAULT);
    CHECK(health_cause_classify(HEALTH_CAUSE_SECURITY) == HEALTH_CLASS_FAULT);
    CHECK(health_cause_classify(HEALTH_CAUSE_TEMPERATURE) == HEALTH_CLASS_FAULT);
    /* A fault outranks the watchdog and the ordinary causes. */
    CHECK(health_cause_classify(HEALTH_CAUSE_WATCHDOG | HEALTH_CAUSE_CPU_LOCKUP) ==
          HEALTH_CLASS_FAULT);
    CHECK(health_cause_classify(HEALTH_CAUSE_POR | HEALTH_CAUSE_TEMPERATURE) == HEALTH_CLASS_FAULT);
}

static void no_flag_or_only_an_unknown_one_is_unknown(void)
{
    CHECK(health_cause_classify(0) == HEALTH_CLASS_UNKNOWN);
    CHECK(health_cause_classify(HEALTH_CAUSE_OTHER) == HEALTH_CLASS_UNKNOWN);
    CHECK(health_cause_classify(UINT32_C(1) << 20) == HEALTH_CLASS_UNKNOWN);
    /* A known flag decides, whatever else is set. */
    CHECK(health_cause_classify(HEALTH_CAUSE_OTHER | HEALTH_CAUSE_POR) == HEALTH_CLASS_NORMAL);
}

static void the_boot_decision_sets_the_log_level_and_never_stops_the_start(void)
{
    health_boot_decision_t decision = health_boot_decide(HEALTH_CAUSE_POR);

    CHECK(decision.cause_class == HEALTH_CLASS_NORMAL);
    CHECK(decision.level == HEALTH_LOG_INFO);
    CHECK(decision.start_watchdog);

    decision = health_boot_decide(HEALTH_CAUSE_WATCHDOG);
    CHECK(decision.cause_class == HEALTH_CLASS_WATCHDOG);
    CHECK(decision.level == HEALTH_LOG_WARN);
    CHECK(decision.start_watchdog);

    decision = health_boot_decide(HEALTH_CAUSE_CPU_LOCKUP);
    CHECK(decision.cause_class == HEALTH_CLASS_FAULT);
    CHECK(decision.level == HEALTH_LOG_ERROR);
    CHECK(decision.start_watchdog);

    decision = health_boot_decide(0);
    CHECK(decision.cause_class == HEALTH_CLASS_UNKNOWN);
    CHECK(decision.level == HEALTH_LOG_WARN);
    CHECK(decision.start_watchdog);
}

static void class_names_are_stable_words(void)
{
    CHECK(strcmp(health_class_name(HEALTH_CLASS_NORMAL), "normal") == 0);
    CHECK(strcmp(health_class_name(HEALTH_CLASS_WATCHDOG), "watchdog") == 0);
    CHECK(strcmp(health_class_name(HEALTH_CLASS_FAULT), "fault") == 0);
    CHECK(strcmp(health_class_name(HEALTH_CLASS_UNKNOWN), "unknown") == 0);
    CHECK(strcmp(health_class_name((health_cause_class_t)99), "unknown") == 0);
}

static void cause_text_lists_the_flags_in_bit_order(void)
{
    char text[128];

    CHECK(health_cause_text(0, text, sizeof text) == HEALTH_OK);
    CHECK(strcmp(text, "none") == 0);
    CHECK(health_cause_text(HEALTH_CAUSE_POR, text, sizeof text) == HEALTH_OK);
    CHECK(strcmp(text, "POR") == 0);
    CHECK(health_cause_text(HEALTH_CAUSE_WATCHDOG | HEALTH_CAUSE_POR, text, sizeof text) ==
          HEALTH_OK);
    CHECK(strcmp(text, "POR+WATCHDOG") == 0);
    CHECK(health_cause_text(HEALTH_CAUSE_OTHER, text, sizeof text) == HEALTH_OK);
    CHECK(strcmp(text, "OTHER") == 0);
    /* A bit that is not a documented flag has no name of its own: it reads as OTHER. */
    CHECK(health_cause_text(UINT32_C(1) << 20, text, sizeof text) == HEALTH_OK);
    CHECK(strcmp(text, "OTHER") == 0);
    CHECK(health_cause_text(HEALTH_CAUSE_OTHER | (UINT32_C(1) << 20), text, sizeof text) ==
          HEALTH_OK);
    CHECK(strcmp(text, "OTHER") == 0);
}

static void cause_text_names_every_flag(void)
{
    char text[160];

    CHECK(health_cause_text((1u << 11) - 1u, text, sizeof text) == HEALTH_OK);
    CHECK(strcmp(text, "POR+PIN+SOFTWARE+WATCHDOG+DEBUG+CPU_LOCKUP+HARDWARE+SECURITY+USER+"
                       "TEMPERATURE+OTHER") == 0);
}

static void cause_text_that_does_not_fit_is_an_error_and_leaves_an_empty_string(void)
{
    char text[8];

    memset(text, 'x', sizeof text);
    CHECK(health_cause_text(HEALTH_CAUSE_POR | HEALTH_CAUSE_WATCHDOG, text, sizeof text) ==
          HEALTH_ERR_RANGE);
    CHECK(text[0] == '\0');
    /* The text and its end of string must fit exactly: "POR" needs 4 bytes. */
    CHECK(health_cause_text(HEALTH_CAUSE_POR, text, 4) == HEALTH_OK);
    CHECK(strcmp(text, "POR") == 0);
    CHECK(health_cause_text(HEALTH_CAUSE_POR, text, 3) == HEALTH_ERR_RANGE);
    CHECK(text[0] == '\0');
}

static void cause_text_rejects_bad_arguments(void)
{
    char text[8];

    CHECK(health_cause_text(HEALTH_CAUSE_POR, NULL, 8) == HEALTH_ERR_RANGE);
    CHECK(health_cause_text(HEALTH_CAUSE_POR, text, 0) == HEALTH_ERR_RANGE);
}

static void the_default_cycle_gets_a_timeout_twenty_cycles_long(void)
{
    uint32_t timeout = 0;

    CHECK(health_watchdog_timeout(100, &timeout) == HEALTH_OK);
    CHECK(timeout == 2000u);
}

static void the_timeout_is_ten_cycles_rounded_up_to_the_step_inside_the_range(void)
{
    uint32_t timeout = 0;

    CHECK(health_watchdog_timeout(10, &timeout) == HEALTH_OK);
    CHECK(timeout == HEALTH_WATCHDOG_MIN_MS);
    CHECK(health_watchdog_timeout(200, &timeout) == HEALTH_OK);
    CHECK(timeout == 2000u);
    CHECK(health_watchdog_timeout(201, &timeout) == HEALTH_OK);
    CHECK(timeout == 2500u); /* 2010 rounded up */
    CHECK(health_watchdog_timeout(255, &timeout) == HEALTH_OK);
    CHECK(timeout == 3000u); /* 2550 rounded up */
    CHECK(health_watchdog_timeout(1000, &timeout) == HEALTH_OK);
    CHECK(timeout == 10000u);
    CHECK(health_watchdog_timeout(6400, &timeout) == HEALTH_OK);
    CHECK(timeout == HEALTH_WATCHDOG_MAX_MS);
}

static void a_long_cycle_is_clamped_while_three_cycles_still_fit(void)
{
    uint32_t timeout = 0;

    CHECK(health_watchdog_timeout(6401, &timeout) == HEALTH_OK);
    CHECK(timeout == HEALTH_WATCHDOG_MAX_MS);
    CHECK(health_watchdog_timeout(21333, &timeout) == HEALTH_OK);
    CHECK(timeout == HEALTH_WATCHDOG_MAX_MS);
}

static void a_cycle_the_watchdog_range_cannot_hold_three_times_is_refused(void)
{
    uint32_t timeout = 12345;

    CHECK(health_watchdog_timeout(21334, &timeout) == HEALTH_ERR_RANGE);
    CHECK(timeout == 12345u); /* untouched on an error */
    CHECK(health_watchdog_timeout(60000, &timeout) == HEALTH_ERR_RANGE);
    CHECK(timeout == 12345u);
    CHECK(health_watchdog_timeout(0, &timeout) == HEALTH_ERR_RANGE);
    CHECK(timeout == 12345u);
    CHECK(health_watchdog_timeout(100, NULL) == HEALTH_ERR_RANGE);
}

static void every_accepted_timeout_is_a_step_inside_the_range_and_generous(void)
{
    for (uint32_t period = 1; period <= 60000u; period++) {
        uint32_t timeout = 0;
        const health_status_t status = health_watchdog_timeout(period, &timeout);

        if (period > 21333u) {
            CHECK(status == HEALTH_ERR_RANGE);
            continue;
        }
        CHECK(status == HEALTH_OK);
        CHECK(timeout % HEALTH_WATCHDOG_STEP_MS == 0u);
        CHECK(timeout >= HEALTH_WATCHDOG_MIN_MS && timeout <= HEALTH_WATCHDOG_MAX_MS);
        CHECK(timeout >= 3u * period);
        if (period <= 6400u) {
            CHECK(timeout >= 10u * period);
        }
        if (failures != 0) {
            return; /* one broken period would print 60000 lines */
        }
    }
}

static void the_feed_tracker_starts_idle_and_wants_no_feed(void)
{
    health_feed_t feed;

    health_feed_init(&feed);
    CHECK(feed.state == HEALTH_FEED_IDLE);
    CHECK(!health_feed_wanted(&feed));
    CHECK(feed.accepted == 0u);
}

static void an_armed_tracker_wants_a_feed_and_counts_the_accepted_ones(void)
{
    health_feed_t feed;

    health_feed_init(&feed);
    health_feed_armed(&feed);
    CHECK(feed.state == HEALTH_FEED_RUNNING);
    for (uint32_t i = 1; i <= 5; i++) {
        CHECK(health_feed_wanted(&feed));
        CHECK(health_feed_result(&feed, true) == HEALTH_FEED_CONTINUE);
        CHECK(feed.accepted == i);
    }
}

static void a_refused_feed_is_reported_once_and_feeding_stops(void)
{
    health_feed_t feed;

    health_feed_init(&feed);
    health_feed_armed(&feed);
    CHECK(health_feed_result(&feed, true) == HEALTH_FEED_CONTINUE);
    CHECK(health_feed_result(&feed, false) == HEALTH_FEED_REPORT_AND_STOP);
    CHECK(feed.state == HEALTH_FEED_STOPPED);
    CHECK(!health_feed_wanted(&feed));
    CHECK(feed.accepted == 1u);
    /* A result that arrives after the stop is ignored: the report is not repeated. */
    CHECK(health_feed_result(&feed, false) == HEALTH_FEED_IGNORED);
    CHECK(health_feed_result(&feed, true) == HEALTH_FEED_IGNORED);
    CHECK(feed.state == HEALTH_FEED_STOPPED);
    CHECK(feed.accepted == 1u);
}

static void a_stopped_tracker_is_never_armed_again(void)
{
    health_feed_t feed;

    health_feed_init(&feed);
    health_feed_armed(&feed);
    (void)health_feed_result(&feed, false);
    health_feed_armed(&feed);
    CHECK(feed.state == HEALTH_FEED_STOPPED);
    CHECK(!health_feed_wanted(&feed));
}

static void a_tracker_that_was_never_armed_ignores_results(void)
{
    health_feed_t feed;

    health_feed_init(&feed);
    CHECK(health_feed_result(&feed, true) == HEALTH_FEED_IGNORED);
    CHECK(health_feed_result(&feed, false) == HEALTH_FEED_IGNORED);
    CHECK(feed.state == HEALTH_FEED_IDLE);
    CHECK(feed.accepted == 0u);
}

static void the_feed_tracker_survives_null(void)
{
    health_feed_init(NULL);
    health_feed_armed(NULL);
    CHECK(!health_feed_wanted(NULL));
    CHECK(health_feed_result(NULL, true) == HEALTH_FEED_IGNORED);
}

int main(void)
{
    flag_values_are_the_documented_bits();
    causes_that_someone_asked_for_are_normal();
    a_watchdog_reset_is_its_own_class();
    a_lockup_a_security_or_a_temperature_reset_is_a_fault();
    no_flag_or_only_an_unknown_one_is_unknown();
    the_boot_decision_sets_the_log_level_and_never_stops_the_start();
    class_names_are_stable_words();
    cause_text_lists_the_flags_in_bit_order();
    cause_text_names_every_flag();
    cause_text_that_does_not_fit_is_an_error_and_leaves_an_empty_string();
    cause_text_rejects_bad_arguments();
    the_default_cycle_gets_a_timeout_twenty_cycles_long();
    the_timeout_is_ten_cycles_rounded_up_to_the_step_inside_the_range();
    a_long_cycle_is_clamped_while_three_cycles_still_fit();
    a_cycle_the_watchdog_range_cannot_hold_three_times_is_refused();
    every_accepted_timeout_is_a_step_inside_the_range_and_generous();
    the_feed_tracker_starts_idle_and_wants_no_feed();
    an_armed_tracker_wants_a_feed_and_counts_the_accepted_ones();
    a_refused_feed_is_reported_once_and_feeding_stops();
    a_stopped_tracker_is_never_armed_again();
    a_tracker_that_was_never_armed_ignores_results();
    the_feed_tracker_survives_null();

    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
