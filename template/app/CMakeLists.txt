# SPDX-License-Identifier: Apache-2.0

# The product's application. The controller framework is a Zephyr module of the product's west
# workspace, found by west: this file names no path, source or include directory of the framework.
# The application links the interface target of the framework and calls its image function, which
# adds the route table and the page of web management. Board values live in boards/, not here.

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(product LANGUAGES C)

target_sources(app PRIVATE src/main.c)
target_compile_options(app PRIVATE -Wall -Wextra -Werror)
target_link_libraries(app PRIVATE controller::framework crux::logging)
controller_framework_image()
