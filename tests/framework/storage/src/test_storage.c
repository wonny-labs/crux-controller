/* SPDX-License-Identifier: Apache-2.0 */

/* The storage scenario of the controller framework on native_sim. One run, three boots, on LittleFS
 * over the flash simulator, whose file on the host keeps the volume across the restarts. main() is
 * the application: it passes its own descriptor and writes under its data root through Crux File,
 * as a product would. Each boot prints what the console harness of testcase.yaml matches, in order:
 *
 *   1. The blank volume is formatted. The first account is set up on the serial command line. The
 *      application fills its data root until Crux File refuses a write at the size limit; the
 * status service then shows storage degraded and a credential save (a second account) still
 * succeeds (criterion 24, gap C15; the parameter save needs a save provider, gap G1). The
 *      read-only account does not see the factory reset command; the administrator changes its
 *      role and resets its password, then runs the factory reset, and the power is cut before the
 *      account erase (criterion 42). Crux's security events of these steps (first-account setup,
 *      login, account creation, logout, role change and password reset) are in the log before the
 *      scenario line that follows them (criterion 44, without persistence).
 *   2. The accounts are still in place: the administrator logs in. The data root is empty. The
 *      factory reset runs again and completes.
 *   3. First-account setup is open again, the data root is empty, and the device identity was kept.
 *      Wrong passwords on the serial command line and on web management are delayed and recorded as
 *      security events (criterion 43).
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <controller/framework.h>
#include <crux/access.h>
#include <crux/config_service.h>
#include <crux/credential_store.h>
#include <crux/file.h>
#include <crux/security_event.h>

#include <crux_access_adapter.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/reboot.h>

#include "https.h"
#include "scenario.h"

#define USER "operator"
#define PASSWORD "storage scenario password"
#define READER "reader"
#define READER_ROLE "read-only"
#define READER_PASSWORD "storage scenario reader"
#define READER_RESET_PASSWORD "storage scenario reader reset"
#define WRONG_PASSWORD "not the password at all"
/* The data root (CONFIG_CRUX_CONTROLLER_APP_ROOT_MAX_BYTES is 16384 here) and one LittleFS block.
 */
#define FILE_BYTES 4096u
#define FILES_MAX 16
#define STATUS_POLLS 20
#define LOGIN_ATTEMPTS 10
#define DRAIN_POLLS 200

static int boot;
static controller_app_context_t *app_context;

static void fail(const char *what)
{
    char text[160];

    (void)snprintf(text, sizeof text, "storage scenario FAILED: %s", what);
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

/* --- the application: four entries that do nothing but succeed --- */

static int app_init(controller_app_context_t *context)
{
    app_context = context;
    return 0;
}

static int app_start(controller_app_context_t *context)
{
    (void)context;
    return 0;
}

static int app_stop(controller_app_context_t *context, controller_app_stop_reason_t reason)
{
    (void)context;
    (void)reason;
    return 0;
}

static void app_safe_state(controller_app_context_t *context)
{
    (void)context;
}

static const controller_app_t app = {app_init, app_start, app_stop, app_safe_state, NULL};

/* --- the power cut of boot 1 --- */

crux_credential_result_t __real_crux_credential_erase_accounts(void);
crux_credential_result_t __wrap_crux_credential_erase_accounts(void);

/* Boot 1: the power goes before the erase writes anything; a restart of the simulated process
 * stands in for the cut (no marker is written, and the volume keeps what was written before). */
crux_credential_result_t __wrap_crux_credential_erase_accounts(void)
{
    if (boot == 1) {
        scenario_say("storage scenario: power cut before the account erase");
        sys_reboot(SYS_REBOOT_COLD);
    }
    return __real_crux_credential_erase_accounts();
}

/* Wait until Crux's drain thread has written every security event that the ring admitted, so the
 * next scenario line follows their log lines: scenario_say() flushes the log first. A report of
 * lost records also counts as a written line, so the written lines reach the admitted ones at
 * least. The counts wrap at 2^32, so their difference is compared as signed. */
static bool events_drained(void)
{
    for (int poll = 0; poll < DRAIN_POLLS; poll++) {
        crux_security_event_stats_t stats;

        if (crux_security_event_get_stats(&stats) == CRUX_OK &&
            (int32_t)(stats.delivered + stats.log_errors - stats.emitted) >= 0) {
            return true;
        }
        k_msleep(10);
    }
    fail("the security events to drain");
    return false;
}

/* --- the serial command line --- */

static bool login(const char *user, const char *password)
{
    if (!expect("login: ")) {
        return false;
    }
    scenario_console_type(user);
    if (!expect("password: ")) {
        return false;
    }
    scenario_console_type(password);
    return expect("> ");
}

static bool setup_first_account(void)
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
    if (!expect("account created")) {
        return false;
    }
    return login(USER, PASSWORD);
}

