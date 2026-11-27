/* SPDX-License-Identifier: Apache-2.0 */

/* The base composition of the controller framework on native_sim, built as a product builds it:
 * the framework comes from the Zephyr module of this repository and the Kconfig symbol
 * CONFIG_CRUX_CONTROLLER_FRAMEWORK, the test calls the start function of
 * <controller/framework.h>, and the CMake file of this scenario names no source or include
 * directory of this repository. It runs the real Crux services, Zephyr's HTTP server with Mbed TLS
 * and the SNTP library over the loopback interface, and the Crux serial console on an emulated
 * UART, into which the test types as a person types at a terminal.
 *
 * One image runs the cases in order, because the start function runs once per program.
 *
 * Health supervision runs in its production watchdog configuration with no watchdog behind the
 * alias crux-watchdog0, so the watchdog is not armed and the controller is degraded (criterion 19,
 * base image part), and the scenario shows the start order of criterion 6: the reset cause read
 * once and cleared, the supervisor step before the step that mounts the volume, the captured copy
 * in the status service, and the end of startup supervision in step 12 with no application.
 *
 * What this scenario cannot show: anything on a board, the Ethernet interface, the board's UART for
 * the console, the RT1060 entropy source (the entropy here is the simulator's test source), a TLS
 * session or an HTTPS login (the management scenario shows those for the same start sequence), an
 * account that outlives a restart (the disk is a RAM disk), a synchronised clock (no SNTP server
 * answers on the loopback address), an armed watchdog, a retained region or a reset (the scenarios
 * recovery and no_watchdog show those), stack use or timing. */

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
#define CONSOLE_UART DEVICE_DT_GET(DT_NODELABEL(serial_test))
/* The listener opens on Zephyr's own thread, so the first connects can be refused. */
#define CONNECT_ATTEMPTS 40
#define CONNECT_RETRY_MS 100
/* The console polls in steps of this length, up to the number of attempts. */
#define CONSOLE_POLL_MS 10
#define CONSOLE_ATTEMPTS 1000

#define FIRST_USER "operator"
#define FIRST_PASSWORD "base image test password"
#define WRONG_PASSWORD "this is the wrong password"
/* The first eight bytes of each, which no prompt or reply of the console contains. */
#define FIRST_PASSWORD_START "base ima"
#define WRONG_PASSWORD_START "this is "

static char log_text[16384];
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

/* What the console has written and no expectation has consumed yet. */
static char console_text[8192];
static size_t console_length;

static void console_drain(void)
{
    uint8_t chunk[64];
    uint32_t got;

    while ((got = uart_emul_get_tx_data(CONSOLE_UART, chunk, sizeof chunk)) > 0u) {
        zassert_true(console_length + got < sizeof console_text, "the console wrote too much");
        memcpy(&console_text[console_length], chunk, got);
        console_length += got;
        console_text[console_length] = '\0';
        /* A password is read without echo: neither a whole one nor its first bytes come back. */
        zassert_is_null(strstr(console_text, FIRST_PASSWORD_START), "a password was echoed");
        zassert_is_null(strstr(console_text, WRONG_PASSWORD_START), "a password was echoed");
    }
}

/* Wait for the console to write text, then drop everything up to and including it. With first,
 * nothing may come before it. */
static void console_expect(const char *text, bool first)
{
    const size_t length = strlen(text);

    for (int attempt = 0; attempt < CONSOLE_ATTEMPTS; attempt++) {
        console_drain();
        const char *found = strstr(console_text, text);

        if (first && console_length >= length) {
            zassert_equal(strncmp(console_text, text, length), 0, "first output: %s", console_text);
        }
        if (found != NULL) {
            const size_t consumed = (size_t)(found - console_text) + length;

            memmove(console_text, &console_text[consumed], console_length - consumed + 1u);
            console_length -= consumed;
            return;
        }
        k_msleep(CONSOLE_POLL_MS);
    }
    zassert_unreachable("the console did not write \"%s\"; it wrote \"%s\"", text, console_text);
}

