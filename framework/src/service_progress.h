/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SERVICE_PROGRESS_H
#define SERVICE_PROGRESS_H

/*
 * Supervision of the Crux service threads by their progress (specification sections 4.3 and 4.4,
 * gap C8). Crux calls one registered progress function on each started service thread once per pass
 * of its loop, at least about once a second when idle (Crux <crux/service_priority_zephyr.h>). The
 * framework gives each service thread that it starts its own task watchdog channel and feeds that
 * channel from the progress function, so a thread that stops passing through its loop lets its
 * channel expire, and the supervisor latches the fault and resets as for any channel.
 *
 * The composition zone registers the progress function with Crux and maps Crux's thread identifiers
 * to the ones below (framework/compose); this module holds no Crux or Zephyr type, so host tests
 * run it with a fake port.
 *
 * Threads and order. Activation runs on the start function's thread, once per thread, right after
 * the Crux call that starts the thread returned success. Reports come on the service threads,
 * possibly on several at once and before the activation: a report reads the channel handle with one
 * atomic load and either feeds or does nothing, takes no lock and never waits, as Crux requires of
 * the progress function. A report before the activation is dropped; the activation feeds the new
 * channel at once, so timing starts there (section 4.4, "Activate").
 *
 * Crux's reboot worker is never started (section 5.1), and its identifier, which Crux Reboot also
 * reports from the framework's own reboot thread (gap C14), has no entry here, so the composition
 * zone drops it. Crux's network settings worker is not started by the framework either.
 */

#include <stdbool.h>
#include <stdint.h>

/* The Crux service threads that the framework starts. */
typedef enum {
    SERVICE_THREAD_EVENT_DRAIN = 0, /* crux_security_event_start() */
    SERVICE_THREAD_WEB_SESSION,     /* crux_web_session_start_worker() */
    SERVICE_THREAD_WEB_MANAGEMENT,  /* crux_web_management_start_worker() */
    SERVICE_THREAD_CONSOLE,         /* crux_cli_serial_start() */
    SERVICE_THREAD_COUNT,
} service_thread_t;

typedef enum {
    SERVICE_PROGRESS_OK = 0,
    SERVICE_PROGRESS_ERR_ARGUMENT = -1,       /* unknown thread, or no port or reload period */
    SERVICE_PROGRESS_ERR_ACTIVE = -2,         /* the thread already has its channel */
    SERVICE_PROGRESS_ERR_FULL = -3,           /* the channel table or the task watchdog is full */
    SERVICE_PROGRESS_ERR_NOT_REGISTERED = -4, /* Crux did not take the progress function */
} service_progress_status_t;

typedef struct {
    /* Activate a task watchdog channel, fed now; returns a handle of zero or more, or a negative
     * value. The name is borrowed for the program's life. */
    int (*channel_add)(const char *name, uint32_t reload_ms);
    /* Feed a channel; called on the reporting thread. */
    void (*channel_feed)(int handle);
    /* True when the thread of that name is to stop feeding (a fault injection of the scenarios);
     * NULL in an image without fault injection. */
    bool (*silenced)(const char *name);
} service_progress_port_t;

/* Set the port and the reload period of every service thread's channel. Before any activation, on
 * the start function's thread. */
void service_progress_init(const service_progress_port_t *port, uint32_t reload_ms);

/* Crux refused the progress function (crux_service_progress_register() failed), so nothing would
 * feed a channel: later activations add none and answer SERVICE_PROGRESS_ERR_NOT_REGISTERED, and
 * the threads stay supervised indirectly only (section 4.3). Without this, each started thread's
 * channel would expire and reset the device. On the start function's thread, after
 * service_progress_init() and before any activation; a later service_progress_init() undoes it. */
void service_progress_withdraw(void);

/* Give a started thread its channel. Returns the channel handle (zero or more) or a negative
 * service_progress_status_t. */
int service_progress_activate(service_thread_t thread);

/* A progress report of a thread, on that thread: feeds its channel when it has one. */
void service_progress_report(service_thread_t thread);

/* True when the thread has its channel. */
bool service_progress_active(service_thread_t thread);

/* The thread's name, as the channel and the fault injection name it; NULL for an unknown thread. */
const char *service_progress_name(service_thread_t thread);

#endif
