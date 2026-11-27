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
#define SUPERVISION_CHANNELS_MAX 8u

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
} supervision_t;

void supervision_init(supervision_t *state);

/* A startup step begins; its deadline counts from now_ms. A deadline of zero means none. */
void supervision_step_begin(supervision_t *state, const char *name, uint32_t deadline_ms,
                            uint64_t now_ms);

/* The step returned within its deadline, or startup ended. */
void supervision_step_end(supervision_t *state);

/*
 * One supervisor pass. expired holds a bit per channel that expired since the boot (bit i for
 * names[i], at most SUPERVISION_CHANNELS_MAX). The first finding wins: a step past its deadline,
 * else the lowest expired channel.
 */
supervision_action_t supervision_poll(supervision_t *state, uint64_t now_ms, uint32_t expired,
                                      const char *const names[], size_t count);

/* Latch a fault that the supervisor learns of from elsewhere (an application stop that failed).
 * Returns true when this call latched, false when a fault was latched already. */
bool supervision_latch(supervision_t *state, boot_fault_reason_t reason, const char *name);

/*
 * Whether one watchdog timeout T covers the feed period with a margin: T at least twice the
 * period, both above zero (section 4.1: T covers the feed period plus a scheduling margin).
 */
bool supervision_timing_valid(uint32_t timeout_ms, uint32_t period_ms);

#endif
