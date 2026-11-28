/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The adapter zone of the supervisor (framework/src/supervisor_port.h): the supervisor thread, the
 * single Crux watchdog token, the Zephyr task watchdog and the stack measurement of the status
 * service. Every decision is the portable core's (framework/src/supervision.h); this file holds the
 * thread, the lock and the clock, and carries the decision out.
 *
 * The pattern is Crux's documented one for several activities: one thread holds the watchdog token
 * and feeds only while every activity has made progress, and the task watchdog runs without a
 * hardware fallback (task_wdt_init(NULL)), so each channel callback only records the expiry and the
 * supervisor stops feeding when it sees one. Crux System refuses a build with
 * CONFIG_TASK_WDT_HW_FALLBACK, and every channel has a callback, so no channel resets the device on
 * its own.
 *
 * Status: built in CI for the board and run on native_sim; never run on a board.
 */

#include "../src/recovery.h"
#include "../src/supervision.h"
#include "../src/supervisor_port.h"

#include <crux/logging.h>
#include <crux/status.h>
#include <crux/system.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/task_wdt/task_wdt.h>

#define LOG_TAG "supervisor"

/* The supervisor band of the reference configuration (specification section 7.4): above the startup
 * thread (8), below the application band (3 to 6). */
#define SUPERVISOR_PRIORITY 7
#define SUPERVISOR_STACK_BYTES 3072
/* The stacks are measured once every this many periods. */
#define STACK_EVERY 10u

BUILD_ASSERT(
    !IS_ENABLED(CONFIG_TASK_WDT_HW_FALLBACK),
    "the supervisor feeds the one Crux watchdog itself: no task watchdog hardware fallback");
BUILD_ASSERT(CONFIG_TASK_WDT_CHANNELS >= 2, "the framework needs task watchdog channels");

static K_THREAD_STACK_DEFINE(supervisor_stack, SUPERVISOR_STACK_BYTES);
static struct k_thread supervisor_thread;

static struct k_spinlock lock;
static supervision_t state;
static supervisor_port_config_t config;
static crux_watchdog_t watchdog;
static bool armed;
static bool started;

/* The channel table: a name and a task watchdog identifier per handle. A slot is free when its name
 * is NULL; a deleted application channel frees its slot (specification section 4.4). The names that
 * the supervisor passes to its poll cover every slot, so channel_count is the table's size. */
static const char *channel_names[SUPERVISION_CHANNELS_MAX];
static int channel_ids[SUPERVISION_CHANNELS_MAX];
static const size_t channel_count = SUPERVISION_CHANNELS_MAX;
/* The slot number of each handle, whose address is the callback's argument. */
static const size_t slot_numbers[SUPERVISION_CHANNELS_MAX] = {0, 1, 2,  3,  4,  5,  6,  7,
                                                              8, 9, 10, 11, 12, 13, 14, 15};
BUILD_ASSERT(SUPERVISION_CHANNELS_MAX == 16u, "slot_numbers lists every slot");
BUILD_ASSERT(SUPERVISION_CHANNELS_MAX <= 32u, "the expiry bits fit one atomic_t");
/* One bit per handle whose channel expired; set in the timer callback, read by the thread. A slot
 * whose bit is set is never given again before the reset. */
static atomic_t expired;

/* The last stack measurement. */
static char stack_name[BOOT_NAME_SIZE];
static uint32_t stack_unused;
static bool stack_measured;

static void say(crux_log_level_t level, const char *text)
{
    (void)crux_log_write(level, LOG_TAG, text);
}

/* The callback of every channel. It runs in the task watchdog's timer callback: it records the
 * expiry of its handle and nothing else, and it may run again before the reset. */
static void channel_expired(int channel_id, void *user_data)
{
    ARG_UNUSED(channel_id);
    const size_t *slot = user_data;

    (void)atomic_or(&expired, (atomic_val_t)BIT(*slot));
}

#if defined(CONFIG_THREAD_STACK_INFO) && defined(CONFIG_INIT_STACKS) &&                            \
    defined(CONFIG_THREAD_NAME) && defined(CONFIG_THREAD_MONITOR)
struct stack_search {
    char name[BOOT_NAME_SIZE];
    size_t unused;
    bool found;
};

