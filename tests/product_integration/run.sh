#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The product integration check: the fixture product of this folder imports crux-controller at the
# commit under test into a west workspace of its own, builds for native_sim and runs.
#
#   tests/product_integration/run.sh workspace|build|run|all FOLDER
#
#   workspace  make FOLDER a new west workspace: the fixture as its manifest repository (with the
#              commit of this clone as the revision of crux-controller), a clone of that commit,
#              then west update with the default groups, the project list checked, the Mbed TLS
#              group switched on, the list checked again and west update for the Mbed modules
#   build      build the fixture for native_sim/native/64 with the verified Zephyr gate
#   run        run the image with a time limit and check that every case passed
#   all        the three in order
#
# FOLDER must not exist, be empty, or be a workspace that this script made earlier (it holds the file
# .product-integration); anything else is refused and left alone. The script needs Linux (native_sim),
# git, west, CMake, Ninja, a host C compiler and Python 3 with PyYAML; the workspace step installs the
# Python requirements of Zephyr. It flashes nothing and operates no board. scripts/ci/checks.toml runs
# it as the nightly job product-integration (CONTRIBUTING.md, CI tiers).
set -euo pipefail

usage() {
    printf 'Usage: %s workspace|build|run|all FOLDER\n' "$0" >&2
    exit 2
}

[[ $# -eq 2 ]] || usage
step=$1
case "$step" in
    workspace | build | run | all) ;;
    *) usage ;;
esac
if [[ "$(uname -s)" != Linux && -z "${CRUX_PRODUCT_INTEGRATION_ANY_HOST:-}" ]]; then
    printf 'error: native_sim needs a Linux host. Run this in the Dev Container. See CONTRIBUTING.md#ci-tiers.\n' >&2
    exit 2
fi

fixture=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo=$(git -C "$fixture" rev-parse --show-toplevel)
folder=$2
marker=.product-integration
board=native_sim/native/64
python=${PYTHON:-python3}

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

make_workspace() {
    if [[ -e "$folder" ]]; then
        if [[ -f "$folder/$marker" ]]; then
            rm -rf -- "$folder"
        elif [[ -d "$folder" && -z "$(ls -A "$folder")" ]]; then
            rmdir -- "$folder"
        else
            printf 'error: %s exists and is not a workspace that this script made; it is left alone.\n' "$folder" >&2
            exit 2
        fi
    fi
    local sha
    sha=$(git -C "$repo" rev-parse HEAD)
    mkdir -p "$folder/product"
    : > "$folder/$marker"
    folder=$(cd "$folder" && pwd)
    cp "$fixture/west.yml" "$fixture/CMakeLists.txt" "$fixture/prj.conf" "$fixture/app.overlay" "$folder/product/"
    cp -R "$fixture/src" "$folder/product/src"
    "$python" "$fixture/manifest.py" --revision "$sha" "$folder/product/west.yml"
    # The product is a repository of its own, as a product's manifest repository is.
    git -C "$folder/product" init --quiet
    git -C "$folder/product" add -A
    git -C "$folder/product" -c user.name="product integration" -c user.email="product-integration@localhost" \
        commit --quiet -m "fixture product at crux-controller $sha"

    # The commit under test is cloned before west update, so west finds it in place and does not
    # fetch it: the commit may exist only in this clone. A product fetches it from its remote.
    git clone --quiet --no-checkout "$repo" "$folder/crux-controller"
    git -C "$folder/crux-controller" checkout --quiet --detach "$sha"

    cd "$folder"
    west init -l product
    west update
    west list --all -f '{name} {active}' > list-default.txt
    cat list-default.txt
    "$python" crux-controller/scripts/check_mbed_only.py --mode default < list-default.txt
    west config --local manifest.group-filter -- +crux-secure-management
    west list --all -f '{name} {active}' > list-mbed.txt
    "$python" crux-controller/scripts/check_mbed_only.py --mode mbed --baseline list-default.txt < list-mbed.txt
    west update
    for name in wolfssl wolfssh wolfpsa; do
        [[ ! -e "modules/crypto/$name" ]] || fail "unexpected $name in the workspace"
    done
    for name in mbedtls tf-psa-crypto; do
        [[ -d "modules/crypto/$name" ]] || fail "missing $name in the workspace"
    done
    [[ "$(git -C crux-controller rev-parse HEAD)" == "$sha" ]] || fail "crux-controller is not at $sha"
    "$python" -m pip install --quiet -r zephyr/scripts/requirements-base.txt
    printf 'ok: a new workspace at %s imports crux-controller at %s\n' "$folder" "$sha"
}

need_workspace() {
    [[ -f "$folder/$marker" && -d "$folder/.west" ]] ||
        fail "$folder is not a workspace of this script; run the workspace step first"
    folder=$(cd "$folder" && pwd)
}

build_image() {
    need_workspace
    cd "$folder"
    export ZEPHYR_BASE="$folder/zephyr"
    export ZEPHYR_TOOLCHAIN_VARIANT="${ZEPHYR_TOOLCHAIN_VARIANT:-host}"
    west build -p always -b "$board" -d "$folder/build" product -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON
    local config="$folder/build/zephyr/.config"
    for option in CONFIG_ZEPHYR_CRUX_CONTROLLER_MODULE=y CONFIG_CRUX_CONTROLLER_FRAMEWORK=y \
        CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT=y CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL=y \
        CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC=y; do
        grep -qxF "$option" "$config" || fail "missing $option in the fixture's configuration"
    done
    # The framework comes from the project of the workspace, not from the clone that ran this script.
    grep -qF "$folder/crux-controller" "$folder/build/zephyr_modules.txt" ||
        fail "the module crux-controller is not the project of the workspace"
    printf 'ok: the fixture product builds for %s with the imported framework\n' "$board"
}

run_image() {
    need_workspace
    local log="$folder/run.log"
    timeout -k 10 "${CRUX_PRODUCT_INTEGRATION_TIMEOUT:-300}" "$folder/build/zephyr/zephyr.exe" > "$log" 2>&1 ||
        { tail -40 "$log" >&2; fail 'the image failed, or ran past its time limit'; }
    cat "$log"
    grep -q 'PROJECT EXECUTION SUCCESSFUL' "$log" || fail 'the image did not report success'
    grep -q 'pass = 3, fail = 0' "$log" || fail 'the image did not pass its three cases'
    printf 'ok: the fixture product runs on native_sim. Nothing was flashed and no board was used.\n'
}

case "$step" in
    workspace) make_workspace ;;
    build) build_image ;;
    run) run_image ;;
    all)
        make_workspace
        build_image
        run_image
        ;;
esac
