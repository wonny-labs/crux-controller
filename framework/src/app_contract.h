/* SPDX-License-Identifier: Apache-2.0 */
#ifndef APP_CONTRACT_H
#define APP_CONTRACT_H

/*
 * The application contract of the controller framework (specification sections 3 and 4.4 to 4.8):
 * the registrations that an application makes in init, the task watchdog channel lifecycle, and
 * the calls of init, start, stop and safe_state with the clean-up that each failure needs. Plain C
 * with ISO C includes only (tests/host/test_app_contract.c).
 *
 * Who calls what (section 3.3):
 *   - one framework thread calls app_contract_run_init(), app_contract_start() and
 *     app_contract_stop(), never two at once; the deadline of each call is the caller's (the
 *     supervisor enforces it), so nothing here waits or measures time;
 *   - any application thread calls app_contract_feed() and app_contract_report_fault();
 *   - the supervisor thread calls app_contract_supervisor_safe_state() once it has latched a fault;
 *   - any thread reads app_contract_state() and app_contract_items_available().
 * The fields that more than one thread reads are atomics; the others belong to the framework
 * thread.
 *
 * A channel requirement is a name and a reload period that init registers; it becomes an active
 * channel through the channel port immediately before start, and the port's handle may change at
 * each activation, so an application feeds through the index that its registration returned.
 */

#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "controller_state.h"

/* Most channel requirements of one application; the capacity given to app_contract_init() is at
 * most this. */
#define APP_CONTRACT_CHANNELS_MAX 8u
/* Longest channel name, in bytes without the terminator. */
#define APP_CONTRACT_NAME_MAX 31u

typedef enum {
    APP_STOP_OPERATOR = 0, /* an operator stop */
    APP_STOP_PLANNED_RESET,
    APP_STOP_FAULT, /* the application reported a fault */
} app_stop_reason_t;

/* The four entries of the descriptor (section 3.1), each called with the same argument. */
typedef struct {
    int (*init)(void *argument);
    int (*start)(void *argument);
    int (*stop)(void *argument, app_stop_reason_t reason);
    void (*safe_state)(void *argument);
    void *argument;
} app_entries_t;

/* True when every entry is there (section 3.3: a descriptor without a mandatory entry is refused).
 */
bool app_entries_complete(const app_entries_t *entries);

/* The task watchdog behind the active channels. add returns a handle of zero or more, or a negative
 * value for a refusal; it feeds the new channel at once. */
typedef struct {
    int (*add)(void *port, const char *name, uint32_t reload_ms);
    void (*remove)(void *port, int handle);
    void (*feed)(void *port, int handle);
    void *port;
} app_channel_port_t;

typedef enum {
    APP_CONTRACT_OK = 0,
    APP_CONTRACT_ERR_INVALID = -1,   /* an argument is missing or out of range */
    APP_CONTRACT_ERR_CLOSED = -2,    /* not inside init */
    APP_CONTRACT_ERR_DUPLICATE = -3, /* the name or the table is registered already */
    APP_CONTRACT_ERR_FULL = -4,      /* beyond the free channel capacity */
} app_contract_status_t;

typedef struct {
    const char *name; /* borrowed for the program's life */
    uint32_t reload_ms;
    atomic_int handle; /* the port's handle while active, otherwise -1 */
} app_requirement_t;

typedef struct {
    app_entries_t entries;
    app_channel_port_t channels;
    app_requirement_t requirements[APP_CONTRACT_CHANNELS_MAX];
    atomic_size_t requirement_count;
    size_t capacity;
    bool registration_open;
    const void *status_items; /* an array that the composition interprets; NULL for none */
    size_t status_count;
    const void *parameters; /* the same, for the parameter table */
    size_t parameter_count;
    atomic_bool released;    /* registrations released: items and parameters unavailable */
    atomic_bool initialised; /* init succeeded in this boot */
    atomic_bool fault_reported;
    atomic_int state; /* app_state_t */
    app_hold_t hold;  /* the reason, while held */
} app_contract_t;

/*
 * Prepare the contract. With complete entries the state is not initialised; with entries NULL the
 * state is absent (the base image) and every call below refuses or does nothing. capacity is the
 * free channel capacity, cut to APP_CONTRACT_CHANNELS_MAX.
 */
