/* SPDX-License-Identifier: Apache-2.0 */

#include <stdio.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/kernel.h>
#include <zephyr/ztest.h>

#include "workload.h"
#include "workload_thread.h"

#define LOG_UART DEVICE_DT_GET(DT_NODELABEL(logging_test))

static char captured[4096];

ZTEST(s1, test_the_workload_logs_one_line_per_message)
{
    const workload_config_t config = {.period_ms = 10, .message_every = 1};
    size_t length;

    zassert_true(device_is_ready(LOG_UART));
    zassert_equal(0, workload_thread_start(&config));
    k_msleep(150);
    zassert_equal(0, workload_thread_stop());
    k_msleep(200); /* let the deferred log thread drain */

    length = uart_emul_get_tx_data(LOG_UART, (uint8_t *)captured, sizeof captured - 1);
    captured[length] = '\0';

    /* At least three consecutive messages, each carrying the value that its cycle implies. */
    uint32_t expected_cycle = 0;
    unsigned int found = 0;

    for (const char *line = strstr(captured, "workload: cycle="); line != NULL;
         line = strstr(line + 1, "workload: cycle=")) {
        unsigned int cycle;
        unsigned int value;

        zassert_equal(2, sscanf(line, "workload: cycle=%u value=%u", &cycle, &value),
                      "unparsable line: %.60s", line);
        zassert_equal(WORKLOAD_VALUE_OF(cycle), value);
        if (found > 0) {
            zassert_equal(expected_cycle + 1, cycle, "cycles are not consecutive");
        }
        expected_cycle = cycle;
        found++;
    }
    zassert_true(found >= 3, "only %u workload lines in: %s", found, captured);
}

ZTEST_SUITE(s1, NULL, NULL, NULL, NULL, NULL);
