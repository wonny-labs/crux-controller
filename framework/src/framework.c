/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The start function of the controller framework: the step table of the services that the build
 * turns on, run by the portable startup sequence (startup.h). Each service is reached through its
 * port, whose implementation is in the composition zone (framework/compose) or the adapter zone
 * (framework/os) of the module, so this file includes no Zephyr header.
 *
 * Steps, with the numbers of specification section 4.1 where a step is one of them:
 *   clock (1)       the Crux monotonic clock answers. Required: without it nothing can be timed.
 *                   With health supervision it also reads the reset cause once, keeps the copy and
 *                   clears the flags (gap C2), reads the retained region, updates the boot counter
 *                   and decides normal boot or safe mode (sections 5.1 and 5.2).
 *   supervisor (2)  with health supervision: the supervisor thread, which arms the hardware
 *                   watchdog with the one timeout T (gap C3) and supervises the steps after it.
 *   web management  storage mount and the two roots of the credential store, security events, the
 *                   credential store and Access, Crux Reboot with the framework's policy, the
 *                   configuration service, the status service with the captured reset cause and
 *                   the framework's items, the TLS certificate, sessions and web management, then
 *                   the HTTPS listener (management_port.h has the order inside the step); then the
 *                   framework's reboot thread. One step covers steps 3, 4, 6, 7 and 10 of section
 *                   4.1, with one deadline, until the port is split.
 *   command line (9)  the framework's command tables to the Crux registry, then the Crux serial
 *                   console on the UART of the alias crux-serial0, with its first-account setup.
 *                   It needs Access, so it runs only when web management started (cli_port.h).
 *   time synchronisation (8)  the SNTP thread that sets the Crux Time realtime clock; left out
 *                   in safe mode.
 *   application (12)  with health supervision: no application is given yet, so the step ends
 *                   startup supervision with no application.
 * Each step from web management on, the application step included, has a software deadline
 * (Kconfig), which the supervisor enforces. The network interface is up before main() (the Zephyr
 * network configuration library), and Crux Logging needs no start. A step after the clock that
 * fails is reported and the controller runs without that service.
 */

#include <controller/framework.h>

#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include <crux/logging.h>
#include <crux/status.h>
#include <crux/time.h>

#include "startup.h"

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
#include "management_policy.h"
#include "management_port.h"

/* The versions that the status service reports come from the build (zephyr/CMakeLists.txt), and a
 * build without them stops here, because the port refuses a start without a valid text. */
#ifndef CONTROLLER_PLATFORM_VERSION
#error "web management needs CONTROLLER_PLATFORM_VERSION from zephyr/CMakeLists.txt"
#endif
#ifndef CONTROLLER_PROJECT_VERSION
#error "web management needs CONTROLLER_PROJECT_VERSION from zephyr/CMakeLists.txt"
#endif
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
#include "cli_port.h"
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC
#include "time_sync.h"
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
#include <crux/system.h>

#include "boot_record.h"
#include "controller_state.h"
#include "fault_injection.h"
#include "framework_status.h"
#include "recovery.h"
#include "supervision_compose.h"
#include "supervisor_port.h"

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
#include "reboot_port.h"
#endif

/* The identity of the image, from the build (zephyr/CMakeLists.txt): another image clears the boot
 * counter (section 5.1). */
#ifndef CONTROLLER_IMAGE_ID_TEXT
#error "health supervision needs CONTROLLER_IMAGE_ID_TEXT from zephyr/CMakeLists.txt"
#endif

_Static_assert(CONFIG_CRUX_CONTROLLER_WATCHDOG_TIMEOUT_MS >=
                   2 * CONFIG_CRUX_CONTROLLER_SUPERVISOR_PERIOD_MS,
               "the watchdog timeout T must cover the supervisor's period with a margin");
_Static_assert(CONFIG_CRUX_CONTROLLER_SAFE_MODE_THRESHOLD >= 1 &&
                   CONFIG_CRUX_CONTROLLER_SAFE_MODE_THRESHOLD <= BOOT_COUNTER_MAX,
               "the safe-mode threshold must fit the boot counter");

#define DEADLINE_MANAGEMENT_MS ((uint32_t)CONFIG_CRUX_CONTROLLER_DEADLINE_MANAGEMENT_MS)
#define DEADLINE_COMMAND_LINE_MS ((uint32_t)CONFIG_CRUX_CONTROLLER_DEADLINE_COMMAND_LINE_MS)
#define DEADLINE_TIME_SYNC_MS ((uint32_t)CONFIG_CRUX_CONTROLLER_DEADLINE_TIME_SYNC_MS)
#define DEADLINE_APPLICATION_MS ((uint32_t)CONFIG_CRUX_CONTROLLER_DEADLINE_APPLICATION_MS)
#define STABLE_PERIOD_MS ((uint64_t)CONFIG_CRUX_CONTROLLER_STABLE_PERIOD_S * 1000u)
#else
#define DEADLINE_MANAGEMENT_MS 0u
#define DEADLINE_COMMAND_LINE_MS 0u
#define DEADLINE_TIME_SYNC_MS 0u
#endif