static void logout(void)
{
    scenario_console_type("logout");
}

/* The storage health in the status service: the status command, until it shows the value. */
static bool storage_health_is(const char *value)
{
    char item[160];

    (void)snprintf(item, sizeof item,
                   "{\"name\":\"controller.health.storage\",\"status\":\"ok\",\"type\":\"text\","
                   "\"value\":\"%s\"}",
                   value);
    for (int poll = 0; poll < STATUS_POLLS; poll++) {
        scenario_console_type("status");
        if (scenario_console_expect(item)) {
            return expect("> ");
        }
        k_msleep(500);
    }
    fail(item);
    return false;
}

/* --- Crux Access in the administrator's name (no command makes a second account, gap C21) --- */

static bool admin_session(crux_access_session_t *session)
{
    const crux_access_origin_t origin = {CRUX_ACCESS_CHANNEL_SERIAL, {0}, 0u};
    uint32_t retry_after_ms = 0u;

    return crux_access_login_password(USER, PASSWORD, strlen(PASSWORD), &origin, session,
                                      &retry_after_ms) == CRUX_ACCESS_OK;
}

static bool reader_created(void)
{
    crux_access_session_t session = {0u};

    if (!admin_session(&session)) {
        fail("the administrator's session for the read-only account");
        return false;
    }
    const crux_access_result_t created = crux_access_account_create(
        session, READER, READER_ROLE, READER_PASSWORD, strlen(READER_PASSWORD));

    crux_access_logout(&session);
    return created == CRUX_ACCESS_OK;
}

/* --- the application's data root --- */

static int data_root(void)
{
    return controller_app_data_root(app_context);
}

/* Write files of one block until Crux File refuses one; the count of files written. */
static int fill_data_root(crux_file_result_t *refusal)
{
    static uint8_t block[FILE_BYTES];

    memset(block, 0x5a, sizeof block);
    for (int index = 0; index < FILES_MAX; index++) {
        char name[32];
        crux_file_t *file = NULL;
        size_t written = 0u;

        (void)snprintf(name, sizeof name, "fill%02d.bin", index);
        crux_file_result_t result =
            crux_file_open_at((crux_file_root_t)data_root(), name, CRUX_FILE_CREATE_REPLACE, &file);
        if (result == CRUX_FILE_OK) {
            result = crux_file_write(file, block, sizeof block, &written);
            if (result == CRUX_FILE_OK) {
                result = crux_file_sync(file);
            }
            (void)crux_file_close(&file);
        }
        if (result != CRUX_FILE_OK) {
            *refusal = result;
            return index;
        }
    }
    *refusal = CRUX_FILE_OK;
    return FILES_MAX;
}

static bool data_root_empty(void)
{
    crux_file_dir_t *dir = NULL;
    char name[64];
    crux_file_info_t info;
    bool end = false;

    if (crux_file_dir_open((crux_file_root_t)data_root(), &dir) != CRUX_FILE_OK) {
        return false;
    }
    const crux_file_result_t result = crux_file_dir_read(dir, name, sizeof name, &info, &end);

    (void)crux_file_dir_close(&dir);
    return result == CRUX_FILE_OK && end;
}

