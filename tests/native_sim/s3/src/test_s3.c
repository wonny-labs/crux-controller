/* SPDX-License-Identifier: Apache-2.0 */

/* Runs the application's own config_store.c and the composition zone (app/compose) on the
 * simulator provider of Crux File, over a RAM disk. One case per image, chosen by S3_CASE,
 * because File is bound once per program and has no unbind. This is test code, so it may use
 * Zephyr's file system API directly, for example to remove a directory behind File's back. */

#include <stdint.h>
#include <string.h>

#include <zephyr/fs/fs.h>
#include <zephyr/ztest.h>

#include <crux/file.h>

#include "config_store.h"
#include "storage_port.h"
#include "workload.h"

#define FILES_DIRECTORY "/RAM:/files"

static workload_config_t record(uint32_t period_ms, uint32_t message_every)
{
    const workload_config_t config = {.period_ms = period_ms, .message_every = message_every};

    return config;
}

static void expect_file_is_not_ready(void)
{
    crux_file_t *file = NULL;

    zassert_equal(crux_file_open(CONFIG_STORE_FILE_NAME, CRUX_FILE_READ, &file),
                  CRUX_FILE_ERR_NOT_READY);
    zassert_is_null(file);
    zassert_equal(crux_file_remove(CONFIG_STORE_FILE_NAME), CRUX_FILE_ERR_NOT_READY);
}

static void expect_store_is_not_ready(void)
{
    const workload_config_t config = record(100, 10);
    workload_config_t out = record(1, 1);

    zassert_equal(config_store_load(&out), CONFIG_STORE_ERR_NOT_READY);
    zassert_equal(out.period_ms, 1u);
    zassert_equal(config_store_save(&config), CONFIG_STORE_ERR_NOT_READY);
}

#if defined(S3_CASE_not_ready)

/* No mount, no bind: File answers NOT_READY and the store passes that on. */
ZTEST_SUITE(s3, NULL, NULL, NULL, NULL, NULL);

ZTEST(s3, test_file_calls_return_not_ready_before_the_bind)
{
    expect_file_is_not_ready();
}

ZTEST(s3, test_the_store_reports_not_ready_before_the_bind)
{
    expect_store_is_not_ready();
}

ZTEST(s3, test_a_bind_before_any_mount_fails_and_file_stays_not_ready)
{
    zassert_equal(storage_port_bind(), STORAGE_PORT_ERR_BIND);
    expect_file_is_not_ready();
}

#elif defined(S3_CASE_mounted_not_bound)

static void *setup(void)
{
    zassert_equal(storage_port_mount(STORAGE_PORT_FORMAT_ON_FAILED_MOUNT), STORAGE_PORT_OK);
    return NULL;
}

/* A mounted volume is not a ready File: only the bind makes it ready. */
ZTEST_SUITE(s3, NULL, setup, NULL, NULL, NULL);

ZTEST(s3, test_file_calls_return_not_ready_after_a_mount_without_a_bind)
{
    expect_file_is_not_ready();
}

ZTEST(s3, test_the_store_reports_not_ready_after_a_mount_without_a_bind)
{
    expect_store_is_not_ready();
}

ZTEST(s3, test_a_second_mount_is_refused)
{
    zassert_equal(storage_port_mount(STORAGE_PORT_KEEP_VOLUME), STORAGE_PORT_ERR_ALREADY_MOUNTED);
}

#elif defined(S3_CASE_mount_failure)

/* The volume is blank. Keeping it means the mount fails and nothing is formatted. */
ZTEST_SUITE(s3, NULL, NULL, NULL, NULL, NULL);

ZTEST(s3, test_a_blank_volume_does_not_mount_when_it_is_kept)
{
    zassert_equal(storage_port_mount(STORAGE_PORT_KEEP_VOLUME), STORAGE_PORT_ERR_MOUNT);
}

ZTEST(s3, test_a_failed_mount_formats_nothing_and_leaves_file_not_ready)
{
    zassert_equal(storage_port_mount(STORAGE_PORT_KEEP_VOLUME), STORAGE_PORT_ERR_MOUNT);
    zassert_equal(storage_port_mount(STORAGE_PORT_KEEP_VOLUME), STORAGE_PORT_ERR_MOUNT,
                  "the first call formatted the volume");
    expect_file_is_not_ready();
}

#elif defined(S3_CASE_roundtrip)

static void *setup(void)
{
    zassert_equal(storage_port_mount(STORAGE_PORT_FORMAT_ON_FAILED_MOUNT), STORAGE_PORT_OK);
    zassert_equal(storage_port_bind(), STORAGE_PORT_OK);
    return NULL;
}

static void remove_the_record(void *fixture)
{
    ARG_UNUSED(fixture);
    (void)crux_file_remove(CONFIG_STORE_FILE_NAME);
}

