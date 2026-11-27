/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The composition zone's part of the framework's health supervision (specification sections 4.3,
 * 5.1 and 5.2), with the public headers of the Crux services only:
 *
 *   - the framework's status items (framework_status.h) for the status service, read with the
 *     status read permission; each source copies a value and neither blocks nor touches storage;
 *   - Crux Reboot with the framework's callback policy (reboot_policy.h) and no Crux reboot worker,
 *     because the framework's reboot thread carries out requests (gap C14);
 *   - the framework's commands of the serial command line: status, which prints every status item
 *     that the session may read, and, with Crux Reboot, reboot, recovery clear and recovery exit,
 *     which need system.reboot. recovery clear sets the boot counter to zero; recovery exit sets it
 *     to zero and asks Crux Reboot for a restart, which carries the operator reset marker, so the
 *     next boot is a normal boot (safe-mode exit). Label: the authorised operator command of
 *     specification section 5.2 is a decision of the specification (D4); carrying it on the serial
 *     command line through Crux Reboot is a project-specific workaround. Crux docs/reboot-service.md
 *     (decision 16) adds no CLI reboot command, because the issue asked for none; its alternative
 *     column names a serial reboot command, which this project uses. The interface is
 *     components/reboot/include/crux/reboot.h.
 *
 * Status: built in CI for the board and run on native_sim; never run on a board.
 */

#include "../src/framework_status.h"
#include "../src/supervision_compose.h"

#include <crux/logging.h>
#include <crux/management_status.h>
#include <crux/status.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
#include "supervision_start.h"

#include <crux/cli.h>
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
#include "../src/management_policy.h"
#include "../src/reboot_policy.h"
#include "../src/recovery.h"

#include <crux/reboot.h>
#endif

#define LOG_TAG "recovery"

typedef void (*text_source_t)(char *text, size_t size);

/* The text sources, so that an item's context is the address of one: an object pointer, which a
 * function pointer is not. */
static const text_source_t sources[] = {
    framework_status_controller, framework_status_application, framework_status_boot,
    framework_status_watchdog,   framework_status_last_fault,  framework_status_stack,
};

static crux_status_t read_text(void *context, crux_mgmt_status_value_t *out)
{
    const text_source_t *source = context;

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

#define TEXT_ITEM(item_name, index)                                                                \
    {(item_name), CRUX_MGMT_STATUS_PERMISSION_READ, read_text, (void *)&sources[(index)]}

static const crux_mgmt_status_item_t items[] = {
    TEXT_ITEM("controller.state", 0),
    TEXT_ITEM("controller.application", 1),
    {"controller.safe_mode", CRUX_MGMT_STATUS_PERMISSION_READ, read_safe_mode, NULL},
    {"controller.boot_counter", CRUX_MGMT_STATUS_PERMISSION_READ, read_boot_counter, NULL},
    TEXT_ITEM("controller.boot", 2),
    TEXT_ITEM("controller.watchdog", 3),
    TEXT_ITEM("controller.last_fault", 4),
    TEXT_ITEM("controller.stack_min", 5),
};

const void *supervision_compose_status_items(size_t *count)
{
    if (count != NULL) {
        *count = sizeof items / sizeof items[0];
    }
    return items;
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
/* The Crux Reboot policy callback: the framework's rule for the operator reset marker. Crux calls
 * it on the requesting thread and again on the framework's reboot thread just before the reset. The
 * framework does not refuse, so it writes no reason. */
static bool reboot_policy(void *context, crux_reboot_refusal_t *refusal)
{
    (void)context;
    (void)refusal;
    return reboot_policy_allow(reboot_policy_port());
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

static const crux_cli_command_t commands[] = {
    CRUX_CLI_COMMAND("status", "Show the status items",
                     CRUX_CLI_PERMISSION(CRUX_MGMT_STATUS_PERMISSION_READ), 0u, 0u,
                     CRUX_CLI_CHANNEL_SERIAL, status_command, NULL),
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
