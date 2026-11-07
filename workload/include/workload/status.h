/* SPDX-License-Identifier: Apache-2.0 */
#ifndef WORKLOAD_STATUS_H
#define WORKLOAD_STATUS_H

#ifdef __cplusplus
extern "C" {
#endif

/** Result of every workload call. Zero is success. */
typedef enum {
    WORKLOAD_OK = 0,
    WORKLOAD_ERR_NULL,         /**< A required pointer argument was NULL. */
    WORKLOAD_ERR_RANGE,        /**< A value is outside its documented range. */
    WORKLOAD_ERR_SHORT_BUFFER, /**< The output buffer is too small. Nothing was written. */
    WORKLOAD_ERR_TRUNCATED,    /**< The input is a valid prefix of a frame but incomplete. */
    WORKLOAD_ERR_FORMAT        /**< The input is not a valid frame. */
} workload_status_t;

#ifdef __cplusplus
}
#endif

#endif