/* --- the boots --- */

static void boot_1(void)
{
    char text[160];
    crux_file_result_t refusal = CRUX_FILE_OK;

    if (!setup_first_account() || !events_drained()) {
        return;
    }
    scenario_say("storage scenario: first account set up");
    const int written = fill_data_root(&refusal);

    (void)snprintf(text, sizeof text, "storage scenario: data root full after %d files result=%d",
                   written, (int)refusal);
    scenario_say(text);
    if (refusal != CRUX_FILE_ERR_NO_SPACE || written < 1 || written >= FILES_MAX) {
        fail("the size limit of the data root");
        return;
    }
    if (!storage_health_is("degraded")) {
        return;
    }
    scenario_say("storage scenario: the status service shows storage degraded");
    if (!reader_created()) {
        fail("a credential save with the data root full");
        return;
    }
    if (!events_drained()) {
        return;
    }
    scenario_say("storage scenario: a credential save succeeds with the data root full");

    /* A parameter save. This application registers no parameter, so the save has nothing to write
     * and answers OK; a save that writes needs a save provider, which the framework cannot
     * initialise at the Crux pin (gap G1), so criterion 24's parameter save is not shown here. */
    crux_access_session_t session = {0u};
    crux_config_service_save_report_t report;

    memset(&report, 0, sizeof report);
    if (!admin_session(&session)) {
        fail("the administrator's session for the parameter save");
        return;
    }
    const crux_config_service_result_t saved = crux_config_service_save(session, &report);

    crux_access_logout(&session);
    (void)snprintf(text, sizeof text, "storage scenario: parameter save result=%d", (int)saved);
    scenario_say(text);

    /* The read-only account does not see the factory reset; the administrator runs it. */
    logout();
    if (!login(READER, READER_PASSWORD)) {
        return;
    }
    scenario_console_type("factory reset");
    if (!expect("unknown command") || !expect("> ")) {
        return;
    }
    scenario_say("storage scenario: the read-only account cannot run the factory reset");
    logout();
    if (!login(USER, PASSWORD)) {
        return;
    }
    /* Account changes that no command or route makes in the base image (gap C21), in the
     * administrator's name, for their security events. The factory reset erases the account. */
    if (!admin_session(&session)) {
        fail("the administrator's session for the account changes");
        return;
    }
    const crux_access_result_t role =
        crux_access_account_set_role(session, READER, "administrator");
    const crux_access_result_t reset = crux_access_account_reset_password(
        session, READER, READER_RESET_PASSWORD, strlen(READER_RESET_PASSWORD));

    crux_access_logout(&session);
    if (role != CRUX_ACCESS_OK || reset != CRUX_ACCESS_OK) {
        (void)snprintf(text, sizeof text, "the account changes role=%d reset=%d", (int)role,
                       (int)reset);
        fail(text);
        return;
    }
    if (!events_drained()) {
        return;
    }
    scenario_say("storage scenario: the role and the password of an account changed");
    scenario_console_type("factory reset");
    if (!expect("restart requested")) {
        return;
    }
    scenario_say("storage scenario: factory reset requested");
}

static void boot_2(void)
{
    if (!expect("login: ")) {
        return;
    }
    /* The console asks for the account before it says that setup is closed. */
    scenario_console_type("!setup");
    if (!expect("new user: ")) {
        return;
    }
    scenario_console_type("intruder");
    if (!expect("password: ")) {
        return;
    }
    scenario_console_type(PASSWORD);
    if (!expect("repeat: ")) {
        return;
    }
    scenario_console_type(PASSWORD);
    if (!expect("setup not available")) {
        return;
    }
    if (!login(USER, PASSWORD)) {
        return;
    }
    scenario_say("storage scenario: the accounts are still in place after the power cut");
    if (!data_root_empty()) {
        fail("an empty data root after the power cut");
        return;
    }
    scenario_say("storage scenario: the data root is empty");
    scenario_console_type("factory reset");
    if (!expect("restart requested")) {
        return;
    }
    scenario_say("storage scenario: factory reset requested again");
}

