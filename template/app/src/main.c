/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The product's main(): it passes the product's descriptor to the start function of the controller
 * framework, which starts the framework services and then calls the entries below on its
 * application thread (<controller/framework.h> states the rules of each entry).
 *
 * The entries do nothing yet except log. Replace each body with the product's own work:
 *   init        register the watchdog channels, status items and parameter tables that the product
 *               needs (controller_app_channel_register() and <controller/framework_management.h>);
 *               nothing is registered later;
 *   start       create the product's threads with Zephyr, each feeding its own channel;
 *   stop        end every thread that start created, then return;
 *   safe_state  put the outputs into the product's safe state; it never blocks, takes no lock,
 *               allocates nothing and logs nothing.
 */

#include <stddef.h>

#include <controller/framework.h>
#include <crux/logging.h>

/* The log tag of the product's records (letters, digits, '_', '.', '-'). */
#define PRODUCT_LOG_TAG "product"

static void product_log(const char *text)
{
    (void)crux_log_write(CRUX_LOG_INFO, PRODUCT_LOG_TAG, text);
}

static int product_init(controller_app_context_t *context)
{
    (void)context;
    product_log("init");
    return 0;
}

static int product_start(controller_app_context_t *context)
{
    (void)context;
    product_log("start");
    return 0;
}

static int product_stop(controller_app_context_t *context, controller_app_stop_reason_t reason)
{
    (void)context;
    (void)reason;
    product_log("stop");
    return 0;
}

static void product_safe_state(controller_app_context_t *context)
{
    (void)context;
}

/* The descriptor stays valid for the program's life. */
static const controller_app_t product_app = {
    .init = product_init,
    .start = product_start,
    .stop = product_stop,
    .safe_state = product_safe_state,
    .user_data = NULL,
};

int main(void)
{
    return controller_framework_start(&product_app) == CONTROLLER_FRAMEWORK_OK ? 0 : -1;
}
