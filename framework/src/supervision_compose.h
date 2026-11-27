/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SUPERVISION_COMPOSE_H
#define SUPERVISION_COMPOSE_H

/*
 * The port of the composition zone's part of health supervision (framework/compose/
 * supervision_start.c): the framework's status items for the status service, and Crux Reboot with
 * the framework's callback policy. This header names no Crux type, so the start function hands
 * the items to the management port as it receives them.
 */

#include <stddef.h>

/* The framework's status items: an array of crux_mgmt_status_item_t of *count entries, for the
 * status_items of management_port_config_t. */
const void *supervision_compose_status_items(size_t *count);

/*
 * Start Crux Reboot with the framework's callback policy (reboot_policy.h) and no Crux reboot
 * worker, after Access and the security events: the after_events hook of management_port_config_t.
 * Returns 0, or -1 when the permission names disagree or Crux refuses the start. An image without
 * Crux Reboot gets 0 and starts nothing.
 */
int supervision_compose_reboot_start(void);

#endif
