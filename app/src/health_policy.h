/* SPDX-License-Identifier: Apache-2.0 */
#ifndef HEALTH_POLICY_H
#define HEALTH_POLICY_H

/*
 * The product's policy for step S4: what a reset cause means at boot, how long the watchdog
 * interval is, and what a refused feed leads to. Plain C with ISO C includes only, so the policy
 * builds and is tested on the host with no Crux or Zephyr header. health.c is the one file that
 * reads the cause, starts the watchdog and feeds it through <crux/system.h>, and it asks this
 * policy what to do.
 *
 * Crux System reports mechanisms only: it names no health verdict and no recovery. These rules are
 * the product's own, they are conservative defaults chosen for this synthetic workload, and the
 * owner has not set a policy. Nothing here resets the controller, retries a feed or clears a fault.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    HEALTH_OK = 0,
    HEALTH_ERR_RANGE, /* an argument is out of range, or the result does not fit */
} health_status_t;

/*
 * The reset cause flags, as Crux publishes them in <crux/system.h> (CRUX_RESET_CAUSE_*). They are
 * copies so that this file needs no Crux header; health.c asserts at build time that each one
 * equals the Crux value, so a change on either side is a build error.
 */
enum {
    HEALTH_CAUSE_POR = 1u << 0,
    HEALTH_CAUSE_PIN = 1u << 1,
    HEALTH_CAUSE_SOFTWARE = 1u << 2,
    HEALTH_CAUSE_WATCHDOG = 1u << 3,
    HEALTH_CAUSE_DEBUG = 1u << 4,
    HEALTH_CAUSE_CPU_LOCKUP = 1u << 5,
    HEALTH_CAUSE_HARDWARE = 1u << 6,
    HEALTH_CAUSE_SECURITY = 1u << 7,
    HEALTH_CAUSE_USER = 1u << 8,
    HEALTH_CAUSE_TEMPERATURE = 1u << 9,
    HEALTH_CAUSE_OTHER = 1u << 10,
};

typedef enum {
    HEALTH_LOG_INFO,
    HEALTH_LOG_WARN,
    HEALTH_LOG_ERROR,
} health_log_level_t;

/* What kind of start this was. */
typedef enum {
    HEALTH_CLASS_NORMAL,   /* power, the pin, software, a debugger, a user or hardware reset */
    HEALTH_CLASS_WATCHDOG, /* the watchdog ended the previous run */
    HEALTH_CLASS_FAULT,    /* a CPU lockup, a security reset or a temperature reset */
    HEALTH_CLASS_UNKNOWN,  /* no flag is set, or only a flag that has no name here */
} health_cause_class_t;

/*
 * Classify the latched flags. They can accumulate, so one class is chosen by precedence: a fault
 * outranks the watchdog, which outranks the ordinary causes. A flag with no name here counts only
 * when nothing else is set.
 */
health_cause_class_t health_cause_classify(uint32_t causes);

/* The class as one lower-case word. An unknown value reads as "unknown". */
const char *health_class_name(health_cause_class_t cause_class);

typedef struct {
    health_cause_class_t cause_class;
    health_log_level_t level; /* the level of the one boot line */
    /*
     * Always true: no cause keeps the product from arming the watchdog, and none puts it in a safe
     * mode. The product only reports. The field is here so that a test pins the rule, and so that
     * a later policy has the place to change it.
     */
    bool start_watchdog;
} health_boot_decision_t;

/* Normal: info. Watchdog or unknown: warning. Fault: error. */
health_boot_decision_t health_boot_decide(uint32_t causes);

/*
 * Write the flags as names in bit order, joined by '+' ("POR+WATCHDOG"), "none" when no bit is
 * set. A bit that has no name reads as OTHER. HEALTH_ERR_RANGE with an empty string when the text
 * and its end of string do not fit, or when the buffer is NULL or empty.
 */
health_status_t health_cause_text(uint32_t causes, char *buffer, size_t capacity);

/*
 * The watchdog interval that Crux System supports on the RT1060-EVKB: 500 ms to 64000 ms in steps
 * of 500 ms (crux-pilot components/system/ports/zephyr/system_zephyr.c at the pinned revision).
 * The product never goes below 2000 ms.
 */
#define HEALTH_WATCHDOG_MIN_MS 2000u
#define HEALTH_WATCHDOG_MAX_MS 64000u
#define HEALTH_WATCHDOG_STEP_MS 500u
/* The interval is this many cycles long, before rounding and clamping. */
#define HEALTH_WATCHDOG_CYCLES 10u
/* A cycle that the clamped interval cannot hold this many times is refused. */
#define HEALTH_WATCHDOG_MIN_CYCLES 3u

/*
 * The interval for a workload cycle of period_ms: ten cycles, rounded up to the step and kept in
 * [HEALTH_WATCHDOG_MIN_MS, HEALTH_WATCHDOG_MAX_MS]. When even the clamped interval is shorter than
 * three cycles, a late cycle would reset the controller, so the product does not arm: the call
 * returns HEALTH_ERR_RANGE and leaves *timeout_ms as it was. Also for a period of 0 or a NULL
 * output.
 */
health_status_t health_watchdog_timeout(uint32_t period_ms, uint32_t *timeout_ms);

typedef enum {
    HEALTH_FEED_IDLE,    /* not armed: no feed is wanted */
    HEALTH_FEED_RUNNING, /* armed: one feed is wanted for each pass that has cycles due */
    HEALTH_FEED_STOPPED, /* a feed was refused: no feed is wanted, for good */
} health_feed_state_t;

typedef struct {
    health_feed_state_t state;
    uint32_t accepted; /* feeds that Crux accepted */
} health_feed_t;

typedef enum {
    HEALTH_FEED_CONTINUE,        /* the feed was accepted */
    HEALTH_FEED_REPORT_AND_STOP, /* the first refusal: report it once, feed no more */
    HEALTH_FEED_IGNORED,         /* no feed was expected, so the result means nothing */
} health_feed_outcome_t;

/* All four are safe with a NULL tracker: init and armed do nothing, wanted is false. */
void health_feed_init(health_feed_t *feed);

/* After Crux accepted the one watchdog start. Idle becomes running; a stopped tracker stays. */
void health_feed_armed(health_feed_t *feed);

/* True when this cycle should call the feed: armed and not stopped. */
bool health_feed_wanted(const health_feed_t *feed);

/*
 * What to do with the result of a feed. After a refusal Crux System keeps the watchdog lifecycle
 * faulted and every later feed fails, so the product reports the first refusal once and stops
 * feeding. The watchdog then ends the run when its interval runs out, which is what a missed feed
 * means in the Crux contract; the product adds no reset of its own.
 */
health_feed_outcome_t health_feed_result(health_feed_t *feed, bool accepted);

#endif
