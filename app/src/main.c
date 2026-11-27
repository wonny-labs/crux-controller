/* SPDX-License-Identifier: Apache-2.0 */

/* The base image starts the controller framework with no application. The configurations built on
 * the workload start their own services through composition.c. */

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK
#include <controller/framework.h>
#endif

#include "composition.h"

int main(void)
{
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK
    return controller_framework_start(NULL) == CONTROLLER_FRAMEWORK_OK ? 0 : -1;
#else
    return composition_start() == 0 ? 0 : -1;
#endif
}
