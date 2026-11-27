/* SPDX-License-Identifier: Apache-2.0 */
#ifndef FRAMEWORK_CONTROL_H
#define FRAMEWORK_CONTROL_H

/*
 * The operator stop and operator start of the application (specification sections 4.4 and 4.8),
 * which device management requests. The start function implements them (framework/src/framework.c)
 * and carries each out on the application thread, so the calling thread of device management does
 * not wait for the application. The composition zone offers them as the serial commands
 * "application stop" and "application start" (framework/compose/supervision_start.c).
 */

typedef enum {
    FRAMEWORK_CONTROL_REQUESTED = 0,  /* posted to the application thread */
    FRAMEWORK_CONTROL_NO_APPLICATION, /* the image has no application */
    FRAMEWORK_CONTROL_STARTING,       /* startup supervision has not ended yet */
} framework_control_t;

framework_control_t framework_control_application_stop(void);
framework_control_t framework_control_application_start(void);

#endif