static void stack_visit(const struct k_thread *thread, void *user_data)
{
    struct stack_search *search = user_data;
    size_t unused = 0;

    if (k_thread_stack_space_get(thread, &unused) != 0) {
        return;
    }
    if (!search->found || unused < search->unused) {
        const char *name = k_thread_name_get((k_tid_t)thread);

        search->found = true;
        search->unused = unused;
        (void)snprintf(search->name, sizeof search->name, "%s",
                       name != NULL && name[0] != '\0' ? name : "unnamed");
    }
}

static void measure_stacks(void)
{
    struct stack_search search = {.found = false};

    k_thread_foreach_unlocked(stack_visit, &search);
    if (search.found) {
        const k_spinlock_key_t key = k_spin_lock(&lock);

        memcpy(stack_name, search.name, sizeof stack_name);
        stack_unused = (uint32_t)search.unused;
        stack_measured = true;
        k_spin_unlock(&lock, key);
    }
}
#else
static void measure_stacks(void)
{
}
#endif

/* The latch: feeding has stopped already, because the thread does not feed on this pass. Write the
 * record, best effort, then the latched function (the application's safe_state), then reset in
 * software when no watchdog will. */
static void latched(boot_fault_reason_t reason, const char *name)
{
    char text[CRUX_LOG_TEXT_MAX];

    recovery_fault(reason, name, (uint32_t)k_uptime_get(), 0u);
    if (config.latched != NULL) {
        config.latched();
    }
    (void)snprintf(text, sizeof text, "fault latched reason=%s name=%s: feeding stopped, %s",
                   boot_fault_reason_name(reason), name,
                   armed ? "the watchdog resets the device" : "software reset requested");
    say(CRUX_LOG_ERROR, text);
    if (!armed) {
        const crux_status_t reset = crux_system_reset();

        (void)snprintf(text, sizeof text, "software reset refused status=%d", (int)reset);
        say(CRUX_LOG_ERROR, text);
    }
}

static void supervisor_run(void *unused0, void *unused1, void *unused2)
{
    ARG_UNUSED(unused0);
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    uint32_t pass = 0u;

    for (;;) {
        const uint64_t now = (uint64_t)k_uptime_get();
        boot_fault_reason_t reason = BOOT_FAULT_NONE;
        char name[BOOT_NAME_SIZE] = "";
        k_spinlock_key_t key = k_spin_lock(&lock);
        const supervision_channels_t channels = {channel_names, channel_count,
                                                 (uint32_t)atomic_get(&expired)};
        const supervision_action_t action = supervision_poll(&state, now, &channels);
        /* A fault latched from outside (supervisor_port_latch()) is carried out here, once. */
        const bool reported =
            action == SUPERVISION_STOPPED && supervision_take_report(&state, &reason, name);

        if (action == SUPERVISION_LATCH) {
            reason = state.reason;
            memcpy(name, state.name, sizeof name);
        }
        k_spin_unlock(&lock, key);

        if (action == SUPERVISION_FEED) {
            if (armed) {
                (void)crux_watchdog_feed(watchdog);
            }
            if (config.tick != NULL) {
                config.tick(now);
            }
            if (pass % STACK_EVERY == 0u) {
                measure_stacks();
            }
        } else if (action == SUPERVISION_LATCH || reported) {
            latched(reason, name);
        }
        pass++;
        k_msleep((int32_t)config.period_ms);
    }
}

supervisor_port_status_t supervisor_port_start(const supervisor_port_config_t *configuration,
                                               int *watchdog_status)
{
    if (started || configuration == NULL ||
        !supervision_timing_valid(configuration->timeout_ms, configuration->period_ms)) {
        return SUPERVISOR_PORT_ERR;
    }
    started = true;
    config = *configuration;
    supervision_init(&state);
    for (size_t slot = 0; slot < channel_count; slot++) {
        channel_ids[slot] = -1;
    }
    /* The task watchdog without hardware: each channel only reports to the supervisor. */
    if (task_wdt_init(NULL) != 0) {
        say(CRUX_LOG_ERROR, "task watchdog not started: framework threads are not supervised");
    }

    const crux_status_t result = crux_watchdog_start(config.timeout_ms, &watchdog);

    armed = result == CRUX_OK;
    if (watchdog_status != NULL) {
        *watchdog_status = (int)result;
    }
    (void)k_thread_create(&supervisor_thread, supervisor_stack,
                          K_THREAD_STACK_SIZEOF(supervisor_stack), supervisor_run, NULL, NULL, NULL,
                          K_PRIO_PREEMPT(SUPERVISOR_PRIORITY), 0, K_NO_WAIT);
    (void)k_thread_name_set(&supervisor_thread, "supervisor");
    return armed ? SUPERVISOR_PORT_ARMED : SUPERVISOR_PORT_NOT_ARMED;
}

