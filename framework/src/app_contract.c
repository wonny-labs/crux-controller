/* SPDX-License-Identifier: Apache-2.0 */

#include "app_contract.h"

#include <string.h>

static app_state_t state_of(const app_contract_t *contract)
{
    return (app_state_t)atomic_load(&contract->state);
}

/* Move along the transition table of section 4.5; a pair that the table lacks leaves the state. */
static void advance(app_contract_t *contract, app_event_t event, app_hold_t hold)
{
    app_state_t next = state_of(contract);

    if (app_state_next(state_of(contract), event, hold, &next)) {
        atomic_store(&contract->state, (int)next);
    }
}

bool app_entries_complete(const app_entries_t *entries)
{
    return entries != NULL && entries->init != NULL && entries->start != NULL &&
           entries->stop != NULL && entries->safe_state != NULL;
}

static bool channel_port_complete(const app_channel_port_t *channels)
{
    return channels != NULL && channels->add != NULL && channels->remove != NULL &&
           channels->feed != NULL;
}

void app_contract_init(app_contract_t *contract, const app_entries_t *entries,
                       const app_channel_port_t *channels, size_t capacity)
{
    if (contract == NULL) {
        return;
    }
    memset(contract, 0, sizeof *contract);
    for (size_t index = 0; index < APP_CONTRACT_CHANNELS_MAX; index++) {
        atomic_init(&contract->requirements[index].handle, -1);
    }
    atomic_init(&contract->requirement_count, 0u);
    atomic_init(&contract->released, false);
    atomic_init(&contract->initialised, false);
    atomic_init(&contract->fault_reported, false);
    contract->hold = APP_HOLD_NONE;
    contract->capacity = capacity < APP_CONTRACT_CHANNELS_MAX ? capacity : APP_CONTRACT_CHANNELS_MAX;
    if (app_entries_complete(entries) && channel_port_complete(channels)) {
        contract->entries = *entries;
        contract->channels = *channels;
        atomic_init(&contract->state, (int)APP_NOT_INITIALISED);
    } else {
        atomic_init(&contract->state, (int)APP_ABSENT);
    }
}

static bool name_valid(const char *name)
{
    if (name == NULL || name[0] == '\0') {
        return false;
    }
    for (size_t index = 0; index <= APP_CONTRACT_NAME_MAX; index++) {
        if (name[index] == '\0') {
            return true;
        }
    }
    return false;
}

app_contract_status_t app_contract_register_channel(app_contract_t *contract, const char *name,
                                                    uint32_t reload_ms, size_t *index)
{
    if (contract == NULL || !contract->registration_open) {
        return contract == NULL ? APP_CONTRACT_ERR_INVALID : APP_CONTRACT_ERR_CLOSED;
    }
    if (!name_valid(name) || reload_ms == 0u || index == NULL) {
        return APP_CONTRACT_ERR_INVALID;
    }
    const size_t count = atomic_load(&contract->requirement_count);

    for (size_t existing = 0; existing < count; existing++) {
        if (strcmp(contract->requirements[existing].name, name) == 0) {
            return APP_CONTRACT_ERR_DUPLICATE;
        }
    }
    if (count >= contract->capacity) {
        return APP_CONTRACT_ERR_FULL;
    }
    contract->requirements[count].name = name;
    contract->requirements[count].reload_ms = reload_ms;
    atomic_store(&contract->requirements[count].handle, -1);
    atomic_store(&contract->requirement_count, count + 1u);
    *index = count;
    return APP_CONTRACT_OK;
}

static app_contract_status_t register_table(const app_contract_t *contract, const void **table,
                                            size_t *table_count, const void *given, size_t count)
{
    if (contract == NULL) {
        return APP_CONTRACT_ERR_INVALID;
    }
    if (!contract->registration_open) {
        return APP_CONTRACT_ERR_CLOSED;
    }
    if (given == NULL || count == 0u) {
        return APP_CONTRACT_ERR_INVALID;
    }
    if (*table != NULL) {
        return APP_CONTRACT_ERR_DUPLICATE;
    }
    *table = given;
    *table_count = count;
    return APP_CONTRACT_OK;
}