static void write_raw(const void *bytes, size_t length)
{
    crux_file_t *file = NULL;
    size_t written = 0;

    zassert_equal(crux_file_open(CONFIG_STORE_FILE_NAME, CRUX_FILE_CREATE_REPLACE, &file),
                  CRUX_FILE_OK);
    zassert_equal(crux_file_write(file, bytes, length, &written), CRUX_FILE_OK);
    zassert_equal(written, length);
    zassert_equal(crux_file_close(&file), CRUX_FILE_OK);
}

/* After the bind, a record written is the record read back. */
ZTEST_SUITE(s3, NULL, setup, remove_the_record, NULL, NULL);

ZTEST(s3, test_a_saved_record_reads_back_the_same)
{
    const workload_config_t config = record(250, 7);
    workload_config_t out = record(1, 1);

    zassert_equal(config_store_save(&config), CONFIG_STORE_OK);
    zassert_equal(config_store_load(&out), CONFIG_STORE_OK);
    zassert_equal(out.period_ms, 250u);
    zassert_equal(out.message_every, 7u);
}

ZTEST(s3, test_a_second_save_replaces_the_first)
{
    const workload_config_t first = record(100, 10);
    const workload_config_t second = record(300, 3);
    workload_config_t out = record(1, 1);
    crux_file_info_t info;

    zassert_equal(config_store_save(&first), CONFIG_STORE_OK);
    zassert_equal(config_store_save(&second), CONFIG_STORE_OK);
    zassert_equal(config_store_load(&out), CONFIG_STORE_OK);
    zassert_equal(out.period_ms, 300u);
    zassert_equal(out.message_every, 3u);
    zassert_equal(crux_file_stat(CRUX_FILE_ROOT_DEFAULT, CONFIG_STORE_FILE_NAME, &info),
                  CRUX_FILE_OK);
    zassert_equal(info.size, (uint64_t)WORKLOAD_CONFIG_RECORD_SIZE);
}

ZTEST(s3, test_a_load_without_a_saved_record_is_not_found)
{
    workload_config_t out = record(1, 1);

    zassert_equal(config_store_load(&out), CONFIG_STORE_ERR_NOT_FOUND);
    zassert_equal(out.period_ms, 1u);
}

ZTEST(s3, test_a_file_that_is_not_a_record_is_a_format_error)
{
    workload_config_t out = record(1, 1);

    write_raw("hello", 5);
    zassert_equal(config_store_load(&out), CONFIG_STORE_ERR_FORMAT);
    write_raw("WCR1\0\0\0\x64\0\0\0\x0a\0", 13);
    zassert_equal(config_store_load(&out), CONFIG_STORE_ERR_FORMAT, "a longer file is not a record");
    zassert_equal(out.period_ms, 1u);
}

ZTEST(s3, test_saving_an_invalid_record_writes_nothing)
{
    const workload_config_t invalid = record(9, 10);
    workload_config_t out = record(1, 1);

    zassert_equal(config_store_save(&invalid), CONFIG_STORE_ERR_RANGE);
    zassert_equal(config_store_load(&out), CONFIG_STORE_ERR_NOT_FOUND);
}

ZTEST(s3, test_a_second_bind_is_refused)
{
    zassert_equal(storage_port_bind(), STORAGE_PORT_ERR_ALREADY_BOUND);
}

#elif defined(S3_CASE_bind_failure)

static void *setup(void)
{
    zassert_equal(storage_port_mount(STORAGE_PORT_FORMAT_ON_FAILED_MOUNT), STORAGE_PORT_OK);
    zassert_ok(fs_unlink(FILES_DIRECTORY), "the directory File would bind is still there");
    return NULL;
}

/* A bind to a directory that is gone fails and leaves File unbound, so that a bind after the
 * directory is back succeeds. */
ZTEST_SUITE(s3, NULL, setup, NULL, NULL, NULL);

ZTEST(s3, test_a_failed_bind_leaves_file_not_ready_and_a_later_bind_succeeds)
{
    workload_config_t out = record(1, 1);

    zassert_equal(storage_port_bind(), STORAGE_PORT_ERR_BIND);
    expect_file_is_not_ready();
    zassert_equal(config_store_load(&out), CONFIG_STORE_ERR_NOT_READY);

    zassert_ok(fs_mkdir(FILES_DIRECTORY));
    zassert_equal(storage_port_bind(), STORAGE_PORT_OK);
    zassert_equal(config_store_load(&out), CONFIG_STORE_ERR_NOT_FOUND);
    zassert_equal(storage_port_bind(), STORAGE_PORT_ERR_ALREADY_BOUND);
}

#else
#error "S3_CASE names no case of this test"
#endif
