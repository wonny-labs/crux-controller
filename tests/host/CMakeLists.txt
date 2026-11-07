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
