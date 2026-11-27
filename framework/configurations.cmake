# SPDX-License-Identifier: Apache-2.0

# The framework sources that the configurations of app/ built on the workload compile into the
# target app: the sntp and management configurations. app/CMakeLists.txt includes this file inside
# its workload block, so the sources take the warning level and the definitions of the target app.
# The base image does not use this file: the module (zephyr/CMakeLists.txt) builds the same
# sources into its own library, and the two never meet in one image (app/CMakeLists.txt refuses
# the workload together with the framework).
#
# The adapter zone source is a source of the target app, not of a library of its own, for the
# reason that app/os/CMakeLists.txt gives. No include path is added: the sources include their
# headers with relative quoted paths.

if(CONFIG_CRUX_CONTROLLER_SNTP)
    target_sources(app PRIVATE
        "${CMAKE_CURRENT_LIST_DIR}/src/time_sync.c"
        "${CMAKE_CURRENT_LIST_DIR}/src/time_sync_policy.c"
        "${CMAKE_CURRENT_LIST_DIR}/os/time_sync_zephyr.c")
    set_source_files_properties("${CMAKE_CURRENT_LIST_DIR}/os/time_sync_zephyr.c"
                                TARGET_DIRECTORY app
                                PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Werror")
endif()

if(CONFIG_CRUX_CONTROLLER_MANAGEMENT)
    target_sources(app PRIVATE "${CMAKE_CURRENT_LIST_DIR}/src/management_policy.c")
endif()
