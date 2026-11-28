# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20)
project(crux_controller_host_tests C)

option(WORKLOAD_SANITIZE "Build with the address and undefined-behaviour sanitizers" OFF)
# The coverage report of criterion 41: GCC's --coverage, read by gcovr in the check host-coverage of
# scripts/ci/checks.toml.
option(CRUX_HOST_COVERAGE "Build with coverage instrumentation" OFF)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

if(CRUX_HOST_COVERAGE)
    add_compile_options(--coverage -O0)
    add_link_options(--coverage)
endif()

if(WORKLOAD_SANITIZE)
    add_compile_options(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
    add_link_options(-fsanitize=address,undefined)
endif()

add_subdirectory(../../workload workload)
target_compile_options(workload PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_executable(test_workload test_workload.c)
target_link_libraries(test_workload PRIVATE workload)
target_compile_options(test_workload PRIVATE -Wall -Wextra -Wpedantic -Werror)

enable_testing()
add_test(NAME workload COMMAND test_workload)

# The application's exchange logic, run against a peer on the loopback interface. The
# peer address and port are Kconfig values in the image, so the test defines them.
find_package(Threads REQUIRED)
add_executable(test_net_client test_net_client.c ../../app/src/net_client.c)
target_include_directories(test_net_client PRIVATE ../../app/src)
target_link_libraries(test_net_client PRIVATE workload Threads::Threads)
# The port is a variable of the test (test_peer_port.h), set to the port that the system assigns,
# so that two copies of the test can run at the same time. net_client.c is built unchanged.
target_compile_definitions(test_net_client PRIVATE
    _POSIX_C_SOURCE=200809L
    CONFIG_CRUX_CONTROLLER_PEER_ADDRESS="127.0.0.1"
    CONFIG_CRUX_CONTROLLER_PEER_PORT=test_peer_port)
target_compile_options(test_net_client PRIVATE -include ${CMAKE_CURRENT_SOURCE_DIR}/test_peer_port.h)
target_compile_options(test_net_client PRIVATE -Wall -Wextra -Werror)
add_test(NAME net_client COMMAND test_net_client)
# Two copies at the same time, as when two build directories are tested in parallel or ctest runs
# with -j. Each copy asks the system for its own port, so neither may disturb the other.
add_test(NAME net_client_concurrent
         COMMAND sh -c "\"$0\" & first=$!; \"$0\"; second=$?; wait $first || second=1; exit $second"
                 $<TARGET_FILE:test_net_client>)

# The reset-cause and watchdog policy of the system capability: ISO C only, so it builds here without Crux or
# Zephyr headers. The glue that calls Crux System is not built on the host.
add_executable(test_health_policy test_health_policy.c ../../app/src/health_policy.c)
target_include_directories(test_health_policy PRIVATE ../../app/src)
target_compile_options(test_health_policy PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME health_policy COMMAND test_health_policy)

# The time synchronisation policy of the sntp capability: ISO C only, so it builds here without Crux or Zephyr
# headers. The glue that calls the Crux Time authority and the adapter that calls Zephyr's SNTP
# library are not built on the host.
add_executable(test_time_sync_policy test_time_sync_policy.c ../../framework/src/time_sync_policy.c)
target_include_directories(test_time_sync_policy PRIVATE ../../framework/src)
target_compile_options(test_time_sync_policy PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME time_sync_policy COMMAND test_time_sync_policy)

# The address text and the role policy of the management groundwork: ISO C only, so it builds
# here without Crux or Zephyr headers. No firmware image compiles it yet.
add_executable(test_startup test_startup.c ../../framework/src/startup.c)
target_include_directories(test_startup PRIVATE ../../framework/src)
target_compile_options(test_startup PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME startup COMMAND test_startup)

add_executable(test_management_policy test_management_policy.c ../../framework/src/management_policy.c)
target_include_directories(test_management_policy PRIVATE ../../framework/src)
target_compile_options(test_management_policy PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME management_policy COMMAND test_management_policy)

# The retained region, the reset classification, the boot counter and safe mode of the framework's
# health supervision: ISO C only. The glue that reads the reset cause and the retained region is not
# built on the host.
add_executable(test_boot_record test_boot_record.c ../../framework/src/boot_record.c)
target_include_directories(test_boot_record PRIVATE ../../framework/src)
target_compile_options(test_boot_record PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME boot_record COMMAND test_boot_record)

# The supervisor's decisions, the controller and application states and the operator reset marker
# rule of the framework's health supervision: ISO C only. The supervisor thread, the task watchdog
# and the reboot thread that carry them out are not built on the host.
add_executable(test_supervision test_supervision.c ../../framework/src/supervision.c)
target_include_directories(test_supervision PRIVATE ../../framework/src)
target_compile_options(test_supervision PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME supervision COMMAND test_supervision)

add_executable(test_controller_state test_controller_state.c ../../framework/src/controller_state.c)
target_include_directories(test_controller_state PRIVATE ../../framework/src)
target_compile_options(test_controller_state PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME controller_state COMMAND test_controller_state)

add_executable(test_reboot_policy test_reboot_policy.c ../../framework/src/reboot_policy.c)
target_include_directories(test_reboot_policy PRIVATE ../../framework/src)
target_compile_options(test_reboot_policy PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME reboot_policy COMMAND test_reboot_policy)

# The application contract of delivery stage 3: registrations, the channel lifecycle and the order
# of the application's calls with the clean-up of each failure. ISO C only; the framework thread,
# the task watchdog and the composition that carry it out are not built on the host.
add_executable(test_app_contract test_app_contract.c ../../framework/src/app_contract.c
    ../../framework/src/controller_state.c)
target_include_directories(test_app_contract PRIVATE ../../framework/src)
target_compile_options(test_app_contract PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME app_contract COMMAND test_app_contract)

# The operator requests of the application thread and the gate of a planned reset: ISO C only.
add_executable(test_app_requests test_app_requests.c ../../framework/src/app_requests.c)
target_include_directories(test_app_requests PRIVATE ../../framework/src)
target_compile_options(test_app_requests PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME app_requests COMMAND test_app_requests)

# The health verdict and the trial deadline of a test image (criterion 25, delivery stage 4), against
# a fake image state port in the test. ISO C only; no image builds image_trial.c yet, because Crux has
# no image state provider for Zephyr (gap C10).
add_executable(test_image_trial test_image_trial.c ../../framework/src/image_trial.c)
target_include_directories(test_image_trial PRIVATE ../../framework/src)
target_compile_options(test_image_trial PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME image_trial COMMAND test_image_trial)

# Supervision of the Crux service threads by their progress reports (specification sections 4.3 and
# 4.4, gap C8; criterion 33, host part), against a fake channel port, with concurrent reporters.
add_executable(test_service_progress test_service_progress.c ../../framework/src/service_progress.c)
target_include_directories(test_service_progress PRIVATE ../../framework/src)
target_compile_options(test_service_progress PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(test_service_progress PRIVATE Threads::Threads)
add_test(NAME service_progress COMMAND test_service_progress)

# The fuzz targets of criterion 41 (delivery stage 4), in fuzz/. Every build links each target with
# fuzz/fuzz_driver.c and runs it over its seed corpus in fuzz/corpus/NAME (hexadecimal text, as the
# repository keeps no binary file) as a test. With
# CRUX_HOST_FUZZ, which needs Clang with libFuzzer, each target is also built as fuzz_NAME with
# -fsanitize=fuzzer; the check host-fuzz of scripts/ci/checks.toml runs those in the nightly tier.
option(CRUX_HOST_FUZZ "Build the fuzz targets with libFuzzer (Clang only)" OFF)
set(fuzz_sources_boot_record fuzz/fuzz_boot_record.c ../../framework/src/boot_record.c)
set(fuzz_sources_management_text fuzz/fuzz_management_text.c ../../framework/src/management_policy.c)
if(CRUX_HOST_FUZZ)
    include(CheckCSourceCompiles)
    set(CMAKE_REQUIRED_FLAGS -fsanitize=fuzzer)
    set(CMAKE_REQUIRED_LINK_OPTIONS -fsanitize=fuzzer)
    check_c_source_compiles([=[
#include <stddef.h>
#include <stdint.h>
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) { (void)data; (void)size; return 0; }
]=] CRUX_HAVE_LIBFUZZER)
    unset(CMAKE_REQUIRED_FLAGS)
    unset(CMAKE_REQUIRED_LINK_OPTIONS)
    if(NOT CMAKE_C_COMPILER_ID MATCHES "Clang" OR NOT CRUX_HAVE_LIBFUZZER)
        message(FATAL_ERROR "CRUX_HOST_FUZZ needs Clang with libFuzzer (-fsanitize=fuzzer); "
                            "${CMAKE_C_COMPILER} has none. On Ubuntu install clang-18 and libclang-rt-18-dev, "
                            "then configure with -DCMAKE_C_COMPILER=clang-18.")
    endif()
endif()
foreach(name boot_record management_text)
    add_executable(fuzz_${name}_corpus fuzz/fuzz_driver.c ${fuzz_sources_${name}})
    target_include_directories(fuzz_${name}_corpus PRIVATE ../../framework/src fuzz)
    target_compile_options(fuzz_${name}_corpus PRIVATE -Wall -Wextra -Wpedantic -Werror)
    file(GLOB fuzz_seeds CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/fuzz/corpus/${name}/*.hex)
    add_test(NAME fuzz_${name}_corpus COMMAND fuzz_${name}_corpus ${fuzz_seeds})
    if(CRUX_HOST_FUZZ)
        add_executable(fuzz_${name} ${fuzz_sources_${name}})
        target_include_directories(fuzz_${name} PRIVATE ../../framework/src fuzz)
        target_compile_options(fuzz_${name} PRIVATE -Wall -Wextra -Wpedantic -Werror -g
            -fsanitize=fuzzer,address,undefined -fno-sanitize-recover=all)
        target_link_options(fuzz_${name} PRIVATE -fsanitize=fuzzer,address,undefined)
    endif()
endforeach()
