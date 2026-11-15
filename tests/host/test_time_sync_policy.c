/* SPDX-License-Identifier: Apache-2.0 */

/* The time synchronisation policy of step S5: plain C, no Crux or Zephyr include. */

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "time_sync_policy.h"

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

#define MS INT64_C(1000000) /* nanoseconds in a millisecond */
#define SEC INT64_C(1000000000)

/* A time well inside the supported range: 2030-01-01T00:00:00Z. */
#define T0 INT64_C(1893456000)

static const time_sync_limits_t defaults = {
    .threshold_ms = 100u,
    .max_step_ms = 1000u,
    .stale_age_s = 1800u,
};

static time_sync_instant_t at(int64_t seconds, uint32_t nanoseconds)
{
    const time_sync_instant_t instant = {.seconds = seconds, .nanoseconds = nanoseconds};

    return instant;
}

/* The instant that is delta_ns after base. */
static time_sync_instant_t after(time_sync_instant_t base, int64_t delta_ns)
{
    const int64_t total = base.seconds * SEC + (int64_t)base.nanoseconds + delta_ns;
    int64_t seconds = total / SEC;
    int64_t rest = total % SEC;

    if (rest < 0) {
        rest += SEC;
        seconds -= 1;
    }
    return at(seconds, (uint32_t)rest);
}

/* An answer while Crux time is valid and synchronised at T0, with a fresh last good answer. */
static time_sync_input_t synchronised_with(time_sync_instant_t sample)
{
    time_sync_input_t input = {
        .result = TIME_SYNC_SAMPLE_OK,
        .sample = sample,
        .time_valid = true,
        .time_synchronized = true,
        .now = at(T0, 0),
        .seconds_since_good = 600u,
    };

    return input;
}

static time_sync_decision_t decide(const time_sync_input_t *input)
{
    return time_sync_decide(input, &defaults);
}

static void the_supported_range_is_the_one_of_crux_time(void)
{
    CHECK(TIME_SYNC_MIN_UNIX_SECONDS == INT64_C(946684800));
    CHECK(TIME_SYNC_MAX_UNIX_SECONDS_EXCLUSIVE == INT64_C(4102444800));
}

static void the_range_check_has_exact_boundaries(void)
{
    /* 1999-12-31T23:59:59Z, 2000-01-01T00:00:00Z */
    CHECK(!time_sync_instant_in_range(at(INT64_C(946684799), 999999999u)));
    CHECK(time_sync_instant_in_range(at(INT64_C(946684800), 0u)));
    /* 2099-12-31T23:59:59Z, 2100-01-01T00:00:00Z */
    CHECK(time_sync_instant_in_range(at(INT64_C(4102444799), 999999999u)));
    CHECK(!time_sync_instant_in_range(at(INT64_C(4102444800), 0u)));
    CHECK(time_sync_instant_in_range(at(T0, 0u)));
    CHECK(!time_sync_instant_in_range(at(0, 0u)));
    CHECK(!time_sync_instant_in_range(at(-1, 0u)));
    CHECK(!time_sync_instant_in_range(at(INT64_MIN, 0u)));
    CHECK(!time_sync_instant_in_range(at(INT64_MAX, 0u)));
    /* A fraction of a second must be normalised. */
    CHECK(time_sync_instant_in_range(at(T0, 999999999u)));
    CHECK(!time_sync_instant_in_range(at(T0, 1000000000u)));
    CHECK(!time_sync_instant_in_range(at(T0, UINT32_MAX)));
}

static void an_sntp_fraction_becomes_nanoseconds_below_a_second_rounding_down(void)
{
    /* The Zephyr fraction counts 2^-32 s. */
    CHECK(time_sync_instant_from_sntp(T0, 0u).nanoseconds == 0u);
    CHECK(time_sync_instant_from_sntp(T0, 0x80000000u).nanoseconds == 500000000u);
    CHECK(time_sync_instant_from_sntp(T0, 0x40000000u).nanoseconds == 250000000u);
    CHECK(time_sync_instant_from_sntp(T0, 0xFFFFFFFFu).nanoseconds == 999999999u);
    /* One tick is 0.2328 ns: it rounds down to 0, and 5 ticks to 1 ns. */
    CHECK(time_sync_instant_from_sntp(T0, 1u).nanoseconds == 0u);
    CHECK(time_sync_instant_from_sntp(T0, 4u).nanoseconds == 0u);
    CHECK(time_sync_instant_from_sntp(T0, 5u).nanoseconds == 1u);
    CHECK(time_sync_instant_from_sntp(T0, 0x00000001u).seconds == T0);
}

