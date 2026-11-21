# Optional board container of Crux Controller: the default dev container image plus the SEGGER J-Link
# software, for `west flash` and `west debug` with the J-Link runner on the RT1060-EVKB. UNTESTED on
# hardware: nobody has built this image or reached a probe from it. docs/board-bring-up.md is the route.
#
# It is a layer on the default image (.devcontainer/Dockerfile), which .devcontainer/board/build-base.sh
# builds on the host first under the name crux-controller-dev. The default container does not change.
#
# The J-Link package is never fetched by this build and never committed. Download the "J-Link Software
# and Documentation Pack" for Linux, 64-bit DEB installer, from SEGGER yourself, accept its licence terms
# yourself, and put exactly one JLink_Linux_<version>_x86_64.deb into .devcontainer/board/jlink/. That
# folder ignores everything except its .gitignore, so the package stays out of Git. The build stops with a
# message when there is no package or more than one.
#
# The apt-get step needs the network for usbutils and for the packages that the J-Link package depends on.
# Behind a proxy, both build routes pass the host's proxy variables as build arguments:
# devcontainer.json through build.args, as the default devcontainer.json does, and scripts/board-shell.sh
# by name only. They are not declared here on purpose: Docker predefines the proxy build arguments, so they
# reach the RUN steps without an ARG line and stay out of the image history. The container gets the
# USB bus of the host through a bind mount and a device cgroup rule (devcontainer.json and
# scripts/board-shell.sh), never through --privileged.
ARG BASE_IMAGE=crux-controller-dev
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

COPY jlink/ /tmp/jlink/

RUN set -eu; \
    set -- /tmp/jlink/JLink_Linux_*_x86_64.deb; \
    if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then \
        echo "board image: put exactly one JLink_Linux_<version>_x86_64.deb, downloaded by you from SEGGER, into .devcontainer/board/jlink/ (docs/board-bring-up.md)" >&2; \
        exit 1; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends usbutils "$1"; \
    apt-get clean; \
    find /var/lib/apt/lists -type f -delete; \
    rm -rf /tmp/jlink
