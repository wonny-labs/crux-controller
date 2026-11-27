/* SPDX-License-Identifier: Apache-2.0 */

#include "app_requests.h"

#include <stddef.h>

void app_requests_init(app_requests_t *requests)
{
    if (requests == NULL) {
        return;
    }
    atomic_store(&requests->pending, (int)APP_REQUEST_NONE);
    atomic_store(&requests->open, false);
    atomic_store(&requests->steps_returned, false);
    atomic_store(&requests->reset_planned, false);
}

void app_requests_startup_returned(app_requests_t *requests, bool supervision_ended)
{
    if (requests == NULL) {
        return;
    }
    atomic_store(&requests->steps_returned, true);
    if (supervision_ended) {
        atomic_store(&requests->open, true);
    }
}

app_request_result_t app_requests_post(app_requests_t *requests, app_request_t request)
{
    if (requests == NULL || (request != APP_REQUEST_STOP && request != APP_REQUEST_START)) {
        return APP_REQUEST_INVALID;
    }
    if (!atomic_load(&requests->open)) {
        return APP_REQUEST_REFUSED_STARTING;
    }
    if (atomic_load(&requests->reset_planned)) {
        return APP_REQUEST_REFUSED_RESET;
    }
    /* A store, not a merge: the newest request replaces one that waits. */
    atomic_store(&requests->pending, (int)request);
    return APP_REQUEST_ACCEPTED;
}

app_request_t app_requests_take(app_requests_t *requests)
{
    if (requests == NULL) {
        return APP_REQUEST_NONE;
    }
    const int request = atomic_exchange(&requests->pending, (int)APP_REQUEST_NONE);

    /* Checked after the exchange: a post that passed its check before the reset was planned and
     * stored after it is dropped here. */
    if (atomic_load(&requests->reset_planned)) {
        return APP_REQUEST_NONE;
    }
    return (app_request_t)request;
}

bool app_requests_reset_allowed(const app_requests_t *requests)
{
    return requests != NULL && atomic_load(&requests->steps_returned);
}

bool app_requests_plan_reset(app_requests_t *requests)
{
    if (!app_requests_reset_allowed(requests)) {
        return false;
    }
    atomic_store(&requests->reset_planned, true);
    (void)atomic_exchange(&requests->pending, (int)APP_REQUEST_NONE);
    return true;
}

void app_requests_reset_abandoned(app_requests_t *requests)
{
    if (requests != NULL) {
        atomic_store(&requests->reset_planned, false);
    }
}
