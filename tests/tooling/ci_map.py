# SPDX-License-Identifier: Apache-2.0
"""Read the CI map file scripts/ci/checks.toml for the tooling tests.

A job of a workflow (and a stage of the Jenkinsfile) calls scripts/ci/run-tier.sh, which runs the
checks of the job of the same name in the map file. The tests that read what a job runs read
those checks. Python 3.11 or later reads the file (tomllib); on an older Python the tests that need
it skip with that reason, and CI runs them on Python 3.12.
"""

import pathlib
import unittest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and older
    tomllib = None

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAP = ROOT / "scripts" / "ci" / "checks.toml"
PREPARE = ROOT / "scripts" / "ci" / "prepare-job.sh"
BUDGET = ROOT / "scripts" / "ci" / "budget.sh"

needs_tomllib = unittest.skipIf(
    tomllib is None, "reading scripts/ci/checks.toml needs Python 3.11 or later (tomllib)")

# The first lines of a check that moves to the west workspace folder and sets ZEPHYR_BASE there.
WORKSPACE_LINES = ("cd ..", 'export ZEPHYR_BASE="$PWD/zephyr"')


def data():
    return tomllib.loads(MAP.read_text())


def checks(job=None):
    """The checks of the map file, or of one job, in run order."""
    return [c for c in data()["check"] if job is None or c["job"] == job]


def check(check_id):
    found = [c for c in data()["check"] if c["id"] == check_id]
    assert len(found) == 1, f"{check_id}: {len(found)} checks"
    return found[0]


def run(check_id):
    return check(check_id)["run"]


def ids(job):
    return [c["id"] for c in checks(job)]


def commands(job):
    """The text of every check of a job, as the tests read the steps of a workflow job."""
    return "\n".join(c["run"] for c in checks(job))


def job_env(job):
    return data()["jobs"][job].get("env", {})


def command(check_id):
    """The command of a check without the lines that move it to the workspace folder.

    A check runs from the repository root; one that ran from the workspace folder as a workflow
    step starts with `cd ..` (and sets ZEPHYR_BASE there). The rest is the step's command.
    """
    lines = run(check_id).splitlines()
    while lines and lines[0] in WORKSPACE_LINES:
        lines.pop(0)
    return "\n".join(lines) + "\n"


def prepare_branch(job):
    """The commands that scripts/ci/prepare-job.sh runs for a job, from its case statement."""
    text = PREPARE.read_text()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.endswith(")") and not stripped.startswith("#"):
            labels = [label.strip() for label in stripped[:-1].split("|") if label.strip() != "*"]
            if job in labels or any(label.endswith("*") and job.startswith(label[:-1]) for label in labels):
                body = []
                for following in lines[index + 1:]:
                    if following.strip() == ";;":
                        break
                    body.append(following)
                return "\n".join(body)
    raise AssertionError(f"scripts/ci/prepare-job.sh has no branch for {job}")


def budget_rows():
    """The Budget configurations in the order of the map file: name -> row.

    A row has the keys config, conf, overlay and require of the job env of budget-<name>, which
    scripts/ci/budget.sh reads, and group "mbed" when a check of the job switches the Mbed TLS
    group on.
    """
    rows = {}
    for job, values in data()["jobs"].items():
        if not job.startswith("budget-"):
            continue
        env = values.get("env", {})
        row = {"config": env["CONFIG"], "conf": env["CONF"], "overlay": env["OVERLAY"],
               "require": env["REQUIRE"]}
        if any("+crux-secure-management" in c["run"] for c in checks(job)):
            row["group"] = "mbed"
        rows[job[len("budget-"):]] = row
    return rows


def ci_sources():
    """The text files of scripts/ci (the map file and its scripts), without the bytecode that
    Python writes there when a test loads scripts/ci/tiers.py."""
    return sorted(p for p in (ROOT / "scripts" / "ci").rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
