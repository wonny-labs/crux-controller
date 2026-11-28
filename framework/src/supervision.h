/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SUPERVISION_H
#define SUPERVISION_H

/*
 * The decisions of the supervisor (specification sections 4.1 to 4.4): whether the current startup
 * step is within its deadline, whether a task watchdog channel has expired, and so whether the
 * supervisor feeds the hardware watchdog or latches the fault and stops feeding for good. Plain C
 * with ISO C includes only (tests/host/test_supervision.c). The supervisor thread in the adapter
 * zone (framework/os/supervisor_zephyr.c) holds the lock, the clock and the watchdog token, and
 * asks this state what to do once per feed period.
 *
 * The latch comes first: the poll that finds a fault returns SUPERVISION_LATCH once, and every
 * later poll returns SUPERVISION_STOPPED, so the supervisor writes the record and requests a reset
 * at most once, and never feeds again in this boot. Nothing here resets anything.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "boot_record.h"

/* Most channels in one table; task watchdog channels beyond these are refused. */
#define SUPERVISION_CHANNELS_MAX 16u

typedef enum {
    SUPERVISION_FEED,    /* every supervised activity made progress: feed */
    SUPERVISION_LATCH,   /* a fault was found now: write the record, then reset; do not feed */
    SUPERVISION_STOPPED, /* latched earlier: do nothing */
} supervision_action_t;

typedef struct {
    bool step_active;
    char step[BOOT_NAME_SIZE];
    uint64_t step_started_ms;
    uint32_t step_deadline_ms;
    bool latched;
    boot_fault_reason_t reason; /* with latched */
    char name[BOOT_NAME_SIZE];  /* with latched: the step or the channel */
    bool report_due;            /* latched from outside and not yet taken by the supervisor */
} supervision_t;

void supervision_init(supervision_t *state);

/* A startup step begins at now_ms; its deadline counts from then. A deadline of zero means none. */
void supervision_step_begin(supervision_t *state, uint64_t now_ms, const char *name,
                            uint32_t deadline_ms);

/* The step returned within its deadline, or startup ended. */
void supervision_step_end(supervision_t *state);

/* The task watchdog channels as one pass sees them. */
typedef struct {
    const char *const *names; /* names[i] for channel i; may be NULL */
    size_t count;             /* entries of names */
    uint32_t expired;         /* bit i: channel i expired since the boot (at most 32 channels) */
} supervision_channels_t;

/*
 * One supervisor pass. The first finding wins: a step past its deadline, else the lowest expired
 * channel. channels may be NULL for none.
 */
supervision_action_t supervision_poll(supervision_t *state, uint64_t now_ms,
                                      const supervision_channels_t *channels);

/* Latch a fault that the supervisor learns of from elsewhere (an application stop that failed).
 * Returns true when this call latched, false when a fault was latched already. */
bool supervision_latch(supervision_t *state, boot_fault_reason_t reason, const char *name);

/*
 * The supervisor's side of an outside latch: true once after supervision_latch() latched, with the
 * reason and the name, so that the supervisor writes the record, calls safe_state and resets as it
 * does for a fault that its own poll found. A latch that a poll found was reported by that poll's
 * SUPERVISION_LATCH and is not reported again here.
 */
bool supervision_take_report(supervision_t *state, boot_fault_reason_t *reason,
                             char name[BOOT_NAME_SIZE]);

/*
 * Whether one watchdog timeout T covers the feed period with a margin: T at least twice the
 * period, both above zero (section 4.1: T covers the feed period plus a scheduling margin).
 */
bool supervision_timing_valid(uint32_t timeout_ms, uint32_t period_ms);

#endif
