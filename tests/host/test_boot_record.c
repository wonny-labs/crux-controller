/* SPDX-License-Identifier: Apache-2.0 */

/* The retained region, the reset classification, the boot counter and safe mode of the controller
 * framework (specification sections 5.1 and 5.2; criteria 10 and 18): plain C, no Crux or Zephyr
 * include. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "boot_record.h"

static int failures;
static int checks;

#define CHECK(condition)                                                                           \
    do {                                                                                           \
        checks++;                                                                                  \
        if (!(condition)) {                                                                        \
            failures++;                                                                            \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition);                            \
        }                                                                                          \
    } while (0)

#define IMAGE_A 0x1111u
#define IMAGE_B 0x2222u
#define N 3u

/* The boot after a reset with these causes, over the region the last boot wrote. */
static boot_decision_t boot(const boot_region_t *region, bool valid, uint32_t causes,
                            uint32_t image)
{
    const boot_input_t in = {
        .cause_captured = true,
        .causes = causes,
        .region_valid = valid,
        .region = valid ? *region : (boot_region_t){0},
        .image_id = image,
        .threshold = N,
    };
    boot_decision_t out;

    memset(&out, 0xa5, sizeof out);
    CHECK(boot_decide(&in, &out));
    return out;
}

/* A region of IMAGE_A after count fault resets, with no record. */
static boot_region_t region_with(uint8_t count)
{
    boot_region_t region;

    boot_region_init(&region, IMAGE_A);
    region.counter = count;
    return region;
}

/* The region survives the trip through its bytes. */
static boot_region_t round_trip(const boot_region_t *region)
{
    uint8_t bytes[BOOT_REGION_SIZE];
    boot_region_t back;

    boot_region_encode(region, bytes);
    memset(&back, 0, sizeof back);
    CHECK(boot_region_decode(bytes, &back));
    return back;
}

static void test_the_region_round_trips_through_its_bytes(void)
{
    boot_region_t region = region_with(2u);

    region.marker = true;
    boot_fault_set(&region, BOOT_FAULT_DEADLINE, "command line", 1234u, 0u);
    const boot_region_t back = round_trip(&region);

    CHECK(back.image_id == IMAGE_A);
    CHECK(back.counter == 2u);
    CHECK(back.marker);
    CHECK(back.fault.reason == BOOT_FAULT_DEADLINE);
    CHECK(strcmp(back.fault.name, "command line") == 0);
    CHECK(back.fault.uptime_ms == 1234u);
    CHECK(back.fault.sequence == 1u);
    CHECK(!back.fault.consumed);
}

static void test_the_checksum_rejects_a_damaged_region(void)
{
    boot_region_t region = region_with(1u);
    uint8_t bytes[BOOT_REGION_SIZE];
    boot_region_t untouched;

    boot_fault_set(&region, BOOT_FAULT_FATAL, NULL, 9u, 3u);
    boot_region_encode(&region, bytes);
    for (size_t index = 0; index < BOOT_REGION_SIZE; index++) {
        for (unsigned bit = 0; bit < 8u; bit++) {
            uint8_t damaged[BOOT_REGION_SIZE];

            memcpy(damaged, bytes, sizeof damaged);
            damaged[index] ^= (uint8_t)(1u << bit);
            memset(&untouched, 0x5a, sizeof untouched);
            CHECK(!boot_region_decode(damaged, &untouched));
            CHECK(untouched.counter == 0x5au);
        }
    }
    /* Zeroed memory and erased memory are not a region. */
    memset(bytes, 0, sizeof bytes);
    CHECK(!boot_region_decode(bytes, &untouched));
    memset(bytes, 0xff, sizeof bytes);
    CHECK(!boot_region_decode(bytes, &untouched));
}

/* A reset cut a write after the new counter and before the new checksum: the next boot sees an
 * invalid region, which counts as empty, and the captured cause still classifies the reset. */
