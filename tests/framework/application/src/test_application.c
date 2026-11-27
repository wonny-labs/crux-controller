/* SPDX-License-Identifier: Apache-2.0 */

/* The application scenario of the controller framework on native_sim (specification sections 3 and
 * 4, delivery stage 3). One run, nine boots of the fixture application (../fixture): the simulated
 * watchdog of Crux System restarts the simulated process after a missed feed, Crux Reboot restarts
 * it on the reboot command, and the retained region over the test-only retained memory of ../common
 * survives both. Each boot picks the fixture's behaviour, starts the framework with the fixture's
 * descriptor and prints what the console harness of testcase.yaml matches, in order:
 *
 *   1. The contract (criteria 4, 5, 6, 21, 23, 8 and 34): a descriptor without an entry and a
 * second start are refused; init, the start prerequisites, then start, last in startup; the status
 * item and the parameter in device management; every route answers 401 without a session except the
 *      public ones; an operator stop and start; a runtime dependency that fails and recovers; a
 *      reported fault; then the reboot command.
 *   2. stop returns an error: the supervisor stops feeding, calls safe_state, and the image
 * restarts (criterion 8).
 *   3. The worker stops feeding its channel: the expiry is recorded and the image restarts
 *      (criterion 9).
 *   4. start passes its deadline: the record names the step and the image restarts (criterion 20).
 *   5. stop passes its deadline: the image restarts (criterion 21).
 *   6. init fails after its registrations: fault, safe_state, the registrations released, the
 *      controller operational, device management answers (criterion 8).
 *   7. The activation of the second channel is refused, and
 *   8. start returns an error: the activated channels are deleted, fault, safe_state, the
 * controller operational, device management answers (criterion 22).
 *   9. A start prerequisite fails at boot: the application is held and the controller degraded;
 * after the service recovers, an operator start runs it (criterion 23); then the reboot command,
 * which stops the running application with the reason planned reset before the reset (section 3.3).
 *  10. A normal boot after the planned reset.
 *
 * The safe-mode threshold is above the four fault resets of the run, so no boot enters safe mode.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <controller/framework.h>
#include <controller/framework_test.h>
#include <crux/web.h>
#include <zephyr/kernel.h>

#include "fixture.h"
#include "https.h"
#include "scenario.h"

#define USER "operator"
#define PASSWORD "application scenario password"
#define WAIT_STEP_MS 100
#define WAIT_STEPS 100

/* The route table that Crux generates for the image (crux_web_routes() of
 * framework/management/management.cmake). */
extern const crux_web_route_t *const crux_web_route_table[];
extern const size_t crux_web_route_count;

static char response[8192];

static void fail(const char *what)
{
    char text[160];

    (void)snprintf(text, sizeof text, "application scenario FAILED: %s", what);
    scenario_say(text);
}

static void say(const char *what)
{
    char text[160];

    (void)snprintf(text, sizeof text, "application scenario: %s", what);
    scenario_say(text);
}

static bool expect(const char *text)
{
    if (!scenario_console_expect(text)) {
        fail(text);
        return false;
    }
    return true;
}

/* Make the first account on the serial command line and log in with it. */
static bool account_and_login(void)
{
    if (!expect("login: ")) {
        return false;
    }
    scenario_console_type("!setup");
    if (!expect("new user: ")) {
        return false;
    }
    scenario_console_type(USER);
    if (!expect("password: ")) {
        return false;
    }
    scenario_console_type(PASSWORD);
    if (!expect("repeat: ")) {
        return false;
    }
    scenario_console_type(PASSWORD);
    if (!expect("account created") || !expect("login: ")) {
        return false;
    }
    scenario_console_type(USER);
    if (!expect("password: ")) {
        return false;
    }
    scenario_console_type(PASSWORD);
    return expect("> ");
}

/* A command whose output holds reply, and the prompt after it. */
static bool command(const char *line, const char *reply)
{
    scenario_console_type(line);
    return expect(reply) && expect("> ");
}

