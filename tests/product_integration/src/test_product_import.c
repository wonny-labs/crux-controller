/* SPDX-License-Identifier: Apache-2.0 */

/* The fixture product's test: the framework, imported into a west workspace of its own, starts its
 * services on native_sim. The product reaches the framework through <controller/framework.h> and
 * its Kconfig symbols only. The test reads what Crux Logging wrote to an emulated UART and what the
 * Crux serial console wrote to another.
 *
 * The cases run in order, in one image, because the start function runs once per program. The
 * behaviour of each service is the subject of the scenarios of crux-controller; this test shows
 * that a product that imports the framework builds it and runs it. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <controller/framework.h>
#include <zephyr/device.h>
#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log_ctrl.h>
#include <zephyr/ztest.h>

#define LOG_UART DEVICE_DT_GET(DT_NODELABEL(logging_test))
#define CONSOLE_UART DEVICE_DT_GET(DT_NODELABEL(serial_test))
#define CONSOLE_POLL_MS 10
#define CONSOLE_ATTEMPTS 1000

static char log_text[8192];
static size_t log_length;

/* Everything that Crux Logging wrote since the last call, appended to what was read before. */
static const char *drain_log(void)
{
    log_flush();
    log_length += uart_emul_get_tx_data(LOG_UART, (uint8_t *)log_text + log_length,
                                        sizeof log_text - 1u - log_length);
    log_text[log_length] = '\0';
    return log_text;
}

ZTEST_SUITE(product, NULL, NULL, NULL, NULL, NULL);

ZTEST(product, test_01_the_imported_framework_starts_every_phase)
{
    zassert_equal(controller_framework_start(), CONTROLLER_FRAMEWORK_OK);
    const char *log = drain_log();

    zassert_not_null(strstr(log, "phase clock ok"), "%s", log);
    zassert_not_null(strstr(log, "phase web management ok"), "%s", log);
    zassert_not_null(strstr(log, "phase command line ok"), "%s", log);
    zassert_not_null(strstr(log, "phase time synchronisation ok"), "%s", log);
    zassert_not_null(strstr(log, "startup done phases=4 failed=0"), "%s", log);
}

ZTEST(product, test_02_a_second_start_is_refused)
{
    zassert_equal(controller_framework_start(), CONTROLLER_FRAMEWORK_ERR_ALREADY_STARTED);
}

ZTEST(product, test_03_the_serial_console_prompts_for_a_login)
{
    char text[64];
    size_t length = 0u;

    zassert_true(device_is_ready(CONSOLE_UART));
    for (int attempt = 0; attempt < CONSOLE_ATTEMPTS; attempt++) {
        length += uart_emul_get_tx_data(CONSOLE_UART, (uint8_t *)text + length,
                                        sizeof text - 1u - length);
        text[length] = '\0';
        if (strstr(text, "login: ") != NULL) {
            return;
        }
        k_msleep(CONSOLE_POLL_MS);
    }
    zassert_unreachable("the console did not prompt; it wrote \"%s\"", text);
}