static void every_sntp_fraction_in_a_sweep_stays_below_a_second_and_never_decreases(void)
{
    uint32_t previous = 0u;

    for (uint64_t fraction = 0; fraction <= UINT32_MAX; fraction += 65537u) {
        const uint32_t nanoseconds = time_sync_instant_from_sntp(T0, (uint32_t)fraction).nanoseconds;

        CHECK(nanoseconds < 1000000000u);
        CHECK(nanoseconds >= previous);
        previous = nanoseconds;
    }
}

static void sntp_seconds_beyond_the_signed_range_are_clamped_and_then_refused(void)
{
    const time_sync_instant_t huge = time_sync_instant_from_sntp(UINT64_MAX, 0u);

    CHECK(huge.seconds == INT64_MAX);
    CHECK(!time_sync_instant_in_range(huge));
    CHECK(time_sync_instant_from_sntp((uint64_t)INT64_MAX, 0u).seconds == INT64_MAX);
    CHECK(time_sync_instant_from_sntp(UINT64_C(946684800), 0u).seconds == INT64_C(946684800));
    CHECK(time_sync_instant_in_range(time_sync_instant_from_sntp(UINT64_C(946684800), 0u)));
    CHECK(!time_sync_instant_in_range(time_sync_instant_from_sntp(UINT64_C(946684799), 0u)));
}

/* Rule 1: a failed, kiss-o'-death or timed-out answer never sets. */
static void a_failed_answer_never_sets_and_is_named_by_its_reason(void)
{
    const struct {
        time_sync_sample_result_t result;
        time_sync_reason_t reason;
    } cases[] = {
        {TIME_SYNC_SAMPLE_TIMEOUT, TIME_SYNC_REASON_TIMEOUT},
        {TIME_SYNC_SAMPLE_KISS_OF_DEATH, TIME_SYNC_REASON_KISS_OF_DEATH},
        {TIME_SYNC_SAMPLE_ERROR, TIME_SYNC_REASON_ERROR},
    };

    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        /* Not valid at boot, valid but not synchronised, and synchronised and fresh. */
        time_sync_input_t boot = {.result = cases[i].result, .seconds_since_good = 0u};
        time_sync_input_t unsynchronised = synchronised_with(at(T0, 0));
        time_sync_input_t fresh = synchronised_with(at(T0, 0));
        const time_sync_input_t *all[] = {&boot, &unsynchronised, &fresh};

        unsynchronised.result = cases[i].result;
        unsynchronised.time_synchronized = false;
        fresh.result = cases[i].result;
        for (size_t k = 0; k < 3; k++) {
            const time_sync_decision_t decision = decide(all[k]);

            CHECK(decision.action == TIME_SYNC_NO_ACTION);
            CHECK(decision.reason == cases[i].reason);
            CHECK(!decision.clear_synchronized);
            CHECK(!decision.refresh_good);
        }
    }
}

static void a_failed_answer_ignores_whatever_sample_it_carries(void)
{
    time_sync_input_t input = synchronised_with(at(T0 + 5, 0));

    input.result = TIME_SYNC_SAMPLE_TIMEOUT;
    CHECK(decide(&input).action == TIME_SYNC_NO_ACTION);
    input.result = TIME_SYNC_SAMPLE_ERROR;
    input.sample = at(0, 0);
    CHECK(decide(&input).reason == TIME_SYNC_REASON_ERROR);
}

static void synchronisation_goes_stale_only_after_more_than_the_limit(void)
{
    time_sync_input_t input = synchronised_with(at(T0, 0));
    time_sync_decision_t decision;

    input.result = TIME_SYNC_SAMPLE_TIMEOUT;
    input.seconds_since_good = 1799u;
    CHECK(decide(&input).action == TIME_SYNC_NO_ACTION);
    input.seconds_since_good = 1800u; /* exactly at the limit */
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_NO_ACTION);
    CHECK(!decision.clear_synchronized);
    input.seconds_since_good = 1801u;
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_MARK_STALE);
    CHECK(decision.reason == TIME_SYNC_REASON_TIMEOUT);
    CHECK(decision.clear_synchronized);
    CHECK(!decision.refresh_good);
    input.seconds_since_good = UINT32_MAX;
    CHECK(decide(&input).action == TIME_SYNC_MARK_STALE);
}

