/* SPDX-License-Identifier: Apache-2.0 */

/*
 * Test-only retained memory for the native_sim scenarios (dts/bindings/vnd,retained-env.yaml).
 * Zephyr has no retained memory on native_sim that survives the restart of
 * CONFIG_NATIVE_SIM_REBOOT, which runs the program again with execv(). The environment of the
 * process survives that call, so this driver keeps its bytes in the environment variable
 * CONTROLLER_TEST_RETAINED, as hexadecimal text, and reads them back at the next start. It is a
 * project-specific workaround for the scenarios and models no board: whether a board's retained
 * RAM survives its resets is a board fact (specification section 5.6).
 */

#define DT_DRV_COMPAT vnd_retained_env

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <nsi_host_trampolines.h>
#include <zephyr/device.h>
#include <zephyr/drivers/retained_mem.h>
#include <zephyr/kernel.h>

#define ENV_NAME "CONTROLLER_TEST_RETAINED"
#define AREA_SIZE DT_INST_PROP(0, size)

static uint8_t area[AREA_SIZE];
static char text[2 * AREA_SIZE + 1];

static int nibble(char c)
{
    if (c >= '0' && c <= '9') {
        return c - '0';
    }
    if (c >= 'a' && c <= 'f') {
        return c - 'a' + 10;
    }
    return -1;
}

static void persist(void)
{
    static const char digits[] = "0123456789abcdef";

    for (size_t index = 0; index < AREA_SIZE; index++) {
        text[2 * index] = digits[area[index] >> 4];
        text[2 * index + 1] = digits[area[index] & 0x0f];
    }
    text[(size_t)2 * AREA_SIZE] = '\0';
    (void)nsi_host_setenv(ENV_NAME, text, 1);
}

static int env_init(const struct device *dev)
{
    ARG_UNUSED(dev);
    const char *stored = nsi_host_getenv(ENV_NAME);

    /* A first start has no variable: the area holds zeros, which no retention prefix matches. */
    memset(area, 0, sizeof area);
    if (stored == NULL || strlen(stored) != (size_t)2 * AREA_SIZE) {
        return 0;
    }
    for (size_t index = 0; index < AREA_SIZE; index++) {
        const int high = nibble(stored[2 * index]);
        const int low = nibble(stored[2 * index + 1]);

        if (high < 0 || low < 0) {
            memset(area, 0, sizeof area);
            return 0;
        }
        area[index] = (uint8_t)((high << 4) | low);
    }
    return 0;
}

static ssize_t env_size(const struct device *dev)
{
    ARG_UNUSED(dev);
    return (ssize_t)AREA_SIZE;
}

static int env_read(const struct device *dev, off_t offset, uint8_t *buffer, size_t size)
{
    ARG_UNUSED(dev);
    memcpy(buffer, &area[offset], size);
    return 0;
}

static int env_write(const struct device *dev, off_t offset, const uint8_t *buffer, size_t size)
{
    ARG_UNUSED(dev);
    memcpy(&area[offset], buffer, size);
    persist();
    return 0;
}

static int env_clear(const struct device *dev)
{
    ARG_UNUSED(dev);
    memset(area, 0, sizeof area);
    persist();
    return 0;
}

static DEVICE_API(retained_mem, env_api) = {
    .size = env_size,
    .read = env_read,
    .write = env_write,
    .clear = env_clear,
};

DEVICE_DT_INST_DEFINE(0, env_init, NULL, NULL, NULL, PRE_KERNEL_1,
                      CONFIG_RETAINED_MEM_INIT_PRIORITY, &env_api);
