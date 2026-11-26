#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Install the arm-zephyr-eabi toolchain of Zephyr SDK $SDK_VERSION at $ZEPHYR_SDK_INSTALL_DIR with
# `west sdk install`, run in the given Zephyr folder. An SDK that is already there (restored from a
# cache) is kept. GH_TOKEN, when set, is passed to west for the download.
#
#   scripts/ci/install-sdk.sh ZEPHYR_FOLDER
set -euo pipefail
zephyr=${1:-}
if [[ -z "$zephyr" || $# -ne 1 ]]; then
    printf 'Usage: %s ZEPHYR_FOLDER\n' "$0" >&2
    exit 2
fi
: "${SDK_VERSION:?set SDK_VERSION, the Zephyr SDK version}"
: "${ZEPHYR_SDK_INSTALL_DIR:?set ZEPHYR_SDK_INSTALL_DIR, the folder of the Zephyr SDK}"
if [[ -d "$ZEPHYR_SDK_INSTALL_DIR" ]]; then
    printf 'Zephyr SDK found at %s; not installed again.\n' "$ZEPHYR_SDK_INSTALL_DIR"
    exit 0
fi
cd "$zephyr"
args=(--version "$SDK_VERSION" --install-base "$(dirname "$ZEPHYR_SDK_INSTALL_DIR")"
    --gnu-toolchains arm-zephyr-eabi)
if [[ -n "${GH_TOKEN:-}" ]]; then
    args+=(--personal-access-token "$GH_TOKEN")
fi
exec west sdk install "${args[@]}"