/* Type a line as a terminal does: the bytes and a carriage return. */
static void console_type(const char *text)
{
    char line[96];
    const size_t length = strlen(text);

    zassert_true(length + 1u < sizeof line);
    memcpy(line, text, length);
    line[length] = '\r';
    zassert_equal(uart_emul_put_rx_data(CONSOLE_UART, (const uint8_t *)line, length + 1u),
                  length + 1u);
}

ZTEST_SUITE(base, NULL, NULL, NULL, NULL, NULL);

ZTEST(base, test_01_start_runs_every_phase)
{
    zassert_equal(controller_framework_start(), CONTROLLER_FRAMEWORK_OK);
    const char *log = drain_log();

    zassert_not_null(strstr(log, "phase clock ok"), "%s", log);
    zassert_not_null(strstr(log, "phase supervisor ok"), "%s", log);
    zassert_not_null(strstr(log, "phase web management ok"), "%s", log);
    zassert_not_null(strstr(log, "phase command line ok"), "%s", log);
    zassert_not_null(strstr(log, "phase time synchronisation ok"), "%s", log);
    zassert_not_null(strstr(log, "phase application ok"), "%s", log);
    zassert_not_null(strstr(log, "startup done phases=6 failed=0"), "%s", log);
}

ZTEST(base, test_02_phases_run_in_order)
{
    const char *log = drain_log();
    const char *clock = strstr(log, "phase clock ok");
    const char *supervisor = strstr(log, "phase supervisor ok");
    const char *web = strstr(log, "phase web management ok");
    const char *cli = strstr(log, "phase command line ok");
    const char *time = strstr(log, "phase time synchronisation ok");
    const char *application = strstr(log, "phase application ok");

    zassert_true(clock != NULL && supervisor != NULL && web != NULL && cli != NULL &&
                     time != NULL && application != NULL,
                 "%s", log);
    zassert_true(clock < supervisor && supervisor < web && web < cli && cli < time &&
                     time < application,
                 "%s", log);
    zassert_not_null(strstr(log, "https management started on 127.0.0.1 port 443"), "%s", log);
    zassert_not_null(strstr(log, "serial command line started on crux-serial0"), "%s", log);
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

/* A new image has no account: the console prints its login prompt and nothing before it, and a
 * login is refused. */
ZTEST(base, test_05_the_console_prompts_first_and_refuses_a_login_without_accounts)
{
    zassert_true(device_is_ready(CONSOLE_UART));
    console_expect("login: ", true);
    console_type(FIRST_USER);
    console_expect("password: ", false);
    console_type(WRONG_PASSWORD);
    console_expect("login failed", false);
    console_expect("login: ", false);
}

/* The first account is made over the serial command line, from typed input. */
ZTEST(base, test_06_setup_creates_the_first_account)
{
    console_type("!setup");
    console_expect("new user: ", false);
    console_type(FIRST_USER);
    console_expect("password: ", false);
    console_type(FIRST_PASSWORD);
    console_expect("repeat: ", false);
    console_type(FIRST_PASSWORD);
    console_expect("account created", false);
    console_expect("login: ", false);
}

/* Setup is refused once an account exists. */
ZTEST(base, test_07_a_second_setup_is_refused)
{
    console_type("!setup");
    console_expect("new user: ", false);
    console_type("second");
    console_expect("password: ", false);
    console_type(FIRST_PASSWORD);
    console_expect("repeat: ", false);
    console_type(FIRST_PASSWORD);
    console_expect("setup not available", false);
    console_expect("login: ", false);
}

/* The first account logs in, runs a command and logs out. */
ZTEST(base, test_08_the_first_account_logs_in_and_runs_a_command)
{
    console_type(FIRST_USER);
    console_expect("password: ", false);
    console_type(FIRST_PASSWORD);
    console_expect("> ", false);
    console_type("help");
    console_expect("logout", false);
    console_expect("> ", false);
    console_type("logout");
    console_expect("login: ", false);
}

/* Criterion 6, base image part: the reset cause is read once in step 1 and the flags cleared after
 * the capture; the supervisor step, which arms the watchdog, ends before the step that mounts the
 * volume begins; and startup supervision ends in step 12 with no application. This scenario has no
 * watchdog; the scenario recovery (testcase.yaml) shows "watchdog armed" before the management step
 * with the simulated watchdog. */
ZTEST(base, test_09_the_start_order_of_supervision)
{
    const char *log = drain_log();
    const char *capture = strstr(log, "reset cause=0x001 supported=0x005 captured, flags cleared");
    const char *boot = strstr(log, "boot class=power counter=0 threshold=3 safe mode=no "
                                   "no retained region");
    const char *watchdog = strstr(log, "watchdog not armed");
    const char *supervisor = strstr(log, "phase supervisor ok");
    const char *web = strstr(log, "https management started");
    const char *ended = strstr(log, "startup supervision ended in step 12 with no application");

    zassert_true(capture != NULL && boot != NULL && watchdog != NULL && supervisor != NULL &&
                     web != NULL && ended != NULL,
                 "%s", log);
    zassert_true(capture < boot && boot < watchdog && watchdog < supervisor && supervisor < web &&
                     web < ended,
                 "%s", log);
    /* Read once: one capture line. */
    zassert_is_null(strstr(capture + 1, "captured, flags"), "%s", log);
}

/* Criterion 19, base image part: with the production watchdog configuration and no watchdog, the
 * controller is degraded once startup supervision has ended. */
ZTEST(base, test_10_a_watchdog_that_is_not_armed_degrades_the_controller)
{
    const char *log = NULL;

    for (int attempt = 0; attempt < 50; attempt++) {
        k_msleep(100);
        log = drain_log();
        if (strstr(log, "controller state=degraded") != NULL) {
            break;
        }
    }
    zassert_not_null(strstr(log, "controller state=degraded"), "%s", log);
    zassert_is_null(strstr(log, "controller state=operational"), "%s", log);
}

/* The status service shows the copy of the reset cause that step 1 captured (POR, although the
 * flags were cleared after the capture) and the framework's items, through the status command of
 * the serial command line. */
ZTEST(base, test_11_the_status_command_shows_the_captured_cause_and_the_framework_items)
{
    console_type(FIRST_USER);
    console_expect("password: ", false);
    console_type(FIRST_PASSWORD);
    console_expect("> ", false);
    console_type("status");
    console_expect("{\"name\":\"reset.causes\",\"status\":\"ok\",\"type\":\"u32\",\"value\":1}",
                   false);
    console_expect("{\"name\":\"controller.state\",\"status\":\"ok\",\"type\":\"text\","
                   "\"value\":\"degraded\"}",
                   false);
    console_expect("{\"name\":\"controller.application\",\"status\":\"ok\",\"type\":\"text\","
                   "\"value\":\"absent\"}",
                   false);
    console_expect("{\"name\":\"controller.safe_mode\",\"status\":\"ok\",\"type\":\"bool\","
                   "\"value\":false}",
                   false);
    console_expect("{\"name\":\"controller.boot_counter\",\"status\":\"ok\",\"type\":\"u32\","
                   "\"value\":0}",
                   false);
    console_expect("{\"name\":\"controller.boot\",\"status\":\"ok\",\"type\":\"text\","
                   "\"value\":\"power\"}",
                   false);
    console_expect("{\"name\":\"controller.watchdog\",\"status\":\"ok\",\"type\":\"text\","
                   "\"value\":\"not-armed\"}",
                   false);
    console_expect("{\"name\":\"controller.last_fault\",\"status\":\"ok\",\"type\":\"text\","
                   "\"value\":\"none\"}",
                   false);
    console_expect("{\"name\":\"controller.stack_min\",\"status\":\"ok\",\"type\":\"text\"", false);
    console_expect("> ", false);
    console_type("logout");
    console_expect("login: ", false);
}
