# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20)
project(crux_controller_host_tests C)

option(WORKLOAD_SANITIZE "Build with the address and undefined-behaviour sanitizers" OFF)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

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
target_compile_definitions(test_net_client PRIVATE
    _POSIX_C_SOURCE=200809L
    CONFIG_CRUX_CONTROLLER_PEER_ADDRESS="127.0.0.1"
    CONFIG_CRUX_CONTROLLER_PEER_PORT=42431)
target_compile_options(test_net_client PRIVATE -Wall -Wextra -Werror)
add_test(NAME net_client COMMAND test_net_client)

# The reset-cause and watchdog policy of step S4: ISO C only, so it builds here without Crux or
# Zephyr headers. The glue that calls Crux System is not built on the host.
add_executable(test_health_policy test_health_policy.c ../../app/src/health_policy.c)
target_include_directories(test_health_policy PRIVATE ../../app/src)
target_compile_options(test_health_policy PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME health_policy COMMAND test_health_policy)

# The time synchronisation policy of step S5: ISO C only, so it builds here without Crux or Zephyr
# headers. The glue that calls the Crux Time authority and the adapter that calls Zephyr's SNTP
# library are not built on the host.
add_executable(test_time_sync_policy test_time_sync_policy.c ../../app/src/time_sync_policy.c)
target_include_directories(test_time_sync_policy PRIVATE ../../app/src)
target_compile_options(test_time_sync_policy PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME time_sync_policy COMMAND test_time_sync_policy)

# The address text and the role policy of the S6 management groundwork: ISO C only, so it builds
# here without Crux or Zephyr headers. No firmware image compiles it yet.
add_executable(test_management_policy test_management_policy.c ../../app/src/management_policy.c)
target_include_directories(test_management_policy PRIVATE ../../app/src)
target_compile_options(test_management_policy PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME management_policy COMMAND test_management_policy)
