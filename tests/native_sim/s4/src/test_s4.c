/* SPDX-License-Identifier: Apache-2.0 */

/* Runs the application's own health.c and health_policy.c on the real Crux System provider, on
 * native_sim. The simulator binds no watchdog device, so Crux System reports the watchdog as not
 * supported there: a feed cycle and a missed feed cannot be shown here, and the Host test of the
 * policy and the RT1060-EVKB build stand in for them. What this scenario does show is the boot
 * line that names the reset cause, the clear after it, and a product that carries on when the
 * watchdog is not available. One case per image, chosen by S4_CASE, because Crux System allows
 * one watchdog start per boot. */

#include <stdint.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/kernel.h>
#include <zephyr/ztest.h>

#include <crux/status.h>
#include <crux/system.h>

#include "health.h"

#define LOG_UART DEVICE_DT_GET(DT_NODELABEL(logging_test))

static char captured[4096];

/* Everything that Crux Logging wrote to the emulated UART so far. */
static const char *log_text(void)
{
    k_msleep(200); /* let the deferred log thread drain */
    const size_t length = uart_emul_get_tx_data(LOG_UART, (uint8_t *)captured, sizeof captured - 1);

    captured[length] = '\0';
    return captured;
}

static unsigned int occurrences(const char *text, const char *needle)
{
    unsigned int count = 0;

    for (const char *at = strstr(text, needle); at != NULL; at = strstr(at + 1, needle)) {
        count++;
    }
    return count;
}

ZTEST_SUITE(s4, NULL, NULL, NULL, NULL, NULL);

#if defined(S4_CASE_reset_cause)

/* The boot line: one line, the cause that the simulator reports (power on), its class, and the
 * flags are cleared after the line was written. */
ZTEST(s4, test_the_boot_line_names_the_reset_cause_once_and_the_flags_are_cleared)
{
    crux_reset_cause_t cause = {0};

    zassert_true(device_is_ready(LOG_UART));
    zassert_equal(health_report_reset_cause(), 0);
    const char *log = log_text();

    zassert_equal(occurrences(log, "system: reset cause="), 1u, "not one cause line in: %s", log);
    zassert_not_null(strstr(log, "system: reset cause=POR class=normal"), "no POR line in: %s", log);
    zassert_is_null(strstr(log, "not cleared"), "the clear was refused: %s", log);

    zassert_equal(crux_system_reset_cause_get(&cause), CRUX_OK);
    zassert_equal(cause.causes, 0u, "the flags are still set after the clear");
}

#elif defined(S4_CASE_watchdog_unsupported)

/* The simulator has no watchdog: the start is refused as not supported, said once, and the cycle
 * hook then does nothing. Crux System reports the watchdog as unavailable, not as faulted. */
ZTEST(s4, test_a_product_without_a_watchdog_says_so_once_and_the_cycle_hook_does_nothing)
{
    crux_system_status_t status = {0};

    zassert_true(device_is_ready(LOG_UART));
    zassert_equal(health_watchdog_start(100), CRUX_ERR_NOT_SUPPORTED);
    for (int i = 0; i < 5; i++) {
        health_cycle();
    }
    const char *log = log_text();

    zassert_equal(occurrences(log, "system: watchdog not started"), 1u, "in: %s", log);
    zassert_is_null(strstr(log, "feed"), "a feed was reported in: %s", log);
    zassert_is_null(strstr(log, "watchdog started"), "the start was reported in: %s", log);

    zassert_equal(crux_system_status_get(&status), CRUX_OK);
    zassert_equal(status.watchdog_status, CRUX_ERR_NOT_SUPPORTED);
    zassert_equal(status.watchdog_state, CRUX_WATCHDOG_UNAVAILABLE);
    zassert_equal(status.watchdog_timeout_ms, 0u);
}

#elif defined(S4_CASE_period_out_of_range)

/* A cycle that the supported interval cannot hold three times is refused by the product before
 * Crux System is asked, and nothing is fed. */
ZTEST(s4, test_a_cycle_too_long_for_the_watchdog_is_refused_before_crux_is_asked)
{
    zassert_true(device_is_ready(LOG_UART));
    zassert_equal(health_watchdog_start(30000), CRUX_ERR_OUT_OF_RANGE);
    zassert_equal(health_watchdog_start(0), CRUX_ERR_OUT_OF_RANGE);
    health_cycle();
    const char *log = log_text();

    zassert_equal(occurrences(log, "system: watchdog not started"), 2u, "in: %s", log);
    zassert_not_null(strstr(log, "30000 ms"), "the cycle is not named in: %s", log);
    zassert_is_null(strstr(log, "feed"), "a feed was reported in: %s", log);
}

#else
#error "S4_CASE names no case of this test"
#endif
