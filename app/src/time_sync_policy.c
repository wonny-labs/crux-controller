/* SPDX-License-Identifier: Apache-2.0 */

#include "time_sync_policy.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define NS_PER_SECOND INT64_C(1000000000)
#define NS_PER_MS INT64_C(1000000)

bool time_sync_instant_in_range(time_sync_instant_t instant)
{
    return instant.seconds >= TIME_SYNC_MIN_UNIX_SECONDS &&
           instant.seconds < TIME_SYNC_MAX_UNIX_SECONDS_EXCLUSIVE &&
           instant.nanoseconds < (uint32_t)NS_PER_SECOND;
}

time_sync_instant_t time_sync_instant_from_sntp(uint64_t seconds, uint32_t fraction)
{
    time_sync_instant_t instant;

    instant.seconds = seconds > (uint64_t)INT64_MAX ? INT64_MAX : (int64_t)seconds;
    /* fraction / 2^32 s in nanoseconds: at most (2^32 - 1) * 10^9 / 2^32, below 10^9. */
    instant.nanoseconds = (uint32_t)(((uint64_t)fraction * (uint64_t)NS_PER_SECOND) >> 32);
    return instant;
}

static time_sync_decision_t decision_of(time_sync_action_t action, time_sync_reason_t reason)
{
    time_sync_decision_t decision = {.action = action, .reason = reason};

    return decision;
}

/*
 * A failure, or an answer that was refused for its range. It never sets. A synchronised clock whose
 * last good answer is older than the limit is marked stale instead of being left to claim a
 * synchronisation that nothing confirms; Crux refuses that call for a time that is not valid.
 * When the snapshot could not be read the flags are not known, so only the age counts; if the time
 * turns out not to be valid, Crux refuses the call and the glue logs it.
 */
static time_sync_decision_t failure(const time_sync_input_t *input, const time_sync_limits_t *limits,
                                    time_sync_action_t action, time_sync_reason_t reason)
{
    time_sync_decision_t decision = decision_of(action, reason);

    const bool may_be_synchronised =
        input->clock_unreadable || (input->time_valid && input->time_synchronized);

    if (may_be_synchronised && input->seconds_since_good > limits->stale_age_s) {
        decision.action = TIME_SYNC_MARK_STALE;
        decision.clear_synchronized = true;
    }
    return decision;
}