app_contract_status_t app_contract_register_status(app_contract_t *contract, const void *items,
                                                   size_t count)
{
    if (contract == NULL) {
        return APP_CONTRACT_ERR_INVALID;
    }
    return register_table(contract, &contract->status_items, &contract->status_count, items,
                          count);
}

app_contract_status_t app_contract_register_parameters(app_contract_t *contract,
                                                       const void *parameters, size_t count)
{
    if (contract == NULL) {
        return APP_CONTRACT_ERR_INVALID;
    }
    return register_table(contract, &contract->parameters, &contract->parameter_count, parameters,
                          count);
}

void app_contract_feed(app_contract_t *contract, size_t index)
{
    if (contract == NULL || index >= atomic_load(&contract->requirement_count)) {
        return;
    }
    const int handle = atomic_load(&contract->requirements[index].handle);

    if (handle >= 0) {
        contract->channels.feed(contract->channels.port, handle);
    }
}

/* The registrations go: requirements dropped, items and parameters unavailable. Called only once no
 * application thread runs (section 3.3), so no feed can race with the drop. */
static void release(app_contract_t *contract)
{
    atomic_store(&contract->released, true);
    atomic_store(&contract->requirement_count, 0u);
}

/* Delete every active channel, in the order of registration. */
static void delete_active(app_contract_t *contract)
{
    const size_t count = atomic_load(&contract->requirement_count);

    for (size_t index = 0; index < count; index++) {
        const int handle = atomic_exchange(&contract->requirements[index].handle, -1);

        if (handle >= 0) {
            contract->channels.remove(contract->channels.port, handle);
        }
    }
}

int app_contract_run_init(app_contract_t *contract)
{
    if (contract == NULL || state_of(contract) != APP_NOT_INITIALISED) {
        return -1;
    }
    contract->registration_open = true;
    const int result = contract->entries.init(contract->entries.argument);

    contract->registration_open = false;
    if (result == 0) {
        atomic_store(&contract->initialised, true);
        advance(contract, APP_EVENT_INIT_OK, APP_HOLD_NONE);
        return 0;
    }
    /* Partial init failure: nothing that init started runs any more (section 3.1). */
    contract->entries.safe_state(contract->entries.argument);
    release(contract);
    advance(contract, APP_EVENT_INIT_FAILED, APP_HOLD_NONE);
    return result;
}

void app_contract_hold_safe_mode(app_contract_t *contract)
{
    if (contract != NULL && state_of(contract) == APP_NOT_INITIALISED) {
        contract->hold = APP_HOLD_SAFE_MODE;
        advance(contract, APP_EVENT_HOLD, APP_HOLD_SAFE_MODE);
    }
}

/* Activate every requirement, immediately before start. On a refusal the channels activated here
 * are deleted again; false then. */
static bool activate(app_contract_t *contract)
{
    const size_t count = atomic_load(&contract->requirement_count);

    for (size_t index = 0; index < count; index++) {
        app_requirement_t *requirement = &contract->requirements[index];
        const int handle = contract->channels.add(contract->channels.port, requirement->name,
                                                  requirement->reload_ms);

        if (handle < 0) {
            return false;
        }
        atomic_store(&requirement->handle, handle);
    }
    return true;
}

/* Partial start failure (sections 3.3 and 4.4): safe_state, delete what was activated, release,
 * fault. Threads that start created are the application's to end before it returns its error. */
static app_run_t start_failed(app_contract_t *contract, app_hold_t hold)
{
    contract->entries.safe_state(contract->entries.argument);
    delete_active(contract);
    release(contract);
    advance(contract, APP_EVENT_START_FAILED, hold);
    contract->hold = APP_HOLD_NONE;
    return APP_RUN_FAILED;
}

