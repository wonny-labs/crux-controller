# SPDX-License-Identifier: Apache-2.0

# The controller framework as a Zephyr module. With CONFIG_CRUX_CONTROLLER_FRAMEWORK on it builds:
#   - controller::framework, an interface target that gives the interface headers of
#     include/ (<controller/framework.h>, <controller/version.h>), and that an image links to its
#     target app;
#   - the library controller_framework, with the portable core (framework/src) and the
#     sources of the adapter zone (framework/os) of the services the build turns on;
#   - the library compose of the composition zone (framework/compose), linked by the framework
#     library only, so that no other target gets the composition interfaces of Crux.
# The boundary check (scripts/check_boundary.py) reads the includes of these trees; this file adds
# no include path to them beyond the interface headers, and a source includes the headers of the
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
        # The generated route table includes <crux/web.h>, so the target that compiles it links the
        # public target of the web API, as the management configuration of app/ does.
        target_link_libraries(app PRIVATE crux::web)
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
    # <controller/framework_management.h> takes the Crux types of the status and configuration
    # services, so an image that includes it gets their public headers.
    if(CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT)
        target_link_libraries(controller_framework_api INTERFACE crux::mgmt_status crux::config_service)
    endif()

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
        zephyr_library_sources(
            "${controller_root}/framework/src/management_policy.c"
            "${controller_root}/framework/src/service_progress.c")
        zephyr_library_compile_definitions(
            CONTROLLER_PLATFORM_VERSION="zephyr-${KERNEL_VERSION_STRING}"
            CONTROLLER_PROJECT_VERSION="crux-controller-framework")
        add_subdirectory("${controller_root}/framework/compose" compose)
        # crux::security_event: the framework's own events (framework/src/framework_events.h).
        zephyr_library_link_libraries(compose crux::security_event)
    endif()

    if(CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC)
        zephyr_library_sources(
            "${controller_root}/framework/src/time_sync.c"
            "${controller_root}/framework/src/time_sync_policy.c"
            "${controller_root}/framework/os/time_sync_zephyr.c")
        if(CONFIG_CRUX_SECURITY_EVENT)
            zephyr_library_link_libraries(crux::security_event)
        endif()
    endif()

    # Health supervision: the portable rules (boot record, supervision, states), the framework's
    # copy of the retained region, and the adapter zone's supervisor thread, retained region and
    # fatal error handler, and the application contract with its thread. The image identity is the
    # commit of this repository, the commit of the application's repository (the product's, whose
    # update may change only its application code) and the hash of the resolved configuration, so
    # another image or another configuration clears the boot counter (project-specific workaround:
    # the specification asks for an identifier of the image and names no source for it; uncommitted
    # changes do not change the identity).
    if(CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION)
        zephyr_library_sources(
            "${controller_root}/framework/src/app_contract.c"
            "${controller_root}/framework/src/app_requests.c"
            "${controller_root}/framework/src/boot_record.c"
            "${controller_root}/framework/src/controller_state.c"
            "${controller_root}/framework/src/recovery.c"
            "${controller_root}/framework/src/supervision.c"
            "${controller_root}/framework/os/app_zephyr.c"
            "${controller_root}/framework/os/fatal_zephyr.c"
            "${controller_root}/framework/os/retained_zephyr.c"
            "${controller_root}/framework/os/supervisor_zephyr.c")
        if(CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT)
            zephyr_library_sources("${controller_root}/framework/os/storage_worker_zephyr.c")
        endif()
        zephyr_library_link_libraries(crux::system)
        # The network's health comes from Crux NetIf where the image has it (section 4.7).
        if(CONFIG_CRUX_NETIF)
            zephyr_library_link_libraries(crux::netif)
        endif()
        # A start prerequisite or runtime dependency on a service that the build leaves out fails
        # the build (section 7.1). Kconfig only warns about an assignment whose dependency is not
        # met, so the symbols have no dependency and the check is here, as Crux's testcases turn an
        # unsatisfied dependency into an error in CMake.
        set(controller_services
            "NETWORK:CRUX_NETIF:network (Crux NetIf)"
            "STORAGE:CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT:storage (web management)"
            "ACCESS:CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT:Access (web management)"
            "CONFIGURATION:CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT:configuration (web management)"
            "TIME:CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC:time synchronisation"
            "WEB:CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT:web management"
            "COMMAND_LINE:CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL:the serial command line")
        foreach(entry IN LISTS controller_services)
            string(REPLACE ":" ";" parts "${entry}")
            list(GET parts 0 service)
            list(GET parts 1 needed)
            list(GET parts 2 words)
            foreach(kind PREREQUISITE DEPENDENCY)
                if(CONFIG_CRUX_CONTROLLER_${kind}_${service} AND NOT CONFIG_${needed})
                    message(FATAL_ERROR "CONFIG_CRUX_CONTROLLER_${kind}_${service} needs ${words}, "
                                        "which this build leaves out (CONFIG_${needed} is not set)")
                endif()
            endforeach()
        endforeach()
        find_package(Git QUIET)
        set(controller_commit "unknown")
        if(GIT_FOUND)
            execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${controller_root}" rev-parse HEAD
                OUTPUT_VARIABLE controller_commit OUTPUT_STRIP_TRAILING_WHITESPACE
                ERROR_QUIET RESULT_VARIABLE controller_git_result)
            if(NOT controller_git_result EQUAL 0)
                set(controller_commit "unknown")
            endif()
        endif()
        set(controller_application_commit "unknown")
        if(GIT_FOUND)
            execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${APPLICATION_SOURCE_DIR}" rev-parse HEAD
                OUTPUT_VARIABLE controller_application_commit OUTPUT_STRIP_TRAILING_WHITESPACE
                ERROR_QUIET RESULT_VARIABLE controller_git_result)
            if(NOT controller_git_result EQUAL 0)
                set(controller_application_commit "unknown")
            endif()
        endif()
        file(SHA256 "${DOTCONFIG}" controller_config_hash)
        zephyr_library_compile_definitions(
            CONTROLLER_IMAGE_ID_TEXT="${controller_commit}-${controller_application_commit}-${controller_config_hash}")
        if(CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT)
            zephyr_library_sources(
                "${controller_root}/framework/src/reboot_policy.c"
                "${controller_root}/framework/os/reboot_zephyr.c")
            zephyr_library_link_libraries(crux::reboot)
        endif()
        if(CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION)
            if(NOT CONFIG_BOARD_NATIVE_SIM)
                message(FATAL_ERROR "fault injection is for the native_sim scenarios only")
            endif()
            zephyr_library_sources("${controller_root}/framework/src/fault_injection.c")
        endif()
    endif()
endif()