static void every_kind_of_failure_can_make_the_time_stale(void)
{
    time_sync_input_t input = synchronised_with(at(T0, 0));

    input.seconds_since_good = 1801u;
    input.result = TIME_SYNC_SAMPLE_KISS_OF_DEATH;
    CHECK(decide(&input).action == TIME_SYNC_MARK_STALE);
    CHECK(decide(&input).reason == TIME_SYNC_REASON_KISS_OF_DEATH);
    input.result = TIME_SYNC_SAMPLE_ERROR;
    CHECK(decide(&input).action == TIME_SYNC_MARK_STALE);
    CHECK(decide(&input).reason == TIME_SYNC_REASON_ERROR);
}

static void the_stale_limit_is_the_one_that_was_passed_in(void)
{
    time_sync_input_t input = synchronised_with(at(T0, 0));
    time_sync_limits_t limits = defaults;

    input.result = TIME_SYNC_SAMPLE_TIMEOUT;
    input.seconds_since_good = 61u;
    limits.stale_age_s = 60u;
    CHECK(time_sync_decide(&input, &limits).action == TIME_SYNC_MARK_STALE);
    limits.stale_age_s = 61u;
    CHECK(time_sync_decide(&input, &limits).action == TIME_SYNC_NO_ACTION);
}

static void stale_is_marked_only_while_the_time_is_valid_and_synchronised(void)
{
    time_sync_input_t input = synchronised_with(at(T0, 0));

    input.result = TIME_SYNC_SAMPLE_TIMEOUT;
    input.seconds_since_good = 100000u;
    input.time_synchronized = false; /* already stale or lost: nothing more to clear */
    CHECK(decide(&input).action == TIME_SYNC_NO_ACTION);
    input.time_valid = false; /* never set: the call would answer no data */
    CHECK(decide(&input).action == TIME_SYNC_NO_ACTION);
    input.time_synchronized = true; /* an inconsistent report is not trusted either */
    CHECK(decide(&input).action == TIME_SYNC_NO_ACTION);
}

static void an_unreadable_clock_is_a_failed_round_and_never_sets(void)
{
    /* The glue gives time_valid = false when the snapshot read failed, as it did before. The
     * answer must not be taken for a first sync then: the clock could not be compared. */
    time_sync_input_t input = {
        .result = TIME_SYNC_SAMPLE_OK,
        .sample = at(T0 + 5, 0),
        .clock_unreadable = true,
        .seconds_since_good = 0u,
    };
    time_sync_decision_t decision = decide(&input);

    CHECK(decision.action == TIME_SYNC_NO_ACTION);
    CHECK(decision.reason == TIME_SYNC_REASON_CLOCK_UNREADABLE);
    CHECK(!decision.clear_synchronized);
    CHECK(!decision.refresh_good);
    CHECK(decision.delta_ns == 0);
    CHECK(time_sync_decision_level(decision) == TIME_SYNC_LOG_WARN);

    /* The same answer with a snapshot that was read and reports no time is still a first sync. */
    input.clock_unreadable = false;
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_APPLY_SET);
    CHECK(decision.reason == TIME_SYNC_REASON_FIRST_SYNC);

    /* A far answer is not applied either, whatever the report says about the flags. */
    input = synchronised_with(after(at(T0, 0), 5 * SEC));
    input.clock_unreadable = true;
    input.time_valid = false;
    input.time_synchronized = false;
    CHECK(decide(&input).action == TIME_SYNC_NO_ACTION);
    CHECK(decide(&input).reason == TIME_SYNC_REASON_CLOCK_UNREADABLE);
}

static void an_unreadable_clock_counts_towards_staleness_like_any_failure(void)
{
    time_sync_input_t input = {
        .result = TIME_SYNC_SAMPLE_OK,
        .sample = at(T0, 0),
        .clock_unreadable = true,
        .seconds_since_good = 1800u, /* exactly at the limit */
    };
    time_sync_decision_t decision = decide(&input);

    CHECK(decision.action == TIME_SYNC_NO_ACTION);
    CHECK(!decision.clear_synchronized);
    input.seconds_since_good = 1801u;
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_MARK_STALE);
    CHECK(decision.reason == TIME_SYNC_REASON_CLOCK_UNREADABLE);
    CHECK(decision.clear_synchronized);
    CHECK(!decision.refresh_good);
    CHECK(time_sync_decision_level(decision) == TIME_SYNC_LOG_WARN);
}

static void an_unreadable_clock_does_not_change_the_reason_of_a_failed_query_or_a_bad_answer(void)
{
    time_sync_input_t input = {.result = TIME_SYNC_SAMPLE_TIMEOUT, .clock_unreadable = true};

    CHECK(decide(&input).reason == TIME_SYNC_REASON_TIMEOUT);
    input.result = TIME_SYNC_SAMPLE_OK;
    input.sample = at(0, 0);
    CHECK(decide(&input).action == TIME_SYNC_REFUSE_RANGE);
    CHECK(decide(&input).reason == TIME_SYNC_REASON_OUT_OF_RANGE);
}