time_sync_decision_t time_sync_decide(const time_sync_input_t *input, const time_sync_limits_t *limits)
{
    if (input == NULL || limits == NULL || limits->threshold_ms > limits->max_step_ms) {
        return decision_of(TIME_SYNC_NO_ACTION, TIME_SYNC_REASON_BAD_INPUT);
    }
    switch (input->result) {
    case TIME_SYNC_SAMPLE_TIMEOUT:
        return failure(input, limits, TIME_SYNC_NO_ACTION, TIME_SYNC_REASON_TIMEOUT);
    case TIME_SYNC_SAMPLE_KISS_OF_DEATH:
        return failure(input, limits, TIME_SYNC_NO_ACTION, TIME_SYNC_REASON_KISS_OF_DEATH);
    case TIME_SYNC_SAMPLE_ERROR:
        return failure(input, limits, TIME_SYNC_NO_ACTION, TIME_SYNC_REASON_ERROR);
    case TIME_SYNC_SAMPLE_OK:
        break;
    default:
        return decision_of(TIME_SYNC_NO_ACTION, TIME_SYNC_REASON_BAD_INPUT);
    }
    if (!time_sync_instant_in_range(input->sample)) {
        return failure(input, limits, TIME_SYNC_REFUSE_RANGE, TIME_SYNC_REASON_OUT_OF_RANGE);
    }
    /* A snapshot that could not be read gives nothing to compare with, and no ground to treat the
     * clock as not valid: the round fails and sets nothing. */
    if (input->clock_unreadable) {
        return failure(input, limits, TIME_SYNC_NO_ACTION, TIME_SYNC_REASON_CLOCK_UNREADABLE);
    }
    /* A clock that is not valid, not synchronised, or reads outside the range (it cannot be
     * compared) takes any in-range answer. */
    if (!input->time_valid || !input->time_synchronized || !time_sync_instant_in_range(input->now)) {
        time_sync_decision_t decision =
            decision_of(TIME_SYNC_APPLY_SET,
                        input->time_valid ? TIME_SYNC_REASON_RESYNC : TIME_SYNC_REASON_FIRST_SYNC);

        decision.refresh_good = true;
        return decision;
    }
    /* Both instants are in [2000, 2100): the difference is below 3.2e18 ns and fits an int64_t. */
    const int64_t delta_ns = (input->sample.seconds - input->now.seconds) * NS_PER_SECOND +
                             ((int64_t)input->sample.nanoseconds - (int64_t)input->now.nanoseconds);
    const int64_t magnitude = delta_ns < 0 ? -delta_ns : delta_ns;
    time_sync_decision_t decision;

    if (magnitude < (int64_t)limits->threshold_ms * NS_PER_MS) {
        decision = decision_of(TIME_SYNC_NO_ACTION, TIME_SYNC_REASON_WITHIN_THRESHOLD);
        decision.refresh_good = true;
    } else if (magnitude <= (int64_t)limits->max_step_ms * NS_PER_MS) {
        decision = decision_of(TIME_SYNC_APPLY_SET, TIME_SYNC_REASON_CORRECTION);
        decision.refresh_good = true;
    } else {
        decision = decision_of(TIME_SYNC_REFUSE_STEP, TIME_SYNC_REASON_STEP_TOO_LARGE);
        decision.clear_synchronized = true;
    }
    decision.delta_ns = delta_ns;
    return decision;
}

time_sync_log_level_t time_sync_decision_level(time_sync_decision_t decision)
{
    switch (decision.reason) {
    case TIME_SYNC_REASON_FIRST_SYNC:
    case TIME_SYNC_REASON_RESYNC:
    case TIME_SYNC_REASON_WITHIN_THRESHOLD:
    case TIME_SYNC_REASON_CORRECTION:
        return TIME_SYNC_LOG_INFO;
    default:
        return TIME_SYNC_LOG_WARN;
    }
}

const char *time_sync_action_name(time_sync_action_t action)
{
    switch (action) {
    case TIME_SYNC_NO_ACTION:
        return "no-action";
    case TIME_SYNC_APPLY_SET:
        return "apply-set";
    case TIME_SYNC_REFUSE_RANGE:
        return "refuse-range";
    case TIME_SYNC_REFUSE_STEP:
        return "refuse-step";
    case TIME_SYNC_MARK_STALE:
        return "mark-stale";
    default:
        return "unknown";
    }
}

const char *time_sync_reason_name(time_sync_reason_t reason)
{
    switch (reason) {
    case TIME_SYNC_REASON_FIRST_SYNC:
        return "first-sync";
    case TIME_SYNC_REASON_RESYNC:
        return "resync";
    case TIME_SYNC_REASON_WITHIN_THRESHOLD:
        return "within-threshold";
    case TIME_SYNC_REASON_CORRECTION:
        return "correction";
    case TIME_SYNC_REASON_STEP_TOO_LARGE:
        return "step-too-large";
    case TIME_SYNC_REASON_OUT_OF_RANGE:
        return "out-of-range";
    case TIME_SYNC_REASON_TIMEOUT:
        return "timeout";
    case TIME_SYNC_REASON_KISS_OF_DEATH:
        return "kiss-of-death";
    case TIME_SYNC_REASON_ERROR:
        return "error";
    case TIME_SYNC_REASON_CLOCK_UNREADABLE:
        return "clock-unreadable";
    case TIME_SYNC_REASON_BAD_INPUT:
        return "bad-input";
    default:
        return "unknown";
    }
}
