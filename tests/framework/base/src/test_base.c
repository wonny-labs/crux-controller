/* SPDX-License-Identifier: Apache-2.0 */

/* The base composition of the controller framework on native_sim, built as a product builds it:
 * the framework comes from the Zephyr module of this repository and the Kconfig symbol
 * CONFIG_CRUX_CONTROLLER_FRAMEWORK, the test calls the start function of
 * <controller/framework.h>, and the CMake file of this scenario names no source or include
 * directory of this repository. It runs the real Crux services, Zephyr's HTTP server with Mbed TLS
 * and the SNTP library over the loopback interface.
 *
 * One image runs the cases in order, because the start function runs once per program.
 *
 * What this scenario cannot show: anything on a board, the Ethernet interface, the RT1060 entropy
 * source (the entropy here is the simulator's test source), a TLS session or a login (the
 * management scenario shows those for the same start sequence), a synchronised clock (no SNTP
 * server answers on the loopback address), stack use or timing. */

#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <controller/framework.h>
#include <zephyr/device.h>
#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log_ctrl.h>
#include <zephyr/net/socket.h>
#include <zephyr/ztest.h>

#define LOG_UART DEVICE_DT_GET(DT_NODELABEL(logging_test))
/* The listener opens on Zephyr's own thread, so the first connects can be refused. */
#define CONNECT_ATTEMPTS 40
#define CONNECT_RETRY_MS 100

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

ZTEST_SUITE(base, NULL, NULL, NULL, NULL, NULL);

ZTEST(base, test_01_start_runs_every_phase)
{
    zassert_equal(controller_framework_start(), CONTROLLER_FRAMEWORK_OK);
    const char *log = drain_log();

    zassert_not_null(strstr(log, "phase clock ok"), "%s", log);
    zassert_not_null(strstr(log, "phase web management ok"), "%s", log);
    zassert_not_null(strstr(log, "phase time synchronisation ok"), "%s", log);
    zassert_not_null(strstr(log, "startup done phases=3 failed=0"), "%s", log);
}

ZTEST(base, test_02_phases_run_in_order)
{
    const char *log = drain_log();
    const char *clock = strstr(log, "phase clock ok");
    const char *web = strstr(log, "phase web management ok");
    const char *time = strstr(log, "phase time synchronisation ok");

    zassert_true(clock != NULL && web != NULL && time != NULL, "%s", log);
    zassert_true(clock < web && web < time, "%s", log);
    zassert_not_null(strstr(log, "https management started on 127.0.0.1 port 443"), "%s", log);
}

ZTEST(base, test_03_a_second_start_is_refused)
{
    zassert_equal(controller_framework_start(), CONTROLLER_FRAMEWORK_ERR_ALREADY_STARTED);
}

ZTEST(base, test_04_the_listener_accepts_a_connection)
{
    struct net_sockaddr_in address = {
        .sin_family = NET_AF_INET,
        .sin_port = net_htons(443),
    };
    int last_errno = 0;
    bool connected = false;

    zassert_equal(zsock_inet_pton(NET_AF_INET, "127.0.0.1", &address.sin_addr), 1);
    for (int attempt = 0; attempt < CONNECT_ATTEMPTS && !connected; attempt++) {
        const int sock = zsock_socket(NET_AF_INET, NET_SOCK_STREAM, NET_IPPROTO_TCP);

        zassert_true(sock >= 0, "no socket (errno %d)", errno);
        if (zsock_connect(sock, (const struct net_sockaddr *)&address, sizeof address) == 0) {
            connected = true;
        } else {
            last_errno = errno;
            k_msleep(CONNECT_RETRY_MS);
        }
        (void)zsock_close(sock);
    }
    zassert_true(connected, "no connection to the listener (errno %d)", last_errno);
}