app_run_t app_contract_start(app_contract_t *contract, const app_start_conditions_t *conditions,
                             bool operator)
{
    if (contract == NULL || conditions == NULL) {
        return APP_RUN_NOT_NOW;
    }
    const app_state_t from = state_of(contract);
    const bool startable =
        operator ? (from == APP_STOPPED ||
                    (from == APP_HELD && contract->hold == APP_HOLD_PREREQUISITE))
                 : from == APP_INITIALISED;

    if (!startable) {
        return APP_RUN_NOT_NOW;
    }
    const app_start_inputs_t inputs = {
        .state = from,
        .safe_mode = conditions->safe_mode,
        .prerequisites_healthy = conditions->prerequisites_healthy,
        .watchdog_armed = conditions->watchdog_armed,
        .start_without_watchdog = conditions->start_without_watchdog,
    };
    app_hold_t hold = APP_HOLD_NONE;

    if (app_start_decide(&inputs, &hold) != APP_START_GO) {
        if (!operator) {
            contract->hold = hold;
            advance(contract, APP_EVENT_HOLD, hold);
        }
        return APP_RUN_HELD;
    }
    /* The hold that an operator start ends, for the transition out of held. */
    const app_hold_t ending = from == APP_HELD ? contract->hold : APP_HOLD_NONE;

    /* A fault reported while the application was not running belongs to no running application. */
    atomic_store(&contract->fault_reported, false);
    if (!activate(contract)) {
        return start_failed(contract, ending);
    }
    if (contract->entries.start(contract->entries.argument) != 0) {
        return start_failed(contract, ending);
    }
    advance(contract, operator ? APP_EVENT_OPERATOR_START : APP_EVENT_START_OK, ending);
    contract->hold = APP_HOLD_NONE;
    return APP_RUN_STARTED;
}

app_stop_t app_contract_stop(app_contract_t *contract, app_stop_reason_t reason)
{
    if (contract == NULL || state_of(contract) != APP_RUNNING) {
        return APP_STOP_NOT_NOW;
    }
    if (contract->entries.stop(contract->entries.argument, reason) != 0) {
        return APP_STOP_HANG;
    }
    /* Every application thread has ended, so no thread writes outputs after safe_state and none
     * feeds a channel that is being deleted (sections 3.1 and 4.4). */
    contract->entries.safe_state(contract->entries.argument);
    delete_active(contract);
    if (reason == APP_STOP_FAULT) {
        release(contract);
        advance(contract, APP_EVENT_FAULT, APP_HOLD_NONE);
    } else {
        advance(contract, APP_EVENT_STOPPED, APP_HOLD_NONE);
    }
    return APP_STOPPED_OK;
}

void app_contract_report_fault(app_contract_t *contract)
{
    if (contract != NULL) {
        atomic_store(&contract->fault_reported, true);
    }
}

bool app_contract_take_fault(app_contract_t *contract)
{
    return contract != NULL && atomic_exchange(&contract->fault_reported, false);
}

bool app_contract_supervisor_safe_state(app_contract_t *contract)
{
    if (contract == NULL || state_of(contract) == APP_ABSENT ||
        !atomic_load(&contract->initialised)) {
        return false;
    }
    contract->entries.safe_state(contract->entries.argument);
    return true;
}

app_state_t app_contract_state(const app_contract_t *contract)
{
    return contract != NULL ? state_of(contract) : APP_ABSENT;
}

app_hold_t app_contract_hold(const app_contract_t *contract)
{
    return contract != NULL && state_of(contract) == APP_HELD ? contract->hold : APP_HOLD_NONE;
}

bool app_contract_items_available(const app_contract_t *contract)
{
    return contract != NULL && state_of(contract) != APP_ABSENT &&
           !atomic_load(&contract->released);
}

static const void *table_or_none(const app_contract_t *contract, const void *table,
                                 size_t table_count, size_t *count)
{
    const bool available = app_contract_items_available(contract) && table != NULL;

    if (count != NULL) {
        *count = available ? table_count : 0u;
    }
    return available ? table : NULL;
}

const void *app_contract_status_items(const app_contract_t *contract, size_t *count)
{
    if (contract == NULL) {
        return table_or_none(NULL, NULL, 0u, count);
    }
    return table_or_none(contract, contract->status_items, contract->status_count, count);
}

const void *app_contract_parameters(const app_contract_t *contract, size_t *count)
{
    if (contract == NULL) {
        return table_or_none(NULL, NULL, 0u, count);
    }
    return table_or_none(contract, contract->parameters, contract->parameter_count, count);
}

size_t app_contract_requirement_count(const app_contract_t *contract)
{
    return contract != NULL ? atomic_load(&contract->requirement_count) : 0u;
}

const char *app_contract_requirement_name(const app_contract_t *contract, size_t index)
{
    if (contract == NULL || index >= atomic_load(&contract->requirement_count)) {
        return NULL;
    }
    return contract->requirements[index].name;
}
