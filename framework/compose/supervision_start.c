/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The composition zone's part of the framework's health supervision (specification sections 4.3,
 * 5.1 and 5.2), with the public headers of the Crux services only:
 *
 *   - the framework's status items (framework_status.h) for the status service, read with the
 *     status read permission; each source copies a value and neither blocks nor touches storage;
 *     after them the application's items, each behind a framework item of the same name and
 *     permission that answers CRUX_ERR_NOT_READY once the registrations are released (specification
 *     section 3.3);
 *   - Crux Reboot with the framework's callback policy (reboot_policy.h) and no Crux reboot worker,
 *     because the framework's reboot thread carries out requests (gap C14);
 *   - the framework's commands of the serial command line: status, which prints every status item
 *     that the session may read, and, with Crux Reboot, reboot, recovery clear and recovery exit,
 *     which need system.reboot. recovery clear sets the boot counter to zero; recovery exit sets it
 *     to zero and asks Crux Reboot for a restart, which carries the operator reset marker, so the
 *     next boot is a normal boot (safe-mode exit). Label: the authorised operator command of
 *     specification section 5.2 is a decision of the specification (D4); carrying it on the serial
 *     command line through Crux Reboot is a project-specific workaround. Crux
 *     docs/reboot-service.md (decision 16) adds no CLI reboot command, because the issue asked for
 *     none; its alternative column names a serial reboot command, which this project uses. The
 *     interface is components/reboot/include/crux/reboot.h.
 *   - the operator stop and start of the application (framework_control.h): application stop and
 *     application start, which need system.reboot (an open question of delivery stage 3: a
 *     permission of their own) and are carried out on the framework's application thread.
 *
 * Status: built in CI for the board and run on native_sim; never run on a board.
 */

#include "../src/controller_state.h"
#include "../src/framework_status.h"
#include "../src/supervision_compose.h"
#ifdef CONFIG_CRUX_WEB_MANAGEMENT
#include "../src/management_port.h"
#endif
#if defined(CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT) && defined(CONFIG_CRUX_THREAD)
#include "../src/service_progress.h"

#include <crux/service_priority_zephyr.h>
#endif

#include <crux/logging.h>
#include <crux/management_status.h>
#include <crux/status.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
#include "../src/framework_control.h"
#include "../src/management_policy.h"
#include "supervision_start.h"

#include <crux/cli.h>
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
#include "../src/management_policy.h"
#include "../src/reboot_policy.h"
#include "../src/recovery.h"

#include <crux/reboot.h>

#include <stdio.h>
#endif

#define LOG_TAG "recovery"

typedef void (*text_source_t)(char *text, size_t size);

/* The text sources, so that an item's context is the address of one: an object pointer, which a
 * function pointer is not. */
static const text_source_t sources[] = {
    framework_status_controller, framework_status_application, framework_status_boot,
    framework_status_watchdog,   framework_status_last_fault,  framework_status_stack,
#ifdef CONFIG_CRUX_WEB_MANAGEMENT
    management_port_certificate,
#endif
};

static crux_status_t read_text(void *context, crux_mgmt_status_value_t *out)
{
    const text_source_t *source = (const text_source_t *)context;

    out->type = CRUX_MGMT_STATUS_TEXT;
    (*source)(out->data.text, sizeof out->data.text);
    return CRUX_OK;
}

static crux_status_t read_safe_mode(void *context, crux_mgmt_status_value_t *out)
{
    (void)context;
    out->type = CRUX_MGMT_STATUS_BOOL;
    out->data.boolean = framework_status_safe_mode();
    return CRUX_OK;
}

static crux_status_t read_boot_counter(void *context, crux_mgmt_status_value_t *out)
{
    (void)context;
    out->type = CRUX_MGMT_STATUS_U32;
    out->data.u32 = framework_status_boot_counter();
    return CRUX_OK;
}

/* The services, so that a health item's context is the address of its identifier. */
static const int services[SERVICE_COUNT] = {
    SERVICE_NETWORK, SERVICE_STORAGE, SERVICE_ACCESS, SERVICE_CONFIGURATION,
    SERVICE_STATUS,  SERVICE_TIME,    SERVICE_WEB,    SERVICE_COMMAND_LINE,
};

static crux_status_t read_health(void *context, crux_mgmt_status_value_t *out)
{
    const int *service = context;

    out->type = CRUX_MGMT_STATUS_TEXT;
    framework_status_health(*service, out->data.text, sizeof out->data.text);
    return CRUX_OK;
}