#define LOG_TAG "framework"

static void say(crux_log_level_t level, const char *text)
{
    (void)crux_log_write(level, LOG_TAG, text);
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
/* What the steps learn and the status service shows. The fields without atomics are written by the
 * start function in step 1, before the threads and the status service that read them start; the
 * others are read by the supervisor thread and the status service while the steps run. */
static struct {
    crux_status_t cause_status;
    crux_reset_cause_t cause;
    recovery_boot_t boot;
    atomic_bool safe_mode;
    atomic_bool armed;
    atomic_bool startup_done;
    atomic_int state;
    atomic_int health[SERVICE_COUNT];
    boot_stability_t stability;
    controller_state_t logged;
} fw;

static void capture_reset_cause(void)
{
    char text[CRUX_LOG_TEXT_MAX];
    crux_reset_cause_t cause = {0u, 0u};

    fw.cause_status = crux_system_reset_cause_get(&cause);
    fw.cause = cause;
    if (fw.cause_status != CRUX_OK) {
        (void)snprintf(text, sizeof text, "reset cause unavailable status=%d",
                       (int)fw.cause_status);
        say(CRUX_LOG_WARN, text);
        return;
    }
    /* The copy is kept, so the flags can go: one read and one clear per boot (gap C2). */
    const crux_status_t cleared = crux_system_reset_cause_clear();

    (void)snprintf(text, sizeof text, "reset cause=0x%03lx supported=0x%03lx captured, flags %s",
                   (unsigned long)cause.causes, (unsigned long)cause.supported,
                   cleared == CRUX_OK ? "cleared" : "not cleared");
    say(cleared == CRUX_OK ? CRUX_LOG_INFO : CRUX_LOG_WARN, text);
}

static void decide_boot(void)
{
    char text[CRUX_LOG_TEXT_MAX];
    char fault[CRUX_LOG_TEXT_MAX];
    const boot_decision_t *decision = &fw.boot.decision;

    recovery_boot(fw.cause_status == CRUX_OK, fw.cause.causes,
                  boot_image_id(CONTROLLER_IMAGE_ID_TEXT),
                  (uint8_t)CONFIG_CRUX_CONTROLLER_SAFE_MODE_THRESHOLD, &fw.boot);
    atomic_store(&fw.safe_mode, decision->safe_mode);
    (void)snprintf(text, sizeof text, "boot class=%s counter=%u threshold=%u safe mode=%s %s",
                   boot_class_name(decision->boot_class), (unsigned)decision->region.counter,
                   (unsigned)CONFIG_CRUX_CONTROLLER_SAFE_MODE_THRESHOLD,
                   atomic_load(&fw.safe_mode) ? "yes" : "no",
                   fw.boot.retained ? "retained region" : "no retained region");
    say(atomic_load(&fw.safe_mode) || decision->boot_class == BOOT_CLASS_FAULT ? CRUX_LOG_WARN
                                                                               : CRUX_LOG_INFO,
        text);
    if (decision->fault_reported) {
        recovery_last_fault_text(fault, sizeof fault);
        (void)snprintf(text, sizeof text, "last fault %s sequence=%lu", fault,
                       (unsigned long)decision->fault.sequence);
        say(CRUX_LOG_WARN, text);
    }
}
#endif

static int phase_clock(void)
{
    crux_monotonic_time_t now;

    if (crux_monotonic_now(&now) != CRUX_OK) {
        return -1;
    }
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    capture_reset_cause();
    decide_boot();
#endif
    return 0;
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
static void set_health(service_id_t service, service_health_t health)
{
    atomic_store(&fw.health[service], (int)health);
}

/* Once per supervisor period, on the supervisor thread: the controller state and the successful
 * boot (section 5.2). The base image has no application, so the application condition holds. */
static void supervisor_tick(uint64_t now_ms)
{
    controller_inputs_t inputs = {
        .startup_done = atomic_load(&fw.startup_done),
        .safe_mode = atomic_load(&fw.safe_mode),
        .watchdog_armed = atomic_load(&fw.armed),
#ifdef CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG
        .watchdog_optional = true,
#else
        .watchdog_optional = false,
#endif
        .required = 0u,
    };

    for (int service = 0; service < SERVICE_COUNT; service++) {
        inputs.health[service] = (service_health_t)atomic_load(&fw.health[service]);
    }
    const controller_state_t state = controller_state_decide(&inputs);

    atomic_store(&fw.state, (int)state);
    if (state != fw.logged) {
        char text[CRUX_LOG_TEXT_MAX];

        fw.logged = state;
        (void)snprintf(text, sizeof text, "controller state=%s", controller_state_name(state));
        say(state == CONTROLLER_OPERATIONAL ? CRUX_LOG_INFO : CRUX_LOG_WARN, text);
    }
    if (boot_stability_update(&fw.stability,
                              controller_successful_boot_conditions(state, APP_ABSENT), now_ms,
                              STABLE_PERIOD_MS)) {
        recovery_counter_clear();
        say(CRUX_LOG_INFO, "successful boot: boot counter cleared");
    }
    if (inputs.startup_done && fault_injection_fatal_due()) {
        say(CRUX_LOG_WARN, "fault injection: fatal error in the supervisor thread");
        supervisor_port_fatal();
    }
}

static int phase_supervisor(void)
{
    char text[CRUX_LOG_TEXT_MAX];
    const supervisor_port_config_t config = {
        .timeout_ms = (uint32_t)CONFIG_CRUX_CONTROLLER_WATCHDOG_TIMEOUT_MS,
        .period_ms = (uint32_t)CONFIG_CRUX_CONTROLLER_SUPERVISOR_PERIOD_MS,
        .tick = supervisor_tick,
    };
    int watchdog_status = 0;
    const supervisor_port_status_t status = supervisor_port_start(&config, &watchdog_status);

    if (status == SUPERVISOR_PORT_ERR) {
        return (int)status;
    }
    atomic_store(&fw.armed, status == SUPERVISOR_PORT_ARMED);
    if (status == SUPERVISOR_PORT_ARMED) {
        (void)snprintf(text, sizeof text, "watchdog armed timeout=%u ms",
                       (unsigned)CONFIG_CRUX_CONTROLLER_WATCHDOG_TIMEOUT_MS);
        say(CRUX_LOG_INFO, text);
    } else {
        (void)snprintf(text, sizeof text, "watchdog not armed status=%d", watchdog_status);
        say(CRUX_LOG_WARN, text);
    }
    return 0;
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC
static bool skip_in_safe_mode(void)
{
    return atomic_load(&fw.safe_mode);
}
#endif

static int phase_application(void)
{
    say(CRUX_LOG_INFO, atomic_load(&fw.safe_mode) ? "no application: safe mode" : "no application");
    return 0;
}

static void hook_begin(const char *name, uint32_t deadline_ms)
{
    supervisor_port_step_begin(name, deadline_ms);
    if (fault_injection_step_stalls(name)) {
        char text[CRUX_LOG_TEXT_MAX];

        (void)snprintf(text, sizeof text, "fault injection: step %s stalls", name);
        say(CRUX_LOG_WARN, text);
        supervisor_port_stall();
    }
}

static void hook_end(const char *name)
{
    (void)name;
    supervisor_port_step_end();
}

static void hook_skipped(const char *name)
{
    char text[CRUX_LOG_TEXT_MAX];

    (void)snprintf(text, sizeof text, "phase %s left out: safe mode", name);
    say(CRUX_LOG_WARN, text);
}

static const startup_hooks_t hooks = {hook_begin, hook_end, hook_skipped};
#define HOOKS (&hooks)
#define SKIP_IN_SAFE_MODE skip_in_safe_mode
#else
#define HOOKS NULL
#define SKIP_IN_SAFE_MODE NULL
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
/* True once web management started, and with it Access, which the command line needs. */
static bool management_started;

static int phase_management(void)
{
    management_port_config_t config = {
        .policy = management_policy_get(),
        .platform_version = CONTROLLER_PLATFORM_VERSION,
        .project_version = CONTROLLER_PROJECT_VERSION,
    };
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    config.reset_cause_given = true;
    config.reset_cause_status = (int)fw.cause_status;
    config.reset_cause_supported = fw.cause.supported;
    config.reset_cause_causes = fw.cause.causes;
    config.status_items = supervision_compose_status_items(&config.status_item_count);
    config.after_events = supervision_compose_reboot_start;
#endif
    const management_port_status_t status = management_port_start(&config);

    management_started = status == MANAGEMENT_PORT_OK;
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    const service_health_t health = management_started ? SERVICE_HEALTHY : SERVICE_FAILED;

    set_health(SERVICE_STORAGE, health);
    set_health(SERVICE_ACCESS, health);
    set_health(SERVICE_CONFIGURATION, health);
    set_health(SERVICE_STATUS, health);
    set_health(SERVICE_WEB, health);
#endif
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
    if (management_started) {
        (void)reboot_port_start();
    }
#endif
    return (int)status;
}
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
/* The phase result when web management, and so Access, did not start. */
#define PHASE_COMMAND_LINE_NO_ACCESS (-100)

static int phase_command_line(void)
{
    /* The first account gets the role of the management policy that manages accounts. */
    cli_port_config_t config = {.setup_role = MANAGEMENT_ROLE_ADMINISTRATOR};

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    config.framework_commands = true;
#endif
    if (!management_started) {
        return PHASE_COMMAND_LINE_NO_ACCESS;
    }
    const int result = (int)cli_port_start(&config);

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    set_health(SERVICE_COMMAND_LINE, result == 0 ? SERVICE_HEALTHY : SERVICE_FAILED);
#endif
    return result;
}
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC
static int phase_time_sync(void)
{
    const int result = time_sync_start();

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    /* Started and not yet synchronised (section 4.7). */
    set_health(SERVICE_TIME, result == 0 ? SERVICE_DEGRADED : SERVICE_FAILED);
#endif
    return result;
}
#endif

static const startup_step_t steps[] = {
    {{"clock", phase_clock, true}, 0u, NULL},
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    {{"supervisor", phase_supervisor, false}, 0u, NULL},
#endif
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
    {{"web management", phase_management, false}, DEADLINE_MANAGEMENT_MS, NULL},
#endif
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
    {{"command line", phase_command_line, false}, DEADLINE_COMMAND_LINE_MS, NULL},
#endif
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC
    {{"time synchronisation", phase_time_sync, false}, DEADLINE_TIME_SYNC_MS, SKIP_IN_SAFE_MODE},
#endif
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    {{"application", phase_application, false}, DEADLINE_APPLICATION_MS, NULL},
#endif
};

static void report(const char *name, int result)
{
    char text[CRUX_LOG_TEXT_MAX];

    if (result == 0) {
        (void)snprintf(text, sizeof text, "phase %s ok", name);
        say(CRUX_LOG_INFO, text);
    } else {
        (void)snprintf(text, sizeof text, "phase %s failed result=%d", name, result);
        say(CRUX_LOG_ERROR, text);
    }
}

controller_framework_status_t controller_framework_start(void)
{
    static bool started;
    startup_summary_t summary = {0u, 0u};
    char text[CRUX_LOG_TEXT_MAX];

    if (started) {
        return CONTROLLER_FRAMEWORK_ERR_ALREADY_STARTED;
    }
    started = true;

    const startup_status_t status =
        startup_run_steps(steps, sizeof steps / sizeof steps[0], report, HOOKS, &summary);

    if (status != STARTUP_OK) {
        say(CRUX_LOG_ERROR, "startup stopped");
        return CONTROLLER_FRAMEWORK_ERR_STARTUP;
    }
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    /* Step 12 has decided not to call an application's start: startup supervision ends here. */
    atomic_store(&fw.startup_done, true);
    say(CRUX_LOG_INFO, "startup supervision ended in step 12 with no application");
#endif
    (void)snprintf(text, sizeof text, "startup done phases=%u failed=%u",
                   (unsigned)summary.completed, (unsigned)summary.failed);
    say(summary.failed == 0u ? CRUX_LOG_INFO : CRUX_LOG_WARN, text);
    return CONTROLLER_FRAMEWORK_OK;
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
void framework_status_controller(char *text, size_t size)
{
    (void)snprintf(text, size, "%s",
                   controller_state_name((controller_state_t)atomic_load(&fw.state)));
}

void framework_status_application(char *text, size_t size)
{
    (void)snprintf(text, size, "%s", app_state_name(APP_ABSENT));
}

bool framework_status_safe_mode(void)
{
    return atomic_load(&fw.safe_mode);
}

uint32_t framework_status_boot_counter(void)
{
    return recovery_counter();
}

void framework_status_boot(char *text, size_t size)
{
    (void)snprintf(text, size, "%s", boot_class_name(fw.boot.decision.boot_class));
}

void framework_status_watchdog(char *text, size_t size)
{
    (void)snprintf(text, size, "%s", atomic_load(&fw.armed) ? "armed" : "not-armed");
}

void framework_status_last_fault(char *text, size_t size)
{
    recovery_last_fault_text(text, size);
}

void framework_status_stack(char *text, size_t size)
{
    char name[BOOT_NAME_SIZE];
    uint32_t unused = 0u;

    if (supervisor_port_stack_min(name, sizeof name, &unused)) {
        (void)snprintf(text, size, "%s %lu", name, (unsigned long)unused);
    } else {
        (void)snprintf(text, size, "not measured");
    }
}
#endif
