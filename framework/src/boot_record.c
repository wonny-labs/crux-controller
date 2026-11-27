/* SPDX-License-Identifier: Apache-2.0 */

#include "boot_record.h"

#include <string.h>

/* The layout of the encoded region. A change of the layout changes the format byte, so a region
 * that an older layout wrote decodes as invalid. */
#define FORMAT 1u
#define AT_FORMAT 0u
#define AT_COUNTER 1u
#define AT_FLAGS 2u
#define AT_REASON 3u
#define AT_IMAGE 4u
#define AT_SEQUENCE 8u
#define AT_UPTIME 12u
#define AT_DETAIL 16u
#define AT_NAME 20u
#define AT_CHECKSUM (AT_NAME + BOOT_NAME_SIZE)
#define FLAG_MARKER 0x01u
#define FLAG_CONSUMED 0x02u
#define FLAGS_KNOWN (FLAG_MARKER | FLAG_CONSUMED)

_Static_assert(AT_CHECKSUM + 4u == BOOT_REGION_SIZE, "the checksum is the last word of the region");

/* CRC-32 (IEEE 802.3, reflected, polynomial 0xEDB88320), bit by bit: the region is 36 bytes. */
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

static void put32(uint8_t *at, uint32_t value)
{
    at[0] = (uint8_t)value;
    at[1] = (uint8_t)(value >> 8);
    at[2] = (uint8_t)(value >> 16);
    at[3] = (uint8_t)(value >> 24);
}

static uint32_t get32(const uint8_t *at)
{
    return (uint32_t)at[0] | ((uint32_t)at[1] << 8) | ((uint32_t)at[2] << 16) |
           ((uint32_t)at[3] << 24);
}

static bool reason_known(uint32_t reason)
{
    return reason <= (uint32_t)BOOT_FAULT_STOP;
}

/* Copy name into a field of BOOT_NAME_SIZE bytes, cut and terminated, the rest zero. */
static void copy_name(char field[BOOT_NAME_SIZE], const char *name)
{
    memset(field, 0, BOOT_NAME_SIZE);
    if (name == NULL) {
        return;
    }
    for (size_t index = 0; index + 1u < BOOT_NAME_SIZE && name[index] != '\0'; index++) {
        field[index] = name[index];
    }
}

void boot_region_init(boot_region_t *region, uint32_t image_id)
{
    if (region == NULL) {
        return;
    }
    memset(region, 0, sizeof *region);
    region->image_id = image_id;
    region->fault.reason = BOOT_FAULT_NONE;
}

void boot_region_encode(const boot_region_t *region, uint8_t out[BOOT_REGION_SIZE])
{
    uint8_t flags = 0u;

    memset(out, 0, BOOT_REGION_SIZE);
    if (region->marker) {
        flags |= FLAG_MARKER;
    }
    if (region->fault.consumed) {
        flags |= FLAG_CONSUMED;
    }
    out[AT_FORMAT] = FORMAT;
    out[AT_COUNTER] = region->counter;
    out[AT_FLAGS] = flags;
    out[AT_REASON] = (uint8_t)region->fault.reason;
    put32(&out[AT_IMAGE], region->image_id);
    put32(&out[AT_SEQUENCE], region->fault.sequence);
    put32(&out[AT_UPTIME], region->fault.uptime_ms);
    put32(&out[AT_DETAIL], region->fault.detail);
    copy_name((char *)&out[AT_NAME], region->fault.name);
    put32(&out[AT_CHECKSUM], crc32(out, AT_CHECKSUM));
}

bool boot_region_decode(const uint8_t in[BOOT_REGION_SIZE], boot_region_t *region)
{
    boot_region_t decoded;

    if (in == NULL || region == NULL || in[AT_FORMAT] != FORMAT ||
        get32(&in[AT_CHECKSUM]) != crc32(in, AT_CHECKSUM) || (in[AT_FLAGS] & ~FLAGS_KNOWN) != 0u ||
        !reason_known(in[AT_REASON]) || in[AT_NAME + BOOT_NAME_SIZE - 1u] != 0u) {
        return false;
    }
    memset(&decoded, 0, sizeof decoded);
    decoded.image_id = get32(&in[AT_IMAGE]);
    decoded.counter = in[AT_COUNTER];
    decoded.marker = (in[AT_FLAGS] & FLAG_MARKER) != 0u;
    decoded.fault.reason = (boot_fault_reason_t)in[AT_REASON];
    decoded.fault.consumed = (in[AT_FLAGS] & FLAG_CONSUMED) != 0u;
    decoded.fault.sequence = get32(&in[AT_SEQUENCE]);
    decoded.fault.uptime_ms = get32(&in[AT_UPTIME]);
    decoded.fault.detail = get32(&in[AT_DETAIL]);
    memcpy(decoded.fault.name, &in[AT_NAME], BOOT_NAME_SIZE);
    *region = decoded;
    return true;
}