static void test_an_interrupted_write_counts_as_an_empty_region(void)
{
    boot_region_t before = region_with(2u);
    boot_region_t after = before;
    uint8_t old_bytes[BOOT_REGION_SIZE];
    uint8_t new_bytes[BOOT_REGION_SIZE];
    uint8_t torn[BOOT_REGION_SIZE];
    boot_region_t decoded;

    after.counter = 3u;
    boot_region_encode(&before, old_bytes);
    boot_region_encode(&after, new_bytes);
    memcpy(torn, new_bytes, BOOT_REGION_SIZE - 4u);
    memcpy(&torn[BOOT_REGION_SIZE - 4u], &old_bytes[BOOT_REGION_SIZE - 4u], 4u);
    CHECK(!boot_region_decode(torn, &decoded));

    /* A watchdog reset counts from an empty region: counter one, no record, no safe mode. */
    const boot_decision_t watchdog = boot(NULL, false, BOOT_CAUSE_WATCHDOG, IMAGE_A);

    CHECK(watchdog.boot_class == BOOT_CLASS_FAULT);
    CHECK(watchdog.region.counter == 1u);
    CHECK(!watchdog.safe_mode);
    CHECK(!watchdog.fault_reported);
    CHECK(watchdog.region.image_id == IMAGE_A);

    /* The marker went with the region, so a software reset counts too. */
    const boot_decision_t software = boot(NULL, false, BOOT_CAUSE_SOFTWARE, IMAGE_A);

    CHECK(software.boot_class == BOOT_CLASS_FAULT);
    CHECK(software.region.counter == 1u);

    /* A pin reset with an invalid region is a region that did not survive: counter zero. */
    const boot_decision_t pin = boot(NULL, false, BOOT_CAUSE_PIN, IMAGE_A);

    CHECK(pin.boot_class == BOOT_CLASS_POWER_CYCLE);
    CHECK(pin.region.counter == 0u);
    CHECK(!pin.fault_reported);
}

static void test_n_consecutive_fault_resets_enter_safe_mode(void)
{
    boot_region_t region;

    boot_region_init(&region, IMAGE_A);
    for (unsigned reset = 1; reset <= N; reset++) {
        const boot_decision_t out = boot(&region, true, BOOT_CAUSE_WATCHDOG, IMAGE_A);

        CHECK(out.boot_class == BOOT_CLASS_FAULT);
        CHECK(out.region.counter == reset);
        CHECK(out.safe_mode == (reset >= N));
        region = round_trip(&out.region);
    }
}

static void test_a_cleared_counter_counts_again_from_one(void)
{
    boot_region_t region = region_with(N);

    boot_counter_clear(&region);
    CHECK(region.counter == 0u);
    const boot_decision_t out = boot(&region, true, BOOT_CAUSE_WATCHDOG, IMAGE_A);

    CHECK(out.region.counter == 1u);
    CHECK(!out.safe_mode);
}

/* The counter saturates at the threshold instead of wrapping: once safe mode is reached, a further
 * fault reset leaves it there, and so does a stored value above the threshold. */
static void test_the_counter_saturates(void)
{
    boot_region_t region = region_with(N);

    const boot_decision_t at = boot(&region, true, BOOT_CAUSE_WATCHDOG, IMAGE_A);

    CHECK(at.region.counter == N);
    CHECK(at.safe_mode);

    region = region_with(BOOT_COUNTER_MAX);
    const boot_decision_t above = boot(&region, true, BOOT_CAUSE_WATCHDOG, IMAGE_A);

    CHECK(above.region.counter == BOOT_COUNTER_MAX);
    CHECK(above.safe_mode);
}

/* Criterion 17: a fault reset in safe mode keeps the counter saturated, so the next boot is in safe
 * mode again. */
static void test_a_fault_reset_in_safe_mode_stays_in_safe_mode(void)
{
    boot_region_t region = region_with(N);

    for (int reset = 0; reset < 3; reset++) {
        const boot_decision_t out = boot(&region, true, BOOT_CAUSE_SOFTWARE, IMAGE_A);

        CHECK(out.boot_class == BOOT_CLASS_FAULT);
        CHECK(out.region.counter == N);
        CHECK(out.safe_mode);
        region = round_trip(&out.region);
    }
}

