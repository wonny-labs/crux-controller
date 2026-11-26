# SPDX-License-Identifier: Apache-2.0

# The composition zone of file and management as a library of its own. It is the only target that links the
# File composition interface, so the application target gets no include path to it: the boundary
# check reads includes, this file keeps the build in line with it. The library needs the Zephyr
# headers of the image (zephyr_interface); the provider itself is selected by Kconfig and
# appended to the Zephyr link by Crux, not linked here. The one source includes the port header
# of framework/src with a relative quoted path, so no include directory is added either.
add_library(compose STATIC storage_mount.c)
target_link_libraries(compose PRIVATE zephyr_interface crux::file_zephyr)
target_compile_options(compose PRIVATE -Wall -Wextra -Werror)

# The management capability: the start sequence of HTTPS management. The source is built only when Crux's web
# management symbol is on, so that the file scenario, which builds this directory without the
# application's Kconfig, still builds the storage source alone. The libraries are Crux's public
# usage targets and give the public headers; the one composition interface of the web start,
# crux::web_zephyr, is linked here and nowhere else, as crux::file_zephyr is. The route sources are
# not here: they belong to the target `app` (framework/management/management.cmake). The service
# libraries themselves are selected by Kconfig and appended to the Zephyr link by Crux.
if(CONFIG_CRUX_WEB_MANAGEMENT)
    target_sources(compose PRIVATE management_start.c)
    target_link_libraries(compose PRIVATE crux::web_zephyr crux::web_session crux::web_management
        crux::access crux::credential_store crux::security_event crux::config_service
        crux::mgmt_status crux::tls_certificate crux::system crux::time crux::logging)
endif()
