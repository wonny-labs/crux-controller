/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The start function of the controller framework: the step table of the services that the build
 * turns on, run by the portable startup sequence (startup.h), and the application interface of
 * <controller/framework.h>. Each service is reached through its port, whose implementation is in
 * the composition zone (framework/compose) or the adapter zone (framework/os) of the module, so
 * this file includes no Zephyr header.
 *
 * Steps, with the numbers of specification section 4.1 where a step is one of them:
 *   clock (1)       the Crux monotonic clock answers. Required: without it nothing can be timed.
 *                   With health supervision it also reads the reset cause once, keeps the copy and
 *                   clears the flags (gap C2), reads the retained region, updates the boot counter
 *                   and decides normal boot or safe mode (sections 5.1 and 5.2).
 *   supervisor (2)  with health supervision: the supervisor thread, which arms the hardware
 *                   watchdog with the one timeout T (gap C3) and supervises the steps after it.
 *   storage access (3, 4)  security events, the realtime clock, the storage mount and the two
 *                   roots of the credential store, the application data root when there is an
 *                   application, the credential store and Access (management_port.h, core part).
 *   app init (5)    with an application: its init on the application thread, which
 *                   registers its channel requirements, status items and parameter table; in safe
 *                   mode the application is held instead. Left out with no application.
 *   web management (6, 7, 10)  Crux Reboot with the framework's policy, the configuration service
 *                   with the application's parameter table, the status service with the captured
 *                   reset cause and the framework's and the application's items, the TLS
 *                   certificate, sessions and web management, then the HTTPS listener
 *                   (management_port.h, services part); then the framework's reboot thread.
 *   command line (9)  the framework's command tables to the Crux registry, then the Crux serial
 *                   console on the UART of the alias crux-serial0, with its first-account setup.
 *                   It needs Access, so it runs only when web management started (cli_port.h).
 *   time synchronisation (8)  the SNTP thread that sets the Crux Time realtime clock; left out
 *                   in safe mode.
 *   start prerequisites (11)  with an application: the health of the start prerequisites
 *                   (Kconfig CONFIG_CRUX_CONTROLLER_PREREQUISITE_*). Left out with no application.
 *   application (12)  with health supervision: unless held, the activation of the application's
 *                   channels and its start, on the application thread; startup supervision ends
 *                   when start returns, or when the step decides not to call it.
 * Each step from storage access on has a software deadline (Kconfig), which the supervisor
 * enforces. Without an application the two management steps run one after the other. The network
 * interface is up before main() (the Zephyr network configuration library), and Crux Logging needs
 * no start. A step after the clock that fails is reported and the controller runs without that
 * service.
 *
 * The application thread (app_port.h) runs init, start and stop, and the operator stop and start
 * and the stop of a reported fault after startup; the supervisor calls safe_state after it has
 * latched a fault (section 4.3). The application contract (app_contract.h) holds the order of those
 * calls and their clean-up.
 */

#include <controller/framework.h>

#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <crux/logging.h>
#include <crux/status.h>
#include <crux/time.h>

#include "startup.h"

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
#include "management_policy.h"
#include "management_port.h"
#include "storage_port.h"

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

#include "app_contract.h"
#include "app_port.h"
#include "app_requests.h"
#include "boot_record.h"
#include "controller_state.h"
#include "fault_injection.h"
#include "framework_control.h"
#include "framework_status.h"
#include "recovery.h"
#include "supervision.h"
#include "supervision_compose.h"
#include "supervisor_port.h"

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
#include <controller/framework_management.h>
#endif

#ifdef CONFIG_CRUX_NETIF
#include <crux/netif.h>
#endif

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

/* The public enumerations mirror the portable core's, value for value. */
_Static_assert((int)CONTROLLER_FRAMEWORK_SERVICE_COUNT == (int)SERVICE_COUNT &&
                   (int)CONTROLLER_FRAMEWORK_SERVICE_COMMAND_LINE == (int)SERVICE_COMMAND_LINE &&
                   (int)CONTROLLER_FRAMEWORK_SERVICE_NETWORK == (int)SERVICE_NETWORK,
               "the public services follow service_id_t");
_Static_assert((int)CONTROLLER_FRAMEWORK_HEALTH_FAILED == (int)SERVICE_FAILED &&
                   (int)CONTROLLER_FRAMEWORK_HEALTH_ABSENT == (int)SERVICE_ABSENT,
               "the public health values follow service_health_t");
_Static_assert((int)CONTROLLER_FRAMEWORK_STATE_RECOVERY == (int)CONTROLLER_RECOVERY &&
                   (int)CONTROLLER_FRAMEWORK_STATE_STARTING == (int)CONTROLLER_STARTING,
               "the public controller states follow controller_state_t");
