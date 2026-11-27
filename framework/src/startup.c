/* SPDX-License-Identifier: Apache-2.0 */

#include "startup.h"

static bool table_valid(const startup_phase_t *phases, size_t count, startup_report_t report)
{
    if (report == NULL || (phases == NULL && count > 0u)) {
        return false;
    }
    for (size_t index = 0; index < count; index++) {
        if (phases[index].name == NULL || phases[index].run == NULL) {
            return false;
        }
    }
    return true;
}

startup_status_t startup_run(const startup_phase_t *phases, size_t count, startup_report_t report,
                             startup_summary_t *summary)
{
    startup_summary_t local = {0u, 0u};
    startup_status_t status = STARTUP_OK;

    if (!table_valid(phases, count, report)) {
        status = STARTUP_ERR_INVALID_ARGUMENT;
    } else {
        for (size_t index = 0; index < count; index++) {
            const int result = phases[index].run();

            local.completed++;
            report(phases[index].name, result);
            if (result != 0) {
                local.failed++;
                if (phases[index].required) {
                    status = STARTUP_ERR_REQUIRED_PHASE;
                    break;
                }
            }
        }
    }
    if (summary != NULL) {
        *summary = local;
    }
    return status;
}

static bool steps_valid(const startup_step_t *steps, size_t count, startup_report_t report,
                        const startup_hooks_t *hooks)
{
    if (report == NULL || (steps == NULL && count > 0u)) {
        return false;
    }
    if (hooks != NULL && (hooks->begin == NULL || hooks->end == NULL || hooks->skipped == NULL)) {
        return false;
    }
    for (size_t index = 0; index < count; index++) {
        if (steps[index].phase.name == NULL || steps[index].phase.run == NULL) {
            return false;
        }
    }
    return true;
}

startup_status_t startup_run_steps(const startup_step_t *steps, size_t count,
                                   startup_report_t report, const startup_hooks_t *hooks,
                                   startup_summary_t *summary)
{
    startup_summary_t local = {0u, 0u};
    startup_status_t status = STARTUP_OK;

    if (!steps_valid(steps, count, report, hooks)) {
        status = STARTUP_ERR_INVALID_ARGUMENT;
    } else {
        for (size_t index = 0; index < count; index++) {
            const startup_step_t *step = &steps[index];

            if (step->skip != NULL && step->skip()) {
                if (hooks != NULL) {
                    hooks->skipped(step->phase.name);
                }
                continue;
            }
            if (hooks != NULL) {
                hooks->begin(step->phase.name, step->deadline_ms);
            }
            const int result = step->phase.run();

            if (hooks != NULL) {
                hooks->end(step->phase.name);
            }
            local.completed++;
            report(step->phase.name, result);
            if (result != 0) {
                local.failed++;
                if (step->phase.required) {
                    status = STARTUP_ERR_REQUIRED_PHASE;
                    break;
                }
            }
        }
    }
    if (summary != NULL) {
        *summary = local;
    }
    return status;
}
