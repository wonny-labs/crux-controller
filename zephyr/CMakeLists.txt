# SPDX-License-Identifier: Apache-2.0

# The controller framework as a Zephyr module. With CONFIG_CRUX_CONTROLLER_FRAMEWORK on it builds:
#   - controller::framework, an interface target that gives the interface header of
#     include/ (<controller/framework.h>), and that an image links to its target app;
#   - the library controller_framework, with the portable core (framework/src) and the
#     sources of the adapter zone (framework/os) of the services the build turns on;
#   - the library compose of the composition zone (framework/compose), linked by the framework
#     library only, so that no other target gets the composition interfaces of Crux.
# The boundary check (scripts/check_boundary.py) reads the includes of these trees; this file adds
# no include path to them beyond the interface header, and a source includes the headers of the
# core with a relative quoted path.
#
# controller_framework_image() is defined whatever the configuration, and an image calls it
# from its own CMakeLists.txt: the route table and the packaged page of web management belong to the
# image's target app, because Crux generates the route table for the target that compiles the route
# sources, in that target's directory scope.

function(controller_framework_image)
    if(NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK)
        message(FATAL_ERROR "controller_framework_image() needs CONFIG_CRUX_CONTROLLER_FRAMEWORK")
    endif()
    if(CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT)
        include("${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../framework/management/management.cmake")
        # A key made from a test source means nothing, so a board image refuses one. The
        # native_sim simulator has only its test source, and only the tests run there.
        if(NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)
            include("${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../framework/management/entropy.cmake")
        endif()
    endif()
endfunction()

if(CONFIG_CRUX_CONTROLLER_FRAMEWORK)
    get_filename_component(controller_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

    add_library(controller_framework_api INTERFACE)
    target_include_directories(controller_framework_api INTERFACE "${controller_root}/include")
    add_library(controller::framework ALIAS controller_framework_api)

    zephyr_library_named(controller_framework)
    zephyr_library_sources(
        "${controller_root}/framework/src/framework.c"
        "${controller_root}/framework/src/startup.c")
    zephyr_library_compile_options(-Wall -Wextra -Werror)
    zephyr_library_link_libraries(controller_framework_api crux::time crux::logging)

    if(NOT KERNEL_VERSION_STRING)
        message(FATAL_ERROR "The controller framework reports the Zephyr version to the status service, "
                            "and the build gave none (KERNEL_VERSION_STRING)")
    endif()

    if(CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT)
        zephyr_library_sources("${controller_root}/framework/src/management_policy.c")
        zephyr_library_compile_definitions(
            CONTROLLER_PLATFORM_VERSION="zephyr-${KERNEL_VERSION_STRING}"
            CONTROLLER_PROJECT_VERSION="crux-controller-framework")
        add_subdirectory("${controller_root}/framework/compose" compose)
        zephyr_library_link_libraries(compose)
    endif()

    if(CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC)
        zephyr_library_sources(
            "${controller_root}/framework/src/time_sync.c"
            "${controller_root}/framework/src/time_sync_policy.c"
            "${controller_root}/framework/os/time_sync_zephyr.c")
    endif()
endif()
