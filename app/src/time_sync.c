/* SPDX-License-Identifier: Apache-2.0 */

#include "time_sync.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include <crux/logging.h>
#include <crux/status.h>
#include <crux/time.h>
#include <crux/time_authority.h>

#include "time_sync_policy.h"
#include "time_sync_port.h"

#define TIME_SYNC_TAG "time"

/* The thread waits this long before its first query, so that the network configuration that the
 * image starts at boot (a static address) has had a moment. A fixed value, not an option. */
#define TIME_SYNC_START_DELAY_MS 5000u

/* The policy's copies of the supported range must be Crux's values. */
_Static_assert(TIME_SYNC_MIN_UNIX_SECONDS == CRUX_TIME_MIN_UNIX_SECONDS, "range start");
_Static_assert(TIME_SYNC_MAX_UNIX_SECONDS_EXCLUSIVE == CRUX_TIME_MAX_UNIX_SECONDS_EXCLUSIVE,
               "range end");

/* The settings must make sense together: a build that breaks one of these does not link. */
_Static_assert(CONFIG_CRUX_CONTROLLER_TIME_THRESHOLD_MS <= CONFIG_CRUX_CONTROLLER_TIME_MAX_STEP_MS,
               "the correction threshold must not exceed the maximum step");
_Static_assert(CONFIG_CRUX_CONTROLLER_TIME_STALE_AGE_S > CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S,
               "the stale age must be longer than the interval, or the time would always be stale");
_Static_assert(CONFIG_CRUX_CONTROLLER_TIME_TIMEOUT_MS < CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S * 1000,
               "a query must be over before the next one is due");

static const time_sync_limits_t limits = {
    .threshold_ms = (uint32_t)CONFIG_CRUX_CONTROLLER_TIME_THRESHOLD_MS,
    .max_step_ms = (uint32_t)CONFIG_CRUX_CONTROLLER_TIME_MAX_STEP_MS,
    .stale_age_s = (uint32_t)CONFIG_CRUX_CONTROLLER_TIME_STALE_AGE_S,
};

static struct {
    bool ready;
    /* The last answer that set the clock or agreed with it, or the start of the service. */
    crux_monotonic_time_t last_good;
} state;

static void say(crux_log_level_t level, const char *text)
{
    (void)crux_log_write(level, TIME_SYNC_TAG, text);
}

static crux_log_level_t crux_level(time_sync_log_level_t level)
{
    return level == TIME_SYNC_LOG_WARN ? CRUX_LOG_WARN : CRUX_LOG_INFO;
}

/* Whole seconds from earlier to later, 0 when later is not after earlier, saturating. */
static uint32_t seconds_between(crux_monotonic_time_t earlier, crux_monotonic_time_t later)
{
    const int64_t ms = crux_duration_to_ms_floor(crux_monotonic_diff(later, earlier));
    const int64_t seconds = ms / 1000;

    if (seconds <= 0) {
        return 0u;
    }
    return seconds > (int64_t)UINT32_MAX ? UINT32_MAX : (uint32_t)seconds;
}

static int32_t delta_ms_of(int64_t delta_ns)
{
    const int64_t ms = delta_ns / 1000000;

    if (ms > INT32_MAX) {
        return INT32_MAX;
    }
    return ms < INT32_MIN ? INT32_MIN : (int32_t)ms;
}

int time_sync_init(void)
{
    char text[96];

    if (state.ready) {
        return 0;
    }
    const crux_status_t prepared = crux_realtime_init();

    if (prepared != CRUX_OK) {
        (void)snprintf(text, sizeof text, "time sync not ready: realtime init status=%d",
                       (int)prepared);
        say(CRUX_LOG_ERROR, text);
        return (int)prepared;
    }
    /* The age counts from here until the first good answer. If the monotonic clock cannot be read,
     * the age stays 0 and the time is never marked stale, which is the safe side. */
    (void)crux_monotonic_now(&state.last_good);
    state.ready = true;
    return 0;
}