/* Rule 1: an answer outside [2000-01-01, 2100-01-01) never sets, and counts as a failure. */
static void an_answer_out_of_range_never_sets_in_any_state(void)
{
    const time_sync_instant_t bad[] = {
        at(INT64_C(946684799), 999999999u), /* 1999-12-31T23:59:59.999999999Z */
        at(INT64_C(4102444800), 0u),        /* 2100-01-01T00:00:00Z */
        at(0, 0u),
        at(-5, 0u),
        at(T0, 1000000000u),
    };

    for (size_t i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        time_sync_input_t boot = {.result = TIME_SYNC_SAMPLE_OK, .sample = bad[i]};
        time_sync_input_t unsynchronised = synchronised_with(bad[i]);
        time_sync_input_t fresh = synchronised_with(bad[i]);
        const time_sync_input_t *all[] = {&boot, &unsynchronised, &fresh};

        unsynchronised.time_synchronized = false;
        for (size_t k = 0; k < 3; k++) {
            const time_sync_decision_t decision = decide(all[k]);

            CHECK(decision.action == TIME_SYNC_REFUSE_RANGE);
            CHECK(decision.reason == TIME_SYNC_REASON_OUT_OF_RANGE);
            CHECK(!decision.clear_synchronized);
            CHECK(!decision.refresh_good);
        }
    }
}

static void an_answer_out_of_range_counts_as_a_failure_for_staleness(void)
{
    time_sync_input_t input = synchronised_with(at(INT64_C(946684799), 0u));
    time_sync_decision_t decision;

    input.seconds_since_good = 1800u;
    CHECK(decide(&input).action == TIME_SYNC_REFUSE_RANGE);
    input.seconds_since_good = 1801u;
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_MARK_STALE);
    CHECK(decision.reason == TIME_SYNC_REASON_OUT_OF_RANGE);
    CHECK(decision.clear_synchronized);
    /* While not synchronised the same answer is only refused. */
    input.time_synchronized = false;
    CHECK(decide(&input).action == TIME_SYNC_REFUSE_RANGE);
}

/* Rule 2: while not synchronised, any in-range answer is applied. */
static void the_first_answer_after_boot_is_applied_whatever_the_clock_says(void)
{
    /* Crux time is not valid: the native clock reads boot-relative time, which must be ignored. */
    time_sync_input_t input = {
        .result = TIME_SYNC_SAMPLE_OK,
        .sample = at(T0, 250000000u),
        .time_valid = false,
        .time_synchronized = false,
        .now = at(42, 1000000000u), /* garbage on purpose */
        .seconds_since_good = 0u,
    };
    time_sync_decision_t decision = decide(&input);

    CHECK(decision.action == TIME_SYNC_APPLY_SET);
    CHECK(decision.reason == TIME_SYNC_REASON_FIRST_SYNC);
    CHECK(!decision.clear_synchronized);
    CHECK(decision.refresh_good);
    /* The very first and the very last instants of the range are fine. */
    input.sample = at(INT64_C(946684800), 0u);
    CHECK(decide(&input).action == TIME_SYNC_APPLY_SET);
    input.sample = at(INT64_C(4102444799), 999999999u);
    CHECK(decide(&input).action == TIME_SYNC_APPLY_SET);
}

static void an_unsynchronised_clock_is_set_by_any_in_range_answer_even_a_far_one(void)
{
    time_sync_input_t input = synchronised_with(after(at(T0, 0), 3600 * SEC));
    time_sync_decision_t decision;

    input.time_synchronized = false; /* stale, lost or never synchronised */
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_APPLY_SET);
    CHECK(decision.reason == TIME_SYNC_REASON_RESYNC);
    CHECK(!decision.clear_synchronized);
    CHECK(decision.refresh_good);
    input.sample = after(at(T0, 0), -3600 * SEC); /* an hour back */
    CHECK(decide(&input).action == TIME_SYNC_APPLY_SET);
    input.sample = at(INT64_C(946684800), 0u);
    CHECK(decide(&input).action == TIME_SYNC_APPLY_SET);
    input.sample = at(INT64_C(4102444799), 0u);
    CHECK(decide(&input).action == TIME_SYNC_APPLY_SET);
}

