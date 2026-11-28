/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The composition zone of the file capability: the one place that mounts a file system and binds it
 * to Crux File. It implements the port that framework/src declares, with the composition interface
 * that Crux publishes for this (<crux/file_zephyr.h>) and the Zephyr headers on the zone's
 * allow-list in docs/composition-zone.md. The volume is the devicetree entry labelled
 * controller_storage, a "zephyr,fstab,fatfs" node or a "zephyr,fstab,littlefs" node on a flash
 * partition, so Zephyr itself declares the file system object and this file needs no vendor or file
 * system library header.
 */

#include "../src/storage_port.h"

#include <crux/file.h>
#include <crux/file_zephyr.h>

#include <errno.h>
#include <stdbool.h>
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

#if DT_NODE_HAS_COMPAT(STORAGE_NODE, zephyr_fstab_littlefs)
    /* LittleFS on a flash partition: the device is the flash area, and the volume's own
     * configuration from the devicetree. */
    if (fs_mkfs(volume()->type, (uintptr_t)volume()->storage_dev, volume()->fs_data, 0) != 0) {
        return STORAGE_PORT_ERR_FORMAT;
    }
#else
    if (fs_mkfs(volume()->type, (uintptr_t)(volume()->mnt_point + 1), NULL, 0) != 0) {
        return STORAGE_PORT_ERR_FORMAT;
    }
#endif
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

#ifdef CONFIG_CRUX_WEB_MANAGEMENT
/*
 * The management capability only: the two directories of the credential store. This part is
 * compiled only when the web management symbol of Crux is on, which the management fragment sets,
 * so the object of every other configuration, file included, is the one it was before.
 */

/* The two directories of the credential store of management, one for each of its slots. */
#define STORE_DIRECTORY_A "secure-a"
#define STORE_DIRECTORY_B "secure-b"

/* A directory of the volume: the mount point, a slash and the name. */
static int directory_path(char *path, size_t capacity, const char *name)
{
    const int length = snprintf(path, capacity, "%s/%s", volume()->mnt_point, name);

    return (length > 0 && (size_t)length < capacity) ? 0 : -1;
}

/* A directory that exists afterwards. An existing entry is fine here: File refuses it at the bind
 * when it is not a directory. */
static int make_directory(const char *path)
{
    const int result = fs_mkdir(path);

    return (result == 0 || result == -EEXIST) ? 0 : -1;
}

storage_port_status_t storage_port_bind_store(void)
{
    char path_a[PATH_CAPACITY];
    char path_b[PATH_CAPACITY];

    if (directory_path(path_a, sizeof path_a, STORE_DIRECTORY_A) != 0 ||
        directory_path(path_b, sizeof path_b, STORE_DIRECTORY_B) != 0) {
        return STORAGE_PORT_ERR_BIND;
    }
    if (make_directory(path_a) != 0 || make_directory(path_b) != 0) {
        return STORAGE_PORT_ERR_LAYOUT;
    }
    switch (crux_file_zephyr_bind_root(STORAGE_PORT_STORE_ROOT_A, path_a)) {
    case CRUX_FILE_OK:
        break;
    case CRUX_FILE_ERR_INVALID_STATE:
        return STORAGE_PORT_ERR_ALREADY_BOUND;
    default:
        return STORAGE_PORT_ERR_BIND;
    }
    switch (crux_file_zephyr_bind_root(STORAGE_PORT_STORE_ROOT_B, path_b)) {
    case CRUX_FILE_OK:
        return STORAGE_PORT_OK;
    case CRUX_FILE_ERR_INVALID_STATE:
        return STORAGE_PORT_ERR_ALREADY_BOUND;
    default:
        return STORAGE_PORT_ERR_BIND;
    }
}
/* The directory of the application's data (specification section 3.2). */
#define APP_DIRECTORY "app"

/* The data root's path and limit, kept for storage_port_app_root_full(); set once by the bind. */
static char app_path[PATH_CAPACITY];
static uint64_t app_max_bytes;

storage_port_status_t storage_port_bind_app(unsigned long long max_bytes)
{
    char path[PATH_CAPACITY];

    if (max_bytes == 0u || directory_path(path, sizeof path, APP_DIRECTORY) != 0) {
        return STORAGE_PORT_ERR_BIND;
    }
    if (make_directory(path) != 0) {
        return STORAGE_PORT_ERR_LAYOUT;
    }
    switch (crux_file_zephyr_bind_root_limited(STORAGE_PORT_APP_ROOT, path, max_bytes)) {
    case CRUX_FILE_OK:
        (void)snprintf(app_path, sizeof app_path, "%s", path);
        app_max_bytes = max_bytes;
        return STORAGE_PORT_OK;
    case CRUX_FILE_ERR_INVALID_STATE:
        return STORAGE_PORT_ERR_ALREADY_BOUND;
    default:
        return STORAGE_PORT_ERR_BIND;
    }
}

/* A size rounded up to whole allocation units, and at least one unit, as Crux File counts a file
 * against the limit (Crux docs/file-contract.md, "Root byte limits"). */
static uint64_t counted(uint64_t size, uint64_t unit)
{
    const uint64_t units = size == 0u ? 1u : (size + unit - 1u) / unit;

    return units * unit;
}

storage_port_status_t storage_port_app_root_full(_Bool *full)
{
    struct fs_statvfs volume_info;

    if (full == NULL || app_max_bytes == 0u || fs_statvfs(app_path, &volume_info) != 0 ||
        volume_info.f_frsize == 0u) {
        return STORAGE_PORT_ERR_BIND;
    }
    const uint64_t unit = (uint64_t)volume_info.f_frsize;
    crux_file_dir_t *dir = NULL;
    uint64_t used = 0u;

    if (crux_file_dir_open(STORAGE_PORT_APP_ROOT, &dir) != CRUX_FILE_OK) {
        return STORAGE_PORT_ERR_BIND;
    }
    for (;;) {
        /* crux_file_dir_read() needs at least 64 bytes for a name. */
        char name[64];
        crux_file_info_t info;
        bool end = false;

        if (crux_file_dir_read(dir, name, sizeof name, &info, &end) != CRUX_FILE_OK) {
            (void)crux_file_dir_close(&dir);
            return STORAGE_PORT_ERR_BIND;
        }
        if (end) {
            break;
        }
        used += counted(info.size, unit);
    }
    (void)crux_file_dir_close(&dir);
    *full = used + unit > app_max_bytes;
    return STORAGE_PORT_OK;
}
#endif /* CONFIG_CRUX_WEB_MANAGEMENT */
