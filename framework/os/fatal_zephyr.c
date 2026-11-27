/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The framework's fatal error policy (specification sections 4.3 and 4.8): Zephyr documents
 * k_sys_fatal_error_handler() as the place where an application introduces its own policy, and the
 * framework owns it, so a product defines no handler of its own.
 *
 * The handler calls no application entry. It writes a minimal record, with the reason and the name
 * of the thread that failed, through the retained port, which takes no mutex. Then it resets:
 * crux_system_reset() where the handler runs in thread context (native_sim), otherwise
 * k_fatal_halt(), after which the armed, unfed hardware watchdog resets the device within T. Crux
 * refuses its reset in interrupt context, and on a Cortex-M the handler runs in the fault
 * exception. In a build whose watchdog is not armed the halt is final; a product build does not run
 * the application in that case (D14). Label: the handler is an established mechanism; the halt that
 * leaves the reset to the watchdog is a project-specific workaround, because zephyr/sys/reboot.h,
 * which Zephyr's own default handler uses with CONFIG_RESET_ON_FATAL_ERROR (kernel/fatal.c), is not
 * on the allow-list of the adapter zone.
 *
 * Status: built in CI for the board and run on native_sim; never run on a board.
 */

#include "../src/recovery.h"

#include <crux/system.h>

#include <stddef.h>
#include <stdint.h>

#include <zephyr/fatal.h>
#include <zephyr/kernel.h>

void k_sys_fatal_error_handler(unsigned int reason, const struct arch_esf *esf)
{
    ARG_UNUSED(esf);
#ifdef CONFIG_THREAD_NAME
    const char *name = k_thread_name_get(k_current_get());
#else
    const char *name = NULL;
#endif

    recovery_fault(BOOT_FAULT_FATAL, name, k_uptime_get_32(), (uint32_t)reason);
    (void)crux_system_reset();
    k_fatal_halt(reason);
}
