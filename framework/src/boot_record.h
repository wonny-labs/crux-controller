/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BOOT_RECORD_H
#define BOOT_RECORD_H

/*
 * The retained region of the controller framework and the rules that read it at boot: the boot
 * counter, the operator reset marker, the image identifier and the last-fault record, the reset
 * classification of specification section 5.1 and the boot counter and safe mode of section 5.2.
 * Plain C with ISO C includes only, so the host tests run every rule
 * (tests/host/test_boot_record.c).
 *
 * The region is a fixed layout of BOOT_REGION_SIZE bytes, little-endian, with a format byte first
 * and a CRC-32 of the bytes before it last. The adapter zone keeps the bytes in a Zephyr retention
 * area, which adds its own prefix and checksum around them; this file decides nothing about where
 * the bytes live. A region whose format byte or checksum does not match decodes as invalid, and an
 * invalid region counts as a region that did not survive (a power cycle).
 *
 * The reset cause bits are copies of Crux's CRUX_RESET_CAUSE_* values, because this file has no
 * Crux include; framework/src/recovery.c asserts at build time that each copy equals the Crux
 * value.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum {
    BOOT_CAUSE_POR = 1u << 0,
    BOOT_CAUSE_PIN = 1u << 1,
    BOOT_CAUSE_SOFTWARE = 1u << 2,
    BOOT_CAUSE_WATCHDOG = 1u << 3,
    BOOT_CAUSE_DEBUG = 1u << 4,
    BOOT_CAUSE_CPU_LOCKUP = 1u << 5,
};

/* Bytes of the encoded region, its checksum included. */
#define BOOT_REGION_SIZE 40u
/* Bytes of a name in a fault record, its terminator included. */
#define BOOT_NAME_SIZE 16u
/* The largest counter that the region can hold. The counter saturates at the threshold N: section
 * 5.2 says that it saturates and that in safe mode it "stays saturated", which holds only when the
 * maximum is N (project-specific reading of the specification; no other source). */
#define BOOT_COUNTER_MAX 255u

/* Why the supervisor or the fatal error handler wrote the record. */
typedef enum {
    BOOT_FAULT_NONE = 0,     /* no record */
    BOOT_FAULT_DEADLINE = 1, /* a startup step passed its deadline; the name is the step */
    BOOT_FAULT_CHANNEL = 2,  /* a task watchdog channel expired; the name is the channel */
    BOOT_FAULT_FATAL = 3,    /* the fatal error handler ran; detail is the Zephyr reason */
    BOOT_FAULT_STOP = 4,     /* an application stop returned an error or passed its deadline */
} boot_fault_reason_t;

typedef struct {
    boot_fault_reason_t reason;
    char name[BOOT_NAME_SIZE]; /* terminated; empty when the reason names none */
    uint32_t uptime_ms;        /* uptime of the boot that wrote it, when it was written */
    uint32_t detail;           /* the fatal error reason, otherwise 0 */
    uint32_t sequence;         /* one more than the record before it */
    bool consumed;             /* a boot has read and reported it */
} boot_fault_t;

typedef struct {
    uint32_t image_id; /* the image that wrote the region (boot_image_id()) */
    uint8_t counter;   /* consecutive fault resets */
    bool marker;       /* the operator reset marker */
    boot_fault_t fault;
} boot_region_t;

/* A blank region of the image: counter zero, no marker, no record. */
void boot_region_init(boot_region_t *region, uint32_t image_id);

/* The bytes of the region, checksum last. */
void boot_region_encode(const boot_region_t *region, uint8_t out[BOOT_REGION_SIZE]);

/*
 * The region in the bytes. False, with *region untouched, when the format byte, the checksum, the
 * reason or the name does not hold: a damaged region and a write that a reset interrupted.
 */
bool boot_region_decode(const uint8_t in[BOOT_REGION_SIZE], boot_region_t *region);

/* A 32-bit identifier of an image from a text of the build (FNV-1a). */
uint32_t boot_image_id(const char *text);

