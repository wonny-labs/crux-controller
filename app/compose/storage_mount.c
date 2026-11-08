/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The composition zone of step S3: the one place that mounts a file system and binds it to Crux
 * File. It implements the port that app/src declares, with the composition interface that Crux
 * publishes for this (<crux/file_zephyr.h>) and the two Zephyr headers on the allow-list of
 * docs/composition-zone.md. The volume is the devicetree entry labelled controller_storage, a
 * "zephyr,fstab,fatfs" node, so Zephyr itself declares the file system object and this file needs
 * no vendor or file system library header.
 */

#include "../src/storage_port.h"

#include <crux/file.h>
#include <crux/file_zephyr.h>

#include <errno.h>
#include <stdint.h>
#include <stdio.h>

#include <zephyr/devicetree.h>
#include <zephyr/fs/fs.h>

#define STORAGE_NODE DT_NODELABEL(controller_storage)
#define FILES_DIRECTORY "files"
/* File accepts 2 to 63 characters, so the buffer holds 63 and the end of string. */
#define PATH_CAPACITY 64u

FS_FSTAB_DECLARE_ENTRY(STORAGE_NODE);

static struct fs_mount_t *volume(void)
{
    return &FS_FSTAB_ENTRY(STORAGE_NODE);
}

/* The directory of the volume that File uses: the mount point and "/files". */
static int files_path(char *path, size_t capacity)
{
    const int length = snprintf(path, capacity, "%s/%s", volume()->mnt_point, FILES_DIRECTORY);

    return (length > 0 && (size_t)length < capacity) ? 0 : -1;
}

#ifdef CONFIG_FILE_SYSTEM_MKFS
/* Format the volume and create the directory that File uses. The disk is the mount point
 * without its leading slash, as the file system library names it. */
static storage_port_status_t format_and_prepare(void)
{
    char path[PATH_CAPACITY];

    if (fs_mkfs(volume()->type, (uintptr_t)(volume()->mnt_point + 1), NULL, 0) != 0) {
        return STORAGE_PORT_ERR_FORMAT;
    }
    if (fs_mount(volume()) != 0) {
        return STORAGE_PORT_ERR_MOUNT;
    }
    if (files_path(path, sizeof path) != 0 || fs_mkdir(path) != 0) {
        return STORAGE_PORT_ERR_LAYOUT;
    }
    return STORAGE_PORT_OK;
}
#else
static storage_port_status_t format_and_prepare(void)
{
    return STORAGE_PORT_ERR_FORMAT;
}
#endif

storage_port_status_t storage_port_mount(storage_port_policy_t policy)
{
    const int result = fs_mount(volume());

    if (result == 0) {
        return STORAGE_PORT_OK;
    }
    if (result == -EBUSY) {
        return STORAGE_PORT_ERR_ALREADY_MOUNTED;
    }
    if (policy == STORAGE_PORT_FORMAT_ON_FAILED_MOUNT) {
        return format_and_prepare();
    }
    return STORAGE_PORT_ERR_MOUNT;
}

storage_port_status_t storage_port_bind(void)
{
    char path[PATH_CAPACITY];

    if (files_path(path, sizeof path) != 0) {
        return STORAGE_PORT_ERR_BIND;
    }
    switch (crux_file_zephyr_bind(path)) {
    case CRUX_FILE_OK:
        return STORAGE_PORT_OK;
    case CRUX_FILE_ERR_INVALID_STATE:
        return STORAGE_PORT_ERR_ALREADY_BOUND;
    default:
        return STORAGE_PORT_ERR_BIND;
    }
}