static void a_clock_that_is_out_of_range_cannot_be_compared_and_counts_as_unsynchronised(void)
{
    time_sync_input_t input = synchronised_with(at(T0, 0));

    input.now = at(0, 0);
    CHECK(decide(&input).action == TIME_SYNC_APPLY_SET);
    CHECK(decide(&input).reason == TIME_SYNC_REASON_RESYNC);
    input.now = at(INT64_MIN, 0u);
    CHECK(decide(&input).action == TIME_SYNC_APPLY_SET);
    input.now = at(T0, 1000000000u);
    CHECK(decide(&input).action == TIME_SYNC_APPLY_SET);
}

/* Rule 3: while synchronised, the size of the difference decides. */
static void a_difference_below_the_threshold_changes_nothing_but_confirms_the_clock(void)
{
    time_sync_input_t input = synchronised_with(at(T0, 0));
    time_sync_decision_t decision = decide(&input);

    CHECK(decision.action == TIME_SYNC_NO_ACTION);
    CHECK(decision.reason == TIME_SYNC_REASON_WITHIN_THRESHOLD);
    CHECK(decision.delta_ns == 0);
    CHECK(decision.refresh_good);
    CHECK(!decision.clear_synchronized);

    input.sample = after(at(T0, 0), 99 * MS + 999999); /* 99.999999 ms ahead */
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_NO_ACTION);
    CHECK(decision.delta_ns == 99999999);
    input.sample = after(at(T0, 0), -(100 * MS - 1)); /* behind */
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_NO_ACTION);
    CHECK(decision.delta_ns == -99999999);
}

static void a_difference_at_the_threshold_is_corrected_in_both_directions(void)
{
    time_sync_input_t input = synchronised_with(after(at(T0, 0), 100 * MS));
    time_sync_decision_t decision = decide(&input);

    CHECK(decision.action == TIME_SYNC_APPLY_SET);
    CHECK(decision.reason == TIME_SYNC_REASON_CORRECTION);
    CHECK(decision.delta_ns == 100000000);
    CHECK(decision.refresh_good);
    CHECK(!decision.clear_synchronized);

    input.sample = after(at(T0, 0), -100 * MS);
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_APPLY_SET);
    CHECK(decision.delta_ns == -100000000);
}

static void a_difference_up_to_and_including_the_maximum_step_is_corrected(void)
{
    time_sync_input_t input = synchronised_with(after(at(T0, 0), 1000 * MS - 1));
    time_sync_decision_t decision = decide(&input);

    CHECK(decision.action == TIME_SYNC_APPLY_SET);
    CHECK(decision.reason == TIME_SYNC_REASON_CORRECTION);
    input.sample = after(at(T0, 0), 1000 * MS); /* exactly the maximum step */
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_APPLY_SET);
    CHECK(decision.reason == TIME_SYNC_REASON_CORRECTION);
    CHECK(decision.delta_ns == 1000000000);
    input.sample = after(at(T0, 0), -1000 * MS);
    CHECK(decide(&input).action == TIME_SYNC_APPLY_SET);
}

static void a_difference_above_the_maximum_step_is_refused_and_synchronisation_is_lost(void)
{
    time_sync_input_t input = synchronised_with(after(at(T0, 0), 1000 * MS + 1));
    time_sync_decision_t decision = decide(&input);

    CHECK(decision.action == TIME_SYNC_REFUSE_STEP);
    CHECK(decision.reason == TIME_SYNC_REASON_STEP_TOO_LARGE);
    CHECK(decision.clear_synchronized);
    CHECK(!decision.refresh_good);
    CHECK(decision.delta_ns == 1000000001);

    input.sample = after(at(T0, 0), -(1000 * MS + 1));
    decision = decide(&input);
    CHECK(decision.action == TIME_SYNC_REFUSE_STEP);
    CHECK(decision.delta_ns == -1000000001);
    input.sample = after(at(T0, 0), 3600 * SEC);
    CHECK(decide(&input).action == TIME_SYNC_REFUSE_STEP);
    /* The widest possible difference inside the supported range does not overflow. */
    input.now = at(INT64_C(946684800), 0u);
    input.sample = at(INT64_C(4102444799), 999999999u);
    CHECK(decide(&input).action == TIME_SYNC_REFUSE_STEP);
    CHECK(decide(&input).delta_ns > 0);
    input.now = at(INT64_C(4102444799), 999999999u);
    input.sample = at(INT64_C(946684800), 0u);
    CHECK(decide(&input).action == TIME_SYNC_REFUSE_STEP);
    CHECK(decide(&input).delta_ns < 0);
}

