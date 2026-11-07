/* SPDX-License-Identifier: Apache-2.0 */
#ifndef WORKLOAD_H
#define WORKLOAD_H

/*
 * A synthetic workload: a validated configuration record, a periodic cycle that
 * catches up after a stall, and a message with a fixed wire form. Plain C17 with no
 * Crux, Zephyr or vendor include. The caller supplies the clock and owns every state.
 */

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Result of every call. A NULL pointer argument counts as WORKLOAD_ERR_RANGE. */
typedef enum {
    WORKLOAD_OK = 0,
    WORKLOAD_ERR_RANGE,  /**< A value or argument is out of range. */
    WORKLOAD_ERR_SIZE,   /**< The output buffer is too small. Nothing was written. */
    WORKLOAD_ERR_FORMAT, /**< The input is not one whole message. */
} workload_status_t;

#define WORKLOAD_PERIOD_MIN_MS 10u
#define WORKLOAD_PERIOD_MAX_MS 60000u
#define WORKLOAD_MESSAGE_EVERY_MIN 1u
#define WORKLOAD_MESSAGE_EVERY_MAX 1000u

/** Configuration record. */
typedef struct {
    uint32_t period_ms;     /**< Cycle period, WORKLOAD_PERIOD_MIN_MS to WORKLOAD_PERIOD_MAX_MS. */
    uint32_t message_every; /**< One message every this many cycles, 1 to 1000. */
} workload_config_t;

/** Write the default record (100 ms, a message every 10 cycles). */
workload_status_t workload_config_default(workload_config_t *out);

/** Check every field against its range. */
workload_status_t workload_config_validate(const workload_config_t *config);

/** A periodic schedule on a caller-supplied millisecond clock. */
typedef struct {
    uint64_t next_ms; /**< When the next cycle is due. */
    uint32_t cycle;   /**< Cycles counted so far. Wraps at 2^32. */
} workload_cycle_t;

/** Start a schedule. The first cycle is due one period after now_ms. */
workload_status_t workload_cycle_init(workload_cycle_t *cycle, const workload_config_t *config,
                                      uint64_t now_ms);

/**
 * Count the cycles that are due at now_ms and advance the schedule past them, on its
 * original grid, so a stall is made up in one call. Time arithmetic is modulo 2^64, so a
 * clock that wraps keeps working. A now_ms that is behind the schedule, including time
 * that went backwards, counts as no cycle. If more than UINT32_MAX cycles are due, the
 * call returns WORKLOAD_ERR_RANGE and changes nothing.
 */
workload_status_t workload_cycle_due(workload_cycle_t *cycle, const workload_config_t *config,
                                     uint64_t now_ms, uint32_t *cycles_elapsed);

/** Message wire form: eight bytes, big-endian cycle, then big-endian value. */
#define WORKLOAD_MESSAGE_SIZE 8u

typedef struct {
    uint32_t cycle;
    uint32_t value;
} workload_message_t;

/** Write one message. On any failure the buffer and *length are untouched. */
workload_status_t workload_message_encode(const workload_message_t *message, uint8_t *buffer,
                                          size_t capacity, size_t *length);

/** Read one message. The input must be exactly WORKLOAD_MESSAGE_SIZE bytes. On failure *message is untouched. */
workload_status_t workload_message_decode(const uint8_t *buffer, size_t length,
                                          workload_message_t *message);

#ifdef __cplusplus
}
#endif

#endif
