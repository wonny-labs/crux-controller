/* SPDX-License-Identifier: Apache-2.0 */
#ifndef FUZZ_TARGET_H
#define FUZZ_TARGET_H

/*
 * The entry point of a fuzz target, as the LLVM libFuzzer documentation names it. libFuzzer calls
 * it in a build with -fsanitize=fuzzer; fuzz_driver.c calls it once for each corpus file in every
 * other build. It handles any input, returns 0, and calls abort() when a property does not hold,
 * which both report as a crash.
 */

#include <stddef.h>
#include <stdint.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size);

#endif
