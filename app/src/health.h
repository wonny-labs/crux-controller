/* SPDX-License-Identifier: Apache-2.0 */
#ifndef HEALTH_H
#define HEALTH_H

/*
 * Step S4: the reset cause and a single-owner watchdog, through <crux/system.h>. This is the one
 * file pair of the product that calls Crux System. It needs no Zephyr header and no zone: the
 * watchdog driver, HWINFO and the reboot call sit inside Crux's own binding, and the product
 * supplies only Kconfig symbols and the devicetree alias crux-watchdog0 (conf/s4.conf and
 * boards/s4.overlay). What the product decides is in health_policy.h.
 *
 * Call from thread context, after Crux Logging is up. Each call reports through Crux Logging under
 * the tag "system" and returns 0 or a negative crux_status_t.
 */

#include <stdint.h>

/*
 * Read the reset cause, write one line for it, then clear the flags (Crux allows a clear only after
 * a successful read, and the flags would otherwise pile up across resets). The line is written
 * before the clear is asked for. A cause that cannot be read is reported as a warning and its
 * status is returned; the product starts anyway. Call once, at boot.
 */
int health_report_reset_cause(void);

/*
 * Start the one watchdog of this boot with the interval that the policy picks for a workload cycle
 * of period_ms. Returns 0 when the watchdog runs and the tracker is armed.
 *
 * No watchdog runs, and the product carries on without one (health_cycle() then does nothing), in
 * three cases of a failed start: the policy refuses the cycle (CRUX_ERR_OUT_OF_RANGE), Crux refuses
 * the interval before any attempt (CRUX_ERR_OUT_OF_RANGE), or the platform has no device
 * (CRUX_ERR_NOT_SUPPORTED). The reset cause policy can also refuse the start before any attempt
 * (CRUX_ERR_INVALID_STATE); that cannot happen today, because start_watchdog is always true.
 * On any other error the native start may have been attempted: Crux does not retry it and cannot
 * tell its outcome, so the state is unknown. The product does not feed it and says so at error
 * level, and the watchdog may still reset the board. Call once, at boot, after
 * health_report_reset_cause().
 */
int health_watchdog_start(uint32_t period_ms);

/*
 * Feed the watchdog once. The workload's producer thread calls it for each pass that finds a cycle
 * due and nothing else does, so a workload that stops cycling stops feeding. Does nothing when
 * the watchdog is not running or after a feed was refused. The first refusal is reported once;
 * nothing retries it and nothing resets the controller: the watchdog ends the run when its interval
 * runs out. Thread context of the caller is the producer thread only.
 */
void health_cycle(void);

#endif