static void test_several_latched_bits_are_one_fault_reset(void)
{
    boot_region_t region = region_with(0u);

    const boot_decision_t out =
        boot(&region, true, BOOT_CAUSE_PIN | BOOT_CAUSE_WATCHDOG | BOOT_CAUSE_DEBUG, IMAGE_A);

    CHECK(out.boot_class == BOOT_CLASS_FAULT);
    CHECK(out.region.counter == 1u);

    const boot_decision_t pin_debug =
        boot(&region, true, BOOT_CAUSE_PIN | BOOT_CAUSE_DEBUG, IMAGE_A);

    CHECK(pin_debug.boot_class == BOOT_CLASS_NOT_FAULT);
    CHECK(pin_debug.region.counter == 0u);
}

static void test_por_together_with_other_bits_is_a_power_cycle(void)
{
    boot_region_t region = region_with(2u);

    boot_fault_set(&region, BOOT_FAULT_CHANNEL, "time", 5u, 0u);
    const boot_decision_t out =
        boot(&region, true, BOOT_CAUSE_POR | BOOT_CAUSE_WATCHDOG | BOOT_CAUSE_SOFTWARE, IMAGE_A);

    CHECK(out.boot_class == BOOT_CLASS_POWER_CYCLE);
    CHECK(out.region.counter == 0u);
    CHECK(!out.fault_reported);
    CHECK(out.region.fault.reason == BOOT_FAULT_NONE);
}

static void test_a_software_reset_counts_only_without_the_marker(void)
{
    boot_region_t region = region_with(1u);

    const boot_decision_t without = boot(&region, true, BOOT_CAUSE_SOFTWARE, IMAGE_A);

    CHECK(without.boot_class == BOOT_CLASS_FAULT);
    CHECK(without.region.counter == 2u);

    boot_marker_set(&region, true);
    const boot_decision_t with = boot(&region, true, BOOT_CAUSE_SOFTWARE, IMAGE_A);

    CHECK(with.boot_class == BOOT_CLASS_NOT_FAULT);
    CHECK(with.region.counter == 1u);
    CHECK(!with.region.marker);
}

static void test_cpu_lockup_with_software_is_a_software_reset(void)
{
    boot_region_t region = region_with(0u);
    const uint32_t both = BOOT_CAUSE_CPU_LOCKUP | BOOT_CAUSE_SOFTWARE;

    const boot_decision_t without = boot(&region, true, both, IMAGE_A);

    CHECK(without.boot_class == BOOT_CLASS_FAULT);
    CHECK(without.region.counter == 1u);

    boot_marker_set(&region, true);
    const boot_decision_t with = boot(&region, true, both, IMAGE_A);

    CHECK(with.boot_class == BOOT_CLASS_NOT_FAULT);
    CHECK(with.region.counter == 0u);

    /* A lockup alone, without the marker, is a fault reset too. */
    boot_marker_set(&region, false);
    const boot_decision_t lockup = boot(&region, true, BOOT_CAUSE_CPU_LOCKUP, IMAGE_A);

    CHECK(lockup.boot_class == BOOT_CLASS_FAULT);
}

static void test_the_marker_does_not_hide_a_watchdog_or_a_record(void)
{
    boot_region_t region = region_with(0u);

    boot_marker_set(&region, true);
    const boot_decision_t watchdog =
        boot(&region, true, BOOT_CAUSE_SOFTWARE | BOOT_CAUSE_WATCHDOG, IMAGE_A);

    CHECK(watchdog.boot_class == BOOT_CLASS_FAULT);

    boot_fault_set(&region, BOOT_FAULT_FATAL, NULL, 1u, 4u);
    const boot_decision_t record = boot(&region, true, BOOT_CAUSE_SOFTWARE, IMAGE_A);

    CHECK(record.boot_class == BOOT_CLASS_FAULT);
    CHECK(record.fault_reported);
    CHECK(record.fault.reason == BOOT_FAULT_FATAL);
    CHECK(record.fault.detail == 4u);
}

/* Criterion 16: the next boot counts a fatal-error reset as a fault reset through its record,
 * whatever cause the SoC latched. */
static void test_a_fatal_record_makes_a_fault_reset(void)
{
    boot_region_t region = region_with(0u);

    boot_fault_set(&region, BOOT_FAULT_FATAL, "supervisor", 77u, 3u);
    const boot_decision_t out = boot(&region, true, BOOT_CAUSE_PIN, IMAGE_A);

    CHECK(out.boot_class == BOOT_CLASS_FAULT);
    CHECK(out.region.counter == 1u);
    CHECK(out.fault_reported);
    CHECK(strcmp(out.fault.name, "supervisor") == 0);
}