static bool controller_is(controller_framework_state_t state)
{
    for (int step = 0; step < WAIT_STEPS; step++) {
        if (fixture_controller_state() == state) {
            return true;
        }
        k_msleep(WAIT_STEP_MS);
    }
    return false;
}

static bool count_reaches(unsigned (*count)(void), unsigned value)
{
    for (int step = 0; step < WAIT_STEPS; step++) {
        if (count() >= value) {
            return true;
        }
        k_msleep(WAIT_STEP_MS);
    }
    return false;
}

static bool worker_counts(void)
{
    const uint32_t before = fixture_counter();

    k_msleep(500);
    return fixture_counter() > before;
}

/* A public route is the login, its attempt result or a static sign-in asset (a fixed GET path
 * outside /api), and nothing else (section 6.2). */
static bool public_route_allowed(const crux_web_route_t *route)
{
    if (strcmp(route->path, "/api/v1/session") == 0) {
        return route->methods == CRUX_WEB_POST;
    }
    if (strcmp(route->path, "/api/v1/session/attempt/{id}") == 0) {
        return route->methods == CRUX_WEB_GET;
    }
    return strncmp(route->path, "/api", 4) != 0 && strchr(route->path, '{') == NULL &&
           route->methods == CRUX_WEB_GET;
}

/* The route's path with each parameter segment replaced by a word. */
static void concrete_path(const char *pattern, char *path, size_t capacity)
{
    size_t used = 0u;

    for (const char *at = pattern; *at != '\0' && used + 1u < capacity; at++) {
        if (*at == '{') {
            const char *end = strchr(at, '}');

            if (end == NULL) {
                break;
            }
            for (const char *word = "x0"; *word != '\0' && used + 1u < capacity; word++) {
                path[used++] = *word;
            }
            at = end;
        } else {
            path[used++] = *at;
        }
    }
    path[used] = '\0';
}

static const char *const method_names[] = {"GET", "POST", "PUT", "DELETE", "PATCH"};

/* Criterion 34, delivery stage 3: a request without a session to every route of the generated
 * table. Each route whose access class is not @public answers 401; the @public ones are only the
 * login, its attempt result and static sign-in assets, and they are not sent, so no login attempt
 * starts. */
static bool route_sweep(void)
{
    unsigned refused = 0u;
    unsigned publics = 0u;
    char path[128];
    char text[160];

    for (size_t index = 0; index < crux_web_route_count; index++) {
        const crux_web_route_t *route = crux_web_route_table[index];

        if (strcmp(route->access, CRUX_WEB_PUBLIC) == 0) {
            publics++;
            if (!public_route_allowed(route)) {
                (void)snprintf(text, sizeof text, "a public route that is not allowed: %s",
                               route->path);
                fail(text);
                return false;
            }
            continue;
        }
        concrete_path(route->path, path, sizeof path);
        for (unsigned bit = 0; bit < 5u; bit++) {
            if ((route->methods & (1u << bit)) == 0u) {
                continue;
            }
            const int status = https_request(method_names[bit], path, "X-Crux-Request: 1\r\n", NULL,
                                             response, sizeof response);

            if (status != 401) {
                (void)snprintf(text, sizeof text, "%s %s without a session answered %d",
                               method_names[bit], path, status);
                fail(text);
                return false;
            }
            refused++;
        }
    }
    (void)snprintf(text, sizeof text, "route sweep routes=%u refused=%u public=%u",
                   (unsigned)crux_web_route_count, refused, publics);
    say(text);
    return refused > 0u && publics > 0u;
}

/* The parameter of the fixture in device management, through the configuration route. */
static bool parameter_shown(void)
{
    char cookie[512];
    char headers[600];

    if (https_login(USER, PASSWORD, cookie, sizeof cookie) != 0) {
        fail("the web login");
        return false;
    }
    (void)snprintf(headers, sizeof headers, "%sX-Crux-Request: 1\r\n", cookie);
    const int status = https_request("GET", "/api/v1/config/fixture.period", headers, NULL,
                                     response, sizeof response);

    if (status != 200 || strstr(response, "fixture.period") == NULL) {
        fail("the parameter route");
        return false;
    }
    return true;
}

