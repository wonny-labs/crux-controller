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
 * section of docs/management-in-a-product.md, the header
 * components/tls_certificate/include/crux/tls_certificate_start.h (start the module once the
 * credential store has started and before any TLS listener), and the header
 * components/web/ports/zephyr/include/crux/web_zephyr.h (services started, TLS material registered
 * under the security tag, then the session and management init with their workers, then start).
 * The guide and Crux's module test start the TLS certificate module after the configuration and
 * status services; this port starts it right after Access, so that its result is known before the
 * application's init (specification sections 4.1 and 5.5; a project-specific workaround that the
 * start header allows).
 *
 *   1. security event init, realtime init, mount the medium and bind the two store roots
 *   2. credential store start, then Access init with the policy below
 *   3. TLS certificate start; a refusal is kept and turns only web management off
 *   4. config service start, management status start, then security event start, then the
 *      configuration's hook (the framework starts Crux Reboot there)
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
    /* The TLS certificate start refused: steps 1 to 3 had started and stay started, and web
     * management (steps 5 to 7) is off. */
    MANAGEMENT_PORT_ERR_TLS_CERTIFICATE = -6,
} management_port_status_t;

/* The Crux service threads that the sequence starts (gap C8). */
typedef enum {
    MANAGEMENT_PORT_THREAD_EVENT_DRAIN = 0, /* the security event thread, step 4 */
    MANAGEMENT_PORT_THREAD_WEB_SESSION,     /* the web session worker, step 6 */
    MANAGEMENT_PORT_THREAD_WEB_MANAGEMENT,  /* the web management worker, step 6 */
} management_port_thread_t;

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
    /* Called once the security events run, after the TLS certificate start; a result other than
     * zero refuses the start. NULL for none. */
    int (*after_events)(void);
    /* Called on the starting thread right after the Crux call that starts a service thread
     * returned success, so that the framework gives the thread its task watchdog channel (gap C8).
     * NULL for none. */
    void (*thread_started)(management_port_thread_t thread);
    /* True: the core part also binds the application data root (storage_port_bind_app()). */
    bool bind_app_root;
    /* The parameter table of the configuration service: an array of crux_config_service_entry_t,
     * borrowed for the program's life, or NULL with a count of zero. */
    const void *parameters;
    size_t parameter_count;
} management_port_config_t;

/* Start HTTPS management, or refuse and leave it off. Returns once, never serves a half start. It
 * runs the core part and then the services part, with the same configuration, and returns the
 * result of the part that refused. */
management_port_status_t management_port_start(const management_port_config_t *config);

/*
 * The two parts of the sequence, for the start function, whose application init (startup step 5)
 * runs between them:
 *   core      steps 1 to 3 above (the medium, the store roots and, with bind_app_root, the data
 *             root, the credential store, Access and the TLS certificate): startup steps 3 and 4;
 *   services  steps 4 to 7 (configuration with the parameter table, status with the items, the
 *             event thread and the hook, the TLS material, sessions, management and the
 *             listener): startup steps 6, 7 and 10.
 * The core part checks the configuration and runs once; the services part runs once, after a
 * successful core part (MANAGEMENT_PORT_ERR_NOT_READY otherwise), and reads the status items and
 * the parameters of its own configuration, so they can be known only after init. A refused TLS
 * certificate start does not fail the core part; the services part then answers
 * MANAGEMENT_PORT_ERR_TLS_CERTIFICATE after it started configuration, status and the event thread,
 * and only web management stays off. Any other refusal leaves the services part off as a whole.
 */
management_port_status_t management_port_start_core(const management_port_config_t *config);
management_port_status_t management_port_start_services(const management_port_config_t *config);

/* What happened to the TLS certificate in the core part, as the status service shows it: "not
 * started", "stored", "made at boot" (Crux made the key and a self-signed certificate in this boot,
 * specification section 5.5) or "refused". It copies a value, does not block and touches no
 * storage, as a status item source must. */
void management_port_certificate(char *text, size_t size);

#endif