static void test_a_consumed_record_is_reported_and_counted_once(void)
{
    boot_region_t region = region_with(0u);

    boot_fault_set(&region, BOOT_FAULT_DEADLINE, "web management", 10u, 0u);
    const boot_decision_t first = boot(&region, true, BOOT_CAUSE_WATCHDOG, IMAGE_A);

    CHECK(first.fault_reported);
    CHECK(first.region.fault.consumed);
    CHECK(first.region.counter == 1u);

    const boot_region_t stored = round_trip(&first.region);
    const boot_decision_t second = boot(&stored, true, BOOT_CAUSE_PIN, IMAGE_A);

    CHECK(!second.fault_reported);
    CHECK(second.boot_class == BOOT_CLASS_NOT_FAULT);
    CHECK(second.region.counter == 1u);
}

static void test_a_new_record_takes_the_next_sequence_number(void)
{
    boot_region_t region = region_with(0u);

    boot_fault_set(&region, BOOT_FAULT_DEADLINE, "a", 1u, 0u);
    boot_fault_set(&region, BOOT_FAULT_CHANNEL, "b", 2u, 0u);
    CHECK(region.fault.sequence == 2u);
    CHECK(region.fault.reason == BOOT_FAULT_CHANNEL);
    boot_fault_set(&region, BOOT_FAULT_NONE, "c", 3u, 0u);
    CHECK(region.fault.sequence == 2u);
    boot_fault_set(&region, BOOT_FAULT_STOP, "a name much longer than the field", 4u, 0u);
    CHECK(strlen(region.fault.name) == BOOT_NAME_SIZE - 1u);
    CHECK(strncmp(region.fault.name, "a name much lon", BOOT_NAME_SIZE - 1u) == 0);
}

/* An update, and a revert by the boot loader, both boot another image: the counter clears and the
 * previous image's last record is reported. */
static void test_a_different_image_clears_the_counter_and_reports_the_last_record(void)
{
    boot_region_t region = region_with(N);

    boot_fault_set(&region, BOOT_FAULT_CHANNEL, "time", 50u, 0u);
    const boot_decision_t update = boot(&region, true, BOOT_CAUSE_WATCHDOG, IMAGE_B);

    CHECK(update.boot_class == BOOT_CLASS_NEW_IMAGE);
    CHECK(update.region.counter == 0u);
    CHECK(!update.safe_mode);
    CHECK(update.fault_reported);
    CHECK(strcmp(update.fault.name, "time") == 0);
    CHECK(update.region.image_id == IMAGE_B);

    boot_region_t after_update = round_trip(&update.region);

    after_update.counter = 2u;
    const boot_decision_t rollback = boot(&after_update, true, BOOT_CAUSE_SOFTWARE, IMAGE_A);

    CHECK(rollback.boot_class == BOOT_CLASS_NEW_IMAGE);
    CHECK(rollback.region.counter == 0u);
    CHECK(rollback.region.image_id == IMAGE_A);
    CHECK(!rollback.fault_reported);
}

static void test_without_a_captured_cause_only_the_record_counts(void)
{
    boot_region_t region = region_with(1u);
    boot_input_t in = {
        .cause_captured = false,
        .causes = BOOT_CAUSE_WATCHDOG,
        .region_valid = true,
        .region = region,
        .image_id = IMAGE_A,
        .threshold = N,
    };
    boot_decision_t out;

    CHECK(boot_decide(&in, &out));
    CHECK(out.boot_class == BOOT_CLASS_NOT_FAULT);
    CHECK(out.region.counter == 1u);

    boot_fault_set(&in.region, BOOT_FAULT_DEADLINE, "x", 1u, 0u);
    CHECK(boot_decide(&in, &out));
    CHECK(out.boot_class == BOOT_CLASS_FAULT);
    CHECK(out.region.counter == 2u);
}

static void test_invalid_arguments_are_refused(void)
{
    boot_input_t in = {.cause_captured = true, .image_id = IMAGE_A, .threshold = 0u};
    boot_decision_t out;

    CHECK(!boot_decide(&in, &out));
    in.threshold = N;
    CHECK(!boot_decide(NULL, &out));
    CHECK(!boot_decide(&in, NULL));
    boot_fault_set(NULL, BOOT_FAULT_FATAL, "x", 1u, 1u);
    boot_counter_clear(NULL);
    boot_marker_set(NULL, true);
}

