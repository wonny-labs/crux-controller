# Build environment of Crux Controller for a developer who cannot use Ubuntu 24.04 natively, for
# example on Windows with WSL2 and Docker Engine (no Docker Desktop). It carries the host packages
# and tools that the CI jobs of .github/workflows/ci.yml install on ubuntu-24.04. The workspace
# (Zephyr, the west modules), the virtual environment and the Zephyr SDK are not part of the image:
# .devcontainer/setup.sh fetches them into the bind-mounted workspace and the named volume, so a
# rebuilt image does not download them again.
#
# The base image is pinned by digest (a multi-architecture index). To move it, resolve the new
# digest of the tag and change it here in a reviewed pull request.
# tests/tooling/test_devcontainer.py checks that the base image is pinned by digest, and
# it compares the SDK version and the tool versions with ci.yml.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04@sha256:d94c97dd9cacf183d0a6fd12a8e87b526e9e928307674ae9c94139139c0c6eae

ARG DEBIAN_FRONTEND=noninteractive

# The user id and group id of the host user. The Dev Containers extension adjusts the user itself
# (updateRemoteUserUID in devcontainer.json), so it leaves these at 1000. scripts/dev-shell.sh passes the
# ids of the caller, so that files written to the bind-mounted workspace belong to that user.
ARG USER_UID=1000
ARG USER_GID=1000

# Proxy settings of the host, for the apt-get below: devcontainer.json passes them as build arguments
# when the host has them (scripts/dev-shell.sh does not yet). They are not declared here on purpose. Docker
# predefines the proxy build arguments (HTTP_PROXY, http_proxy, HTTPS_PROXY, https_proxy, NO_PROXY,
# no_proxy), so they reach the RUN steps without an ARG line, and a predefined argument is left out
# of the image history; a declared ARG would show a proxy URL with credentials there. They are never
# ENV either: the proxy of the company that builds the image must not become part of the environment
# of every container.

# The packages of the "Install host packages" step of the workload job, plus python3-venv (CI gets its
# Python from actions/setup-python), curl and sudo for the setup script, and clang-tidy-18 at the
# version of the "Static analysis" job.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc-multilib \
        ca-certificates \
        clang-tidy-18=1:18.1.3-1ubuntu1 \
        curl \
        device-tree-compiler \
        file \
        gperf \
        git \
        libmagic1 \
        libsdl2-dev \
        pkg-config \
        python3-dev \
        python3-venv \
        sudo \
        wget \
        xz-utils \
    && apt-get clean \
    && find /var/lib/apt/lists -type f -delete

RUN if [ "$USER_GID" != "$(id -g vscode)" ]; then groupmod -o --gid "$USER_GID" vscode; fi \
    && if [ "$USER_UID" != "$(id -u vscode)" ]; then usermod -o --uid "$USER_UID" vscode; fi \
    && chown -R "$USER_UID:$USER_GID" /home/vscode \
    && install -d -o "$USER_UID" -g "$USER_GID" /opt/crux-cache

# The Zephyr SDK version of the CI jobs. The SDK and the virtual environment are installed by
# .devcontainer/setup.sh into /opt/crux-cache, which is a named volume.
ENV ZEPHYR_SDK_VERSION=1.0.1
ENV ZEPHYR_SDK_INSTALL_DIR=/opt/crux-cache/sdk/zephyr-sdk-${ZEPHYR_SDK_VERSION} \
    ZEPHYR_BASE=/workspaces/ws/zephyr \
    CRUX_CACHE_DIR=/opt/crux-cache \
    CLANG_TIDY=clang-tidy-18 \
    PATH=/opt/crux-cache/venv/bin:${PATH}

# SEGGER J-Link software for flashing and debugging a board (docs/board-bring-up.md). The package comes from
# the first of: a file the developer placed in .devcontainer/jlink/packages/; CRUX_JLINK_URL, a copy that an
# organisation hosts, checked against CRUX_JLINK_DEB_SHA256; the version pinned below, downloaded from
# SEGGER's download endpoint and checked against the pinned SHA-256. That download accepts SEGGER's terms of
# use (see jlink/install-jlink.sh). CRUX_JLINK=auto (devcontainer.json) installs it and, when none of the
# three gives a package, prints a warning and builds the image without it, so Host and native_sim work for
# everyone; 1 requires it; 0 skips it. To bump J-Link, change the two CRUX_JLINK_SEGGER_* values together.
# The proxy build arguments are not declared here, as above.
ARG CRUX_JLINK=auto
ARG CRUX_JLINK_DEB=
ARG CRUX_JLINK_DEB_SHA256=
ARG CRUX_JLINK_URL=
ARG CRUX_JLINK_SEGGER_VERSION=V996a
ARG CRUX_JLINK_SEGGER_SHA256=e23591160efa39e0f9e184031195a594d962853a801a1261b168a02644ab2a0a
COPY jlink/ /tmp/crux-jlink/
RUN if [ "$CRUX_JLINK" != 0 ]; then \
        sh /tmp/crux-jlink/install-jlink.sh /tmp/crux-jlink/packages \
        && rm -rf /var/lib/apt/lists/*; \
    fi \
    && rm -rf /tmp/crux-jlink
