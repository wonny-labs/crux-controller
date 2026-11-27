/* SPDX-License-Identifier: Apache-2.0 */
#ifndef RECOVERY_H
#define RECOVERY_H

/*
 * The framework's copy of the retained region and the calls that change it (specification sections
 * 5.1 and 5.2): the boot decision of startup step 1, the fault record that the supervisor and the
 * fatal error handler write, the operator commands that clear the counter, and the operator reset
 * marker. Each change is written through the retained port at once (retained_port.h). The rules are
 * those of boot_record.h; this file holds the state.
 *
 * Callers: recovery_boot() once, from the start function; recovery_fault() from the supervisor
 * thread and from the fatal error handler; the others from any thread. No call blocks.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "boot_record.h"

typedef struct {
    bool retained;     /* the image has a retained region */
    bool region_valid; /* the region held a valid record of the last boot */
    boot_decision_t decision;
} recovery_boot_t;

/*
 * Read the region, decide the boot from the captured reset cause, and write the region back.
 * causes holds BOOT_CAUSE_* bits and counts only when cause_captured. threshold is N.
 */
void recovery_boot(bool cause_captured, uint32_t causes, uint32_t image_id, uint8_t threshold,
                   recovery_boot_t *out);

/* Write a fault record, best effort. */
void recovery_fault(boot_fault_reason_t reason, const char *name, uint32_t uptime_ms,
                    uint32_t detail);

/* The counter to zero: a successful boot or an authorised operator command. */
void recovery_counter_clear(void);

/* Set or clear the operator reset marker. */
void recovery_marker(bool set);

/* The counter as the region holds it now. */
uint8_t recovery_counter(void);

/* The record that this boot reported in step 1, as "reason name uptime_ms", or "none". */
void recovery_last_fault_text(char *text, size_t size);

#endif
