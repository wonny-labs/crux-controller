/* SPDX-License-Identifier: Apache-2.0 */

#include "health.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include <crux/logging.h>
#include <crux/status.h>
#include <crux/system.h>

#include "health_policy.h"

#define HEALTH_TAG "system"

/* The policy's copies of the reset flags must be Crux's values. */
_Static_assert(HEALTH_CAUSE_POR == CRUX_RESET_CAUSE_POR, "POR flag");
_Static_assert(HEALTH_CAUSE_PIN == CRUX_RESET_CAUSE_PIN, "PIN flag");
_Static_assert(HEALTH_CAUSE_SOFTWARE == CRUX_RESET_CAUSE_SOFTWARE, "SOFTWARE flag");
_Static_assert(HEALTH_CAUSE_WATCHDOG == CRUX_RESET_CAUSE_WATCHDOG, "WATCHDOG flag");
_Static_assert(HEALTH_CAUSE_DEBUG == CRUX_RESET_CAUSE_DEBUG, "DEBUG flag");
_Static_assert(HEALTH_CAUSE_CPU_LOCKUP == CRUX_RESET_CAUSE_CPU_LOCKUP, "CPU_LOCKUP flag");
_Static_assert(HEALTH_CAUSE_HARDWARE == CRUX_RESET_CAUSE_HARDWARE, "HARDWARE flag");
_Static_assert(HEALTH_CAUSE_SECURITY == CRUX_RESET_CAUSE_SECURITY, "SECURITY flag");
_Static_assert(HEALTH_CAUSE_USER == CRUX_RESET_CAUSE_USER, "USER flag");
_Static_assert(HEALTH_CAUSE_TEMPERATURE == CRUX_RESET_CAUSE_TEMPERATURE, "TEMPERATURE flag");
_Static_assert(HEALTH_CAUSE_OTHER == CRUX_RESET_CAUSE_OTHER, "OTHER flag");

static struct {
    crux_watchdog_t watchdog; /* valid only after crux_watchdog_start() returned CRUX_OK */
    health_feed_t feed;
    bool watchdog_allowed;
} state = {.feed = {.state = HEALTH_FEED_IDLE}, .watchdog_allowed = true};

static crux_log_level_t crux_level(health_log_level_t level)
{
    switch (level) {
    case HEALTH_LOG_ERROR:
        return CRUX_LOG_ERROR;
    case HEALTH_LOG_WARN:
        return CRUX_LOG_WARN;
    case HEALTH_LOG_INFO:
    default:
        return CRUX_LOG_INFO;
    }
}

static void say(health_log_level_t level, const char *text)
{
    (void)crux_log_write(crux_level(level), HEALTH_TAG, text);
}

int health_report_reset_cause(void)
{
    crux_reset_cause_t cause = {0};
    char names[96];
    char text[160];
    const crux_status_t read = crux_system_reset_cause_get(&cause);

    if (read != CRUX_OK) {
        (void)snprintf(text, sizeof text, "reset cause unavailable status=%d", (int)read);
        say(HEALTH_LOG_WARN, text);
        return (int)read;
    }
    const health_boot_decision_t decision = health_boot_decide(cause.causes);

    if (health_cause_text(cause.causes, names, sizeof names) != HEALTH_OK) {
        (void)snprintf(names, sizeof names, "0x%08x", (unsigned)cause.causes);
    }
    (void)snprintf(text, sizeof text, "reset cause=%s class=%s", names,
                   health_class_name(decision.cause_class));
    say(decision.level, text);
    state.watchdog_allowed = decision.start_watchdog;

    /* The line is written, so the flags can go: Crux asks for the diagnostics to be kept first. */
    const crux_status_t cleared = crux_system_reset_cause_clear();

    if (cleared != CRUX_OK) {
        (void)snprintf(text, sizeof text, "reset cause not cleared status=%d", (int)cleared);
        say(HEALTH_LOG_WARN, text);
    }
    return 0;
}

int health_watchdog_start(uint32_t period_ms)
{
    uint32_t timeout_ms = 0;
    char text[160];

    if (!state.watchdog_allowed) {
        say(HEALTH_LOG_WARN, "watchdog not started: the reset cause policy does not allow it");
        return CRUX_ERR_INVALID_STATE;
    }
    if (health_watchdog_timeout(period_ms, &timeout_ms) != HEALTH_OK) {
        (void)snprintf(text, sizeof text,
                       "watchdog not started: a cycle of %u ms does not fit the supported interval",
                       (unsigned)period_ms);
        say(HEALTH_LOG_WARN, text);
        return CRUX_ERR_OUT_OF_RANGE;
    }
    const crux_status_t started = crux_watchdog_start(timeout_ms, &state.watchdog);

    if (started != CRUX_OK) {
        (void)snprintf(text, sizeof text, "watchdog not started: status=%d", (int)started);
        /* Not supported is a platform without a watchdog. Any other status can mean that the
         * native start was attempted and its outcome is unknown, which Crux does not retry. */
        say(started == CRUX_ERR_NOT_SUPPORTED ? HEALTH_LOG_WARN : HEALTH_LOG_ERROR, text);
        return (int)started;
    }
    health_feed_armed(&state.feed);
    (void)snprintf(text, sizeof text, "watchdog started timeout=%u ms cycle=%u ms",
                   (unsigned)timeout_ms, (unsigned)period_ms);
    say(HEALTH_LOG_INFO, text);
    return 0;
}

void health_cycle(void)
{
    if (!health_feed_wanted(&state.feed)) {
        return;
    }
    const crux_status_t fed = crux_watchdog_feed(state.watchdog);

    if (health_feed_result(&state.feed, fed == CRUX_OK) == HEALTH_FEED_REPORT_AND_STOP) {
        char text[160];

        (void)snprintf(text, sizeof text,
                       "watchdog feed refused status=%d after %u accepted: feeding stopped, "
                       "the watchdog ends the run when its interval runs out",
                       (int)fed, (unsigned)state.feed.accepted);
        say(HEALTH_LOG_ERROR, text);
    }
}
