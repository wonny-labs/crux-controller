/* SPDX-License-Identifier: Apache-2.0 */
#ifndef MANAGEMENT_PORT_H
#define MANAGEMENT_PORT_H

/*
 * The product-owned port of HTTPS management. framework/src declares it, and the composition zone
 * (framework/compose) is the place where an implementation would call the Crux services and the
 * Zephyr web server, so this header names no Crux, Zephyr or composition header. It includes only
 * ISO C and the policy header of this repository, so that it needs nothing from Crux to be read or
 * tested. The implementation copies the policy into the Crux type and sets no password rule, so
 * that Crux uses its reference rule.
 *
 * The composition zone implements this port in framework/compose/management_start.c. The
 * framework start (framework/src/framework.c) calls it in the base image, and
 * app/src/composition.c calls it in the management configuration. The order below is a reading of
 * three Crux sources at the pinned revision, and it has not run on a board: the "Boot order"
 * section of docs/management-in-a-product.md, the start calls of the module test
 * tests/native/management_module/src/main.c (configuration service, management status and security
 * event start, and only then the TLS certificate start), and the header
 * components/web/ports/zephyr/include/crux/web_zephyr.h (services started, TLS material registered
 * under the security tag, then the session and management init with their workers, then start).
 *
 *   1. security event init, realtime init, mount the medium and bind the two store roots
 *   2. credential store start, then Access init with the policy below
 *   3. config service start, management status start, then security event start, then the
 *      configuration's hook (the framework starts Crux Reboot there)
 *   4. TLS certificate start
 *   5. take the certificate material and register it under the web security tag, and fail the
 *      start if either registration fails (the web listener does not report a missing certificate)
 *   6. web session init and web management init, each with its worker
 *   7. web start, with the session authenticate function
 *
 * The guide puts the first account between steps 3 and 4. This port does not create one: that
 * is the serial console's work (cli_port.h), which the framework starts after this sequence.
 *
 * management_port_start() runs the whole sequence once, on one thread, before any request.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "management_policy.h"

typedef enum {
    MANAGEMENT_PORT_OK = 0,
    MANAGEMENT_PORT_ERR_INVALID_ARGUMENT = -1,
    MANAGEMENT_PORT_ERR_ALREADY_STARTED = -2, /* A second start; nothing changed. */
    MANAGEMENT_PORT_ERR_STEP_FAILED = -3,     /* A step of the sequence refused; nothing serves. */
    MANAGEMENT_PORT_ERR_STORAGE = -4,   /* The medium, a store root or the data root failed. */
    MANAGEMENT_PORT_ERR_NOT_READY = -5, /* The services part before a successful core part. */
} management_port_status_t;

typedef struct {
    /* The roles and the session limits, borrowed for the program's life. */
    const management_policy_t *policy;
    /* At most 63 bytes each, from the build. Borrowed for the call. */
    const char *platform_version;
    const char *project_version;
    /*
     * The reset cause that the boot diagnostic owner captured once, for the status service: the
     * crux_status_t of the read, and the supported and latched masks of crux_reset_cause_t. When
     * reset_cause_given is false, the port reads the cause itself and never clears it, which suits
     * a configuration whose system capability reports and clears the cause on its own.
     */
    bool reset_cause_given;
    int reset_cause_status;
    uint32_t reset_cause_supported;
    uint32_t reset_cause_causes;
    /*
     * Items that the status service shows besides its own: an array of crux_mgmt_status_item_t,
     * which this header cannot name, borrowed for the program's life, or NULL with a count of zero.
     */
    const void *status_items;
    size_t status_item_count;
    /* Called once the security events run, before the TLS certificate; a result other than zero
     * refuses the start. NULL for none. */
    int (*after_events)(void);
    /* True: the core part also binds the application data root (storage_port_bind_app()). */
    bool bind_app_root;
    /* The parameter table of the configuration service: an array of crux_config_service_entry_t,
     * borrowed for the program's life, or NULL with a count of zero. */
    const void *parameters;
    size_t parameter_count;
} management_port_config_t;

/* Start HTTPS management, or refuse and leave it off. Returns once, never serves a half start. It
 * runs the core part and then the services part, with the same configuration. */
management_port_status_t management_port_start(const management_port_config_t *config);

/*
 * The two parts of the sequence, for the start function, whose application init (startup step 5)
 * runs between them:
 *   core      steps 1 and 2 above (the medium, the store roots and, with bind_app_root, the data
 *             root, the credential store and Access): startup steps 3 and 4;
 *   services  steps 3 to 7 (configuration with the parameter table, status with the items, the
 *             event thread and the hook, the TLS certificate, sessions, management and the
 *             listener): startup steps 6, 7 and 10.
 * The core part checks the configuration and runs once; the services part runs once, after a
 * successful core part (MANAGEMENT_PORT_ERR_NOT_READY otherwise), and reads the status items and
 * the parameters of its own configuration, so they can be known only after init.
 */
management_port_status_t management_port_start_core(const management_port_config_t *config);
management_port_status_t management_port_start_services(const management_port_config_t *config);

#endif
