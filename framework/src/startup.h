/* SPDX-License-Identifier: Apache-2.0 */
#ifndef STARTUP_H
#define STARTUP_H

/*
 * The startup sequence of the controller framework: a table of phases that run once each, in the
 * order of the table, on the thread that calls startup_run(). Plain C with no Crux or Zephyr
 * include, so that the host tests run it with fake phases (tests/host/test_startup.c).
 *
 * A phase returns 0 on success; any other value is a failure. Each phase is reported once, with
 * its name and result, after it returns. A failed phase that is required stops the sequence and
 * the phases after it do not run. A failed phase that is not required is reported and the
 * sequence goes on, so the controller runs with that service degraded (degrade and report).
 */

#include <stdbool.h>
#include <stddef.h>

typedef int (*startup_phase_run_t)(void);

typedef struct {
    /* Named in the report; borrowed for the program's life. */
    const char *name;
    startup_phase_run_t run;
    /* True: a failure stops the sequence. */
    bool required;
} startup_phase_t;

/* Called once for each phase that ran, with the phase name and the result it returned. */
typedef void (*startup_report_t)(const char *name, int result);

typedef struct {
    size_t completed; /* Phases that ran, whatever their result. */
    size_t failed;    /* Phases that ran and failed. */
} startup_summary_t;

typedef enum {
    STARTUP_OK = 0,                    /* Every required phase succeeded. */
    STARTUP_ERR_INVALID_ARGUMENT = -1, /* No phase ran: the table or the report is not valid. */
    STARTUP_ERR_REQUIRED_PHASE = -2, /* A required phase failed; the phases after it did not run. */
} startup_status_t;

/*
 * Run the phases in order and report each one. The table is checked before any phase runs: a
 * NULL table with a count above zero, a phase without a name or a function, or a NULL report is
 * refused and nothing runs. summary may be NULL; when given it is set on every return.
 */
startup_status_t startup_run(const startup_phase_t *phases, size_t count, startup_report_t report,
                             startup_summary_t *summary);

#endif
