/* SPDX-License-Identifier: Apache-2.0 */

/*
 * Runs a fuzz target once over each seed file named on the command line, without libFuzzer, so the
 * target builds with any compiler and its seed corpus is a regression test of every host test run
 * (the LLVM libFuzzer documentation: the target does not depend on libFuzzer, and a corpus serves
 * as a regression check). A build with libFuzzer links its own main instead of this file.
 *
 * The seeds are text: the input bytes as pairs of hexadecimal digits, white space ignored, because
 * this repository keeps no binary file (tests/tooling/test_devcontainer.py). The check host-fuzz
 * writes them as raw files for libFuzzer.
 */

#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>

#include "fuzz_target.h"

/* The largest input that the driver reads; the seeds are far smaller. */
#define INPUT_MAX 4096u

static int digit_value(int character)
{
    if (character >= '0' && character <= '9') {
        return character - '0';
    }
    if (character >= 'a' && character <= 'f') {
        return character - 'a' + 10;
    }
    if (character >= 'A' && character <= 'F') {
        return character - 'A' + 10;
    }
    return -1;
}

static bool is_space(int character)
{
    return character == ' ' || character == '\t' || character == '\n' || character == '\r';
}

/* Read the bytes of a hexadecimal seed. False for a character that is not a digit, an odd count of
 * digits or more than INPUT_MAX bytes. */
static bool read_hex(FILE *file, uint8_t *buffer, size_t *size)
{
    int high = -1;
    int character;

    *size = 0u;
    while ((character = fgetc(file)) != EOF) {
        if (is_space(character)) {
            continue;
        }
        const int value = digit_value(character);

        if (value < 0) {
            return false;
        }
        if (high < 0) {
            high = value;
            continue;
        }
        if (*size == INPUT_MAX) {
            return false;
        }
        buffer[(*size)++] = (uint8_t)((high << 4) | value);
        high = -1;
    }
    return high < 0 && ferror(file) == 0;
}

static int run_file(const char *path)
{
    static uint8_t buffer[INPUT_MAX];
    size_t size = 0u;
    FILE *file = fopen(path, "r");

    if (file == NULL) {
        printf("fuzz_driver: cannot open %s\n", path);
        return 1;
    }
    const bool read = read_hex(file, buffer, &size);

    (void)fclose(file);
    if (!read) {
        printf("fuzz_driver: %s is not hexadecimal text of at most %u bytes\n", path, INPUT_MAX);
        return 1;
    }
    (void)LLVMFuzzerTestOneInput(buffer, size);
    return 0;
}

int main(int argc, char **argv)
{
    int failures = 0;

    if (argc < 2) {
        printf("usage: %s SEED.hex...\n", argc > 0 ? argv[0] : "fuzz_driver");
        return 2;
    }
    for (int index = 1; index < argc; index++) {
        failures += run_file(argv[index]);
    }
    printf("%d inputs, %d not read\n", argc - 1, failures);
    return failures == 0 ? 0 : 1;
}