#define TEXT_ITEM(item_name, index)                                                                \
    {(item_name), CRUX_MGMT_STATUS_PERMISSION_READ, read_text, (void *)&sources[(index)]}
#define HEALTH_ITEM(item_name, service)                                                            \
    {(item_name), CRUX_MGMT_STATUS_PERMISSION_READ, read_health, (void *)&services[(service)]}

static const crux_mgmt_status_item_t framework_items[] = {
    TEXT_ITEM("controller.state", 0),
    TEXT_ITEM("controller.application", 1),
    {"controller.safe_mode", CRUX_MGMT_STATUS_PERMISSION_READ, read_safe_mode, NULL},
    {"controller.boot_counter", CRUX_MGMT_STATUS_PERMISSION_READ, read_boot_counter, NULL},
    TEXT_ITEM("controller.boot", 2),
    TEXT_ITEM("controller.watchdog", 3),
    TEXT_ITEM("controller.last_fault", 4),
    TEXT_ITEM("controller.stack_min", 5),
    HEALTH_ITEM("controller.health.network", SERVICE_NETWORK),
    HEALTH_ITEM("controller.health.storage", SERVICE_STORAGE),
    HEALTH_ITEM("controller.health.access", SERVICE_ACCESS),
    HEALTH_ITEM("controller.health.configuration", SERVICE_CONFIGURATION),
    HEALTH_ITEM("controller.health.status", SERVICE_STATUS),
    HEALTH_ITEM("controller.health.time", SERVICE_TIME),
    HEALTH_ITEM("controller.health.web", SERVICE_WEB),
    HEALTH_ITEM("controller.health.command-line", SERVICE_COMMAND_LINE),
#ifdef CONFIG_CRUX_WEB_MANAGEMENT
    /* How the TLS certificate started: stored, made at boot, refused or not started (section 5.5).
     */
    TEXT_ITEM("controller.certificate", 6),
#endif
};

#define FRAMEWORK_ITEMS (sizeof framework_items / sizeof framework_items[0])

_Static_assert(FRAMEWORK_ITEMS + CONFIG_CRUX_CONTROLLER_APP_STATUS_ITEMS <=
                   CRUX_MGMT_STATUS_PROJECT_ITEMS_MAX,
               "the framework's and the application's status items must fit the status service");

/* The table that the status service gets: the framework's items, then one framework item per
 * application item, whose context is the application's item. */
static crux_mgmt_status_item_t items[FRAMEWORK_ITEMS + CONFIG_CRUX_CONTROLLER_APP_STATUS_ITEMS];

/* An application item's source: unavailable once the registrations are released, otherwise the
 * application's own source. */
static crux_status_t read_application_item(void *context, crux_mgmt_status_value_t *out)
{
    const crux_mgmt_status_item_t *item = context;

    if (!framework_status_application_items()) {
        return CRUX_ERR_NOT_READY;
    }
    return item->read(item->context, out);
}

