/* SPDX-License-Identifier: Apache-2.0 */

/* The base image on native_sim for a person at the host (docs/native-sim-interactive.md): main
 * starts the controller framework as the base image does, and a bridge thread connects the Crux
 * serial console to a pseudo-terminal of the host.
 *
 * The bridge exists because Crux Serial accepts only an emulated UART on native_sim (the
 * BUILD_ASSERT in components/serial/ports/zephyr/serial_binding.c at the pinned Crux), while a
 * person needs a pseudo-terminal. It copies what the person types on the PTY UART uart1 into the
 * receive side of the emulated UART, and what the console writes on the emulated UART to uart1. It
 * polls both, because the PTY UART reads without blocking. Development only: a board image has no
 * bridge, and the console owns its UART there. */

#include <stddef.h>
#include <stdint.h>

#include <controller/framework.h>
#include <zephyr/device.h>
#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#define CONSOLE_EMUL DEVICE_DT_GET(DT_ALIAS(crux_serial0))
#define CONSOLE_PTY DEVICE_DT_GET(DT_NODELABEL(uart1))
#define BRIDGE_POLL_MS 5
#define BRIDGE_CHUNK 64u
#define BRIDGE_STACK 2048
/* Below the console (CONFIG_CRUX_CLI_CONSOLE_PRIORITY) and the web workers, above the log. */
#define BRIDGE_PRIORITY 13

/* Typed bytes into the emulated UART. A full receive FIFO is retried, so a paste is kept. */
static void bridge_typed(void)
{
    uint8_t chunk[BRIDGE_CHUNK];
    unsigned char byte;
    size_t length = 0u;

    while (length < sizeof chunk && uart_poll_in(CONSOLE_PTY, &byte) == 0) {
        chunk[length++] = byte;
    }
    for (size_t done = 0u; done < length;) {
        done += uart_emul_put_rx_data(CONSOLE_EMUL, &chunk[done], length - done);
        if (done < length) {
            k_msleep(BRIDGE_POLL_MS);
        }
    }
}

/* The console's output to the pseudo-terminal. */
static void bridge_written(void)
{
    uint8_t chunk[BRIDGE_CHUNK];
    uint32_t got;

    while ((got = uart_emul_get_tx_data(CONSOLE_EMUL, chunk, sizeof chunk)) > 0u) {
        for (uint32_t i = 0u; i < got; i++) {
            uart_poll_out(CONSOLE_PTY, chunk[i]);
        }
    }
}

static void bridge_run(void *unused1, void *unused2, void *unused3)
{
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    ARG_UNUSED(unused3);

    if (!device_is_ready(CONSOLE_EMUL) || !device_is_ready(CONSOLE_PTY)) {
        printk("console bridge: a UART is not ready\n");
        return;
    }
    for (;;) {
        bridge_typed();
        bridge_written();
        k_msleep(BRIDGE_POLL_MS);
    }
}

K_THREAD_DEFINE(console_bridge, BRIDGE_STACK, bridge_run, NULL, NULL, NULL, BRIDGE_PRIORITY, 0, 0);

int main(void)
{
    return controller_framework_start(NULL) == CONTROLLER_FRAMEWORK_OK ? 0 : -1;
}
