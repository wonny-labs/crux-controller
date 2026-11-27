/* SPDX-License-Identifier: Apache-2.0 */

/* The scenario of a refused TLS certificate start (specification section 4.1, known deviation, and
 * section 5.5, interim state): the TLS certificate start returns CRUX_TLS_CERTIFICATE_ERR_KEY_MISMATCH,
 * as Crux does for a stored certificate without its key. Only web management stays off: the
 * configuration and status services, the serial command line (the operator's recovery path), the
 * reboot thread and a start prerequisite on the configuration service behave as after a successful
 * start, and the application starts.
 *
 * The start is wrapped at link time (CMakeLists.txt), because no public Crux interface can store a
 * certificate of another key: the record writes are behind Crux's credential adapter.
 *
 * What this scenario cannot show: the real refusal inside Crux (the wrapper returns before the
 * module runs, so its state and its security event are not those of a real refusal), a board, or
 * an operator's later certificate installation. */

#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include <controller/framework.h>
#include <crux/tls_certificate_start.h>
#include <zephyr/kernel.h>
#include <zephyr/net/socket.h>

#include "fixture.h"
#include "scenario.h"

#define WAIT_STEP_MS 100
#define WAIT_STEPS 100
/* A listener opens on Zephyr's own thread, so a refused connect is tried again for a while. */
#define CONNECT_ATTEMPTS 20
#define CONNECT_RETRY_MS 100

#define FIRST_USER "operator"
#define FIRST_PASSWORD "tls scenario test password"

crux_tls_certificate_result_t
__wrap_crux_tls_certificate_start(const crux_tls_certificate_options_t *options,
                                  crux_tls_certificate_start_t *how);

static unsigned wrapped_starts;

/* The wrapped start: a stored certificate of another key. The real start is never called. */
crux_tls_certificate_result_t
__wrap_crux_tls_certificate_start(const crux_tls_certificate_options_t *options,
                                  crux_tls_certificate_start_t *how)
{
    (void)options;
    (void)how;
    wrapped_starts++;
    return CRUX_TLS_CERTIFICATE_ERR_KEY_MISMATCH;
}

static bool reboot_thread_found;

static void find_reboot_thread(const struct k_thread *thread, void *unused)
{
    (void)unused;
    const char *name = k_thread_name_get((k_tid_t)thread);

    if (name != NULL && strcmp(name, "reboot") == 0) {
        reboot_thread_found = true;
    }
}

static bool listener_answers(void)
{
    struct net_sockaddr_in address = {
        .sin_family = NET_AF_INET,
        .sin_port = net_htons(443),
    };

    if (zsock_inet_pton(NET_AF_INET, "127.0.0.1", &address.sin_addr) != 1) {
        return true;
    }
    for (int attempt = 0; attempt < CONNECT_ATTEMPTS; attempt++) {
        const int sock = zsock_socket(NET_AF_INET, NET_SOCK_STREAM, NET_IPPROTO_TCP);

        if (sock < 0) {
            return true;
        }
        const bool connected =
            zsock_connect(sock, (const struct net_sockaddr *)&address, sizeof address) == 0;

        (void)zsock_close(sock);
        if (connected) {
            return true;
        }
        k_msleep(CONNECT_RETRY_MS);
    }
    return false;
}

static bool healthy(controller_framework_service_t service)
{
    return fixture_health(service) == CONTROLLER_FRAMEWORK_HEALTH_HEALTHY;
}

static bool console_makes_first_account(void)
{
    if (!scenario_console_expect("login: ")) {
        return false;
    }
    scenario_console_type("!setup");
    if (!scenario_console_expect("new user: ")) {
        return false;
    }
    scenario_console_type(FIRST_USER);
    if (!scenario_console_expect("password: ")) {
        return false;
    }
    scenario_console_type(FIRST_PASSWORD);
    if (!scenario_console_expect("repeat: ")) {
        return false;
    }
    scenario_console_type(FIRST_PASSWORD);
    return scenario_console_expect("account created") && scenario_console_expect("login: ");
}

/* The status service's items come in a fixed order: the controller state, then the health of each
 * service in the order of controller_framework_service_t. */
static bool status_shows_web_failed(void)
{
    static const char *const expected[] = {
        "{\"name\":\"controller.state\",\"status\":\"ok\",\"type\":\"text\","
        "\"value\":\"operational\"}",
        "{\"name\":\"controller.health.configuration\",\"status\":\"ok\",\"type\":\"text\","
        "\"value\":\"healthy\"}",
        "{\"name\":\"controller.health.status\",\"status\":\"ok\",\"type\":\"text\","
        "\"value\":\"healthy\"}",
        "{\"name\":\"controller.health.web\",\"status\":\"ok\",\"type\":\"text\","
        "\"value\":\"failed\"}",
        "{\"name\":\"controller.health.command-line\",\"status\":\"ok\",\"type\":\"text\","
        "\"value\":\"healthy\"}",
    };

    scenario_console_type(FIRST_USER);
    if (!scenario_console_expect("password: ")) {
        return false;
    }
    scenario_console_type(FIRST_PASSWORD);
    if (!scenario_console_expect("> ")) {
        return false;
    }
    scenario_console_type("status");
    for (size_t index = 0; index < sizeof expected / sizeof expected[0]; index++) {
        if (!scenario_console_expect(expected[index])) {
            return false;
        }
    }
    if (!scenario_console_expect("> ")) {
        return false;
    }
    scenario_console_type("logout");
    return scenario_console_expect("login: ");
}

static void check(bool passed, const char *what)
{
    char text[128];

    (void)snprintf(text, sizeof text, "tls scenario%s %s", passed ? ":" : " FAILED:", what);
    scenario_say(text);
}

int main(void)
{
    scenario_forward_log();
    scenario_say("tls scenario start");
    if (controller_framework_start(fixture_descriptor(FIXTURE_NORMAL)) != CONTROLLER_FRAMEWORK_OK) {
        scenario_say("tls scenario FAILED: the start function");
        return 0;
    }
    bool running = false;

    for (int step = 0; step < WAIT_STEPS && !running; step++) {
        running = fixture_controller_state() == CONTROLLER_FRAMEWORK_STATE_OPERATIONAL &&
                  fixture_starts() == 1u;
        k_msleep(WAIT_STEP_MS);
    }
    check(wrapped_starts == 1u, "the wrapped start ran once");
    check(healthy(CONTROLLER_FRAMEWORK_SERVICE_STORAGE) &&
              healthy(CONTROLLER_FRAMEWORK_SERVICE_ACCESS) &&
              healthy(CONTROLLER_FRAMEWORK_SERVICE_CONFIGURATION) &&
              healthy(CONTROLLER_FRAMEWORK_SERVICE_STATUS) &&
              healthy(CONTROLLER_FRAMEWORK_SERVICE_COMMAND_LINE) &&
              fixture_health(CONTROLLER_FRAMEWORK_SERVICE_WEB) == CONTROLLER_FRAMEWORK_HEALTH_FAILED,
          "configuration, status and command line healthy, web failed");
    k_thread_foreach(find_reboot_thread, NULL);
    check(reboot_thread_found, "the reboot thread runs");
    check(!listener_answers(), "no listener on port 443");
    check(running && fixture_inits() == 1u, "controller operational, application running");
    check(console_makes_first_account(), "the console made the first account");
    check(status_shows_web_failed(), "the status command shows web failed and the others healthy");
    scenario_say("tls scenario done");
    for (;;) {
        k_sleep(K_FOREVER);
    }
    return 0;
}