_Static_assert((int)CONTROLLER_APP_STOP_FAULT == (int)APP_STOP_FAULT &&
                   (int)CONTROLLER_APP_STOP_OPERATOR == (int)APP_STOP_OPERATOR &&
                   (int)CONTROLLER_APP_STOP_PLANNED_RESET == (int)APP_STOP_PLANNED_RESET,
               "the public stop reasons follow app_stop_reason_t");

#define DEADLINE_MANAGEMENT_MS ((uint32_t)CONFIG_CRUX_CONTROLLER_DEADLINE_MANAGEMENT_MS)
#define DEADLINE_COMMAND_LINE_MS ((uint32_t)CONFIG_CRUX_CONTROLLER_DEADLINE_COMMAND_LINE_MS)
#define DEADLINE_TIME_SYNC_MS ((uint32_t)CONFIG_CRUX_CONTROLLER_DEADLINE_TIME_SYNC_MS)
#define DEADLINE_INIT_MS ((uint32_t)CONFIG_CRUX_CONTROLLER_DEADLINE_INIT_MS)
#define DEADLINE_APPLICATION_MS ((uint32_t)CONFIG_CRUX_CONTROLLER_DEADLINE_APPLICATION_MS)
#define DEADLINE_STOP_MS ((uint32_t)CONFIG_CRUX_CONTROLLER_DEADLINE_STOP_MS)
#define STABLE_PERIOD_MS ((uint64_t)CONFIG_CRUX_CONTROLLER_STABLE_PERIOD_S * 1000u)

/* The framework's own task watchdog channels: the time synchronisation thread and the reboot
 * thread. The application's requirements share the rest of the table (section 4.4, "Capacity"). */
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC
#define CHANNELS_TIME 1u
#else
#define CHANNELS_TIME 0u
#endif
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
#define CHANNELS_REBOOT 1u
#else
#define CHANNELS_REBOOT 0u
#endif
#define CHANNELS_FRAMEWORK (CHANNELS_TIME + CHANNELS_REBOOT)
#define CHANNELS_LIMIT                                                                             \
    ((size_t)CONFIG_TASK_WDT_CHANNELS < (size_t)SUPERVISION_CHANNELS_MAX                           \
         ? (size_t)CONFIG_TASK_WDT_CHANNELS                                                        \
         : (size_t)SUPERVISION_CHANNELS_MAX)
#define CHANNELS_APPLICATION                                                                       \
    (CHANNELS_LIMIT > CHANNELS_FRAMEWORK ? CHANNELS_LIMIT - CHANNELS_FRAMEWORK : 0u)

/* The start prerequisites and runtime dependencies of the build (section 7.1), one bit per
 * service_id_t. zephyr/CMakeLists.txt refuses a build that selects a service it leaves out. */
static const uint32_t prerequisites = 0u
#ifdef CONFIG_CRUX_CONTROLLER_PREREQUISITE_NETWORK
                                      | (1u << SERVICE_NETWORK)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_PREREQUISITE_STORAGE
                                      | (1u << SERVICE_STORAGE)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_PREREQUISITE_ACCESS
                                      | (1u << SERVICE_ACCESS)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_PREREQUISITE_CONFIGURATION
                                      | (1u << SERVICE_CONFIGURATION)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_PREREQUISITE_TIME
                                      | (1u << SERVICE_TIME)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_PREREQUISITE_WEB
                                      | (1u << SERVICE_WEB)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_PREREQUISITE_COMMAND_LINE
                                      | (1u << SERVICE_COMMAND_LINE)
#endif
    ;

static const uint32_t dependencies = 0u
#ifdef CONFIG_CRUX_CONTROLLER_DEPENDENCY_NETWORK
                                     | (1u << SERVICE_NETWORK)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_DEPENDENCY_STORAGE
                                     | (1u << SERVICE_STORAGE)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_DEPENDENCY_ACCESS
                                     | (1u << SERVICE_ACCESS)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_DEPENDENCY_CONFIGURATION
                                     | (1u << SERVICE_CONFIGURATION)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_DEPENDENCY_TIME
                                     | (1u << SERVICE_TIME)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_DEPENDENCY_WEB
                                     | (1u << SERVICE_WEB)
#endif
#ifdef CONFIG_CRUX_CONTROLLER_DEPENDENCY_COMMAND_LINE
                                     | (1u << SERVICE_COMMAND_LINE)
#endif
    ;

/* The requests of the application thread (app_port.h). */
#define REQUEST_INIT 0x01u
#define REQUEST_START 0x02u
#define REQUEST_OPERATOR 0x04u /* the request itself is in fw.requests (app_requests.h) */
#define REQUEST_FAULT 0x10u
#define REQUEST_PLANNED_STOP 0x20u
#else
#define DEADLINE_MANAGEMENT_MS 0u
#define DEADLINE_COMMAND_LINE_MS 0u
#define DEADLINE_TIME_SYNC_MS 0u
#endif

