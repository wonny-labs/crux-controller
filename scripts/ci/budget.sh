#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The Budget check of one build configuration: build it with the Zephyr baseline gate required,
# check that the configuration is what was built, then collect its static resource use, check it
# against budgets/limits.json and summarise it. It publishes the numbers as a job summary only (on
# GitHub; elsewhere in the log). No image, ELF or map file is uploaded, because the repository
# publishes hashes only.
#
# The job env of the Budget jobs in scripts/ci/checks.toml gives BOARD, CONFIG (the configuration
# name), CONF (the fragments), OVERLAY (the overlays) and REQUIRE (the options that the build must
# have resolved). It runs in the west workspace folder, beside the clone crux-controller.
set -eo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
export ZEPHYR_BASE="$PWD/zephyr"
: "${BOARD:?}" "${CONFIG:?}"

# Build the configuration with the baseline gate required.
build="crux-controller/build/$CONFIG"
mkdir -p "$build/budget"
args=(-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON)
if [ -n "$CONF" ]; then args+=("-DEXTRA_CONF_FILE=$CONF"); fi
if [ -n "$OVERLAY" ]; then args+=("-DEXTRA_DTC_OVERLAY_FILE=$OVERLAY"); fi
west build -p always -b "$BOARD" -d "$build" crux-controller/app -- \
  "${args[@]}" 2>&1 | tee "$build/budget/build.log"
west build -d "$build" -t rom_report > "$build/budget/rom_report.log" 2>&1
west build -d "$build" -t ram_report > "$build/budget/ram_report.log" 2>&1

# Check that the configuration is what was built.
# An unmet Kconfig dependency only warns, so an image could build without the capability.
for option in $REQUIRE; do
  grep -qxF "$option" "crux-controller/build/$CONFIG/zephyr/.config" || {
    echo "missing $option: the capability was not built" >&2
    exit 1
  }
done

# Collect, check and summarise.
python crux-controller/budgets/collect.py --build-dir "$build" \
  --config "$CONFIG" --out measurement.json
{
  echo "### $CONFIG"
  python - <<'PY'
import json, sys
sys.path.insert(0, "crux-controller/budgets")
import check
print(check.table(json.load(open("measurement.json"))))
PY
  echo '```json'
  cat measurement.json
  echo '```'
  echo "Run-time values (stack use, heap peaks, timing) are not measured."
} >> "${GITHUB_STEP_SUMMARY:-/dev/stdout}"
python crux-controller/budgets/check.py --measurement measurement.json \
  --limits crux-controller/budgets/limits.json
