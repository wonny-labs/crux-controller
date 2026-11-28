/* SPDX-License-Identifier: Apache-2.0 */

#include "reboot_policy.h"

#include <stdatomic.h>
#include <stddef.h>

/* True from a marker write on the reboot thread until that thread clears it after the call. */
static atomic_bool marker_left;

static bool port_complete(const reboot_policy_port_t *port)
{
    return port != NULL && port->on_reboot_thread != NULL && port->restart_allowed != NULL &&
           port->marker_write != NULL && port->work_once != NULL && port->request_ended != NULL;
}

bool reboot_policy_allow(const reboot_policy_port_t *port)
{
    if (!port_complete(port) || !port->restart_allowed()) {
        return false;
    }
    if (port->on_reboot_thread()) {
        port->marker_write(true);
        atomic_store(&marker_left, true);
    }
    return true;
}

void reboot_policy_pass(const reboot_policy_port_t *port)
{
    if (!port_complete(port)) {
        return;
    }
    const bool ended = port->work_once();

    /* The call returned, so no reset happened: the marker must not mark a later reset. */
    if (atomic_exchange(&marker_left, false)) {
        port->marker_write(false);
    }
    /* The request, and every request that joined it, ended without a reset: what was marked for
     * that reset must not apply to a later one. */
    if (ended) {
        port->request_ended();
    }
}
