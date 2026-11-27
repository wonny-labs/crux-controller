/* SPDX-License-Identifier: Apache-2.0 */

#include "scenario.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <nsi_host_trampolines.h>
#include <zephyr/device.h>
#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log_ctrl.h>
#include <zephyr/sys/printk.h>

#define BOOT_ENV "CONTROLLER_TEST_BOOT"
#define LOG_UART DEVICE_DT_GET(DT_NODELABEL(logging_test))
#define FORWARD_PRIORITY 2
#define FORWARD_PERIOD_MS 5
#define CONSOLE_POLL_MS 10
#define CONSOLE_ATTEMPTS 3000

static K_THREAD_STACK_DEFINE(forward_stack, 2048);
static struct k_thread forward_thread;
static K_MUTEX_DEFINE(print_lock);

int scenario_boot_number(void)
{
    const char *stored = nsi_host_getenv(BOOT_ENV);
    const int number = (stored != NULL ? atoi(stored) : 0) + 1;
    char text[16];

    (void)snprintf(text, sizeof text, "%d", number);
    (void)nsi_host_setenv(BOOT_ENV, text, 1);
    return number;
}

static void forward_once(void)
{
    uint8_t chunk[128];
    uint32_t got;

    while ((got = uart_emul_get_tx_data(LOG_UART, chunk, sizeof chunk - 1u)) > 0u) {
        chunk[got] = '\0';
        printk("%s", (const char *)chunk);
    }
}

static void forward_run(void *unused0, void *unused1, void *unused2)
{
    ARG_UNUSED(unused0);
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    for (;;) {
        (void)k_mutex_lock(&print_lock, K_FOREVER);
        forward_once();
        (void)k_mutex_unlock(&print_lock);
        k_msleep(FORWARD_PERIOD_MS);
    }
}

void scenario_forward_log(void)
{
    (void)k_thread_create(&forward_thread, forward_stack, K_THREAD_STACK_SIZEOF(forward_stack),
                          forward_run, NULL, NULL, NULL, K_PRIO_PREEMPT(FORWARD_PRIORITY), 0,
                          K_NO_WAIT);
}

void scenario_say(const char *text)
{
    log_flush();
    (void)k_mutex_lock(&print_lock, K_FOREVER);
    forward_once();
    printk("\n%s\n", text);
    (void)k_mutex_unlock(&print_lock);
}

#if DT_NODE_EXISTS(DT_NODELABEL(serial_test))
#define CONSOLE_UART DEVICE_DT_GET(DT_NODELABEL(serial_test))

static char console_text[8192];
static size_t console_length;

static void console_drain(void)
{
    uint8_t chunk[64];
    uint32_t got;

    while ((got = uart_emul_get_tx_data(CONSOLE_UART, chunk, sizeof chunk)) > 0u) {
        if (console_length + got >= sizeof console_text) {
            /* Keep the newest text: drop the oldest half. */
            const size_t keep = console_length / 2u;

            memmove(console_text, &console_text[console_length - keep], keep);
            console_length = keep;
        }
        memcpy(&console_text[console_length], chunk, got);
        console_length += got;
        console_text[console_length] = '\0';
    }
}

bool scenario_console_expect(const char *text)
{
    const size_t length = strlen(text);

    for (int attempt = 0; attempt < CONSOLE_ATTEMPTS; attempt++) {
        console_drain();
        const char *found = strstr(console_text, text);

        if (found != NULL) {
            const size_t consumed = (size_t)(found - console_text) + length;

            memmove(console_text, &console_text[consumed], console_length - consumed + 1u);
            console_length -= consumed;
            return true;
        }
        k_msleep(CONSOLE_POLL_MS);
    }
    return false;
}

void scenario_console_type(const char *text)
{
    char line[96];
    const size_t length = strlen(text);

    if (length + 1u >= sizeof line) {
        return;
    }
    /* The bytes go to the UART with a carriage return and no terminator. */
    // NOLINTNEXTLINE(bugprone-not-null-terminated-result)
    memcpy(line, text, length);
    line[length] = '\r';
    (void)uart_emul_put_rx_data(CONSOLE_UART, (const uint8_t *)line, length + 1u);
}
#else
bool scenario_console_expect(const char *text)
{
    ARG_UNUSED(text);
    return false;
}

void scenario_console_type(const char *text)
{
    ARG_UNUSED(text);
}
#endif
