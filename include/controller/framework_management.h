/* SPDX-License-Identifier: Apache-2.0 */
#ifndef CONTROLLER_FRAMEWORK_MANAGEMENT_H
#define CONTROLLER_FRAMEWORK_MANAGEMENT_H

/*
 * The registrations of the application interface that device management shows (specification
 * section 3.2): status items, which the framework adds to the Crux status service, and one parameter
 * table, which it adds to the Crux configuration service. They take the Crux types as they are; the
 * framework wraps neither service. Both are made inside init, which runs before the two services
 * start (startup steps 5 to 7), and only in a build with web management
 * (CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT).
 *
 * After a fault the registrations are released: each status item then answers CRUX_ERR_NOT_READY.
 * A parameter stays in the configuration service, which has no call that removes one at the
 * pinned Crux revision; after a failed init no parameter reaches the service.
 */

#include <stddef.h>

#include <controller/framework.h>
#include <crux/config_service.h>
#include <crux/management_status.h>

/*
 * Register the application's status items, once, inside init. The array and its strings are
 * borrowed for the program's life, and each item follows the rules of <crux/management_status.h>
 * (name, required permission, a source that neither blocks nor touches storage). At most
 * CONFIG_CRUX_CONTROLLER_APP_STATUS_ITEMS items.
 */
controller_app_result_t controller_app_status_register(controller_app_context_t *context,
                                                       const crux_mgmt_status_item_t *items,
                                                       size_t count);

/*
 * Register the application's parameter table, once, inside init. The entries follow the rules of
 * <crux/config_service.h>, and the application loads each parameter before init returns. At most
 * CRUX_CONFIG_SERVICE_MAX entries.
 */
controller_app_result_t controller_app_parameters_register(controller_app_context_t *context,
                                                           const crux_config_service_entry_t *entries,
                                                           size_t count);

#endif