/* Wrong passwords on the serial command line until the console answers with a delay. */
static bool serial_login_delayed(void)
{
    for (int attempt = 0; attempt < LOGIN_ATTEMPTS; attempt++) {
        if (!expect("login: ")) {
            return false;
        }
        scenario_console_type("nobody");
        if (!expect("password: ")) {
            return false;
        }
        scenario_console_type(WRONG_PASSWORD);
        /* A refused password answers "login failed" at once; inside the delay window the console
         * answers "try again in N s" instead, so the next attempt must come quickly. */
        const int answer = scenario_console_expect_either("try again in ", "login failed");

        if (answer == 1) {
            return true;
        }
        if (answer == 0) {
            return false;
        }
    }
    return false;
}

/* Wrong passwords on web management until the session routes answer "retry later". */
static bool web_login_delayed(void)
{
    static char response[4096];
    char body[160];

    (void)snprintf(body, sizeof body, "{\"user\":\"nobody-web\",\"password\":\"%s\"}",
                   WRONG_PASSWORD);
    for (int attempt = 0; attempt < LOGIN_ATTEMPTS; attempt++) {
        const int status =
            https_request("POST", "/api/v1/session",
                          "Origin: https://" HTTPS_HOST "\r\nContent-Type: application/json\r\n",
                          body, response, sizeof response);

        if (status == 429 || strstr(response, "retry_later") != NULL) {
            return true;
        }
        /* An accepted attempt is checked on the session worker; its result can say it too. */
        const char *start = status == 202 ? strstr(response, "{\"id\":\"") : NULL;

        if (start != NULL) {
            char path[160];

            start += strlen("{\"id\":\"");
            (void)snprintf(path, sizeof path, "/api/v1/session/attempt/%.*s",
                           (int)strcspn(start, "\""), start);
            for (int poll = 0; poll < 20; poll++) {
                const int result = https_request("GET", path, "X-Crux-Request: 1\r\n", NULL,
                                                 response, sizeof response);

                if (result == 429 || strstr(response, "retry_later") != NULL) {
                    return true;
                }
                if (result != 200 || strstr(response, "\"state\":\"pending\"") == NULL) {
                    break;
                }
                k_msleep(100);
            }
        }
        /* The attempt is checked on the session worker; give it time before the next one. */
        k_msleep(300);
    }
    return false;
}

static void boot_3(void)
{
    if (!setup_first_account()) {
        return;
    }
    scenario_say("storage scenario: first-account setup is open after the factory reset");
    if (!data_root_empty()) {
        fail("an empty data root after the factory reset");
        return;
    }
    scenario_say("storage scenario: the data root is empty after the factory reset");
    scenario_console_type("status");
    if (!expect("{\"name\":\"controller.certificate\",\"status\":\"ok\",\"type\":\"text\","
                "\"value\":\"stored\"}") ||
        !expect("> ")) {
        return;
    }
    scenario_say("storage scenario: the device identity was kept");
    logout();
    if (!serial_login_delayed()) {
        fail("a delayed login on the serial command line");
        return;
    }
    scenario_say("storage scenario: the serial command line delays failed logins");
    if (!web_login_delayed()) {
        fail("a delayed login on web management");
        return;
    }
    scenario_say("storage scenario: web management delays failed logins");
    /* Let the security event thread drain the events to the log before the last line. */
    k_msleep(2000);
    scenario_say("storage scenario done");
}

int main(void)
{
    char text[64];

    boot = scenario_boot_number();
    scenario_forward_log();
    (void)snprintf(text, sizeof text, "storage scenario boot %d", boot);
    scenario_say(text);
    if (controller_framework_start(&app) != CONTROLLER_FRAMEWORK_OK) {
        fail("the start function");
    }
    switch (boot) {
    case 1:
        boot_1();
        break;
    case 2:
        boot_2();
        break;
    case 3:
        boot_3();
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
