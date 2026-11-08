/* SPDX-License-Identifier: Apache-2.0 */

#include "config_store.h"

#include <stddef.h>
#include <stdint.h>

#include <crux/file.h>

static config_store_status_t status_of(crux_file_result_t result)
{
    switch (result) {
    case CRUX_FILE_OK:
        return CONFIG_STORE_OK;
    case CRUX_FILE_ERR_NOT_READY:
        return CONFIG_STORE_ERR_NOT_READY;
    case CRUX_FILE_ERR_NOT_FOUND:
        return CONFIG_STORE_ERR_NOT_FOUND;
    default:
        return CONFIG_STORE_ERR_IO;
    }
}

/* Write the whole record and flush it. A short write is an error here. */
static config_store_status_t write_and_sync(crux_file_t *file, const uint8_t *record, size_t length)
{
    size_t written = 0;
    const crux_file_result_t wrote = crux_file_write(file, record, length, &written);

    if (wrote == CRUX_FILE_OK && written == length) {
        return status_of(crux_file_sync(file));
    }
    if (wrote == CRUX_FILE_OK || wrote == CRUX_FILE_PARTIAL) {
        return CONFIG_STORE_ERR_IO;
    }
    return status_of(wrote);
}

/* Read up to capacity bytes. A file longer than the record shows as one byte too many. */
static config_store_status_t read_up_to(crux_file_t *file, uint8_t *buffer, size_t capacity,
                                        size_t *length)
{
    *length = 0;
    return status_of(crux_file_read(file, buffer, capacity, length));
}

config_store_status_t config_store_save(const workload_config_t *config)
{
    uint8_t record[WORKLOAD_CONFIG_RECORD_SIZE];
    size_t length = 0;
    crux_file_t *file = NULL;
    config_store_status_t status;
    crux_file_result_t opened;

    if (workload_config_encode(config, record, sizeof record, &length) != WORKLOAD_OK) {
        return CONFIG_STORE_ERR_RANGE;
    }
    opened = crux_file_open(CONFIG_STORE_FILE_NAME, CRUX_FILE_CREATE_REPLACE, &file);
    if (opened != CRUX_FILE_OK) {
        return status_of(opened);
    }
    status = write_and_sync(file, record, length);
    if (crux_file_close(&file) != CRUX_FILE_OK && status == CONFIG_STORE_OK) {
        status = CONFIG_STORE_ERR_IO;
    }
    return status;
}

config_store_status_t config_store_load(workload_config_t *config)
{
    uint8_t buffer[WORKLOAD_CONFIG_RECORD_SIZE + 1u];
    size_t length = 0;
    crux_file_t *file = NULL;
    config_store_status_t status;
    crux_file_result_t opened;

    if (config == NULL) {
        return CONFIG_STORE_ERR_RANGE;
    }
    opened = crux_file_open(CONFIG_STORE_FILE_NAME, CRUX_FILE_READ, &file);
    if (opened != CRUX_FILE_OK) {
        return status_of(opened);
    }
    status = read_up_to(file, buffer, sizeof buffer, &length);
    if (crux_file_close(&file) != CRUX_FILE_OK && status == CONFIG_STORE_OK) {
        status = CONFIG_STORE_ERR_IO;
    }
    if (status != CONFIG_STORE_OK) {
        return status;
    }
    return workload_config_decode(buffer, length, config) == WORKLOAD_OK ? CONFIG_STORE_OK
                                                                         : CONFIG_STORE_ERR_FORMAT;
}
