/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TIME_SYNC_POLICY_H
#define TIME_SYNC_POLICY_H

/*
 * The product's policy for step S5: when an answer from an SNTP server may set the clock of Crux
 * Time, and when Crux has to be told that its time is no longer synchronised. Plain C with ISO C
 * includes only, so the policy builds and is tested on the host with no Crux or Zephyr header.
 * time_sync.c is the one file that reads the Crux Time snapshot and calls the Crux Time authority
 * through <crux/time_authority.h>, and it asks this policy what to do.
 *
 * Crux Time reports mechanisms only. It states that staleness and source policy belong to the
 * application, so these rules are the product's own: conservative defaults for this synthetic
 * workload, not a security measure. SNTP here carries no authentication, so a server (or anything
 * on the path) that answers with a time inside the supported range can move the clock.
 *
 * The rules, in the order that time_sync_decide() applies them:
 *
 *   1. An answer that failed, timed out or was a kiss-o'-death never sets the clock. An answer that
 *      is outside [2000-01-01, 2100-01-01) or not a normalised time is refused. Each of these
 *      counts as a failure: when Crux is synchronised and the last good answer is older than the
 *      stale limit (strictly), the time is marked no longer synchronised. That happens once,
 *      because the next call finds Crux unsynchronised.
 *   2. While Crux time is not valid, or not synchronised (boot, stale, lost), any in-range answer
 *      is applied. The clock is not compared with it.
 *   3. While Crux time is synchronised, the difference d = answer - clock decides:
 *        |d| below the correction threshold   no action; the answer confirms the clock
 *        |d| from the threshold up to and including the maximum step   the clock is set
 *        |d| above the maximum step           the answer is refused and synchronisation is
 *                                              marked lost, so that the next in-range answer
 *                                              applies by rule 2
 *
 * Nothing here persists time: after a reset the time is not valid until the first answer.
 */

#include <stdbool.h>
#include <stdint.h>

/*
 * The supported range of Crux Time, as it publishes it in <crux/time.h> (CRUX_TIME_MIN_UNIX_SECONDS
 * and CRUX_TIME_MAX_UNIX_SECONDS_EXCLUSIVE). They are copies so that this file needs no Crux
 * header; time_sync.c asserts at build time that each one equals the Crux value.
 */
#define TIME_SYNC_MIN_UNIX_SECONDS INT64_C(946684800)
#define TIME_SYNC_MAX_UNIX_SECONDS_EXCLUSIVE INT64_C(4102444800)

/* A point in time as seconds since 1970-01-01T00:00:00Z (no leap seconds) and nanoseconds. */
typedef struct {
    int64_t seconds;
    uint32_t nanoseconds; /* below 1000000000 in a normalised time */
} time_sync_instant_t;

/* What one query to the server came to. */
typedef enum {
    TIME_SYNC_SAMPLE_OK = 0,        /* an answer with a time */
    TIME_SYNC_SAMPLE_TIMEOUT,       /* no answer in time */
    TIME_SYNC_SAMPLE_KISS_OF_DEATH, /* the server asked the client to stop (stratum 0) */
    TIME_SYNC_SAMPLE_ERROR,         /* any other failure: address, socket, a malformed answer */
} time_sync_sample_result_t;

/* The limits that the policy applies. threshold_ms must not exceed max_step_ms. */
typedef struct {
    uint32_t threshold_ms; /* below this a difference is left alone */
    uint32_t max_step_ms;  /* above this a difference is refused */
    uint32_t stale_age_s;  /* a last good answer older than this makes synchronisation stale */
} time_sync_limits_t;

typedef struct {
    time_sync_sample_result_t result;
    time_sync_instant_t sample; /* the answer; read only when result is OK */
    bool time_valid;            /* from the Crux Time snapshot: a time has been established */
    bool time_synchronized;     /* from the Crux Time snapshot: currently reported synchronised */
    time_sync_instant_t now;    /* the Crux realtime; read only when time_valid */
    /*
     * Seconds since the last good answer, or since the service started when there was none. A
     * good answer is one that set the clock or agreed with it, see refresh_good below.
     */
    uint32_t seconds_since_good;
} time_sync_input_t;