void app_contract_init(app_contract_t *contract, const app_entries_t *entries,
                       const app_channel_port_t *channels, size_t capacity);

/* Registrations, inside init only. A channel's index goes to *index. A reload period of zero, a
 * name already registered, a name longer than APP_CONTRACT_NAME_MAX, or one more than the capacity
 * is refused. Status items and parameters are one table each, with at least one entry. */
app_contract_status_t app_contract_register_channel(app_contract_t *contract, const char *name,
                                                    uint32_t reload_ms, size_t *index);
app_contract_status_t app_contract_register_status(app_contract_t *contract, const void *items,
                                                   size_t count);
app_contract_status_t app_contract_register_parameters(app_contract_t *contract,
                                                       const void *parameters, size_t count);

/* Feed the active channel of a registration index. Does nothing while the channel is not active. */
void app_contract_feed(app_contract_t *contract, size_t index);

/*
 * Step 5: call init with the registrations open. On success the state is initialised. On failure
 * safe_state runs, the registrations are released and the state is fault; start and stop are not
 * called after it. Returns init's result, or -1 when the state is not "not initialised".
 */
int app_contract_run_init(app_contract_t *contract);

/* Step 5 in safe mode: not initialised to held, without calling init. */
void app_contract_hold_safe_mode(app_contract_t *contract);

typedef struct {
    bool safe_mode;
    bool prerequisites_healthy;
    bool watchdog_armed;
    bool start_without_watchdog;
} app_start_conditions_t;

typedef enum {
    APP_RUN_STARTED = 0, /* activated and started: running */
    APP_RUN_HELD,        /* not started; held (step 12) or left as it was (operator start) */
    APP_RUN_FAILED,      /* activation or start failed: cleaned up, fault */
    APP_RUN_NOT_NOW,     /* not a state to start from */
} app_run_t;

/*
 * Step 12 (operator false, from initialised) and an operator start (operator true, from stopped, or
 * from held when the hold was for a start prerequisite). The decision is app_start_decide(). On a
 * go the requirements are activated in order, then start runs. A failed activation or start runs
 * safe_state, deletes the channels activated in this call, releases the registrations and enters
 * fault. A hold at step 12 enters held; at an operator start the state stays.
 */
app_run_t app_contract_start(app_contract_t *contract, const app_start_conditions_t *conditions,
                             bool operator);

typedef enum {
    APP_STOPPED_OK = 0, /* stop succeeded and the clean-up ran */
    APP_STOP_HANG,      /* stop returned an error: a hang, which the caller latches (section 4.8) */
    APP_STOP_NOT_NOW,   /* not running */
} app_stop_t;

/*
 * Stop the running application. stop runs with the reason; on success safe_state runs and every
 * active channel is deleted. For an operator stop or a planned reset the requirements stay
 * registered and the state is stopped; for a fault the registrations are released too and the state
 * is fault. On an error nothing more runs and the state stays running until the reset.
 */
app_stop_t app_contract_stop(app_contract_t *contract, app_stop_reason_t reason);

/* An application thread reports a fault; the framework thread takes it with
 * app_contract_take_fault() and stops the application if it is running. */
void app_contract_report_fault(app_contract_t *contract);
bool app_contract_take_fault(app_contract_t *contract);

/* The supervisor, after it latched a fault: safe_state, when init has succeeded in this boot.
 * Returns true when it called safe_state. */
bool app_contract_supervisor_safe_state(app_contract_t *contract);

app_state_t app_contract_state(const app_contract_t *contract);
app_hold_t app_contract_hold(const app_contract_t *contract);

/* False once the registrations have been released (and for an absent application). */
bool app_contract_items_available(const app_contract_t *contract);

/* The registration tables, for the composition; *count gets 0 and the result is NULL when none. */
const void *app_contract_status_items(const app_contract_t *contract, size_t *count);
const void *app_contract_parameters(const app_contract_t *contract, size_t *count);

/* The registered requirements, and the name of one, for the record of an expiry. */
size_t app_contract_requirement_count(const app_contract_t *contract);
const char *app_contract_requirement_name(const app_contract_t *contract, size_t index);

#endif
