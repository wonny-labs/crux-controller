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

#include <stdbool.h>

typedef enum {
    FRAMEWORK_CONTROL_REQUESTED = 0,  /* posted to the application thread */
    FRAMEWORK_CONTROL_NO_APPLICATION, /* the image has no application */
    FRAMEWORK_CONTROL_STARTING,       /* startup supervision has not ended yet */
    FRAMEWORK_CONTROL_RESETTING,      /* a planned reset is under way */
} framework_control_t;

framework_control_t framework_control_application_stop(void);
framework_control_t framework_control_application_start(void);

/*
 * The rules of a stop and a start that an operator requests and of a planned reset are in
 * app_requests.h: the newest operator request wins, and a planned reset refuses later starts and
 * drops a waiting one.
 */

/*
 * The framework's judgement of a restart through Crux Reboot, on any thread: false while the step
 * table of an image with an application runs, because step 12 may be about to call start or may be
 * inside it, and a reset then would skip stop and safe_state. True for an image without an
 * application.
 */
bool framework_control_restart_allowed(void);

/*
 * Before a planned reset (specification section 3.3), on the framework's reboot thread just before
 * Crux Reboot resets the device, after framework_control_restart_allowed() returned true: refuse
 * later operator requests, then stop a running application with the reason planned reset on the
 * application thread and wait until that stop and its safe_state have run. The wait is bounded by
 * the stop's deadline, which the supervisor enforces. Does nothing with no application.
 */
void framework_control_planned_reset(void);

/* After a pass of the reboot thread: no reset happened, so operator requests are accepted again. */
void framework_control_reset_abandoned(void);

/*
 * A factory reset (specification section 5.3), which an authorised operator requests before asking
 * Crux Reboot for the restart: set true marks the next planned reset as a factory reset, and false
 * withdraws the mark when Crux Reboot refused the request. framework_control_planned_reset() then
 * runs the data part (management_port_factory_reset()) on the reboot thread, after the application
 * stopped and before the operator reset marker is written, and clears the mark. Any thread.
 */
void framework_control_factory_reset(bool requested);

/*
 * On the reboot thread, after crux_reboot_work_once() carried out a request that ended without a
 * reset (reboot_policy.h): withdraw a factory reset mark, so that a later restart that someone
 * without access.manage requests erases nothing (specification sections 5.3 and 6.2).
 */
void framework_control_restart_ended(void);

#endif
