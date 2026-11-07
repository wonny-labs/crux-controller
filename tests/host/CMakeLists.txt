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
