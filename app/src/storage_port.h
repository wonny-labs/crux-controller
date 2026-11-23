/* SPDX-License-Identifier: Apache-2.0 */
#ifndef STORAGE_PORT_H
#define STORAGE_PORT_H

/*
 * The product-owned port to the storage composition. The application declares it and the
 * composition zone (app/compose) implements it, so the application never includes a Zephyr or a
 * Crux composition header: the link joins the two, no include does. This header has no include
 * of its own, so it stays inside the rules of app/src.
 *
 * Two calls, in this order, once each, from thread context before any other thread calls File:
 *
 *   storage_port_mount()  makes the volume available. It does not make File ready.
 *   storage_port_bind()   makes File ready. Until it succeeds, every File call returns
 *                         CRUX_FILE_ERR_NOT_READY.
 *
 * The management capability does not bind the directory "files". It makes the volume available with
 * storage_port_mount() and then calls, once, from thread context:
 *
 *   storage_port_bind_store()  creates the two directories of the credential store on the mounted
 *                              volume and binds them as the File roots STORAGE_PORT_STORE_ROOT_A
 *                              and STORAGE_PORT_STORE_ROOT_B. It is the only call that makes File
 *                              ready in that step, and it comes after storage_port_mount().
 *
 * A failed call leaves the other state as it was, with one exception: with
 * STORAGE_PORT_FORMAT_ON_FAILED_MOUNT, a call that formatted and mounted the volume and then could
 * not create the directory returns STORAGE_PORT_ERR_LAYOUT with the volume still mounted. A failed
 * bind leaves File unbound, so a later call can succeed. There is no unbind and no second bind.
 */

typedef enum {
    STORAGE_PORT_OK = 0,
    STORAGE_PORT_ERR_MOUNT = -1,  /* the volume did not mount */
    STORAGE_PORT_ERR_FORMAT = -2, /* the volume could not be formatted, or this image cannot */
    STORAGE_PORT_ERR_LAYOUT = -3, /* the directory that File uses could not be created */
    STORAGE_PORT_ERR_BIND = -4,   /* File refused the directory (absent, not a directory) */
    STORAGE_PORT_ERR_ALREADY_MOUNTED = -5, /* the volume is already mounted */
    STORAGE_PORT_ERR_ALREADY_BOUND = -6,   /* File is already bound; there is no rebind */
} storage_port_status_t;

typedef enum {
    /* Mount what is there. A volume that does not mount stays untouched and the call fails. */
    STORAGE_PORT_KEEP_VOLUME,
    /*
     * When the mount fails, format the volume and create the directory that File uses. It
     * destroys a damaged file system, so it is for a volume that holds nothing worth keeping
     * (a RAM disk, a test). It creates the directory only after a format it ran itself; a volume
     * that mounts is left as it is. An image without the formatting service cannot use it.
     */
    STORAGE_PORT_FORMAT_ON_FAILED_MOUNT,
} storage_port_policy_t;

/* Mount the volume that the devicetree entry "controller_storage" describes. */
storage_port_status_t storage_port_mount(storage_port_policy_t policy);

/* Bind the directory "files" of the mounted volume as File's root. */
storage_port_status_t storage_port_bind(void);

/* The File roots that the credential store of Crux uses: two slots on two directories that do not
 * overlap, as the store requires. The numbers are the product's choice and are given to the store
 * by the composition. */
#define STORAGE_PORT_STORE_ROOT_A 1
#define STORAGE_PORT_STORE_ROOT_B 2

/*
 * Create the directories "secure-a" and "secure-b" of the mounted volume, if they are not there
 * yet, and bind them as the File roots STORAGE_PORT_STORE_ROOT_A and STORAGE_PORT_STORE_ROOT_B.
 * Neither is the directory that storage_port_bind() uses, and neither contains the other. A failed
 * directory leaves File unbound (STORAGE_PORT_ERR_LAYOUT); a root that File refuses, or one that
 * is already bound, returns STORAGE_PORT_ERR_BIND or STORAGE_PORT_ERR_ALREADY_BOUND. There is no
 * unbind and no second bind of a root. A consequence: root A stays bound when root B fails,
 * because there is no unbind, and a second call then answers STORAGE_PORT_ERR_ALREADY_BOUND for
 * root A. The caller treats any failure as the end of the
 * management start (management_start.c does), and does not retry.
 */
storage_port_status_t storage_port_bind_store(void);

#endif