uint32_t boot_image_id(const char *text)
{
    uint32_t hash = 2166136261u;

    if (text != NULL) {
        for (const char *at = text; *at != '\0'; at++) {
            hash = (hash ^ (uint8_t)*at) * 16777619u;
        }
    }
    return hash;
}

/* An unconsumed record that names a fault. */
static bool record_names_fault(const boot_fault_t *fault)
{
    return !fault->consumed && fault->reason != BOOT_FAULT_NONE;
}

static bool is_fault_reset(const boot_input_t *in)
{
    const uint32_t causes = in->cause_captured ? in->causes : 0u;

    if ((causes & BOOT_CAUSE_WATCHDOG) != 0u || record_names_fault(&in->region.fault)) {
        return true;
    }
    if (in->region.marker) {
        return false;
    }
    /* CPU_LOCKUP together with SOFTWARE is a SOFTWARE reset; either alone is a fault reset too. */
    return (causes & (BOOT_CAUSE_SOFTWARE | BOOT_CAUSE_CPU_LOCKUP)) != 0u;
}

bool boot_decide(const boot_input_t *in, boot_decision_t *out)
{
    boot_decision_t decision;

    if (in == NULL || out == NULL || in->threshold == 0u) {
        return false;
    }
    memset(&decision, 0, sizeof decision);
    boot_region_init(&decision.region, in->image_id);

    const bool por = in->cause_captured && (in->causes & BOOT_CAUSE_POR) != 0u;

    if (por) {
        decision.boot_class = BOOT_CLASS_POWER_CYCLE;
    } else if (!in->region_valid) {
        /* An empty region: the captured cause alone classifies the reset. */
        boot_input_t empty = *in;

        boot_region_init(&empty.region, in->image_id);
        if (is_fault_reset(&empty)) {
            decision.boot_class = BOOT_CLASS_FAULT;
            decision.region.counter = 1u;
        } else {
            decision.boot_class = BOOT_CLASS_POWER_CYCLE;
        }
    } else {
        decision.region = in->region;
        decision.region.image_id = in->image_id;
        decision.region.marker = false;
        if (record_names_fault(&in->region.fault)) {
            decision.fault_reported = true;
            decision.fault = in->region.fault;
            decision.region.fault.consumed = true;
        }
        if (in->region.image_id != in->image_id) {
            decision.boot_class = BOOT_CLASS_NEW_IMAGE;
            decision.region.counter = 0u;
        } else if (is_fault_reset(in)) {
            decision.boot_class = BOOT_CLASS_FAULT;
            if (decision.region.counter < in->threshold) {
                decision.region.counter++;
            }
        } else {
            decision.boot_class = BOOT_CLASS_NOT_FAULT;
        }
    }
    decision.safe_mode = decision.region.counter >= in->threshold;
    *out = decision;
    return true;
}

void boot_fault_set(boot_region_t *region, boot_fault_reason_t reason, const char *name,
                    uint32_t uptime_ms, uint32_t detail)
{
    if (region == NULL || reason == BOOT_FAULT_NONE || !reason_known((uint32_t)reason)) {
        return;
    }
    region->fault.reason = reason;
    copy_name(region->fault.name, name);
    region->fault.uptime_ms = uptime_ms;
    region->fault.detail = detail;
    region->fault.sequence++;
    region->fault.consumed = false;
}

void boot_counter_clear(boot_region_t *region)
{
    if (region != NULL) {
        region->counter = 0u;
    }
}

void boot_marker_set(boot_region_t *region, bool set)
{
    if (region != NULL) {
        region->marker = set;
    }
}

const char *boot_fault_reason_name(boot_fault_reason_t reason)
{
    switch (reason) {
    case BOOT_FAULT_NONE:
        return "none";
    case BOOT_FAULT_DEADLINE:
        return "deadline";
    case BOOT_FAULT_CHANNEL:
        return "channel";
    case BOOT_FAULT_FATAL:
        return "fatal";
    case BOOT_FAULT_STOP:
        return "stop";
    default:
        return "unknown";
    }
}

const char *boot_class_name(boot_class_t boot_class)
{
    switch (boot_class) {
    case BOOT_CLASS_NOT_FAULT:
        return "normal";
    case BOOT_CLASS_FAULT:
        return "fault";
    case BOOT_CLASS_POWER_CYCLE:
        return "power";
    case BOOT_CLASS_NEW_IMAGE:
        return "image";
    default:
        return "unknown";
    }
}

void boot_stability_init(boot_stability_t *stability)
{
    if (stability != NULL) {
        memset(stability, 0, sizeof *stability);
    }
}

bool boot_stability_update(boot_stability_t *stability, bool conditions_hold, uint64_t now_ms,
                           uint64_t period_ms)
{
    if (stability == NULL || stability->done) {
        return false;
    }
    if (!conditions_hold) {
        stability->holding = false;
        return false;
    }
    if (!stability->holding) {
        stability->holding = true;
        stability->since_ms = now_ms;
    }
    if (now_ms >= stability->since_ms && now_ms - stability->since_ms >= period_ms) {
        stability->done = true;
        return true;
    }
    return false;
}
