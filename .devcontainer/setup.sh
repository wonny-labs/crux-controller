#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Prepare the workspace inside the dev container. VS Code runs it after the container is created
# (postCreateCommand) and scripts/dev-shell.sh runs it before every command. It is safe to run again:
# each step checks whether it is already done and does nothing then, and a step that was interrupted
# is done again from its start.
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
#
# Completion markers: a finished SDK install writes $ZEPHYR_SDK_INSTALL_DIR/.crux-installed, and the
# west workspace counts as initialised only with .west/config. A folder without its marker is what an
# interrupted run leaves behind, so it is removed (the message says which) and made again.
#
# Network: when http_proxy, https_proxy or no_proxy is set (either case), both cases are exported for
# pip, west, git and curl. When CRUX_EXTRA_CA_FILE names a readable PEM file (scripts/dev-shell.sh
# mounts it), it is installed as a system certificate for a proxy that inspects TLS, and the system
# bundle is selected for pip, requests and git. Without these variables the script behaves as before.
#
# Everything it prints goes to the standard error stream, also what pip, west and git print, so a
# command that scripts/dev-shell.sh runs after it keeps a clean standard output. When a step fails it
# prints which one, and how to run the script again.
set -euo pipefail

exec 1>&2

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="$(dirname "$repo")"
cache="${CRUX_CACHE_DIR:-/opt/crux-cache}"
sdk_version="${ZEPHYR_SDK_VERSION:?ZEPHYR_SDK_VERSION is not set}"
sdk_dir="${ZEPHYR_SDK_INSTALL_DIR:?ZEPHYR_SDK_INSTALL_DIR is not set}"
extra_ca_target=/usr/local/share/ca-certificates/crux-extra-ca.crt
system_ca_bundle=/etc/ssl/certs/ca-certificates.crt

current_step="starting"
step() {
    current_step="$1"
}
say() {
    printf 'setup: %s\n' "$*"
}
fail() {
    printf 'setup: %s\n' "$*" >&2
    exit 1
}
report_failure() {
    local status=$?
    if ((status != 0)); then
        printf 'setup: failed during %s; rerun: bash .devcontainer/setup.sh\n' "$current_step"
    fi
}
trap report_failure EXIT

step "the check of the workspace folder"
[[ "$(basename "$repo")" == "crux-controller" ]] \
    || fail "the clone is in a folder named '$(basename "$repo")'. West needs it to be named crux-controller (west.yml, self: path). Clone it as <workspace>/crux-controller."
for marker in .bashrc .profile .ssh .gnupg .gitconfig; do
    [[ ! -e "$workspace/$marker" ]] \
        || fail "'$workspace' looks like a home directory ($marker is in it). Put the clone in a folder of its own, for example ~/work/controller-ws/crux-controller, because west init puts .west, zephyr/ and modules/ next to it."
done

# The container is a throw-away environment, so any directory may be trusted by its Git. The bind
# mounts can belong to another numeric user than the one in the container. The setting is added once:
# a run of this script in a container that lives on must not add it again.
step "the Git settings"
safe_directories="$(git config --global --get-all safe.directory || true)"
if ! grep -qxF '*' <<<"$safe_directories"; then
    git config --global --add safe.directory '*'
fi

# The proxy settings and the certificate of a proxy that inspects TLS, for the steps below.
step "the network settings"
proxies_found=""
for pair in http_proxy:HTTP_PROXY https_proxy:HTTPS_PROXY no_proxy:NO_PROXY; do
    lower="${pair%%:*}"
    upper="${pair##*:}"
    value="${!lower:-}"
    [[ -n "$value" ]] || value="${!upper:-}"
    if [[ -n "$value" ]]; then
        export "$lower=$value" "$upper=$value"
        proxies_found="$proxies_found $lower"
    fi
done
if [[ -n "$proxies_found" ]]; then
    # Only the names: a proxy URL can hold a password.
    say "using the proxy settings of the host for pip, west, git and curl:$proxies_found"
fi
if [[ -n "${CRUX_EXTRA_CA_FILE:-}" ]]; then
    [[ -f "$CRUX_EXTRA_CA_FILE" && -r "$CRUX_EXTRA_CA_FILE" ]] \
        || fail "CRUX_EXTRA_CA_FILE is '$CRUX_EXTRA_CA_FILE', which is not a readable file."
    grep -q -- '-----BEGIN CERTIFICATE-----' "$CRUX_EXTRA_CA_FILE" \
        || fail "CRUX_EXTRA_CA_FILE ($CRUX_EXTRA_CA_FILE) is not a PEM certificate (no BEGIN CERTIFICATE line). Convert a DER file (.cer) with: openssl x509 -inform der -in company.cer -out company.crt"
    say "installing $CRUX_EXTRA_CA_FILE as a system certificate"
    sudo install -m 0644 "$CRUX_EXTRA_CA_FILE" "$extra_ca_target"
    sudo update-ca-certificates
    export SSL_CERT_FILE="$system_ca_bundle" REQUESTS_CA_BUNDLE="$system_ca_bundle"
    export PIP_CERT="$system_ca_bundle" GIT_SSL_CAINFO="$system_ca_bundle"
fi

# The volume may have been created for another user id.
step "the cache volume"
if [[ "$(stat -c %u "$cache")" != "$(id -u)" ]]; then
    sudo chown -R "$(id -u):$(id -g)" "$cache"
fi