/* Criterion 10: the successful boot clears the counter only after the stable period without
 * interruption; it does not clear while the application is in fault or held. */
static void test_the_stable_period_must_pass_without_interruption(void)
{
    boot_stability_t stability;

    boot_stability_init(&stability);
    CHECK(!boot_stability_update(&stability, true, 1000u, 500u));
    CHECK(!boot_stability_update(&stability, true, 1400u, 500u));
    /* Interrupted: the period starts again when the conditions hold again. */
    CHECK(!boot_stability_update(&stability, false, 1450u, 500u));
    CHECK(!boot_stability_update(&stability, true, 1500u, 500u));
    CHECK(!boot_stability_update(&stability, true, 1999u, 500u));
    CHECK(boot_stability_update(&stability, true, 2000u, 500u));
    /* Exactly once. */
    CHECK(!boot_stability_update(&stability, true, 9000u, 500u));
}

static void test_a_held_or_failed_application_keeps_the_counter(void)
{
    boot_stability_t stability;

    boot_stability_init(&stability);
    for (uint64_t now = 0; now < 100000u; now += 1000u) {
        CHECK(!boot_stability_update(&stability, false, now, 500u));
    }
}

static void test_the_names(void)
{
    CHECK(strcmp(boot_fault_reason_name(BOOT_FAULT_DEADLINE), "deadline") == 0);
    CHECK(strcmp(boot_fault_reason_name(BOOT_FAULT_CHANNEL), "channel") == 0);
    CHECK(strcmp(boot_fault_reason_name(BOOT_FAULT_FATAL), "fatal") == 0);
    CHECK(strcmp(boot_fault_reason_name(BOOT_FAULT_STOP), "stop") == 0);
    CHECK(strcmp(boot_fault_reason_name(BOOT_FAULT_NONE), "none") == 0);
    CHECK(strcmp(boot_fault_reason_name((boot_fault_reason_t)99), "unknown") == 0);
    CHECK(strcmp(boot_class_name(BOOT_CLASS_FAULT), "fault") == 0);
    CHECK(strcmp(boot_class_name(BOOT_CLASS_NOT_FAULT), "normal") == 0);
    CHECK(strcmp(boot_class_name(BOOT_CLASS_POWER_CYCLE), "power") == 0);
    CHECK(strcmp(boot_class_name(BOOT_CLASS_NEW_IMAGE), "image") == 0);
    CHECK(strcmp(boot_class_name((boot_class_t)99), "unknown") == 0);
}

static void test_the_image_identifier_depends_on_the_text(void)
{
    CHECK(boot_image_id("a") != boot_image_id("b"));
    CHECK(boot_image_id("same") == boot_image_id("same"));
    CHECK(boot_image_id(NULL) == boot_image_id(""));
}

int main(void)
{
    test_the_region_round_trips_through_its_bytes();
    test_the_checksum_rejects_a_damaged_region();
    test_an_interrupted_write_counts_as_an_empty_region();
    test_n_consecutive_fault_resets_enter_safe_mode();
    test_a_cleared_counter_counts_again_from_one();
    test_the_counter_saturates();
    test_a_fault_reset_in_safe_mode_stays_in_safe_mode();
    test_several_latched_bits_are_one_fault_reset();
    test_por_together_with_other_bits_is_a_power_cycle();
    test_a_software_reset_counts_only_without_the_marker();
    test_cpu_lockup_with_software_is_a_software_reset();
    test_the_marker_does_not_hide_a_watchdog_or_a_record();
    test_a_fatal_record_makes_a_fault_reset();
    test_a_consumed_record_is_reported_and_counted_once();
    test_a_new_record_takes_the_next_sequence_number();
    test_a_different_image_clears_the_counter_and_reports_the_last_record();
    test_without_a_captured_cause_only_the_record_counts();
    test_invalid_arguments_are_refused();
    test_the_stable_period_must_pass_without_interruption();
    test_a_held_or_failed_application_keeps_the_counter();
    test_the_names();
    test_the_image_identifier_depends_on_the_text();
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
