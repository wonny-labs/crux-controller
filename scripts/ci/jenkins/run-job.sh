#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Jenkins only: install the tools of one job of scripts/ci/checks.toml, prepare its workspace with
# scripts/ci/prepare-job.sh, then run that job's checks of the tier with scripts/ci/run-tier.sh.
# The root Jenkinsfile calls it once per stage; the GitHub workflows set up their runners in their
# own steps with the same pins.
#
#   scripts/ci/jenkins/run-job.sh JOB      (the tier comes from $TIER, default auto)
#
# The repository must be checked out as <workspace>/crux-controller. See CONTRIBUTING.md#ci-tiers.
set -euo pipefail
job=${1:-}
if [[ -z "$job" || $# -ne 1 ]]; then
    printf 'Usage: %s JOB (see scripts/ci/run-tier.sh --list-jobs)\n' "$0" >&2
    exit 2
fi
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$repo"
tier=${TIER:-auto}
# The image names the Zephyr folder of the Dev Container layout; the stage's workspace is elsewhere.
export ZEPHYR_BASE="$(dirname "$repo")/zephyr"

scripts/ci/run-tier.sh "$tier" --job "$job" --plan
if [[ "$(scripts/ci/run-tier.sh "$tier" --job "$job" --count)" == 0 ]]; then
    exit 0
fi

# The Python tools of the dev container, at the versions of the GitHub workflows
# (tests/tooling/test_ci_tiers.py compares them). The Dev container job runs on the agent itself
# and builds the image with scripts/dev-shell.sh.
if [[ "$job" != devcontainer ]]; then
    tools="$(dirname "$repo")/.ci-tools"
    python3 -m venv "$tools"
    "$tools/bin/pip" install --disable-pip-version-check -r .devcontainer/requirements-tools.txt
    export PATH="$tools/bin:$PATH"
fi

# The Boundary job reads the pins of the Crux product include check from the job env of ci.yml on
# GitHub. Without .github/ the data file that a test keeps equal to it gives them.
if [[ "$job" == boundary ]]; then
    eval "$(python3 - <<'PY'
import json, shlex
pins = json.load(open("scripts/include-check-pins.json"))
checker = pins["files"]["templates/product/check_domain_includes.py"]
wrapper = pins["files"]["templates/product/style/check-includes.sh"]
for key, value in (("CHECK_COMMIT", pins["commit"]), ("CHECK_SHA256", checker),
                   ("KIT_COMMIT", pins["commit"]), ("CHECKER_SHA256", checker),
                   ("WRAPPER_SHA256", wrapper)):
    print(f"export {key}={shlex.quote(value)}")
PY
)"
fi

scripts/ci/prepare-job.sh "$job"
exec scripts/ci/run-tier.sh "$tier" --job "$job"