# 1. The virtual environment with the pinned tools. A folder that has a python but no pip is what an
# interrupted creation leaves, so pip is tested too. --clear starts it again from nothing.
step "the Python virtual environment"
tools="$repo/.devcontainer/requirements-tools.txt"
venv="$cache/venv"
if [[ ! -x "$venv/bin/python" || ! -x "$venv/bin/pip" ]]; then
    if [[ -e "$venv" ]]; then
        say "the virtual environment in $venv is incomplete (python or pip is missing); creating it again"
    else
        say "creating the virtual environment in $venv"
    fi
    python3 -m venv --clear "$venv"
fi
export PATH="$venv/bin:$PATH"
stamp="$venv/.requirements"
tools_hash="$(sha256sum "$tools" | cut -d' ' -f1)"
if [[ "$(cat "$stamp.tools" 2>/dev/null || true)" != "$tools_hash" ]]; then
    say "installing the pinned tools into the virtual environment"
    python -m pip install --no-cache-dir -r "$tools"
    printf '%s\n' "$tools_hash" >"$stamp.tools"
fi

# 2. The workspace, only when it is not initialised yet, or when an earlier update did not finish.
# ZEPHYR_BASE points into the workspace and does not exist before the update. The pending marker
# is written after west init and removed only after west update has ended, so an interrupted first
# run (a network failure, a closed terminal) is run again. A .west folder without .west/config is
# an interrupted west init: west refuses to initialise over it, so it is removed first. A workspace
# that was set up another way has a config and no marker and is left alone.
step "the west workspace"
cd "$workspace"
pending="$workspace/.west/crux-devcontainer-update.pending"
if [[ ! -d "$workspace/.west" || ! -f "$workspace/.west/config" || ! -d "$workspace/zephyr" || -f "$pending" ]]; then
    (
        unset ZEPHYR_BASE
        if [[ ! -f "$workspace/.west/config" ]]; then
            if [[ -e "$workspace/.west" ]]; then
                say "$workspace/.west has no config file (an interrupted west init); removing it and initialising again"
                rm -rf "$workspace/.west"
            fi
            say "west init -l crux-controller"
            west init -l crux-controller
        fi
        touch "$pending"
        say "west update (the first run fetches several GiB and takes a long time)"
        west update
        rm -f "$pending"
    )
else
    say "the workspace is initialised; run \`west update\` yourself after the pin in west.yml moves."
fi

# 3. The Python requirements of Zephyr, as the S1 job installs them.
step "the Python requirements of Zephyr"
requirements=(
    "$workspace/zephyr/scripts/requirements-base.txt"
    "$workspace/zephyr/scripts/requirements-build-test.txt"
    "$workspace/zephyr/scripts/requirements-run-test.txt"
)
zephyr_hash="$(cat "${requirements[@]}" | sha256sum | cut -d' ' -f1)"
if [[ "$(cat "$stamp.zephyr" 2>/dev/null || true)" != "$zephyr_hash" ]]; then
    say "installing the Python requirements of Zephyr"
    python -m pip install --no-cache-dir \
        -r "${requirements[0]}" -r "${requirements[1]}" -r "${requirements[2]}"
    printf '%s\n' "$zephyr_hash" >"$stamp.zephyr"
fi

# 4. The Zephyr SDK with the arm-zephyr-eabi toolchain, as the S1 job installs it. GH_TOKEN is
# optional: it only avoids GitHub's rate limit for anonymous requests. The install is complete when
# the marker exists and the compiler is there; the marker is written only after west sdk install
# returned. The compiler is looked for by name, so that a change of the SDK's folder layout does not
# matter.
step "the Zephyr SDK install"
sdk_marker="$sdk_dir/.crux-installed"
sdk_compiler_present() {
    local found
    found="$(find "$sdk_dir" -maxdepth 5 -type f -perm -100 -name arm-zephyr-eabi-gcc -print 2>/dev/null || true)"
    [[ -n "$found" ]]
}
sdk_complete() {
    [[ -f "$sdk_marker" ]] && sdk_compiler_present
}
if ! sdk_complete; then
    if [[ -e "$sdk_dir" ]]; then
        [[ "$sdk_dir" == "$cache"/* ]] \
            || fail "the Zephyr SDK folder $sdk_dir is incomplete and is not inside $cache, so it is not removed. Remove it yourself and run this script again."
        say "$sdk_dir is incomplete (no install marker, or no compiler); removing it and installing the SDK again"
        rm -rf -- "$sdk_dir"
    fi
    token=()
    if [[ -n "${GH_TOKEN:-}" ]]; then
        token=(--personal-access-token "$GH_TOKEN")
    fi
    say "installing the Zephyr SDK $sdk_version (several GiB, a long time)"
    (
        unset ZEPHYR_BASE
        cd "$workspace/zephyr"
        west sdk install --version "$sdk_version" --install-base "$(dirname "$sdk_dir")" \
            --gnu-toolchains arm-zephyr-eabi ${token[@]+"${token[@]}"}
    )
    [[ ! -d "$sdk_dir" ]] || touch "$sdk_marker"
fi
step "the check of the Zephyr SDK"
[[ -d "$sdk_dir" ]] || fail "the Zephyr SDK is not in $sdk_dir after the install"
sdk_complete || fail "the Zephyr SDK in $sdk_dir has no install marker or no arm-zephyr-eabi-gcc compiler after the install"

step "the final check"
printf 'setup: workspace %s, Zephyr SDK %s, %s\n' "$workspace" "$sdk_version" "$(west --version)"