/* How the boot was classified. */
typedef enum {
    BOOT_CLASS_NOT_FAULT,   /* a reset that the counter does not count */
    BOOT_CLASS_FAULT,       /* a fault reset: the counter counts it */
    BOOT_CLASS_POWER_CYCLE, /* the region did not survive: counter zero, no record */
    BOOT_CLASS_NEW_IMAGE,   /* another image wrote the region: counter zero, its record reported */
} boot_class_t;

typedef struct {
    bool cause_captured; /* false: the reset cause could not be read */
    uint32_t causes;     /* BOOT_CAUSE_* bits that were latched, when captured */
    bool region_valid;   /* the adapter found the region and it decoded */
    boot_region_t region;
    uint32_t image_id; /* the running image */
    uint8_t threshold; /* N: safe mode from this many consecutive fault resets, at least 1 */
} boot_input_t;

typedef struct {
    boot_class_t boot_class;
    bool safe_mode;
    bool fault_reported; /* fault holds the record that this boot reports */
    boot_fault_t fault;
    boot_region_t region; /* what to write back: counter, no marker, the record consumed */
} boot_decision_t;

/*
 * Classify the reset and decide the boot (specification sections 5.1 and 5.2). False for a NULL
 * argument or a threshold of zero, with *out untouched.
 *
 * - A captured POR means that the region did not survive, whatever other bits are latched: the
 *   counter starts at zero and no record is reported.
 * - An invalid region without POR (a write that a reset interrupted, or a region that did not
 *   survive a reset that reads as PIN) counts as an empty region: no record and no marker, and the
 *   captured cause alone decides whether the reset was a fault reset, so the counter is zero or
 * one. Without the marker, SOFTWARE and CPU_LOCKUP count. Section 5.1 states both this rule and the
 *   power-cycle rule; this reading keeps a watchdog reset counted when its region was torn.
 * - A region of another image clears the counter and reports that image's last record.
 * - Otherwise the reset is a fault reset when WATCHDOG is latched, when an unconsumed record names
 *   a deadline, a channel, a fatal error or a stop, or, without the operator reset marker, when
 *   SOFTWARE or CPU_LOCKUP is latched (CPU_LOCKUP together with SOFTWARE is a SOFTWARE reset). PIN
 *   and DEBUG count only through one of these. Without a captured cause only the record counts.
 * - A fault reset adds one to the counter until it reaches the threshold, where it saturates; safe
 *   mode holds while the counter is at or above the threshold.
 * - The marker is cleared, and a reported record is marked consumed, so a later reset counts and
 *   reports it no more.
 */
bool boot_decide(const boot_input_t *in, boot_decision_t *out);

/* What a new fault record says. */
typedef struct {
    boot_fault_reason_t reason;
    const char *name;   /* NULL for none; cut to BOOT_NAME_SIZE - 1 bytes */
    uint32_t uptime_ms; /* uptime of the boot that writes it */
    uint32_t detail;    /* the fatal error reason, otherwise 0 */
} boot_fault_info_t;

/*
 * Write a fault record into the region: the next sequence number, not consumed. Nothing for a
 * NULL argument or the reason BOOT_FAULT_NONE.
 */
void boot_fault_set(boot_region_t *region, const boot_fault_info_t *info);

/* The counter to zero: a successful boot or an authorised operator command. */
void boot_counter_clear(boot_region_t *region);

/* Set or clear the operator reset marker. */
void boot_marker_set(boot_region_t *region, bool set);

/* Lower-case words for the log and the status service; "unknown" for a value out of range. */
const char *boot_fault_reason_name(boot_fault_reason_t reason);
const char *boot_class_name(boot_class_t boot_class);

/*
 * The successful boot of section 5.2: the conditions (controller operational, application neither
 * in fault nor held) must hold without interruption for the stable period. The period starts when
 * they begin to hold and starts again when they stop.
 */
typedef struct {
    bool holding;
    uint64_t since_ms;
    bool done;
} boot_stability_t;

void boot_stability_init(boot_stability_t *stability);

/* True exactly once: on the first update at which the conditions have held for period_ms. */
bool boot_stability_update(boot_stability_t *stability, bool conditions_hold, uint64_t now_ms,
                           uint64_t period_ms);

#endif
