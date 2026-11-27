/* SPDX-License-Identifier: Apache-2.0 */
#ifndef APP_REQUESTS_H
#define APP_REQUESTS_H

/*
 * The operator requests of the application thread and the gate of a planned reset (specification
 * sections 3.3 and 4.8). Plain C with ISO C includes only (tests/host/test_app_requests.c).
 *
 * Rules:
 *   - An operator stop or start is accepted once startup supervision has ended in step 12. Until
 *     then the step table owns the supervisor's step deadline.
 *   - A newer operator request replaces an older one that the application thread has not taken, so
 *     the application ends in the state of the newest request.
 *   - A planned reset is allowed once the step table has returned, because no step calls start
 *     after that. Before it, step 12 may be about to call start or may be inside it, and a reset
 *     then would skip stop and safe_state.
 *   - A planned reset drops a waiting operator request and refuses later ones, so no start runs
 *     between the planned stop and the reset. When the reset does not happen, the gate opens again.
 *
 * Callers: device management posts; the application thread takes; the start function reports the
 * end of the step table; the reboot thread plans a reset and abandons it. Every field is an atomic.
 */

#include <stdatomic.h>
#include <stdbool.h>

typedef enum {
    APP_REQUEST_NONE = 0,
    APP_REQUEST_STOP,
    APP_REQUEST_START,
} app_request_t;

typedef enum {
    APP_REQUEST_ACCEPTED = 0,
    APP_REQUEST_REFUSED_STARTING, /* startup supervision has not ended in step 12 */
    APP_REQUEST_REFUSED_RESET,    /* a planned reset is under way */
    APP_REQUEST_INVALID,          /* not a stop or a start, or no requests */
} app_request_result_t;

typedef struct {
    atomic_int pending;         /* app_request_t: the newest request not taken yet */
    atomic_bool open;           /* startup supervision ended in step 12 */
    atomic_bool steps_returned; /* the step table returned, ended or stopped */
    atomic_bool reset_planned;
} app_requests_t;

/* No request, startup running, no reset planned. */
void app_requests_init(app_requests_t *requests);

/* The step table returned. supervision_ended is true when startup supervision ended in step 12,
 * which opens operator requests; a startup that stopped earlier leaves them refused. */
void app_requests_startup_returned(app_requests_t *requests, bool supervision_ended);

/* Record an operator stop or start for the application thread. */
app_request_result_t app_requests_post(app_requests_t *requests, app_request_t request);

/* On the application thread: the newest request, which is then cleared. NONE while a planned reset
 * is under way, so a request stored across the start of that reset never runs. */
app_request_t app_requests_take(app_requests_t *requests);

/* True when a planned reset may go ahead: the step table has returned. */
bool app_requests_reset_allowed(const app_requests_t *requests);

/* Start a planned reset: drop a waiting request and refuse later ones. False, with nothing
 * changed, while the step table runs. */
bool app_requests_plan_reset(app_requests_t *requests);

/* The planned reset did not happen: accept operator requests again. */
void app_requests_reset_abandoned(app_requests_t *requests);

#endif
