#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the default dev container image on the host, so that the optional board container can be a layer
# on it. VS Code runs this as the initializeCommand of .devcontainer/board/devcontainer.json, and
# scripts/board-shell.sh runs it before it builds the board layer. UNTESTED on hardware and on WSL2.
#
# It first runs .devcontainer/check-host.sh (the layout check of the default container). It then builds
# .devcontainer/Dockerfile as scripts/dev-shell.sh does: for linux/amd64, with the user id and group id of
# the caller, under the name crux-controller-dev (CRUX_DEV_IMAGE overrides it; VS Code always uses the
# default name, because .devcontainer/board/devcontainer.json names it). The proxy variables of the host
# are passed to the build by name only, so that their values do not appear on the command line.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
image="${CRUX_DEV_IMAGE:-crux-controller-dev}"

bash "$repo/.devcontainer/check-host.sh"

proxies=()
for name in HTTP_PROXY http_proxy HTTPS_PROXY https_proxy NO_PROXY no_proxy; do
    if [[ -n "${!name:-}" ]]; then
        proxies+=(--build-arg "$name")
    fi
done

docker build --platform linux/amd64 \
    --build-arg "USER_UID=$(id -u)" --build-arg "USER_GID=$(id -g)" \
    ${proxies[@]+"${proxies[@]}"} \
    -t "$image" "$repo/.devcontainer"