void time_sync_poll(void)
{
    if (!state.ready) {
        return;
    }
    time_sync_instant_t sample = {0};
    const time_sync_sample_result_t result =
        time_sync_port_query(CONFIG_CRUX_CONTROLLER_TIME_SERVER,
                             (uint32_t)CONFIG_CRUX_CONTROLLER_TIME_TIMEOUT_MS, &sample);

    /* The snapshot and the age are read after the query, so that the clock is compared at the
     * time the answer is used. A snapshot that cannot be read is a failed round: the policy sets
     * nothing, because it has no clock to compare the answer with. A snapshot that was read and
     * reports no time is a clock that is not valid, and an in-range answer sets it. */
    crux_realtime_snapshot_t snapshot = {0};
    const crux_status_t snapshot_status = crux_realtime_get_snapshot(&snapshot);
    const bool have_snapshot = snapshot_status == CRUX_OK && snapshot.is_valid;
    crux_monotonic_time_t now_monotonic = {0};
    const bool have_monotonic = crux_monotonic_now(&now_monotonic) == CRUX_OK;
    const uint32_t age_s =
        have_monotonic ? seconds_between(state.last_good, now_monotonic) : 0u;

    const time_sync_input_t input = {
        .result = result,
        .sample = sample,
        .clock_unreadable = snapshot_status != CRUX_OK,
        .time_valid = have_snapshot,
        .time_synchronized = have_snapshot && snapshot.is_synchronized,
        .now = {.seconds = snapshot.timestamp.seconds, .nanoseconds = snapshot.timestamp.nanoseconds},
        .seconds_since_good = age_s,
    };
    const time_sync_decision_t decision = time_sync_decide(&input, &limits);

    crux_status_t write_status = CRUX_OK;
    crux_status_t clear_status = CRUX_OK;

    if (decision.action == TIME_SYNC_APPLY_SET) {
        const crux_realtime_t value = {.seconds = sample.seconds, .nanoseconds = sample.nanoseconds};

        /* The one write of the product. Source EXTERNAL is the only one that may carry
         * synchronised = true. */
        write_status = crux_realtime_set(&value, CRUX_REALTIME_SOURCE_EXTERNAL, true);
    }
    if (decision.clear_synchronized) {
        clear_status = crux_realtime_set_synchronized(false);
    }
    if (decision.refresh_good && write_status == CRUX_OK && have_monotonic) {
        state.last_good = now_monotonic;
    }

    char text[200];

    if (write_status != CRUX_OK) {
        /* A native write failure clears validity and synchronisation in Crux Time (it keeps the
         * previous source), so the time is not valid until a later round sets it. Nothing retries
         * before the next interval. */
        (void)snprintf(text, sizeof text,
                       "time set failed status=%d reason=%s: time is not valid, retry at the next "
                       "interval",
                       (int)write_status, time_sync_reason_name(decision.reason));
        say(CRUX_LOG_ERROR, text);
        return;
    }
    int length = snprintf(text, sizeof text, "sync action=%s reason=%s age=%us",
                          time_sync_action_name(decision.action),
                          time_sync_reason_name(decision.reason), (unsigned)age_s);
    if ((decision.reason == TIME_SYNC_REASON_WITHIN_THRESHOLD ||
         decision.reason == TIME_SYNC_REASON_CORRECTION ||
         decision.reason == TIME_SYNC_REASON_STEP_TOO_LARGE) &&
        length > 0 && (size_t)length < sizeof text) {
        length += snprintf(text + length, sizeof text - (size_t)length, " delta_ms=%d",
                           (int)delta_ms_of(decision.delta_ns));
    }
    if (snapshot_status != CRUX_OK && length > 0 && (size_t)length < sizeof text) {
        length += snprintf(text + length, sizeof text - (size_t)length, " snapshot_status=%d",
                           (int)snapshot_status);
    }
    if (clear_status != CRUX_OK && length > 0 && (size_t)length < sizeof text) {
        (void)snprintf(text + length, sizeof text - (size_t)length, " clear_status=%d",
                       (int)clear_status);
    }
    say(crux_level(time_sync_decision_level(decision)), text);
}

/* The thread: a first query after a short wait, then one every interval. It never ends. */
static void time_sync_run(void)
{
    time_sync_port_sleep_ms(TIME_SYNC_START_DELAY_MS);
    for (;;) {
        time_sync_poll();
        time_sync_port_sleep_ms((uint32_t)CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S * 1000u);
    }
}

int time_sync_start(void)
{
    char text[200];
    const int prepared = time_sync_init();

    if (prepared != 0) {
        return prepared;
    }
    if (time_sync_port_start(time_sync_run) != TIME_SYNC_PORT_OK) {
        say(CRUX_LOG_WARN, "time sync not started: the thread could not be created");
        return CRUX_ERR_INVALID_STATE;
    }
    (void)snprintf(text, sizeof text,
                   "time sync started server=%s interval=%u s timeout=%u ms stale=%u s "
                   "threshold=%u ms max_step=%u ms",
                   CONFIG_CRUX_CONTROLLER_TIME_SERVER,
                   (unsigned)CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S,
                   (unsigned)CONFIG_CRUX_CONTROLLER_TIME_TIMEOUT_MS,
                   (unsigned)CONFIG_CRUX_CONTROLLER_TIME_STALE_AGE_S,
                   (unsigned)CONFIG_CRUX_CONTROLLER_TIME_THRESHOLD_MS,
                   (unsigned)CONFIG_CRUX_CONTROLLER_TIME_MAX_STEP_MS);
    say(CRUX_LOG_INFO, text);
    return 0;
}
