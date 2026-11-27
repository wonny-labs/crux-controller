/* SPDX-License-Identifier: Apache-2.0 */

#include "recovery.h"

#include <stdio.h>
#include <string.h>

#include <crux/system.h>

#include "retained_port.h"

/* The policy's copies of the reset flags must be Crux's values. Both sides are cast: the two sets
 * are constants of different anonymous enums, and GCC rejects comparing those. */
_Static_assert((uint32_t)BOOT_CAUSE_POR == (uint32_t)CRUX_RESET_CAUSE_POR, "POR flag");
_Static_assert((uint32_t)BOOT_CAUSE_PIN == (uint32_t)CRUX_RESET_CAUSE_PIN, "PIN flag");
_Static_assert((uint32_t)BOOT_CAUSE_SOFTWARE == (uint32_t)CRUX_RESET_CAUSE_SOFTWARE,
               "SOFTWARE flag");
_Static_assert((uint32_t)BOOT_CAUSE_WATCHDOG == (uint32_t)CRUX_RESET_CAUSE_WATCHDOG,
               "WATCHDOG flag");
_Static_assert((uint32_t)BOOT_CAUSE_DEBUG == (uint32_t)CRUX_RESET_CAUSE_DEBUG, "DEBUG flag");
_Static_assert((uint32_t)BOOT_CAUSE_CPU_LOCKUP == (uint32_t)CRUX_RESET_CAUSE_CPU_LOCKUP,
               "CPU_LOCKUP flag");

/* The region as the framework last wrote it, and the record that step 1 reported. Both change
 * only under retained_port_lock(). */
static boot_region_t region;
static boot_fault_t reported;
static bool reported_valid;

/* Encode and write under the lock that the caller holds. */
static void store(void)
{
    uint8_t bytes[BOOT_REGION_SIZE];

    boot_region_encode(&region, bytes);
    (void)retained_port_write(bytes, sizeof bytes);
}

void recovery_boot(bool cause_captured, uint32_t causes, uint32_t image_id, uint8_t threshold,
                   recovery_boot_t *out)
{
    uint8_t bytes[BOOT_REGION_SIZE];
    boot_input_t in;
    recovery_boot_t result;

    memset(&in, 0, sizeof in);
    memset(&result, 0, sizeof result);
    in.cause_captured = cause_captured;
    in.causes = causes;
    in.image_id = image_id;
    in.threshold = threshold;
    result.retained = retained_port_present();
    in.region_valid = result.retained && retained_port_read(bytes, sizeof bytes) &&
                      boot_region_decode(bytes, &in.region);
    result.region_valid = in.region_valid;

    const unsigned int key = retained_port_lock();

    if (!boot_decide(&in, &result.decision)) {
        /* Only a threshold of zero gets here, and Kconfig refuses one: count nothing. */
        boot_region_init(&result.decision.region, image_id);
    }
    region = result.decision.region;
    reported = result.decision.fault;
    reported_valid = result.decision.fault_reported;
    store();
    retained_port_unlock(key);
    if (out != NULL) {
        *out = result;
    }
}

void recovery_fault(boot_fault_reason_t reason, const char *name, uint32_t uptime_ms,
                    uint32_t detail)
{
    const unsigned int key = retained_port_lock();

    const boot_fault_info_t info = {reason, name, uptime_ms, detail};

    boot_fault_set(&region, &info);
    store();
    retained_port_unlock(key);
}

void recovery_counter_clear(void)
{
    const unsigned int key = retained_port_lock();

    boot_counter_clear(&region);
    store();
    retained_port_unlock(key);
}

void recovery_marker(bool set)
{
    const unsigned int key = retained_port_lock();

    boot_marker_set(&region, set);
    store();
    retained_port_unlock(key);
}

uint8_t recovery_counter(void)
{
    const unsigned int key = retained_port_lock();
    const uint8_t counter = region.counter;

    retained_port_unlock(key);
    return counter;
}

void recovery_last_fault_text(char *text, size_t size)
{
    if (text == NULL || size == 0u) {
        return;
    }
    const unsigned int key = retained_port_lock();
    const boot_fault_t fault = reported;
    const bool valid = reported_valid;

    retained_port_unlock(key);
    if (!valid) {
        (void)snprintf(text, size, "none");
    } else if (fault.name[0] != '\0') {
        (void)snprintf(text, size, "%s %s %lu", boot_fault_reason_name(fault.reason), fault.name,
                       (unsigned long)fault.uptime_ms);
    } else {
        (void)snprintf(text, size, "%s reason-%lu %lu", boot_fault_reason_name(fault.reason),
                       (unsigned long)fault.detail, (unsigned long)fault.uptime_ms);
    }
}
