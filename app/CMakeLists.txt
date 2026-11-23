# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project(crux_controller)

target_sources(app PRIVATE src/main.c src/composition.c)
target_link_libraries(app PRIVATE crux::time)
target_compile_options(app PRIVATE -Wall -Wextra -Werror)

# workload and every configuration built on it: the workload on Zephyr threads, a message queue and Crux Logging. Its
# portable core is a library of this repository, and the thread and queue calls are the source of
# the adapter zone (app/os), so the application takes no include path of its own and links neither
# Crux Thread nor Crux Queue. The switch is the product's own option, CRUX_CONTROLLER_WORKLOAD.
if(CONFIG_CRUX_CONTROLLER_WORKLOAD)
    add_subdirectory(../workload workload)
    add_subdirectory(os)
    target_sources(app PRIVATE src/workload_thread.c)
    target_link_libraries(app PRIVATE workload crux::logging)
    # The net capability: the TCP exchange, through the Crux Sockets profile.
    if(CONFIG_CRUX_CONTROLLER_NET)
        target_sources(app PRIVATE src/net_client.c)
        target_link_libraries(app PRIVATE crux::sockets crux::netif)
    endif()
    # The file capability: the configuration record in a file, through Crux File. The application uses
    # <crux/file.h> only. The composition zone is a library of its own, the only target that
    # links the File composition interface, so the application gets no include path to it.
    # management uses the same zone for the web start, so it is added for either configuration.
    if(CONFIG_CRUX_CONTROLLER_FILE OR CONFIG_CRUX_CONTROLLER_MANAGEMENT)
        add_subdirectory(compose)
    endif()
    if(CONFIG_CRUX_CONTROLLER_FILE)
        target_sources(app PRIVATE src/config_store.c)
        target_link_libraries(app PRIVATE crux::file compose)
    endif()
    # The system capability: the reset cause and the watchdog, through <crux/system.h>. The glue and the policy
    # are sources of the application, and crux::system gives the public header only: the driver,
    # HWINFO and reboot facilities are inside Crux, so no zone and no include path is added here.
    if(CONFIG_CRUX_CONTROLLER_SYSTEM)
        target_sources(app PRIVATE src/health.c src/health_policy.c)
        target_link_libraries(app PRIVATE crux::system)
    endif()
    # The sntp capability: the realtime clock of Crux Time, set from an SNTP server. The policy and the glue are
    # sources of the application. The glue calls the Crux Time authority, whose header is in the
    # include directory that crux::time gives, and the SNTP library is called by the adapter zone
    # (app/os), so no zone, library or include path is added here.
    if(CONFIG_CRUX_CONTROLLER_SNTP)
        target_sources(app PRIVATE src/time_sync.c src/time_sync_policy.c)
    endif()
    # The management capability: HTTPS management. The policy is a source of the application, and the start sequence
    # is in the composition zone (app/compose). The entropy rules of the image are in
    # app/management/entropy.cmake. The route sources and the packaged page are named by
    # app/management/management.cmake. Both files are included here, not added as subdirectories,
    # because the route table belongs to the target `app`. The application links the public target
    # of the web API for the route macros, and no include path is added anywhere.
    if(CONFIG_CRUX_CONTROLLER_MANAGEMENT)
        target_sources(app PRIVATE src/management_policy.c)
        target_link_libraries(app PRIVATE crux::web compose)
        include("${CMAKE_CURRENT_LIST_DIR}/management/entropy.cmake")
        include("${CMAKE_CURRENT_LIST_DIR}/management/management.cmake")
    endif()
endif()
