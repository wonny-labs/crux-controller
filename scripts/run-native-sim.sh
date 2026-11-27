#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Build the interactive native_sim configuration of the base image (tests/framework/interactive) and
# run it in this terminal, for development only. The log appears here; HTTPS management listens on
# https://127.0.0.1:8443 of this machine, and the Crux serial console is the pseudo-terminal
# build/native-sim/console. How to use it: docs/native-sim-interactive.md.
#
# Usage: bash scripts/run-native-sim.sh [--no-build] [--reset]
#   --no-build  run the image that was built last
#   --reset     delete the flash file first, with its accounts, settings, key and certificate
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build="$repo/build/native-sim"
page="docs/native-sim-interactive.md"
do_build=1
reset=0

for arg in "$@"; do
    case "$arg" in
        --no-build) do_build=0 ;;
        --reset) reset=1 ;;
        *)
            echo "run-native-sim.sh: unknown option $arg. See $page." >&2
            exit 2
            ;;
    esac
done

cd "$repo"
if ((do_build)); then
    if ! west list --all -f '{name} {active}' 2>/dev/null | grep -qx 'mbedtls True'; then
        echo "run-native-sim.sh: the Mbed TLS modules are not active in this workspace." \
            "Switch the group on as $page says, then run this again." >&2
        exit 1
    fi
    west build -p auto -b native_sim/native/64 -d "$build" "$repo/tests/framework/interactive"
fi

exe="$build/zephyr/zephyr.exe"
if [[ ! -x "$exe" ]]; then
    echo "run-native-sim.sh: no image at $exe. Run this without --no-build. See $page." >&2
    exit 1
fi
if ((reset)); then
    rm -f "$build/flash.bin"
fi

# The simulator's entropy source is a test source that repeats its sequence for the same seed, so each
# run takes a new seed from the host. It matters at the first start, when the key is made and stored.
seed=$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')

cat <<EOF
Starting the base image on native_sim (development only; stop it with Ctrl+C).
  Web management: https://127.0.0.1:8443 (accept the self-signed certificate after comparing
                  its SHA-256 fingerprint with the "certificate sha256=" line below)
  Serial console: in a second terminal,
                  python3 -m serial.tools.miniterm --raw --eol CR build/native-sim/console 115200
                  (Ctrl+] leaves it)
  Store:          build/native-sim/flash.bin (--reset deletes it)
EOF

exec "$exe" --seed="$seed" --flash="$build/flash.bin" \
    --uart_1_attach_uart_cmd="ln -sf %s '$build/console'"
