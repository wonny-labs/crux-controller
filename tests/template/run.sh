#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The application template check (criterion 47): a copy of template/ joins a west workspace of its
# own with the framework at the commit under test, builds and runs on native_sim, runs its first
# test, and builds for the reference board.
#
#   tests/template/run.sh workspace|build|run|test|board|all FOLDER
#
#   workspace  make FOLDER a new west workspace by the joining steps of template/README.md: a copy of
#              template/ as the manifest repository, pinned by scripts/pin_framework.py at the commit
#              of this clone, a clone of that commit, west init and west update (with
#              CRUX_TEMPLATE_WEST_CACHE as west's --path-cache when it is set); then the resolved
#              project list (the Mbed modules active, no wolf project), the framework's commit, the
#              template checks of the copy, and the Python requirements of Zephyr and Twister
#   build      build the copy for native_sim/native/64 with the verified Zephyr gate
#   run        run the image until a simulated time limit and check that the log shows the init and
#              start entries of the template's descriptor, in that order
#   test       run the copy's first test with Twister on native_sim
#   board      build the copy for the reference board (CRUX_TEMPLATE_BOARD, by default
#              mimxrt1060_evk@B/mimxrt1062/qspi) with the Zephyr SDK and the verified Zephyr gate
#   all        workspace, build, run and test in order
#
# FOLDER must not exist, be empty, or be a workspace that this script made earlier (it holds the file
# .template-workspace); anything else is refused and left alone. The script needs Linux (native_sim),
# git, west, CMake, Ninja, a host C compiler and Python 3 with PyYAML, and the Zephyr SDK for the
# board step. It flashes nothing and operates no board. scripts/ci/checks.toml runs it in the nightly
# jobs template (native_sim) and base (the board build); CONTRIBUTING.md, CI tiers.
set -euo pipefail

usage() {
    printf 'Usage: %s workspace|build|run|test|board|all FOLDER\n' "$0" >&2
    exit 2
}

[[ $# -eq 2 ]] || usage
step=$1
case "$step" in
    workspace | build | run | test | board | all) ;;
    *) usage ;;
esac
if [[ "$(uname -s)" != Linux && -z "${CRUX_TEMPLATE_ANY_HOST:-}" ]]; then
    printf 'error: native_sim needs a Linux host. Run this in the Dev Container. See CONTRIBUTING.md#ci-tiers.\n' >&2
    exit 2
fi

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo=$(git -C "$here" rev-parse --show-toplevel)
folder=$2
# An absolute folder below the root only: an empty value or / would put the workspace in the wrong place.
if [[ "$folder" != /?* || "$folder" == / || "$folder" =~ ^/+$ ]]; then
    printf 'error: FOLDER must be an absolute path below /, and it is %s\n' "${folder:-empty}" >&2
    exit 2
fi
marker=.template-workspace
native=native_sim/native/64
board=${CRUX_TEMPLATE_BOARD:-mimxrt1060_evk@B/mimxrt1062/qspi}
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
    mkdir -p "$folder"
    : > "$folder/$marker"
    folder=$(cd "$folder" && pwd)

    # The joining steps of template/README.md, with the clone of this check as the framework.
    cp -R "$repo/template" "$folder/product"
    "$python" "$repo/scripts/pin_framework.py" --framework "$repo" "$folder/product/west.yml"
    git -C "$folder/product" init --quiet
    git -C "$folder/product" add .
    git -C "$folder/product" -c user.name="template check" -c user.email="template-check@localhost" \
        commit --quiet -m "feat: start the product from the controller framework template"

    # The commit under test is cloned before west update, so west finds it in place and does not
    # fetch it: the commit may exist only in this clone. A product fetches it from its remote.
    git clone --quiet --no-checkout "$repo" "$folder/crux-controller"
    git -C "$folder/crux-controller" checkout --quiet --detach "$sha"

    cd "$folder"
    west init -l product
    if [[ -n "${CRUX_TEMPLATE_WEST_CACHE:-}" ]]; then
        west update --path-cache "$CRUX_TEMPLATE_WEST_CACHE"
    else
        west update
    fi
    # The copy's manifest switches the Mbed TLS group on; the framework's import keeps the wolf
    # projects out of the resolved manifest.
    west list --all -f '{name} {active}' > list.txt
    cat list.txt
    "$python" crux-controller/scripts/check_mbed_only.py --mode mbed < list.txt
    for name in wolfssl wolfssh wolfpsa; do
        [[ ! -e "modules/crypto/$name" ]] || fail "unexpected $name in the workspace"
    done
    for name in mbedtls tf-psa-crypto; do
        [[ -d "modules/crypto/$name" ]] || fail "missing $name in the workspace"
    done
    [[ "$(git -C crux-controller rev-parse HEAD)" == "$sha" ]] || fail "crux-controller is not at $sha"
    [[ "$(west list crux-controller -f '{sha}')" == "$sha" ]] || fail "west does not resolve crux-controller at $sha"
    "$python" "$repo/scripts/check_template.py" --root "$folder/product"
    "$python" -m pip install --quiet -r zephyr/scripts/requirements-base.txt \
        -r zephyr/scripts/requirements-build-test.txt -r zephyr/scripts/requirements-run-test.txt
    printf 'ok: a copy of the template at %s imports crux-controller at %s\n' "$folder/product" "$sha"
}