typedef enum {
    TIME_SYNC_NO_ACTION = 0, /* leave the clock and the flags as they are */
    TIME_SYNC_APPLY_SET,     /* set the clock with source EXTERNAL, synchronised */
    TIME_SYNC_REFUSE_RANGE,  /* the answer is outside the supported range */
    TIME_SYNC_REFUSE_STEP,   /* the answer is too far from a synchronised clock */
    TIME_SYNC_MARK_STALE,    /* no good answer for too long: no longer synchronised */
} time_sync_action_t;

/* Why. For a failure it names the failure, also when the action is MARK_STALE. */
typedef enum {
    TIME_SYNC_REASON_FIRST_SYNC = 0, /* no valid time yet: any in-range answer is applied */
    TIME_SYNC_REASON_RESYNC, /* valid but not synchronised: any in-range answer is applied */
    TIME_SYNC_REASON_WITHIN_THRESHOLD,
    TIME_SYNC_REASON_CORRECTION, /* between the threshold and the maximum step */
    TIME_SYNC_REASON_STEP_TOO_LARGE,
    TIME_SYNC_REASON_OUT_OF_RANGE,
    TIME_SYNC_REASON_TIMEOUT,
    TIME_SYNC_REASON_KISS_OF_DEATH,
    TIME_SYNC_REASON_ERROR,
    TIME_SYNC_REASON_BAD_INPUT, /* a NULL argument, an unknown result or unusable limits */
} time_sync_reason_t;

typedef struct {
    time_sync_action_t action;
    time_sync_reason_t reason;
    /* Tell Crux that the time is no longer synchronised (REFUSE_STEP and MARK_STALE). */
    bool clear_synchronized;
    /* The answer confirmed or set the clock: the age of the last good answer starts again. */
    bool refresh_good;
    /* answer - clock in nanoseconds; set when the two were compared (reasons WITHIN_THRESHOLD,
     * CORRECTION and STEP_TOO_LARGE), 0 otherwise. */
    int64_t delta_ns;
} time_sync_decision_t;

/* True when seconds is in [TIME_SYNC_MIN_UNIX_SECONDS, TIME_SYNC_MAX_UNIX_SECONDS_EXCLUSIVE) and
 * nanoseconds is below one second. */
bool time_sync_instant_in_range(time_sync_instant_t instant);

/* An SNTP answer as the Zephyr library reports it (struct sntp_time). The two numbers are fields
 * of one type so that a call cannot swap them. */
typedef struct {
    uint64_t seconds;  /* since the Unix epoch */
    uint32_t fraction; /* in units of 2^-32 s */
} time_sync_sntp_answer_t;

/*
 * The instant for an SNTP answer of the Zephyr library: seconds since the Unix epoch and a fraction
 * counted in units of 2^-32 s. The fraction is converted to nanoseconds, rounded down, so it never
 * reaches a whole second. Seconds above INT64_MAX become INT64_MAX, which is out of range.
 */
time_sync_instant_t time_sync_instant_from_sntp(time_sync_sntp_answer_t answer);

/*
 * Decide what to do with one query result. Pure: it reads only its arguments. A NULL argument, a
 * result code that is not one of the four, or limits with threshold_ms above max_step_ms give
 * NO_ACTION with the reason BAD_INPUT.
 */
time_sync_decision_t time_sync_decide(const time_sync_input_t *input,
                                      const time_sync_limits_t *limits);

typedef enum {
    TIME_SYNC_LOG_INFO,
    TIME_SYNC_LOG_WARN,
} time_sync_log_level_t;

/* Information for a clock that was set, confirmed or re-synchronised; a warning for every refusal,
 * every failure and the stale mark. */
time_sync_log_level_t time_sync_decision_level(time_sync_decision_t decision);

/* The action, or the reason, as lower-case words with hyphens. An unknown value reads as
 * "unknown". */
const char *time_sync_action_name(time_sync_action_t action);
const char *time_sync_reason_name(time_sync_reason_t reason);

#endif
