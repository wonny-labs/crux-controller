/* SPDX-License-Identifier: Apache-2.0 */
#ifndef CFGSTORE_H
#define CFGSTORE_H

#include "workload.h"

/* The one file the store keeps in File's root. */
#define CFGSTORE_FILE_NAME "config.rec"

typedef enum {
    CFGSTORE_OK = 0,
    CFGSTORE_ERR_NOT_READY = -1, /* File is not bound yet */
    CFGSTORE_ERR_NOT_FOUND = -2, /* no record was saved */
    CFGSTORE_ERR_FORMAT = -3,    /* the file is not a valid record */
    CFGSTORE_ERR_IO = -4,        /* File reported another error, or a short write */
    CFGSTORE_ERR_RANGE = -5,     /* the record handed to save is not valid; nothing was written */
} config_store_status_t;

/*
 * Write the record, replacing the file, and flush it. Uses the File contract of
 * <crux/file.h> only. A failure while writing may leave a partial file: File promises no
 * rollback, and a later load reports it as CFGSTORE_ERR_FORMAT.
 */
config_store_status_t config_store_save(const workload_config_t *config);

/* Read the record. On any failure *config is untouched. */
config_store_status_t config_store_load(workload_config_t *config);

#endif