static void boot_contract(void)
{
    if (controller_framework_start(fixture_incomplete_descriptor()) ==
        CONTROLLER_FRAMEWORK_ERR_INVALID_DESCRIPTOR) {
        say("a descriptor without safe_state is refused");
    }
    if (controller_framework_start(fixture_descriptor(FIXTURE_NORMAL)) != CONTROLLER_FRAMEWORK_OK) {
        fail("the start function");
        return;
    }
    if (controller_framework_start(fixture_descriptor(FIXTURE_NORMAL)) ==
        CONTROLLER_FRAMEWORK_ERR_ALREADY_STARTED) {
        say("a second start is refused");
    }
    if (!controller_is(CONTROLLER_FRAMEWORK_STATE_OPERATIONAL) || !worker_counts()) {
        fail("an operational controller with a running application");
        return;
    }
    say("controller operational, application running");
    if (!account_and_login() ||
        !command("status", "{\"name\":\"fixture.counter\",\"status\":\"ok\",\"type\":\"u32\"")) {
        return;
    }
    say("the status service shows fixture.counter");
    if (!parameter_shown()) {
        return;
    }
    say("the configuration service shows fixture.period");
    if (!route_sweep()) {
        return;
    }

    /* Criterion 21: an operator stop, then an operator start without init. */
    if (!command("application stop", "application stop requested") ||
        !count_reaches(fixture_stops, 1u) || !count_reaches(fixture_safe_states, 1u)) {
        return;
    }
    k_msleep(1500);
    if (fixture_controller_state() != CONTROLLER_FRAMEWORK_STATE_OPERATIONAL) {
        fail("the controller after the operator stop");
        return;
    }
    say("operator stop: stop, then safe state, controller operational");
    if (!command("application start", "application start requested") ||
        !count_reaches(fixture_starts, 2u) || fixture_inits() != 1u || !worker_counts()) {
        fail("the operator start");
        return;
    }
    say("operator start: started again without init");

    /* Criterion 23: a runtime dependency fails while the application runs. */
    (void)controller_framework_inject(CONTROLLER_FRAMEWORK_FAULT_SERVICE_DOWN, "configuration");
    if (!controller_is(CONTROLLER_FRAMEWORK_STATE_DEGRADED) || !worker_counts() ||
        fixture_health(CONTROLLER_FRAMEWORK_SERVICE_CONFIGURATION) !=
            CONTROLLER_FRAMEWORK_HEALTH_FAILED) {
        fail("the runtime dependency");
        return;
    }
    say("runtime dependency failed: controller degraded, application running");
    (void)controller_framework_inject(CONTROLLER_FRAMEWORK_FAULT_SERVICE_UP, "configuration");
    if (!controller_is(CONTROLLER_FRAMEWORK_STATE_OPERATIONAL)) {
        fail("the recovered dependency");
        return;
    }
    say("runtime dependency recovered: controller operational");

    /* Criterion 8: the running application reports a fault. */
    fixture_report_fault();
    if (!count_reaches(fixture_stops, 2u) || !count_reaches(fixture_safe_states, 2u)) {
        fail("the reported fault");
        return;
    }
    k_msleep(1500);
    if (fixture_controller_state() != CONTROLLER_FRAMEWORK_STATE_OPERATIONAL) {
        fail("the controller after the reported fault");
        return;
    }
    say("reported fault: stop, then safe state, controller operational");
    if (!command("status", "{\"name\":\"controller.application\",\"status\":\"ok\",\"type\":"
                           "\"text\",\"value\":\"fault\"}") ||
        !command("status", "{\"name\":\"fixture.counter\",\"status\":\"not_ready\"")) {
        return;
    }
    say("the status service shows the application in fault and its item released");
    if (command("reboot", "restart requested")) {
        say("restart requested");
    }
}

/* Boots that end in a fault of the application and keep the controller: device management
 * answers, and the reboot command leads to the next boot. */
