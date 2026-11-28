/* SPDX-License-Identifier: Apache-2.0 */
#ifndef FRAMEWORK_EVENTS_H
#define FRAMEWORK_EVENTS_H

/*
 * The framework's own security event identifiers (specification section 6.2, event list; L1), in
 * the project range of Crux security events, which starts at 0x8000. The composition zone declares
 * their names and classes to Crux when it initialises the events (framework/compose/
 * management_start.c); Crux emits the Access, configuration, credential and reboot events itself.
 * Plain integers, so a source of the portable core needs no Crux type to name them.
 */

/* An authorised operator requested a factory reset (section 5.3). */
#define FRAMEWORK_EVENT_FACTORY_RESET 0x8000u
/* The boot entered safe mode (section 5.2). */
#define FRAMEWORK_EVENT_SAFE_MODE 0x8001u
/* Time synchronisation set the wall time (section 6.2: a step of the wall time). */
#define FRAMEWORK_EVENT_TIME_STEP 0x8002u

#endif
