# SPDX-License-Identifier: Apache-2.0

# The management capability: the build of HTTPS management. This file is included by app/CMakeLists.txt, inside the
# management block, after find_package(Zephyr) and project(). It is not a subdirectory, because the
# route table is generated for the target `app` and the generator sets properties on `app`'s own
# sources, which have to be in the same directory scope.
#
# What it does, in the order that Crux's functions need:
#   - finds the Crux module by the variable that Zephyr sets for it, and includes three files of it;
#   - packages the page of app/management/site (crux_web_assets), then names the route sources of
#     the session and management services and generates the route table (crux_web_routes), checked
#     against reviewed-routes.txt.
#
# The route sources are Crux's own files. crux_web_routes() hands each of them its private include
# directories as a property of that one source, so `app` gets no include directory from here and
# this file adds none. If that does not compile from this repository, the capability stops: there is no
# private include path to fall back on (docs/findings/s6-https-management.md).
#
# The entropy rules of the board image are in entropy.cmake, which only the image includes: the
# native_sim scenario includes this file and has a test entropy source on purpose.
#
# The network, reboot and file service routes are separate variables of Crux and are not named, so
# they are not in the table. The version texts that the status service reports are compile
# definitions of the application, read by composition.c.

set(crux_root "${ZEPHYR_CRUX_MODULE_DIR}")
if(NOT crux_root)
    message(FATAL_ERROR "The management capability needs the Crux module: ZEPHYR_CRUX_MODULE_DIR is not set")
endif()

if(NOT KERNEL_VERSION_STRING)
    message(FATAL_ERROR "The management capability reports the Zephyr version to the status service, and the build "
                        "gave none (KERNEL_VERSION_STRING)")
endif()

include("${crux_root}/cmake/CruxWebAssets.cmake")
include("${crux_root}/cmake/CruxWebRoutes.cmake")
include("${crux_root}/components/web/session/sources.cmake")
include("${crux_root}/components/web/management/sources.cmake")

target_compile_definitions(app PRIVATE
    MANAGEMENT_PLATFORM_VERSION="zephyr-${KERNEL_VERSION_STRING}"
    MANAGEMENT_PROJECT_VERSION="crux-controller-management")

set(route_sources ${CRUX_WEB_SESSION_ROUTES} ${CRUX_WEB_MANAGEMENT_ROUTES})
target_sources(app PRIVATE ${route_sources})
crux_web_assets(app FOLDER "${CMAKE_CURRENT_LIST_DIR}/site" STYLE strict)
crux_web_routes(app SOURCES ${route_sources} ZEPHYR_RESOURCES REVIEWED "${CMAKE_CURRENT_LIST_DIR}/reviewed-routes.txt")
