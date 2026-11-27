/* SPDX-License-Identifier: Apache-2.0 */

#include "supervision.h"

#include <stdio.h>
#include <string.h>

static void copy_name(char field[BOOT_NAME_SIZE], const char *name)
{
    memset(field, 0, BOOT_NAME_SIZE);
    if (name == NULL) {
        return;
    }
    for (size_t index = 0; index + 1u < BOOT_NAME_SIZE && name[index] != '\0'; index++) {
        field[index] = name[index];
    }
}

void supervision_init(supervision_t *state)
{
    if (state != NULL) {
        memset(state, 0, sizeof *state);
        state->reason = BOOT_FAULT_NONE;
    }
}

void supervision_step_begin(supervision_t *state, uint64_t now_ms, const char *name,
                            uint32_t deadline_ms)
{
    if (state == NULL) {
        return;
    }
    state->step_active = true;
    copy_name(state->step, name);
    state->step_started_ms = now_ms;
    state->step_deadline_ms = deadline_ms;
}

void supervision_step_end(supervision_t *state)
{
    if (state != NULL) {
        state->step_active = false;
    }
}

bool supervision_latch(supervision_t *state, boot_fault_reason_t reason, const char *name)
{
    if (state == NULL || state->latched) {
        return false;
    }
    state->latched = true;
    state->reason = reason;
    copy_name(state->name, name);
    return true;
}

static bool step_overdue(const supervision_t *state, uint64_t now_ms)
{
    return state->step_active && state->step_deadline_ms != 0u && now_ms > state->step_started_ms &&
           now_ms - state->step_started_ms > (uint64_t)state->step_deadline_ms;
}

supervision_action_t supervision_poll(supervision_t *state, uint64_t now_ms,
                                      const supervision_channels_t *channels)
{
    const uint32_t expired = channels != NULL ? channels->expired : 0u;
    const char *const *names = channels != NULL ? channels->names : NULL;
    const size_t count = channels != NULL ? channels->count : 0u;

    if (state == NULL || state->latched) {
        return SUPERVISION_STOPPED;
    }
    if (step_overdue(state, now_ms)) {
        (void)supervision_latch(state, BOOT_FAULT_DEADLINE, state->step);
        return SUPERVISION_LATCH;
    }
    for (unsigned channel = 0; channel < 32u; channel++) {
        if ((expired & (1u << channel)) == 0u) {
            continue;
        }
        if (names != NULL && channel < count && names[channel] != NULL) {
            (void)supervision_latch(state, BOOT_FAULT_CHANNEL, names[channel]);
        } else {
            char unnamed[BOOT_NAME_SIZE];

            (void)snprintf(unnamed, sizeof unnamed, "channel %u", channel);
            (void)supervision_latch(state, BOOT_FAULT_CHANNEL, unnamed);
        }
        return SUPERVISION_LATCH;
    }
    return SUPERVISION_FEED;
}

bool supervision_timing_valid(uint32_t timeout_ms, uint32_t period_ms)
{
    return timeout_ms > 0u && period_ms > 0u && (uint64_t)timeout_ms >= 2u * (uint64_t)period_ms;
}