const void *supervision_compose_status_items(const void *app_items, size_t app_count, size_t *count)
{
    const crux_mgmt_status_item_t *given = app_items;

    if (count != NULL) {
        *count = 0u;
    }
    if (app_count > CONFIG_CRUX_CONTROLLER_APP_STATUS_ITEMS || (given == NULL && app_count > 0u)) {
        return NULL;
    }
    for (size_t index = 0; index < FRAMEWORK_ITEMS; index++) {
        items[index] = framework_items[index];
    }
    for (size_t index = 0; index < app_count; index++) {
        items[FRAMEWORK_ITEMS + index] = (crux_mgmt_status_item_t){
            .name = given[index].name,
            .permission = given[index].permission,
            .read = read_application_item,
            .context = (void *)&given[index],
        };
    }
    if (count != NULL) {
        *count = FRAMEWORK_ITEMS + app_count;
    }
    return items;
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
/* The Crux Reboot policy callback: the framework's rule for the operator reset marker. Crux calls
 * it on the requesting thread and again on the framework's reboot thread just before the reset. The
 * framework refuses only while the startup steps of an image with an application run
 * (framework_control.h), and says so in the reason. */
static bool reboot_policy(void *context, crux_reboot_refusal_t *refusal)
{
    (void)context;
    if (reboot_policy_allow(reboot_policy_port())) {
        return true;
    }
    if (refusal != NULL) {
        (void)snprintf(refusal->reason, sizeof refusal->reason, "%s",
                       "Application startup has not ended");
    }
    return false;
}

int supervision_compose_reboot_start(void)
{
    static const crux_reboot_config_t reboot = {
        .policy_kind = CRUX_REBOOT_POLICY_CALLBACK,
        .policy = reboot_policy,
        .policy_context = NULL,
        .wait_sources = NULL,
        .wait_source_count = 0u,
    };

    /* The administrator's copy of the permission must be the text that Crux Reboot checks. */
    if (strcmp(MANAGEMENT_PERMISSION_SYSTEM_REBOOT, CRUX_REBOOT_PERMISSION) != 0) {
        (void)crux_log_write(CRUX_LOG_ERROR, LOG_TAG, "reboot permission names disagree");
        return -1;
    }
    return crux_reboot_start(&reboot) == CRUX_REBOOT_OK ? 0 : -1;
}

#else
int supervision_compose_reboot_start(void)
{
    return 0;
}
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
/* status: one JSON object per line for each item that the session may read, as the web API shows
 * them (crux_mgmt_status_entry_json()). */
static crux_cli_result_t status_command(crux_cli_call_t *call, size_t argc, const char *const *argv,
                                        void *context)
{
    (void)argc;
    (void)argv;
    (void)context;
    size_t cursor = 0u;
    crux_mgmt_status_entry_t entry;
    char line[CRUX_MGMT_STATUS_JSON_ENTRY_SIZE + 1u];
    size_t length = 0u;

    while (crux_mgmt_status_next(crux_cli_session(call), &cursor, &entry) == CRUX_OK) {
        if (crux_mgmt_status_entry_json(&entry, line, sizeof line - 1u, &length) != CRUX_OK) {
            return CRUX_CLI_ERR_FAILED;
        }
        line[length] = '\n';
        const crux_cli_result_t written = crux_cli_write(call, line, length + 1u);

        if (written != CRUX_CLI_OK) {
            return written;
        }
    }
    return CRUX_CLI_OK;
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
static crux_cli_result_t write_text(crux_cli_call_t *call, const char *text)
{
    return crux_cli_write(call, text, strlen(text));
}

/* Ask Crux Reboot for a restart in the session's name, and say what it answered. */
static crux_cli_result_t request_restart(crux_cli_call_t *call)
{
    char reason[CRUX_REBOOT_REASON_SIZE];
    const crux_reboot_result_t result = crux_reboot_request(crux_cli_session(call), reason);

    if (result == CRUX_REBOOT_OK) {
        return write_text(call, "restart requested\n");
    }
    if (result == CRUX_REBOOT_ERR_DENIED || result == CRUX_REBOOT_ERR_SESSION_INVALID) {
        return CRUX_CLI_ERR_DENIED;
    }
    if (result == CRUX_REBOOT_ERR_REFUSED) {
        (void)write_text(call, "restart refused: ");
        (void)write_text(call, reason);
        (void)write_text(call, "\n");
    }
    return CRUX_CLI_ERR_FAILED;
}

static crux_cli_result_t reboot_command(crux_cli_call_t *call, size_t argc, const char *const *argv,
                                        void *context)
{
    (void)argc;
    (void)argv;
    (void)context;
    return request_restart(call);
}

static crux_cli_result_t recovery_clear_command(crux_cli_call_t *call, size_t argc,
                                                const char *const *argv, void *context)
{
    (void)argc;
    (void)argv;
    (void)context;
    recovery_counter_clear();
    (void)crux_log_write(CRUX_LOG_WARN, LOG_TAG, "boot counter cleared by an operator");
    return write_text(call, "boot counter cleared\n");
}

static crux_cli_result_t recovery_exit_command(crux_cli_call_t *call, size_t argc,
                                               const char *const *argv, void *context)
{
    (void)argc;
    (void)argv;
    (void)context;
    recovery_counter_clear();
    (void)crux_log_write(CRUX_LOG_WARN, LOG_TAG, "safe mode exit requested by an operator");
    return request_restart(call);
}
#endif

/* Say what the framework did with an operator request. */
static crux_cli_result_t control_reply(crux_cli_call_t *call, framework_control_t result,
                                       const char *requested)
{
    const char *text = requested;

    if (result == FRAMEWORK_CONTROL_NO_APPLICATION) {
        text = "refused: no application\n";
    } else if (result == FRAMEWORK_CONTROL_STARTING) {
        text = "refused: startup has not ended\n";
    } else if (result == FRAMEWORK_CONTROL_RESETTING) {
        text = "refused: a reset is under way\n";
    }
    const crux_cli_result_t written = crux_cli_write(call, text, strlen(text));

    if (written != CRUX_CLI_OK) {
        return written;
    }
    return result == FRAMEWORK_CONTROL_REQUESTED ? CRUX_CLI_OK : CRUX_CLI_ERR_FAILED;
}

static crux_cli_result_t application_stop_command(crux_cli_call_t *call, size_t argc,
                                                  const char *const *argv, void *context)
{
    (void)argc;
    (void)argv;
    (void)context;
    return control_reply(call, framework_control_application_stop(),
                         "application stop requested\n");
}

static crux_cli_result_t application_start_command(crux_cli_call_t *call, size_t argc,
                                                   const char *const *argv, void *context)
{
    (void)argc;
    (void)argv;
    (void)context;
    return control_reply(call, framework_control_application_start(),
                         "application start requested\n");
}

static const crux_cli_command_t commands[] = {
    CRUX_CLI_COMMAND("status", "Show the status items",
                     CRUX_CLI_PERMISSION(CRUX_MGMT_STATUS_PERMISSION_READ), 0u, 0u,
                     CRUX_CLI_CHANNEL_SERIAL, status_command, NULL),
    CRUX_CLI_COMMAND("application stop", "Stop the application",
                     CRUX_CLI_PERMISSION(MANAGEMENT_PERMISSION_SYSTEM_REBOOT), 0u, 0u,
                     CRUX_CLI_CHANNEL_SERIAL, application_stop_command, NULL),
    CRUX_CLI_COMMAND("application start", "Start the stopped or held application",
                     CRUX_CLI_PERMISSION(MANAGEMENT_PERMISSION_SYSTEM_REBOOT), 0u, 0u,
                     CRUX_CLI_CHANNEL_SERIAL, application_start_command, NULL),
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
    CRUX_CLI_COMMAND("reboot", "Restart the controller",
                     CRUX_CLI_PERMISSION(CRUX_REBOOT_PERMISSION), 0u, 0u, CRUX_CLI_CHANNEL_SERIAL,
                     reboot_command, NULL),
    CRUX_CLI_COMMAND("recovery clear", "Set the boot counter to zero",
                     CRUX_CLI_PERMISSION(CRUX_REBOOT_PERMISSION), 0u, 0u, CRUX_CLI_CHANNEL_SERIAL,
                     recovery_clear_command, NULL),
    CRUX_CLI_COMMAND("recovery exit", "Leave safe mode: clear the counter and restart",
                     CRUX_CLI_PERMISSION(CRUX_REBOOT_PERMISSION), 0u, 0u, CRUX_CLI_CHANNEL_SERIAL,
                     recovery_exit_command, NULL),
#endif
};

const crux_cli_command_t *supervision_commands(size_t *count)
{
    if (count != NULL) {
        *count = sizeof commands / sizeof commands[0];
    }
    return commands;
}
#endif

#if defined(CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT) && defined(CONFIG_CRUX_THREAD)
/* The progress function: Crux calls it on each service thread, possibly on several at once. It maps
 * the identifier and feeds, and takes no lock and never waits, as <crux/service_priority_zephyr.h>
 * requires. */
static void on_progress(crux_service_thread_t thread, void *context)
{
    (void)context;
    switch (thread) {
    case CRUX_SERVICE_THREAD_SECURITY_EVENT_DRAIN:
        service_progress_report(SERVICE_THREAD_EVENT_DRAIN);
        break;
    case CRUX_SERVICE_THREAD_WEB_SESSION_WORKER:
        service_progress_report(SERVICE_THREAD_WEB_SESSION);
        break;
    case CRUX_SERVICE_THREAD_WEB_MANAGEMENT_WORKER:
        service_progress_report(SERVICE_THREAD_WEB_MANAGEMENT);
        break;
    case CRUX_SERVICE_THREAD_CLI_CONSOLE:
        service_progress_report(SERVICE_THREAD_CONSOLE);
        break;
    default:
        /* The reboot worker is never started, and Crux Reboot reports its identifier on the
         * framework's reboot thread, which feeds its own channel (gap C14); the network settings
         * worker is not started either. */
        break;
    }
}

int supervision_compose_progress_start(void)
{
    return crux_service_progress_register(on_progress, NULL) == CRUX_OK ? 0 : -1;
}
#else
int supervision_compose_progress_start(void)
{
    return -1;
}
#endif
