#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Prepare the workspace inside the dev container. VS Code runs it after the container is created
# (postCreateCommand) and scripts/dev-shell.sh runs it before every command. It is safe to run again:
# each step checks whether it is already done and does nothing then.
#
# The layout is a workspace folder that holds the clone (named crux-controller), the .west folder,
# zephyr/ and modules/. The workspace folder is bind-mounted at /workspaces/ws. The virtual
# environment and the Zephyr SDK are in /opt/crux-cache, a named volume of this workspace folder.
#
# The steps are those of the S1 job of .github/workflows/ci.yml with local values: west init -l
# crux-controller, west update, the Python requirements of Zephyr and west sdk install. West is not
# updated again once the workspace exists: after the pin in west.yml moves, run `west update` by
# hand. The optional Mbed TLS group of step S6 is not switched on here (see
# docs/try-on-native-sim.md).
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="$(dirname "$repo")"
cache="${CRUX_CACHE_DIR:-/opt/crux-cache}"
sdk_version="${ZEPHYR_SDK_VERSION:?ZEPHYR_SDK_VERSION is not set}"
sdk_dir="${ZEPHYR_SDK_INSTALL_DIR:?ZEPHYR_SDK_INSTALL_DIR is not set}"

fail() {
    printf 'setup: %s\n' "$*" >&2
    exit 1
}

[[ "$(basename "$repo")" == "crux-controller" ]] \
    || fail "the clone is in a folder named '$(basename "$repo")'. West needs it to be named crux-controller (west.yml, self: path). Clone it as <workspace>/crux-controller."
for marker in .bashrc .profile .ssh .gitconfig; do
    [[ ! -e "$workspace/$marker" ]] \
        || fail "'$workspace' looks like a home directory ($marker is in it). Put the clone in a folder of its own, for example ~/work/controller-ws/crux-controller, because west init puts .west, zephyr/ and modules/ next to it."
done

# The container is a throw-away environment, so any directory may be trusted by its Git. The bind
# mounts can belong to another numeric user than the one in the container.
git config --global --add safe.directory '*'

# The volume may have been created for another user id.
if [[ "$(stat -c %u "$cache")" != "$(id -u)" ]]; then
    sudo chown -R "$(id -u):$(id -g)" "$cache"
fi

# 1. The virtual environment with the pinned tools.
tools="$repo/.devcontainer/requirements-tools.txt"
venv="$cache/venv"
if [[ ! -x "$venv/bin/python" ]]; then
    python3 -m venv "$venv"
fi
export PATH="$venv/bin:$PATH"
stamp="$venv/.requirements"
tools_hash="$(sha256sum "$tools" | cut -d' ' -f1)"
if [[ "$(cat "$stamp.tools" 2>/dev/null || true)" != "$tools_hash" ]]; then
    python -m pip install --no-cache-dir -r "$tools"
    printf '%s\n' "$tools_hash" >"$stamp.tools"
fi

# 2. The workspace, only when it is not initialised yet, or when an earlier update did not finish.
# ZEPHYR_BASE points into the workspace and does not exist before the update. The pending marker
# is written after west init and removed only after west update has ended, so an interrupted first
# run (a network failure, a closed terminal) is run again. A workspace that was set up another way
# has no marker and is left alone.
cd "$workspace"
pending="$workspace/.west/crux-devcontainer-update.pending"
if [[ ! -d "$workspace/.west" || ! -d "$workspace/zephyr" || -f "$pending" ]]; then
    (
        unset ZEPHYR_BASE
        [[ -d "$workspace/.west" ]] || west init -l crux-controller
        touch "$pending"
        west update
        rm -f "$pending"
    )
else
    printf 'setup: the workspace is initialised; run `west update` yourself after the pin in west.yml moves.\n'
fi

# 3. The Python requirements of Zephyr, as the S1 job installs them.
requirements=(
    "$workspace/zephyr/scripts/requirements-base.txt"
    "$workspace/zephyr/scripts/requirements-build-test.txt"
    "$workspace/zephyr/scripts/requirements-run-test.txt"
)
zephyr_hash="$(cat "${requirements[@]}" | sha256sum | cut -d' ' -f1)"
if [[ "$(cat "$stamp.zephyr" 2>/dev/null || true)" != "$zephyr_hash" ]]; then
    python -m pip install --no-cache-dir \
        -r "${requirements[0]}" -r "${requirements[1]}" -r "${requirements[2]}"
    printf '%s\n' "$zephyr_hash" >"$stamp.zephyr"
fi

# 4. The Zephyr SDK with the arm-zephyr-eabi toolchain, as the S1 job installs it. GH_TOKEN is
# optional: it only avoids GitHub's rate limit for anonymous requests.
if [[ ! -d "$sdk_dir" ]]; then
    token=()
    if [[ -n "${GH_TOKEN:-}" ]]; then
        token=(--personal-access-token "$GH_TOKEN")
    fi
    (
        unset ZEPHYR_BASE
        cd "$workspace/zephyr"
        west sdk install --version "$sdk_version" --install-base "$(dirname "$sdk_dir")" \
            --gnu-toolchains arm-zephyr-eabi "${token[@]}"
    )
fi
[[ -d "$sdk_dir" ]] || fail "the Zephyr SDK is not in $sdk_dir after the install"

printf 'setup: workspace %s, Zephyr SDK %s, %s\n' "$workspace" "$sdk_version" "$(west --version)"