static void fault_kept(const char *what, unsigned starts)
{
    char text[160];

    if (!count_reaches(fixture_safe_states, 1u) || fixture_starts() != starts ||
        !controller_is(CONTROLLER_FRAMEWORK_STATE_OPERATIONAL)) {
        fail(what);
        return;
    }
    (void)snprintf(text, sizeof text, "%s: safe state %u, controller operational", what,
                   fixture_safe_states());
    say(text);
    if (!account_and_login() ||
        !command("status", "{\"name\":\"controller.application\",\"status\":\"ok\",\"type\":"
                           "\"text\",\"value\":\"fault\"}")) {
        return;
    }
    say("device management answers");
    if (command("reboot", "restart requested")) {
        say("restart requested");
    }
}

static void start_or_fail(fixture_behaviour_t behaviour)
{
    if (controller_framework_start(fixture_descriptor(behaviour)) != CONTROLLER_FRAMEWORK_OK) {
        fail("the start function");
    }
}

/* Boots 2 and 5: log in and ask for an operator stop, whose stop fails or hangs. */
static void stop_by_operator(fixture_behaviour_t behaviour)
{
    start_or_fail(behaviour);
    if (!controller_is(CONTROLLER_FRAMEWORK_STATE_OPERATIONAL) || !account_and_login()) {
        return;
    }
    if (command("application stop", "application stop requested")) {
        say("operator stop requested");
    }
}

int main(void)
{
    char text[64];
    const int boot = scenario_boot_number();

    scenario_forward_log();
    (void)snprintf(text, sizeof text, "application scenario boot %d", boot);
    scenario_say(text);
    switch (boot) {
    case 1:
        boot_contract();
        break;
    case 2:
        stop_by_operator(FIXTURE_STOP_FAILS);
        break;
    case 3:
        start_or_fail(FIXTURE_THREAD_STALLS);
        say("waiting for the stalled worker");
        break;
    case 4:
        say("start will pass its deadline");
        start_or_fail(FIXTURE_START_HANGS);
        break;
    case 5:
        stop_by_operator(FIXTURE_STOP_HANGS);
        break;
    case 6:
        start_or_fail(FIXTURE_INIT_FAILS);
        fault_kept("init failed", 0u);
        break;
    case 7:
        (void)controller_framework_inject(CONTROLLER_FRAMEWORK_FAULT_CHANNEL_REFUSED, "monitor");
        start_or_fail(FIXTURE_NORMAL);
        fault_kept("activation refused", 0u);
        break;
    case 8:
        start_or_fail(FIXTURE_START_FAILS);
        fault_kept("start failed", 1u);
        break;
    case 9:
        (void)controller_framework_inject(CONTROLLER_FRAMEWORK_FAULT_SERVICE_DOWN, "configuration");
        start_or_fail(FIXTURE_NORMAL);
        if (!controller_is(CONTROLLER_FRAMEWORK_STATE_DEGRADED) || fixture_starts() != 0u) {
            fail("the hold");
            break;
        }
        say("held by a start prerequisite, controller degraded");
        (void)controller_framework_inject(CONTROLLER_FRAMEWORK_FAULT_SERVICE_UP, "configuration");
        if (!controller_is(CONTROLLER_FRAMEWORK_STATE_OPERATIONAL) || !account_and_login() ||
            !command("application start", "application start requested") ||
            !count_reaches(fixture_starts, 1u) || !worker_counts()) {
            fail("the operator start after the recovery");
            break;
        }
        say("operator start ran the held application");
        if (command("reboot", "restart requested")) {
            say("restart requested");
        }
        break;
    case 10:
        start_or_fail(FIXTURE_NORMAL);
        if (controller_is(CONTROLLER_FRAMEWORK_STATE_OPERATIONAL) && worker_counts()) {
            scenario_say("application scenario done");
        } else {
            fail("the boot after the planned reset");
        }
        break;
    default:
        fail("more boots than planned");
        break;
    }
    for (;;) {
        k_sleep(K_FOREVER);
    }
    return 0;
}
