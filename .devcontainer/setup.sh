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
# hand. The optional Mbed TLS group of step S6 (crux-secure-management) is switched on once per
# workspace, in .west/config and never in west.yml, with the steps and the order of the S6 job: the
# guard scripts/check_mbed_only.py in default mode, the group, the guard in mbed mode, then west update.
# The wolf stacks share that group and are never fetched: a guard error stops the setup before the
# group-on fetch. A marker in .west records the finished switch (see docs/try-on-native-sim.md).
#
# Completion markers: a finished SDK install writes $ZEPHYR_SDK_INSTALL_DIR/.crux-installed, and the
# west workspace counts as initialised only with .west/config. A folder without its marker is what an
# interrupted run leaves behind, so it is removed (the message says which) and made again.
#
# Network: when http_proxy, https_proxy or no_proxy is set (either case), both cases are exported for
# pip, west, git and curl. devcontainer.json passes them from the host environment; scripts/dev-shell.sh
# does not pass them yet. A host proxy on 127.0.0.1 or localhost is not reachable from the container,
# and proxy values in containerEnv are visible with `docker inspect`.
#
# A company proxy that inspects TLS needs its certificate. Before any pip, git, west or curl step the
# script installs ONE PEM file as a system certificate (/usr/local/share/ca-certificates/
# crux-extra-ca.crt, then sudo update-ca-certificates) and selects the system bundle for pip, requests
# and git (SSL_CERT_FILE, REQUESTS_CA_BUNDLE, PIP_CERT, GIT_SSL_CAINFO). The file is, in this order:
#   1. the file that CRUX_EXTRA_CA_FILE names, if the variable is set (an unreadable file is an error:
#      a typo must not fall back silently). Nothing at this revision passes the variable into the
#      container: scripts/dev-shell.sh does not yet. Set it yourself when you run this script by hand.
#   2. else the file .crux-extra-ca.crt in the workspace folder, the parent folder of the clone (on the
#      host, for example ~/work/controller-ws/.crux-extra-ca.crt; in the container
#      /workspaces/ws/.crux-extra-ca.crt). That folder is already mounted, so this route works for
#      VS Code and for the command line alike.
#   3. else no certificate is installed and the script behaves as before.
# The name of the source is printed, never the contents of the certificate.
# The variables are set for this script only: a terminal that you open later in the container does not
# have them, so pip there needs them again (or a cert entry in a pip.conf). The system bundle itself
# holds the certificate for curl, git and apt.
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
ca_file=""
ca_source=""
if [[ -n "${CRUX_EXTRA_CA_FILE:-}" ]]; then
    ca_file="$CRUX_EXTRA_CA_FILE"
    ca_source="CRUX_EXTRA_CA_FILE"
elif [[ -e "$workspace/.crux-extra-ca.crt" || -L "$workspace/.crux-extra-ca.crt" ]]; then
    ca_file="$workspace/.crux-extra-ca.crt"
    ca_source="the workspace CA file"
fi
if [[ -n "$ca_file" ]]; then
    [[ -f "$ca_file" && -r "$ca_file" ]] \
        || fail "$ca_source is '$ca_file', which is not a readable file."
    grep -q -- '-----BEGIN CERTIFICATE-----' "$ca_file" \
        || fail "$ca_source ($ca_file) is not a PEM certificate (no BEGIN CERTIFICATE line). Convert a DER file (.cer) with: openssl x509 -inform der -in company.cer -out company.crt"
    say "installing $ca_file ($ca_source) as a system certificate"
    sudo install -m 0644 "$ca_file" "$extra_ca_target"
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

# 2b. The optional Mbed TLS group of the S6 job, once per workspace. The order is that of the S6 job
# of .github/workflows/ci.yml: the guard on the default listing, the group on in this workspace only,
# the guard on the group-on listing against the default one, then the fetch. The guard comes first
# because the group also holds the wolf stacks (GPL or commercial), which must never be fetched. The
# marker is written after the fetch, so an interrupted run starts again here; the group is then
# removed first, so that the first guard sees the default workspace again.
step "the Mbed TLS group"
s6_marker="$workspace/.west/crux-devcontainer-s6.done"
if [[ -f "$s6_marker" ]]; then
    say "the Mbed TLS group (crux-secure-management) is already switched on in this workspace."
else
    (
        unset ZEPHYR_BASE
        lists="$workspace/.west/crux-s6-lists"
        rm -rf "$lists"
        mkdir -p "$lists"
        if west config --local manifest.group-filter 2>/dev/null | grep -q 'crux-secure-management'; then
            say "an earlier run left the group on; switching it off for the default check"
            west config --local -d manifest.group-filter
        fi
        say "checking that the default workspace holds no wolf stack (check_mbed_only.py, default mode)"
        west list --all -f '{name} {active}' >"$lists/list-default.txt"
        cat "$lists/list-default.txt"
        python crux-controller/scripts/check_mbed_only.py --mode default <"$lists/list-default.txt"
        say "switching the Mbed TLS group on (crux-secure-management), in this workspace only"
        west config --local manifest.group-filter -- +crux-secure-management
        west list --all -f '{name} {active}' >"$lists/list-mbed.txt"
        cat "$lists/list-mbed.txt"
        python crux-controller/scripts/check_mbed_only.py --mode mbed --baseline "$lists/list-default.txt" <"$lists/list-mbed.txt"
        say "west update (fetches the Mbed TLS modules and nothing else)"
        west update
        rm -rf "$lists"
    )
    touch "$s6_marker"
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
# the marker exists, and the marker is written only after west sdk install returned. The compiler is
# looked for by name (a file or a symbolic link, at most five levels down) only to warn: a layout that
# the search does not know must not make every run delete and fetch several GiB again. An SDK folder
# without the marker is removed first, but only a folder that is named zephyr-sdk-*, is inside the
# cache folder and is reached without a .. component.
step "the Zephyr SDK install"
sdk_marker="$sdk_dir/.crux-installed"
sdk_compiler_present() {
    local found
    found="$(find "$sdk_dir" -maxdepth 5 \( -type f -o -type l \) -perm -100 -name arm-zephyr-eabi-gcc -print 2>/dev/null || true)"
    [[ -n "$found" ]]
}
sdk_removable() {
    local cache_root="${cache%/}"
    [[ "$sdk_dir" == "$cache_root"/* ]] || return 1
    [[ "/$sdk_dir/" != */../* ]] || return 1
    [[ "${sdk_dir%/}" != "$cache_root" ]] || return 1
    [[ "$(basename "$sdk_dir")" == zephyr-sdk-* ]]
}
if [[ ! -f "$sdk_marker" ]]; then
    if [[ -e "$sdk_dir" ]]; then
        sdk_removable \
            || fail "the Zephyr SDK folder $sdk_dir has no install marker, but it is not removed: it must be named zephyr-sdk-*, be inside $cache and contain no .. component. Remove it yourself and run this script again."
        say "$sdk_dir is incomplete (it has no install marker); removing it and installing the SDK again"
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
[[ -f "$sdk_marker" ]] || fail "the Zephyr SDK in $sdk_dir has no install marker after the install"
sdk_compiler_present \
    || say "warning: no arm-zephyr-eabi-gcc found under $sdk_dir (the SDK layout may have changed); a build may fail"

step "the final check"
printf 'setup: workspace %s, Zephyr SDK %s, %s\n' "$workspace" "$sdk_version" "$(west --version)"