static void the_difference_counts_the_fraction_across_a_second_boundary(void)
{
    time_sync_input_t input = synchronised_with(at(T0, 0));
    time_sync_decision_t decision;

    input.now = at(T0 - 1, 950000000u); /* 50 ms behind the sample */
    decision = decide(&input);
    CHECK(decision.delta_ns == 50000000);
    CHECK(decision.action == TIME_SYNC_NO_ACTION);
    input.now = at(T0, 500000000u);
    input.sample = at(T0 + 1, 100000000u); /* 600 ms ahead */
    decision = decide(&input);
    CHECK(decision.delta_ns == 600000000);
    CHECK(decision.action == TIME_SYNC_APPLY_SET);
}

static void the_limits_are_the_ones_that_were_passed_in(void)
{
    time_sync_input_t input = synchronised_with(after(at(T0, 0), 50 * MS));
    time_sync_limits_t limits = {.threshold_ms = 50u, .max_step_ms = 50u, .stale_age_s = 10u};

    CHECK(time_sync_decide(&input, &limits).action == TIME_SYNC_APPLY_SET); /* at both */
    limits.threshold_ms = 51u;
    limits.max_step_ms = 51u;
    CHECK(time_sync_decide(&input, &limits).action == TIME_SYNC_NO_ACTION);
    limits.threshold_ms = 10u;
    limits.max_step_ms = 49u;
    CHECK(time_sync_decide(&input, &limits).action == TIME_SYNC_REFUSE_STEP);
    limits.threshold_ms = 0u; /* every answer is applied, even an equal one */
    limits.max_step_ms = 49u;
    input.sample = at(T0, 0);
    CHECK(time_sync_decide(&input, &limits).action == TIME_SYNC_APPLY_SET);
}

static void a_limit_pair_that_makes_no_sense_changes_nothing(void)
{
    time_sync_input_t input = synchronised_with(after(at(T0, 0), 500 * MS));
    time_sync_limits_t limits = {.threshold_ms = 2000u, .max_step_ms = 1000u, .stale_age_s = 1800u};
    time_sync_decision_t decision = time_sync_decide(&input, &limits);

    CHECK(decision.action == TIME_SYNC_NO_ACTION);
    CHECK(decision.reason == TIME_SYNC_REASON_BAD_INPUT);
    CHECK(!decision.clear_synchronized);
    CHECK(!decision.refresh_good);
    decision = time_sync_decide(NULL, &defaults);
    CHECK(decision.action == TIME_SYNC_NO_ACTION);
    CHECK(decision.reason == TIME_SYNC_REASON_BAD_INPUT);
    decision = time_sync_decide(&input, NULL);
    CHECK(decision.action == TIME_SYNC_NO_ACTION);
    CHECK(decision.reason == TIME_SYNC_REASON_BAD_INPUT);
    /* An unknown result code never sets either. */
    input.result = (time_sync_sample_result_t)99;
    CHECK(decide(&input).action == TIME_SYNC_NO_ACTION);
    CHECK(decide(&input).reason == TIME_SYNC_REASON_BAD_INPUT);
}

static void names_and_levels_are_stable_words(void)
{
    CHECK(strcmp(time_sync_action_name(TIME_SYNC_NO_ACTION), "no-action") == 0);
    CHECK(strcmp(time_sync_action_name(TIME_SYNC_APPLY_SET), "apply-set") == 0);
    CHECK(strcmp(time_sync_action_name(TIME_SYNC_REFUSE_RANGE), "refuse-range") == 0);
    CHECK(strcmp(time_sync_action_name(TIME_SYNC_REFUSE_STEP), "refuse-step") == 0);
    CHECK(strcmp(time_sync_action_name(TIME_SYNC_MARK_STALE), "mark-stale") == 0);
    CHECK(strcmp(time_sync_action_name((time_sync_action_t)99), "unknown") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_FIRST_SYNC), "first-sync") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_RESYNC), "resync") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_WITHIN_THRESHOLD), "within-threshold") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_CORRECTION), "correction") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_STEP_TOO_LARGE), "step-too-large") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_OUT_OF_RANGE), "out-of-range") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_TIMEOUT), "timeout") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_KISS_OF_DEATH), "kiss-of-death") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_ERROR), "error") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_CLOCK_UNREADABLE), "clock-unreadable") == 0);
    CHECK(strcmp(time_sync_reason_name(TIME_SYNC_REASON_BAD_INPUT), "bad-input") == 0);
    CHECK(strcmp(time_sync_reason_name((time_sync_reason_t)99), "unknown") == 0);
}