void supervisor_port_step_begin(const char *name, uint32_t deadline_ms)
{
    const k_spinlock_key_t key = k_spin_lock(&lock);

    supervision_step_begin(&state, (uint64_t)k_uptime_get(), name, deadline_ms);
    k_spin_unlock(&lock, key);
}

void supervisor_port_step_end(void)
{
    const k_spinlock_key_t key = k_spin_lock(&lock);

    supervision_step_end(&state);
    k_spin_unlock(&lock, key);
}

/* A free slot: no name, and no expiry recorded for it. -1 when the table is full. Under the lock.
 */
static int free_slot(void)
{
    const uint32_t gone = (uint32_t)atomic_get(&expired);

    for (size_t slot = 0; slot < channel_count; slot++) {
        if (channel_names[slot] == NULL && (gone & BIT(slot)) == 0u) {
            return (int)slot;
        }
    }
    return -1;
}

int supervisor_port_channel_add(const char *name, uint32_t reload_ms)
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    const int handle = name != NULL && reload_ms != 0u ? free_slot() : -1;

    if (handle < 0) {
        k_spin_unlock(&lock, key);
        return -1;
    }
    channel_names[handle] = name;
    channel_ids[handle] = -1;
    k_spin_unlock(&lock, key);

    /* task_wdt_add() feeds the new channel at once, so timing starts here. */
    const int id = task_wdt_add(reload_ms, channel_expired, (void *)&slot_numbers[handle]);

    key = k_spin_lock(&lock);
    if (id < 0) {
        channel_names[handle] = NULL;
    } else {
        channel_ids[handle] = id;
    }
    k_spin_unlock(&lock, key);
    return id < 0 ? -1 : handle;
}

void supervisor_port_channel_feed(int handle)
{
    if (handle >= 0 && (size_t)handle < channel_count && channel_ids[handle] >= 0) {
        (void)task_wdt_feed(channel_ids[handle]);
    }
}

void supervisor_port_channel_delete(int handle)
{
    if (handle < 0 || (size_t)handle >= channel_count) {
        return;
    }
    k_spinlock_key_t key = k_spin_lock(&lock);
    const int id = channel_ids[handle];

    channel_ids[handle] = -1;
    k_spin_unlock(&lock, key);
    if (id >= 0) {
        (void)task_wdt_delete(id);
    }
    /* The name goes last, so an expiry that the timer recorded before the delete still names the
     * channel in the record. */
    key = k_spin_lock(&lock);
    channel_names[handle] = NULL;
    k_spin_unlock(&lock, key);
}

void supervisor_port_latch(boot_fault_reason_t reason, const char *name)
{
    const k_spinlock_key_t key = k_spin_lock(&lock);

    (void)supervision_latch(&state, reason, name);
    k_spin_unlock(&lock, key);
}

bool supervisor_port_stack_min(char *name, size_t size, uint32_t *unused_bytes)
{
    char copy[BOOT_NAME_SIZE];
    const k_spinlock_key_t key = k_spin_lock(&lock);
    const bool measured = stack_measured;
    const uint32_t unused = stack_unused;

    memcpy(copy, stack_name, sizeof copy);
    k_spin_unlock(&lock, key);
    if (measured) {
        if (name != NULL && size > 0u) {
            (void)snprintf(name, size, "%s", copy);
        }
        if (unused_bytes != NULL) {
            *unused_bytes = unused;
        }
    }
    return measured;
}

uint64_t supervisor_port_uptime_ms(void)
{
    return (uint64_t)k_uptime_get();
}

void supervisor_port_fatal(void)
{
    k_oops();
}

void supervisor_port_stall(void)
{
    for (;;) {
        k_sleep(K_FOREVER);
    }
}
