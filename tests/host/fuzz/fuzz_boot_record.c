/* SPDX-License-Identifier: Apache-2.0 */

/*
 * Fuzz target of the retained-record decode (boot_record.h; criterion 41). The retained region
 * survives warm resets and can hold any bytes after a torn write or a damaged region, so the
 * decode and the boot decision must accept any input. The input is laid out as:
 *
 *   bytes 0 to 39  the encoded region (shorter input is padded with zero bytes)
 *   byte 40        bit 0: write a correct checksum first, so that the fields behind it are reached;
 *                  bit 1: the reset cause was captured
 *   byte 41        the BOOT_CAUSE_* bits
 *   byte 42        the threshold N (zero reads as one)
 *   bytes 43 to 46 the running image identifier, little-endian (missing bytes read as zero)
 *
 * Properties checked, each with abort() on failure:
 * - a region that decodes encodes again to bytes that decode to the same region;
 * - the boot decision accepts the decoded region, clears the marker, marks a reported record
 *   consumed, never raises the counter above the larger of its old value and N, and sets safe mode
 *   exactly when the counter is at or above N;
 * - the region that the boot writes back always decodes.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "boot_record.h"
#include "fuzz_target.h"

#define CONTROL_AT BOOT_REGION_SIZE
#define FLAG_FIX_CHECKSUM 0x01u
#define FLAG_CAUSE_CAPTURED 0x02u

/* The CRC-32 of boot_record.c (IEEE 802.3, reflected, polynomial 0xEDB88320), over the bytes
 * before the checksum word. A copy, because boot_record.c keeps its own static. */
static uint32_t crc32(const uint8_t *data, size_t length)
{
    uint32_t crc = 0xffffffffu;

    for (size_t index = 0; index < length; index++) {
        crc ^= data[index];
        for (unsigned bit = 0; bit < 8u; bit++) {
            crc = (crc & 1u) != 0u ? (crc >> 1) ^ 0xedb88320u : crc >> 1;
        }
    }
    return ~crc;
}

static uint8_t byte_at(const uint8_t *data, size_t size, size_t index)
{
    return index < size ? data[index] : 0u;
}

static void require(bool condition)
{
    if (!condition) {
        abort();
    }
}

static bool same_region(const boot_region_t *a, const boot_region_t *b)
{
    return a->image_id == b->image_id && a->counter == b->counter && a->marker == b->marker &&
           a->fault.reason == b->fault.reason && a->fault.uptime_ms == b->fault.uptime_ms &&
           a->fault.detail == b->fault.detail && a->fault.sequence == b->fault.sequence &&
           a->fault.consumed == b->fault.consumed &&
           strncmp(a->fault.name, b->fault.name, BOOT_NAME_SIZE) == 0;
}

/* Encode and decode again: the result must decode, to the same region. */
static void require_round_trip(const boot_region_t *region)
{
    uint8_t bytes[BOOT_REGION_SIZE];
    boot_region_t again;

    boot_region_encode(region, bytes);
    require(boot_region_decode(bytes, &again));
    require(same_region(region, &again));
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    uint8_t bytes[BOOT_REGION_SIZE];
    const uint8_t flags = byte_at(data, size, CONTROL_AT);
    boot_input_t in;
    boot_decision_t out;

    for (size_t index = 0; index < BOOT_REGION_SIZE; index++) {
        bytes[index] = byte_at(data, size, index);
    }
    if ((flags & FLAG_FIX_CHECKSUM) != 0u) {
        const uint32_t crc = crc32(bytes, BOOT_REGION_SIZE - 4u);

        for (size_t index = 0; index < 4u; index++) {
            bytes[BOOT_REGION_SIZE - 4u + index] = (uint8_t)(crc >> (8u * index));
        }
    }

    memset(&in, 0, sizeof in);
    in.region_valid = boot_region_decode(bytes, &in.region);
    if (in.region_valid) {
        /* The decode keeps the name terminated. */
        require(memchr(in.region.fault.name, '\0', BOOT_NAME_SIZE) != NULL);
        require_round_trip(&in.region);
    } else {
        boot_region_init(&in.region, 0u);
    }

    in.cause_captured = (flags & FLAG_CAUSE_CAPTURED) != 0u;
    in.causes = byte_at(data, size, CONTROL_AT + 1u);
    in.threshold = byte_at(data, size, CONTROL_AT + 2u);
    if (in.threshold == 0u) {
        in.threshold = 1u;
    }
    for (size_t index = 0; index < 4u; index++) {
        in.image_id |= (uint32_t)byte_at(data, size, CONTROL_AT + 3u + index) << (8u * index);
    }

    require(boot_decide(&in, &out));
    require(!out.region.marker);
    require(out.region.image_id == in.image_id);
    require(!out.fault_reported || out.region.fault.consumed);
    const unsigned old_counter = in.region_valid ? in.region.counter : 0u;
    const unsigned ceiling = old_counter > in.threshold ? old_counter : in.threshold;
    require(out.region.counter <= ceiling);
    require(out.safe_mode == (out.region.counter >= in.threshold));
    require_round_trip(&out.region);
    return 0;
}