need_workspace() {
    [[ -f "$folder/$marker" && -d "$folder/.west" ]] ||
        fail "$folder is not a workspace of this script; run the workspace step first"
    folder=$(cd "$folder" && pwd)
    cd "$folder"
    export ZEPHYR_BASE="$folder/zephyr"
}

require_options() {
    local config=$1
    shift
    for option in "$@"; do
        grep -qxF "$option" "$config" || fail "missing $option in the configuration of the copy"
    done
}

refuse_options() {
    local config=$1
    shift
    for option in "$@"; do
        ! grep -qxF "$option" "$config" || fail "unexpected $option in the configuration of the copy"
    done
}

build_native() {
    need_workspace
    export ZEPHYR_TOOLCHAIN_VARIANT="${ZEPHYR_TOOLCHAIN_VARIANT:-host}"
    west build -p always -b "$native" -d "$folder/build/native_sim" product/app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON
    local config="$folder/build/native_sim/zephyr/.config"
    require_options "$config" CONFIG_ZEPHYR_CRUX_CONTROLLER_MODULE=y CONFIG_CRUX_CONTROLLER_FRAMEWORK=y \
        CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION=y CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT=y \
        CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL=y CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC=y
    # The framework comes from the project of the workspace, not from the clone that ran this script.
    grep -qF "$folder/crux-controller" "$folder/build/native_sim/zephyr_modules.txt" ||
        fail "the module crux-controller is not the project of the workspace"
    printf 'ok: the copy of the template builds for %s with the imported framework\n' "$native"
}

run_native() {
    need_workspace
    local log="$folder/run.log"
    # --stop_at ends the simulation at that simulated time with exit status 0 (native_sim's timer
    # model); timeout guards the host time.
    timeout -k 10 "${CRUX_TEMPLATE_TIMEOUT:-300}" "$folder/build/native_sim/zephyr/zephyr.exe" \
        --stop_at="${CRUX_TEMPLATE_STOP_AT:-30}" > "$log" 2>&1 ||
        { tail -40 "$log" >&2; fail 'the image failed, or ran past its time limit'; }
    cat "$log"
    local init start
    init=$(grep -n 'product: init' "$log" | head -n 1 | cut -d: -f1)
    start=$(grep -n 'product: start' "$log" | head -n 1 | cut -d: -f1)
    [[ -n "$init" ]] || fail 'the log does not show the init entry of the template'
    [[ -n "$start" ]] || fail 'the log does not show the start entry of the template'
    ((init < start)) || fail 'the log shows start before init'
    printf 'ok: the copy of the template runs on native_sim; init and start ran. Nothing was flashed.\n'
}

test_native() {
    need_workspace
    export ZEPHYR_TOOLCHAIN_VARIANT="${ZEPHYR_TOOLCHAIN_VARIANT:-host}"
    west twister -T product/app -p "$native" -O "$folder/twister-out" --inline-logs \
        -x=CRUX_REQUIRE_VERIFIED_ZEPHYR=ON
    printf 'ok: the first test of the copy passes on native_sim\n'
}

build_board() {
    need_workspace
    west build -p always -b "$board" -d "$folder/build/board" product/app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON
    local build="$folder/build/board/zephyr"
    for output in zephyr.bin zephyr.elf; do
        [[ -f "$build/$output" ]] || fail "missing $output"
    done
    require_options "$build/.config" CONFIG_ZEPHYR_CRUX_CONTROLLER_MODULE=y CONFIG_CRUX_CONTROLLER_FRAMEWORK=y \
        CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION=y CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT=y \
        CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL=y CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC=y \
        CONFIG_STACK_CANARIES=y CONFIG_HW_STACK_PROTECTION=y CONFIG_RETENTION=y
    # The board files are no development build: no start without a watchdog, no test entropy, no
    # shell and no task watchdog hardware fallback (criteria 19 and 38 for these options).
    refuse_options "$build/.config" CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG=y \
        CONFIG_FAKE_ENTROPY_NATIVE_SIM=y CONFIG_TEST_RANDOM_GENERATOR=y CONFIG_SHELL=y \
        CONFIG_TASK_WDT_HW_FALLBACK=y CONFIG_CRUX_DEVELOPMENT_IMAGE=y CONFIG_CRUX_WEB_PLAIN_HTTP_FOR_TESTS=y
    for node in crux-watchdog0 controller_storage controller_retained; do
        grep -q "$node" "$build/zephyr.dts" || fail "no $node in the devicetree of the copy"
    done
    printf 'ok: the copy of the template builds for %s. No flash, reset or hardware command was run.\n' "$board"
}

case "$step" in
    workspace) make_workspace ;;
    build) build_native ;;
    run) run_native ;;
    test) test_native ;;
    board) build_board ;;
    all)
        make_workspace
        build_native
        run_native
        test_native
        ;;
esac