static void a_clock_that_moved_or_a_failure_is_a_warning_and_a_good_answer_is_information(void)
{
    time_sync_input_t input = synchronised_with(at(T0, 0));

    CHECK(time_sync_decision_level(decide(&input)) == TIME_SYNC_LOG_INFO); /* within threshold */
    input.sample = after(at(T0, 0), 500 * MS);
    CHECK(time_sync_decision_level(decide(&input)) == TIME_SYNC_LOG_INFO); /* corrected */
    input.time_synchronized = false;
    CHECK(time_sync_decision_level(decide(&input)) == TIME_SYNC_LOG_INFO); /* resync */
    input.time_synchronized = true;
    input.sample = after(at(T0, 0), 5 * SEC);
    CHECK(time_sync_decision_level(decide(&input)) == TIME_SYNC_LOG_WARN); /* step refused */
    input.sample = at(0, 0);
    CHECK(time_sync_decision_level(decide(&input)) == TIME_SYNC_LOG_WARN); /* range */
    input.result = TIME_SYNC_SAMPLE_TIMEOUT;
    CHECK(time_sync_decision_level(decide(&input)) == TIME_SYNC_LOG_WARN); /* failure */
    input.seconds_since_good = 99999u;
    CHECK(time_sync_decision_level(decide(&input)) == TIME_SYNC_LOG_WARN); /* stale */
}

/* A small model of what the glue does with each decision, to run whole sequences. */
typedef struct {
    bool valid;
    bool synchronized;
    time_sync_instant_t now;
    uint32_t seconds_since_good;
    unsigned sets;
    unsigned stale_marks;
} model_t;

static time_sync_decision_t model_step(model_t *model, time_sync_sample_result_t result,
                                       time_sync_instant_t sample, uint32_t elapsed_s)
{
    /* Time passes first, then the query is answered. */
    model->now = after(model->now, (int64_t)elapsed_s * SEC);
    model->seconds_since_good += elapsed_s;

    const time_sync_input_t input = {
        .result = result,
        .sample = sample,
        .time_valid = model->valid,
        .time_synchronized = model->synchronized,
        .now = model->valid ? model->now : at(0, 0), /* an invalid clock reads boot-relative time */
        .seconds_since_good = model->seconds_since_good,
    };
    const time_sync_decision_t decision = decide(&input);

    if (decision.action == TIME_SYNC_APPLY_SET) {
        model->now = sample;
        model->valid = true;
        model->synchronized = true;
        model->sets++;
    }
    if (decision.clear_synchronized) {
        model->synchronized = false;
        if (decision.action == TIME_SYNC_MARK_STALE) {
            model->stale_marks++;
        }
    }
    if (decision.refresh_good) {
        model->seconds_since_good = 0u;
    }
    return decision;
}

static void a_failed_query_at_boot_never_sets_and_the_first_good_one_does(void)
{
    model_t model = {0};

    for (int i = 0; i < 5; i++) {
        CHECK(model_step(&model, TIME_SYNC_SAMPLE_TIMEOUT, at(0, 0), 600u).action ==
              TIME_SYNC_NO_ACTION);
    }
    CHECK(model.sets == 0u);
    CHECK(!model.valid);
    CHECK(model_step(&model, TIME_SYNC_SAMPLE_OK, at(T0, 0), 600u).action == TIME_SYNC_APPLY_SET);
    CHECK(model.sets == 1u);
    CHECK(model.valid && model.synchronized);
}

static void a_lost_synchronisation_comes_back_with_the_next_good_answer(void)
{
    model_t model = {0};
    time_sync_decision_t decision;

    (void)model_step(&model, TIME_SYNC_SAMPLE_OK, at(T0, 0), 0u);
    /* A step of an hour is refused once, and the clock is left alone. */
    decision = model_step(&model, TIME_SYNC_SAMPLE_OK, at(T0 + 600 + 3600, 0u), 600u);
    CHECK(decision.action == TIME_SYNC_REFUSE_STEP);
    CHECK(!model.synchronized);
    CHECK(model.sets == 1u);
    CHECK(model.now.seconds == T0 + 600);
    /* The next in-range answer re-synchronises, whatever it says. */
    decision = model_step(&model, TIME_SYNC_SAMPLE_OK, at(T0 + 1200 + 3600, 0u), 600u);
    CHECK(decision.action == TIME_SYNC_APPLY_SET);
    CHECK(decision.reason == TIME_SYNC_REASON_RESYNC);
    CHECK(model.synchronized);
    CHECK(model.sets == 2u);
}