#define LOG_TAG "framework"

/* Step names, as the log and the last-fault record name them. The record keeps the first 15 bytes
 * (BOOT_NAME_SIZE), so the names of the application's steps and calls fit in 15. */
/* The table below spells its names out; these two are the same texts, for hook_skipped(). */
#define STEP_APPLICATION_INIT "app init"
#define STEP_PREREQUISITES "start prerequisites"
#define CALL_STOP "app stop"
#define CALL_OPERATOR_START "app start"

static void say(crux_log_level_t level, const char *text)
{
    (void)crux_log_write(level, LOG_TAG, text);
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
/* The handle that the application's entries receive. */
struct controller_app_context {
    const controller_app_t *app;
};

/* What the steps learn and the status service shows. The fields without atomics are written by the
 * start function in step 1, before the threads and the status service that read them start, or by
 * the application thread only; the others are read by the supervisor thread, the status service and
 * the application's threads while the steps run. */
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
    /* The application. */
    struct controller_app_context context;
    app_contract_t app;
    app_requests_t requests; /* operator requests and the gate of a planned reset */
    app_run_t start_result;  /* written by the application thread before it completes a call */
    atomic_int data_root;
    service_health_t reported[SERVICE_COUNT]; /* the supervisor's last report of a dependency */
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
    char fault[64];
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

/* The health that the controller state, the start decision, the status service and the
 * application see: the service's own, unless a scenario injected it down. */
static service_health_t health_of(int service)
{
    if (fault_injection_service_down(service)) {
        return SERVICE_FAILED;
    }
    return (service_health_t)atomic_load(&fw.health[service]);
}

static bool application_present(void)
{
    return app_contract_state(&fw.app) != APP_ABSENT;
}

/* The network's health from Crux NetIf (section 4.7): healthy with the link up and an address,
 * failed when the interface is not up or cannot be read, degraded otherwise. */
static void update_network_health(void)
{
#ifdef CONFIG_CRUX_NETIF
    crux_netif_status_t status;
    service_health_t health = SERVICE_FAILED;

    if (crux_netif_get_status(&status) == CRUX_OK && status.administrative_up) {
        health = status.link == CRUX_NETIF_LINK_UP && status.ipv4_available ? SERVICE_HEALTHY
                                                                            : SERVICE_DEGRADED;
    }
    set_health(SERVICE_NETWORK, health);
#endif
}

static bool prerequisites_healthy(void)
{
    for (int service = 0; service < SERVICE_COUNT; service++) {
        if ((prerequisites & (1u << (unsigned)service)) != 0u &&
            health_of(service) != SERVICE_HEALTHY) {
            return false;
        }
    }
    return true;
}

/* The runtime dependencies whose health changed since the last report: one log line each, which the
 * status service's health items and controller_app_service_health() show as well (section 4.7). */
static void report_dependencies(void)
{
    for (int service = 0; service < SERVICE_COUNT; service++) {
        const service_health_t health = health_of(service);

        if ((dependencies & (1u << (unsigned)service)) == 0u || health == fw.reported[service]) {
            continue;
        }
        char text[CRUX_LOG_TEXT_MAX];

        fw.reported[service] = health;
        (void)snprintf(text, sizeof text, "runtime dependency %s health=%s",
                       service_id_name((service_id_t)service), service_health_name(health));
        say(health == SERVICE_HEALTHY ? CRUX_LOG_INFO : CRUX_LOG_WARN, text);
    }
}

/* Once per supervisor period, on the supervisor thread: the network's health, the controller state,
 * the runtime dependencies and the successful boot (section 5.2). */
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
        .required = prerequisites | dependencies,
    };

    update_network_health();
    for (int service = 0; service < SERVICE_COUNT; service++) {
        inputs.health[service] = health_of(service);
    }
    const controller_state_t state = controller_state_decide(&inputs);

    atomic_store(&fw.state, (int)state);
    if (state != fw.logged) {
        char text[CRUX_LOG_TEXT_MAX];

        fw.logged = state;
        (void)snprintf(text, sizeof text, "controller state=%s", controller_state_name(state));
        say(state == CONTROLLER_OPERATIONAL ? CRUX_LOG_INFO : CRUX_LOG_WARN, text);
    }
    if (inputs.startup_done && application_present()) {
        report_dependencies();
    }
    if (boot_stability_update(
            &fw.stability,
            controller_successful_boot_conditions(state, app_contract_state(&fw.app)), now_ms,
            STABLE_PERIOD_MS)) {
        recovery_counter_clear();
        say(CRUX_LOG_INFO, "successful boot: boot counter cleared");
    }
    if (inputs.startup_done && fault_injection_fatal_due()) {
        say(CRUX_LOG_WARN, "fault injection: fatal error in the supervisor thread");
        supervisor_port_fatal();
    }
}

