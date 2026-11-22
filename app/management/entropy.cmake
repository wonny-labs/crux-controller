# SPDX-License-Identifier: Apache-2.0

# Step S6: the entropy rules of the board image. This file is included by app/CMakeLists.txt, inside
# the step's block, after find_package(Zephyr) and project(). The native_sim scenario does not
# include it, because the simulator has a test entropy source and no other one.
#
# The image generates a TLS key and password salts at its first start. A key or a salt that came from
# a test source means nothing, so the image refuses one. On this board Zephyr's glue for
# TF-PSA-Crypto answers a failed read of the hardware random source with a general-purpose generator
# that is not cryptographic, so Crux's correction replaces that one source with a build-local copy
# that fails the read instead. The correction checks the hash of Zephyr's original and stops the
# configuration when it differs, which is how a Zephyr update shows up here.

if(CONFIG_TEST_RANDOM_GENERATOR OR CONFIG_FAKE_ENTROPY_NATIVE_SIM)
    message(FATAL_ERROR "Step S6 generates a TLS key at its first start: no test entropy source")
endif()
if(NOT CONFIG_ENTROPY_MCUX_TRNG OR NOT CONFIG_MBEDTLS_PSA_DRIVER_GET_ENTROPY)
    message(FATAL_ERROR "Step S6 needs the i.MX RT random source through its driver "
                        "(CONFIG_ENTROPY_MCUX_TRNG) as the PSA entropy source "
                        "(CONFIG_MBEDTLS_PSA_DRIVER_GET_ENTROPY)")
endif()

include("${ZEPHYR_CRUX_MODULE_DIR}/cmake/CruxMbedtlsEntropy.cmake")
crux_mbedtls_fail_closed_entropy()