static void silence_marks_the_time_stale_once_and_a_good_answer_brings_it_back(void)
{
    model_t model = {0};
    time_sync_decision_t decision;

    (void)model_step(&model, TIME_SYNC_SAMPLE_OK, at(T0, 0), 0u);
    /* Intervals of 600 s: 600, 1200, 1800 are not above the limit of 1800 s. */
    for (int i = 0; i < 3; i++) {
        decision = model_step(&model, TIME_SYNC_SAMPLE_TIMEOUT, at(0, 0), 600u);
        CHECK(decision.action == TIME_SYNC_NO_ACTION);
        CHECK(model.synchronized);
    }
    decision = model_step(&model, TIME_SYNC_SAMPLE_TIMEOUT, at(0, 0), 600u);
    CHECK(decision.action == TIME_SYNC_MARK_STALE);
    CHECK(!model.synchronized);
    CHECK(model.valid);
    for (int i = 0; i < 10; i++) {
        CHECK(model_step(&model, TIME_SYNC_SAMPLE_TIMEOUT, at(0, 0), 600u).action ==
              TIME_SYNC_NO_ACTION);
    }
    CHECK(model.stale_marks == 1u);
    /* A good answer, even a far one, re-synchronises. */
    decision = model_step(&model, TIME_SYNC_SAMPLE_OK, at(T0 + 100000, 0u), 600u);
    CHECK(decision.action == TIME_SYNC_APPLY_SET);
    CHECK(model.synchronized);
}

static void answers_within_the_threshold_keep_the_time_fresh_without_a_write(void)
{
    model_t model = {0};

    (void)model_step(&model, TIME_SYNC_SAMPLE_OK, at(T0, 0), 0u);
    for (int i = 0; i < 20; i++) {
        /* Each answer agrees with the clock to within 10 ms. */
        const time_sync_instant_t sample = after(model.now, 600 * SEC + 10 * MS);

        CHECK(model_step(&model, TIME_SYNC_SAMPLE_OK, sample, 600u).action == TIME_SYNC_NO_ACTION);
        CHECK(model.synchronized);
    }
    CHECK(model.sets == 1u);
    CHECK(model.stale_marks == 0u);
}

int main(void)
{
    the_supported_range_is_the_one_of_crux_time();
    the_range_check_has_exact_boundaries();
    an_sntp_fraction_becomes_nanoseconds_below_a_second_rounding_down();
    every_sntp_fraction_in_a_sweep_stays_below_a_second_and_never_decreases();
    sntp_seconds_beyond_the_signed_range_are_clamped_and_then_refused();
    a_failed_answer_never_sets_and_is_named_by_its_reason();
    a_failed_answer_ignores_whatever_sample_it_carries();
    synchronisation_goes_stale_only_after_more_than_the_limit();
    every_kind_of_failure_can_make_the_time_stale();
    the_stale_limit_is_the_one_that_was_passed_in();
    stale_is_marked_only_while_the_time_is_valid_and_synchronised();
    an_unreadable_clock_is_a_failed_round_and_never_sets();
    an_unreadable_clock_counts_towards_staleness_like_any_failure();
    an_unreadable_clock_does_not_change_the_reason_of_a_failed_query_or_a_bad_answer();
    an_answer_out_of_range_never_sets_in_any_state();
    an_answer_out_of_range_counts_as_a_failure_for_staleness();
    the_first_answer_after_boot_is_applied_whatever_the_clock_says();
    an_unsynchronised_clock_is_set_by_any_in_range_answer_even_a_far_one();
    a_clock_that_is_out_of_range_cannot_be_compared_and_counts_as_unsynchronised();
    a_difference_below_the_threshold_changes_nothing_but_confirms_the_clock();
    a_difference_at_the_threshold_is_corrected_in_both_directions();
    a_difference_up_to_and_including_the_maximum_step_is_corrected();
    a_difference_above_the_maximum_step_is_refused_and_synchronisation_is_lost();
    the_difference_counts_the_fraction_across_a_second_boundary();
    the_limits_are_the_ones_that_were_passed_in();
    a_limit_pair_that_makes_no_sense_changes_nothing();
    names_and_levels_are_stable_words();
    a_clock_that_moved_or_a_failure_is_a_warning_and_a_good_answer_is_information();
    a_failed_query_at_boot_never_sets_and_the_first_good_one_does();
    a_lost_synchronisation_comes_back_with_the_next_good_answer();
    silence_marks_the_time_stale_once_and_a_good_answer_brings_it_back();
    answers_within_the_threshold_keep_the_time_fresh_without_a_write();

    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