/* On the supervisor thread, once a fault is latched and its record written: the application's
 * safe_state when init has succeeded (sections 4.3 and 4.4), best effort. The application's threads
 * may still run and overwrite outputs until the reset (section 3.3). */
static void supervisor_latched(void)
{
    if (app_contract_supervisor_safe_state(&fw.app)) {
        say(CRUX_LOG_WARN, "application safe state requested by the supervisor");
    }
}

static int phase_supervisor(void)
{
    char text[CRUX_LOG_TEXT_MAX];
    const supervisor_port_config_t config = {
        .timeout_ms = (uint32_t)CONFIG_CRUX_CONTROLLER_WATCHDOG_TIMEOUT_MS,
        .period_ms = (uint32_t)CONFIG_CRUX_CONTROLLER_SUPERVISOR_PERIOD_MS,
        .tick = supervisor_tick,
        .latched = supervisor_latched,
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

static bool skip_without_application(void)
{
    return !application_present();
}

/* The application's entries, called by the application contract with the context. */
static int entry_init(void *argument)
{
    struct controller_app_context *context = argument;

    return context->app->init(context);
}

static int entry_start(void *argument)
{
    struct controller_app_context *context = argument;

    return context->app->start(context);
}

static int entry_stop(void *argument, app_stop_reason_t reason)
{
    struct controller_app_context *context = argument;

    return context->app->stop(context, (controller_app_stop_reason_t)reason);
}

static void entry_safe_state(void *argument)
{
    struct controller_app_context *context = argument;

    context->app->safe_state(context);
}

/* The application's channels through the supervisor's table, each activation in the log. A scenario
 * can refuse one. */
static int channel_add(void *port, const char *name, uint32_t reload_ms)
{
    (void)port;
    if (fault_injection_channel_refused(name)) {
        char text[CRUX_LOG_TEXT_MAX];

        (void)snprintf(text, sizeof text, "fault injection: channel %s refused", name);
        say(CRUX_LOG_WARN, text);
        return -1;
    }
    const int handle = supervisor_port_channel_add(name, reload_ms);

    if (handle >= 0) {
        char text[CRUX_LOG_TEXT_MAX];

        (void)snprintf(text, sizeof text, "application channel %s activated reload=%lu", name,
                       (unsigned long)reload_ms);
        say(CRUX_LOG_INFO, text);
    }
    return handle;
}

static void channel_remove(void *port, int handle)
{
    (void)port;
    supervisor_port_channel_delete(handle);
}

static void channel_feed(void *port, int handle)
{
    (void)port;
    supervisor_port_channel_feed(handle);
}

static const app_channel_port_t channel_port = {channel_add, channel_remove, channel_feed, NULL};

static const char *hold_name(app_hold_t hold)
{
    switch (hold) {
    case APP_HOLD_SAFE_MODE:
        return "safe mode";
    case APP_HOLD_PREREQUISITE:
        return "start prerequisite";
    case APP_HOLD_WATCHDOG:
        return "watchdog not armed";
    case APP_HOLD_NONE:
    default:
        return "none";
    }
}

static void say_application(crux_log_level_t level, const char *what)
{
    char text[CRUX_LOG_TEXT_MAX];

    (void)snprintf(text, sizeof text, "application %s state=%s", what,
                   app_state_name(app_contract_state(&fw.app)));
    say(level, text);
}

static app_start_conditions_t start_conditions(void)
{
    return (app_start_conditions_t){
        .safe_mode = atomic_load(&fw.safe_mode),
        .prerequisites_healthy = prerequisites_healthy(),
        .watchdog_armed = atomic_load(&fw.armed),
#ifdef CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG
        .start_without_watchdog = true,
#else
        .start_without_watchdog = false,
#endif
    };
}

/* Run a start on the application thread and say what came of it. */
static app_run_t run_start(bool operator)
{
    const app_start_conditions_t conditions = start_conditions();
    const app_run_t result = app_contract_start(&fw.app, &conditions, operator);

    switch (result) {
    case APP_RUN_STARTED:
        say_application(CRUX_LOG_INFO, operator? "started by an operator" : "started");
        break;
    case APP_RUN_HELD: {
        char text[CRUX_LOG_TEXT_MAX];

        (void)snprintf(text, sizeof text,
                       "application held reason=%s",
                       operator? "start prerequisite" : hold_name(app_contract_hold(&fw.app)));
        say(CRUX_LOG_WARN, text);
        break;
    }
    case APP_RUN_FAILED:
        say_application(CRUX_LOG_ERROR, "fault: activation or start failed");
        break;
    case APP_RUN_NOT_NOW:
    default:
        say_application(CRUX_LOG_WARN, "not started");
        break;
    }
    return result;
}

/* A stop after startup, with its deadline (section 4.8): an error is a hang, which the supervisor
 * carries out as for a deadline. */
static void run_stop(app_stop_reason_t reason)
{
    supervisor_port_step_begin(CALL_STOP, DEADLINE_STOP_MS);
    const app_stop_t result = app_contract_stop(&fw.app, reason);

    supervisor_port_step_end();
    if (result == APP_STOP_HANG) {
        say(CRUX_LOG_ERROR, "application stop returned an error: a hang, feeding stops");
        supervisor_port_latch(BOOT_FAULT_STOP, CALL_STOP);
    } else if (result == APP_STOPPED_OK) {
        say_application(reason == APP_STOP_FAULT ? CRUX_LOG_ERROR : CRUX_LOG_INFO,
                        reason == APP_STOP_FAULT ? "fault: stopped and released" : "stopped");
    } else {
        say_application(CRUX_LOG_WARN, "not stopped");
    }
}

/* The work of the application thread, one batch of requests at a time (app_port.h). */
static void application_work(uint32_t requests)
{
    if ((requests & REQUEST_INIT) != 0u) {
        const int result = app_contract_run_init(&fw.app);
        char text[CRUX_LOG_TEXT_MAX];

        (void)snprintf(text, sizeof text, "application init result=%d channels=%u state=%s", result,
                       (unsigned)app_contract_requirement_count(&fw.app),
                       app_state_name(app_contract_state(&fw.app)));
        say(result == 0 ? CRUX_LOG_INFO : CRUX_LOG_ERROR, text);
    }
    if ((requests & REQUEST_START) != 0u) {
        fw.start_result = run_start(false);
    }
    /* A planned reset first. Its gate closed before it was posted, so no operator request is taken
     * after it and no start runs between this stop and the reset (app_requests.h). */
    if ((requests & REQUEST_PLANNED_STOP) != 0u && app_contract_state(&fw.app) == APP_RUNNING) {
        say(CRUX_LOG_INFO, "planned reset: stopping the application");
        run_stop(APP_STOP_PLANNED_RESET);
    }
    /* Only the newest operator request: a newer stop or start replaced an older one. */
    const app_request_t operator_request = app_requests_take(&fw.requests);

    if (operator_request == APP_REQUEST_STOP) {
        run_stop(APP_STOP_OPERATOR);
    } else if (operator_request == APP_REQUEST_START) {
        supervisor_port_step_begin(CALL_OPERATOR_START, DEADLINE_APPLICATION_MS);
        (void)run_start(true);
        supervisor_port_step_end();
    }
    /* A fault reported by a running application, whatever woke the thread. */
    if (app_contract_take_fault(&fw.app)) {
        if (app_contract_state(&fw.app) == APP_RUNNING) {
            say(CRUX_LOG_ERROR, "application reported a fault: stopping it");
            run_stop(APP_STOP_FAULT);
        } else {
            say_application(CRUX_LOG_WARN, "fault report dropped: not running");
        }
    }
}

static int phase_application_init(void)
{
    if (atomic_load(&fw.safe_mode)) {
        app_contract_hold_safe_mode(&fw.app);
        say(CRUX_LOG_WARN, "application held: safe mode");
        return 0;
    }
    app_port_call(REQUEST_INIT);
    return app_contract_state(&fw.app) == APP_INITIALISED ? 0 : -1;
}

/* Step 11: the health of each start prerequisite, in one log line. A prerequisite that is not
 * healthy fails the step; step 12 then holds the application (section 4.7). */
static int phase_prerequisites(void)
{
    char text[CRUX_LOG_TEXT_MAX];
    size_t length = 0u;

    if (prerequisites == 0u) {
        say(CRUX_LOG_INFO, "start prerequisites: none selected");
        return 0;
    }
    const bool healthy = prerequisites_healthy();

    (void)snprintf(text, sizeof text,
                   "start prerequisites %s:", healthy ? "healthy" : "not healthy");
    for (int service = 0; service < SERVICE_COUNT; service++) {
        length = strlen(text);
        if ((prerequisites & (1u << (unsigned)service)) != 0u && length < sizeof text) {
            (void)snprintf(&text[length], sizeof text - length, " %s=%s",
                           service_id_name((service_id_t)service),
                           service_health_name(health_of(service)));
        }
    }
    say(healthy ? CRUX_LOG_INFO : CRUX_LOG_WARN, text);
    return healthy ? 0 : -1;
}

static int phase_application(void)
{
    if (!application_present()) {
        say(CRUX_LOG_INFO,
            atomic_load(&fw.safe_mode) ? "no application: safe mode" : "no application");
        return 0;
    }
    if (app_contract_state(&fw.app) != APP_INITIALISED) {
        say_application(CRUX_LOG_WARN, "not started:");
        return 0;
    }
    app_port_call(REQUEST_START);
    return fw.start_result == APP_RUN_FAILED ? -1 : 0;
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

/* A step is left out for safe mode (time synchronisation) or because there is no application (the
 * application's own steps). */
static void hook_skipped(const char *name)
{
    char text[CRUX_LOG_TEXT_MAX];
    const bool application_step =
        strcmp(name, STEP_APPLICATION_INIT) == 0 || strcmp(name, STEP_PREREQUISITES) == 0;

    (void)snprintf(text, sizeof text, "phase %s left out: %s", name,
                   application_step && !application_present() ? "no application" : "safe mode");
    say(application_step ? CRUX_LOG_INFO : CRUX_LOG_WARN, text);
}

static const startup_hooks_t hooks = {hook_begin, hook_end, hook_skipped};
#define HOOKS (&hooks)
#define SKIP_IN_SAFE_MODE skip_in_safe_mode
#define SKIP_WITHOUT_APPLICATION skip_without_application
#else
#define HOOKS NULL
#define SKIP_IN_SAFE_MODE NULL
#define SKIP_WITHOUT_APPLICATION NULL
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
/* True once the services part started the configuration and status services, with or without web
 * management: the command line needs them and Access, and it is the operator's path to recover a
 * refused TLS certificate (section 4.1). */
static bool management_services_started;
/* True once the core part started storage and Access. */
static bool core_started;

static management_port_config_t management_config(void)
{
    management_port_config_t config = {
        .policy = management_policy_get(),
        .platform_version = CONTROLLER_PLATFORM_VERSION,
        .project_version = CONTROLLER_PROJECT_VERSION,
    };
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    size_t app_items = 0u;
    const void *items = app_contract_status_items(&fw.app, &app_items);

    config.reset_cause_given = true;
    config.reset_cause_status = (int)fw.cause_status;
    config.reset_cause_supported = fw.cause.supported;
    config.reset_cause_causes = fw.cause.causes;
    config.status_items =
        supervision_compose_status_items(items, app_items, &config.status_item_count);
    config.after_events = supervision_compose_reboot_start;
    config.bind_app_root = application_present();
    config.parameters = app_contract_parameters(&fw.app, &config.parameter_count);
#endif
    return config;
}

static int phase_storage_and_access(void)
{
    const management_port_config_t config = management_config();
    const management_port_status_t status = management_port_start_core(&config);

    core_started = status == MANAGEMENT_PORT_OK;
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    const service_health_t health = core_started ? SERVICE_HEALTHY : SERVICE_FAILED;

    set_health(SERVICE_STORAGE, health);
    set_health(SERVICE_ACCESS, health);
    if (core_started && application_present()) {
        atomic_store(&fw.data_root, STORAGE_PORT_APP_ROOT);
    }
#endif
    return (int)status;
}

static int phase_management(void)
{
    /* The application's items and parameters are known now: init has run. */
    const management_port_config_t config = management_config();
    const management_port_status_t status =
        core_started ? management_port_start_services(&config) : MANAGEMENT_PORT_ERR_NOT_READY;

    /* A refused TLS certificate turns only web management off (section 4.1). */
    management_services_started =
        status == MANAGEMENT_PORT_OK || status == MANAGEMENT_PORT_ERR_TLS_CERTIFICATE;
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    const service_health_t health = management_services_started ? SERVICE_HEALTHY : SERVICE_FAILED;

    set_health(SERVICE_CONFIGURATION, health);
    set_health(SERVICE_STATUS, health);
    set_health(SERVICE_WEB, status == MANAGEMENT_PORT_OK ? SERVICE_HEALTHY : SERVICE_FAILED);
#endif
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
    if (management_services_started) {
        (void)reboot_port_start();
    }
#endif
    return (int)status;
}
#endif

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
/* The phase result when the management services, or Access before them, did not start. */
#define PHASE_COMMAND_LINE_NO_ACCESS (-100)

static int phase_command_line(void)
{
    /* The first account gets the role of the management policy that manages accounts. */
    cli_port_config_t config = {.setup_role = MANAGEMENT_ROLE_ADMINISTRATOR};

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    config.framework_commands = true;
#endif
    if (!management_services_started) {
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
    {{"storage access", phase_storage_and_access, false}, DEADLINE_MANAGEMENT_MS, NULL},
#endif
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    {{"app init", phase_application_init, false}, DEADLINE_INIT_MS, SKIP_WITHOUT_APPLICATION},
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
    {{"start prerequisites", phase_prerequisites, false},
     DEADLINE_APPLICATION_MS,
     SKIP_WITHOUT_APPLICATION},
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

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
/* Prepare the application before the steps: the contract, the context and the thread. */
static controller_framework_status_t prepare_application(const controller_app_t *app)
{
    const app_entries_t entries = {entry_init, entry_start, entry_stop, entry_safe_state,
                                   &fw.context};

    atomic_store(&fw.data_root, -1);
    app_requests_init(&fw.requests);
    for (int service = 0; service < SERVICE_COUNT; service++) {
        set_health((service_id_t)service, SERVICE_ABSENT);
    }
    fw.context.app = app;
    if (app == NULL) {
        app_contract_init(&fw.app, NULL, &channel_port, 0u);
        return CONTROLLER_FRAMEWORK_OK;
    }
    if (app->init == NULL || app->start == NULL || app->stop == NULL || app->safe_state == NULL) {
        return CONTROLLER_FRAMEWORK_ERR_INVALID_DESCRIPTOR;
    }
    app_contract_init(&fw.app, &entries, &channel_port, CHANNELS_APPLICATION);
    if (app_port_start(application_work) != 0) {
        return CONTROLLER_FRAMEWORK_ERR_INVALID_DESCRIPTOR;
    }
    return CONTROLLER_FRAMEWORK_OK;
}
#endif

controller_framework_status_t controller_framework_start(const controller_app_t *app)
{
    static bool started;
    startup_summary_t summary = {0u, 0u};
    char text[CRUX_LOG_TEXT_MAX];

    if (started) {
        return CONTROLLER_FRAMEWORK_ERR_ALREADY_STARTED;
    }
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    /* A descriptor without a mandatory entry is refused, and nothing runs (section 3.3). */
    const controller_framework_status_t prepared = prepare_application(app);

    if (prepared != CONTROLLER_FRAMEWORK_OK) {
        say(CRUX_LOG_ERROR, "descriptor refused: an entry is missing");
        return prepared;
    }
#else
    if (app != NULL) {
        say(CRUX_LOG_ERROR, "descriptor refused: an application needs health supervision");
        return CONTROLLER_FRAMEWORK_ERR_INVALID_DESCRIPTOR;
    }
#endif
    started = true;

    const startup_status_t status =
        startup_run_steps(steps, sizeof steps / sizeof steps[0], report, HOOKS, &summary);

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    /* No step calls start from here on, so a planned reset may go ahead; operator requests open
     * only when startup supervision ended in step 12. */
    app_requests_startup_returned(&fw.requests, status == STARTUP_OK);
#endif
    if (status != STARTUP_OK) {
        say(CRUX_LOG_ERROR, "startup stopped");
        return CONTROLLER_FRAMEWORK_ERR_STARTUP;
    }
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    /* Step 12 has returned: start returned, or the step decided not to call it, so startup
     * supervision ends here (section 4.2). */
    atomic_store(&fw.startup_done, true);
    if (application_present()) {
        (void)snprintf(text, sizeof text,
                       "startup supervision ended in step 12 application state=%s",
                       app_state_name(app_contract_state(&fw.app)));
        say(CRUX_LOG_INFO, text);
    } else {
        say(CRUX_LOG_INFO, "startup supervision ended in step 12 with no application");
    }
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
    (void)snprintf(text, size, "%s", app_state_name(app_contract_state(&fw.app)));
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

void framework_status_health(int service, char *text, size_t size)
{
    const service_health_t health =
        service >= 0 && service < SERVICE_COUNT ? health_of(service) : SERVICE_ABSENT;

    (void)snprintf(text, size, "%s", service_health_name(health));
}

bool framework_status_application_items(void)
{
    return app_contract_items_available(&fw.app);
}

/* An operator request from device management, carried out on the application thread. Before the
 * end of startup supervision the step table owns the supervisor's step deadline, so a request is
 * refused then; during a planned reset it is refused too (app_requests.h). */
static framework_control_t control(app_request_t request)
{
    if (!application_present()) {
        return FRAMEWORK_CONTROL_NO_APPLICATION;
    }
    switch (app_requests_post(&fw.requests, request)) {
    case APP_REQUEST_ACCEPTED:
        app_port_post(REQUEST_OPERATOR);
        return FRAMEWORK_CONTROL_REQUESTED;
    case APP_REQUEST_REFUSED_RESET:
        return FRAMEWORK_CONTROL_RESETTING;
    case APP_REQUEST_REFUSED_STARTING:
    case APP_REQUEST_INVALID:
    default:
        return FRAMEWORK_CONTROL_STARTING;
    }
}

framework_control_t framework_control_application_stop(void)
{
    return control(APP_REQUEST_STOP);
}

framework_control_t framework_control_application_start(void)
{
    return control(APP_REQUEST_START);
}

bool framework_control_restart_allowed(void)
{
    return !application_present() || app_requests_reset_allowed(&fw.requests);
}

void framework_control_planned_reset(void)
{
    /* The gate closes before the request is posted. The application thread then decides whether
     * the application runs, after any batch that was running, so a start that it carried out
     * before is stopped and a start that waits is dropped. */
    if (application_present() && app_requests_plan_reset(&fw.requests)) {
        app_port_call(REQUEST_PLANNED_STOP);
    }
}

void framework_control_reset_abandoned(void)
{
    app_requests_reset_abandoned(&fw.requests);
}

/* The application interface (<controller/framework.h>). Each call checks that its context is the
 * framework's; any other pointer is refused or ignored. */
static bool context_valid(const controller_app_context_t *context)
{
    return context != NULL && context == &fw.context && fw.context.app != NULL;
}

static controller_app_result_t result_of(app_contract_status_t status)
{
    switch (status) {
    case APP_CONTRACT_OK:
        return CONTROLLER_APP_OK;
    case APP_CONTRACT_ERR_CLOSED:
        return CONTROLLER_APP_ERR_CLOSED;
    case APP_CONTRACT_ERR_DUPLICATE:
        return CONTROLLER_APP_ERR_DUPLICATE;
    case APP_CONTRACT_ERR_FULL:
        return CONTROLLER_APP_ERR_FULL;
    case APP_CONTRACT_ERR_INVALID:
    default:
        return CONTROLLER_APP_ERR_INVALID;
    }
}

void *controller_app_user_data(const controller_app_context_t *context)
{
    return context_valid(context) ? context->app->user_data : NULL;
}

controller_app_result_t controller_app_channel_register(controller_app_context_t *context,
                                                        const char *name, uint32_t reload_ms,
                                                        controller_app_channel_t *channel)
{
    size_t index = 0u;

    if (!context_valid(context) || channel == NULL) {
        return CONTROLLER_APP_ERR_INVALID;
    }
    const app_contract_status_t status =
        app_contract_register_channel(&fw.app, name, reload_ms, &index);

    if (status == APP_CONTRACT_OK) {
        channel->index = index;
    }
    return result_of(status);
}

void controller_app_channel_feed(controller_app_context_t *context,
                                 controller_app_channel_t channel)
{
    if (context_valid(context)) {
        app_contract_feed(&fw.app, channel.index);
    }
}

int controller_app_data_root(const controller_app_context_t *context)
{
    return context_valid(context) ? atomic_load(&fw.data_root) : -1;
}

controller_framework_state_t
controller_app_controller_state(const controller_app_context_t *context)
{
    (void)context;
    return (controller_framework_state_t)atomic_load(&fw.state);
}

controller_framework_health_t controller_app_service_health(const controller_app_context_t *context,
                                                            controller_framework_service_t service)
{
    (void)context;
    /* The enumeration may be unsigned (short enums on a board), so one comparison covers both ends.
     */
    if ((unsigned)service >= (unsigned)SERVICE_COUNT) {
        return CONTROLLER_FRAMEWORK_HEALTH_ABSENT;
    }
    return (controller_framework_health_t)health_of((int)service);
}

void controller_app_report_fault(controller_app_context_t *context)
{
    if (context_valid(context)) {
        app_contract_report_fault(&fw.app);
        app_port_post(REQUEST_FAULT);
    }
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
controller_app_result_t controller_app_status_register(controller_app_context_t *context,
                                                       const crux_mgmt_status_item_t *items,
                                                       size_t count)
{
    if (!context_valid(context)) {
        return CONTROLLER_APP_ERR_INVALID;
    }
    if (count > (size_t)CONFIG_CRUX_CONTROLLER_APP_STATUS_ITEMS) {
        return CONTROLLER_APP_ERR_FULL;
    }
    return result_of(app_contract_register_status(&fw.app, items, count));
}

controller_app_result_t
controller_app_parameters_register(controller_app_context_t *context,
                                   const crux_config_service_entry_t *entries, size_t count)
{
    if (!context_valid(context)) {
        return CONTROLLER_APP_ERR_INVALID;
    }
    if (count > (size_t)CRUX_CONFIG_SERVICE_MAX) {
        return CONTROLLER_APP_ERR_FULL;
    }
    return result_of(app_contract_register_parameters(&fw.app, entries, count));
}
#endif
#endif
