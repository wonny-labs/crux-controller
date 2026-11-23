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
add_executable(test_time_sync_policy test_time_sync_policy.c ../../app/src/time_sync_policy.c)
target_include_directories(test_time_sync_policy PRIVATE ../../app/src)
target_compile_options(test_time_sync_policy PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME time_sync_policy COMMAND test_time_sync_policy)

# The address text and the role policy of the management management groundwork: ISO C only, so it builds
# here without Crux or Zephyr headers. No firmware image compiles it yet.
add_executable(test_management_policy test_management_policy.c ../../app/src/management_policy.c)
target_include_directories(test_management_policy PRIVATE ../../app/src)
target_compile_options(test_management_policy PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME management_policy COMMAND test_management_policy)
