/* SPDX-License-Identifier: Apache-2.0 */

#include "health_policy.h"

#include <string.h>

#define FAULT_CAUSES                                                                               \
    ((uint32_t)(HEALTH_CAUSE_CPU_LOCKUP | HEALTH_CAUSE_SECURITY | HEALTH_CAUSE_TEMPERATURE))
#define NORMAL_CAUSES                                                                              \
    ((uint32_t)(HEALTH_CAUSE_POR | HEALTH_CAUSE_PIN | HEALTH_CAUSE_SOFTWARE | HEALTH_CAUSE_DEBUG | \
                HEALTH_CAUSE_USER | HEALTH_CAUSE_HARDWARE))
#define NAMED_CAUSES (NORMAL_CAUSES | (uint32_t)HEALTH_CAUSE_WATCHDOG | FAULT_CAUSES)
#define ALL_CAUSES (NAMED_CAUSES | (uint32_t)HEALTH_CAUSE_OTHER)

health_cause_class_t health_cause_classify(uint32_t causes)
{
    if ((causes & FAULT_CAUSES) != 0u) {
        return HEALTH_CLASS_FAULT;
    }
    if ((causes & HEALTH_CAUSE_WATCHDOG) != 0u) {
        return HEALTH_CLASS_WATCHDOG;
    }
    if ((causes & NORMAL_CAUSES) != 0u) {
        return HEALTH_CLASS_NORMAL;
    }
    return HEALTH_CLASS_UNKNOWN;
}

const char *health_class_name(health_cause_class_t cause_class)
{
    switch (cause_class) {
    case HEALTH_CLASS_NORMAL:
        return "normal";
    case HEALTH_CLASS_WATCHDOG:
        return "watchdog";
    case HEALTH_CLASS_FAULT:
        return "fault";
    case HEALTH_CLASS_UNKNOWN:
    default:
        return "unknown";
    }
}

health_boot_decision_t health_boot_decide(uint32_t causes)
{
    health_boot_decision_t decision = {
        .cause_class = health_cause_classify(causes),
        .level = HEALTH_LOG_WARN,
        .start_watchdog = true,
    };

    if (decision.cause_class == HEALTH_CLASS_NORMAL) {
        decision.level = HEALTH_LOG_INFO;
    } else if (decision.cause_class == HEALTH_CLASS_FAULT) {
        decision.level = HEALTH_LOG_ERROR;
    }
    return decision;
}

health_status_t health_cause_text(uint32_t causes, char *buffer, size_t capacity)
{
    static const struct {
        uint32_t flag;
        const char *name;
    } names[] = {
        {HEALTH_CAUSE_POR, "POR"},
        {HEALTH_CAUSE_PIN, "PIN"},
        {HEALTH_CAUSE_SOFTWARE, "SOFTWARE"},
        {HEALTH_CAUSE_WATCHDOG, "WATCHDOG"},
        {HEALTH_CAUSE_DEBUG, "DEBUG"},
        {HEALTH_CAUSE_CPU_LOCKUP, "CPU_LOCKUP"},
        {HEALTH_CAUSE_HARDWARE, "HARDWARE"},
        {HEALTH_CAUSE_SECURITY, "SECURITY"},
        {HEALTH_CAUSE_USER, "USER"},
        {HEALTH_CAUSE_TEMPERATURE, "TEMPERATURE"},
        {HEALTH_CAUSE_OTHER, "OTHER"},
    };
    size_t length = 0;

    if (buffer == NULL || capacity == 0u) {
        return HEALTH_ERR_RANGE;
    }
    buffer[0] = '\0';
    /* A bit without a name is folded into OTHER, so the text never hides a set bit. */
    if ((causes & ~ALL_CAUSES) != 0u) {
        causes |= (uint32_t)HEALTH_CAUSE_OTHER;
    }
    causes &= ALL_CAUSES;
    if (causes == 0u) {
        if (capacity < sizeof "none") {
            return HEALTH_ERR_RANGE;
        }
        memcpy(buffer, "none", sizeof "none");
        return HEALTH_OK;
    }
    for (size_t i = 0; i < sizeof names / sizeof names[0]; i++) {
        if ((causes & names[i].flag) == 0u) {
            continue;
        }
        const size_t name_length = strlen(names[i].name);
        const size_t separator = length == 0u ? 0u : 1u;

        if (length + separator + name_length + 1u > capacity) {
            buffer[0] = '\0';
            return HEALTH_ERR_RANGE;
        }
        if (separator != 0u) {
            buffer[length++] = '+';
        }
        memcpy(buffer + length, names[i].name, name_length + 1u);
        length += name_length;
    }
    return HEALTH_OK;
}

health_status_t health_watchdog_timeout(uint32_t period_ms, uint32_t *timeout_ms)
{
    if (timeout_ms == NULL || period_ms == 0u) {
        return HEALTH_ERR_RANGE;
    }
    /* 64-bit, so that no period can overflow while the range is checked. */
    uint64_t timeout = (uint64_t)period_ms * HEALTH_WATCHDOG_CYCLES;

    timeout = (timeout + HEALTH_WATCHDOG_STEP_MS - 1u) / HEALTH_WATCHDOG_STEP_MS *
              HEALTH_WATCHDOG_STEP_MS;
    if (timeout < HEALTH_WATCHDOG_MIN_MS) {
        timeout = HEALTH_WATCHDOG_MIN_MS;
    }
    if (timeout > HEALTH_WATCHDOG_MAX_MS) {
        timeout = HEALTH_WATCHDOG_MAX_MS;
    }
    if (timeout < (uint64_t)period_ms * HEALTH_WATCHDOG_MIN_CYCLES) {
        return HEALTH_ERR_RANGE;
    }
    *timeout_ms = (uint32_t)timeout;
    return HEALTH_OK;
}

void health_feed_init(health_feed_t *feed)
{
    if (feed == NULL) {
        return;
    }
    feed->state = HEALTH_FEED_IDLE;
    feed->accepted = 0u;
}

void health_feed_armed(health_feed_t *feed)
{
    if (feed != NULL && feed->state == HEALTH_FEED_IDLE) {
        feed->state = HEALTH_FEED_RUNNING;
    }
}

bool health_feed_wanted(const health_feed_t *feed)
{
    return feed != NULL && feed->state == HEALTH_FEED_RUNNING;
}

health_feed_outcome_t health_feed_result(health_feed_t *feed, bool accepted)
{
    if (!health_feed_wanted(feed)) {
        return HEALTH_FEED_IGNORED;
    }
    if (accepted) {
        feed->accepted++;
        return HEALTH_FEED_CONTINUE;
    }
    feed->state = HEALTH_FEED_STOPPED;
    return HEALTH_FEED_REPORT_AND_STOP;
}
