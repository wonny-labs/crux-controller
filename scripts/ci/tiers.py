#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Plan and run one CI tier from scripts/ci/checks.toml.

This is the selector of Crux (crux-pilot scripts/ci/tiers.py at be60bc65), copied unchanged except
for the names of this repository's documentation. Use it through scripts/ci/run-tier.sh;
CONTRIBUTING.md (section "CI tiers") and the Crux CI page linked there describe the tiers, the
selection rules and the options. The same code decides on every CI system: it reads plain git and environment values,
never a CI service's API. Only the standard library is used (Python 3.11 or later).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
import xml.etree.ElementTree as ET

TIERS = ("fast", "full", "nightly")
DOC = "CONTRIBUTING.md#ci-tiers"
CHECK_KEYS = {"id", "job", "run", "scope", "fast", "tiers", "advisory"}
JOB_KEYS = {"description", "env"}
ZERO_SHA = re.compile(r"^0+$")


class ManifestError(Exception):
    """The map file breaks a rule of the map file format."""


class UsageError(Exception):
    """The command line asks for something the map file does not have."""


@dataclass(frozen=True, eq=False)
class Check:
    id: str
    job: str
    run: str
    scope: str | list
    fast: str | list | None
    tiers: tuple
    advisory: bool


@dataclass
class Manifest:
    docs: list
    escalate: list
    max_components: int
    components: dict
    scopes: dict
    jobs: dict
    checks: list


@dataclass
class Plan:
    tier: str
    checks: list
    fallback: bool = False
    reason: str = ""


@dataclass
class Change:
    files: list | None
    diff_base: str | None = None
    note: str = ""


# --- patterns -----------------------------------------------------------------------------------

def _pattern_regex(pattern):
    """Translate a workflow path filter pattern: ** crosses folders, * and ? do not."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def matches(path, patterns):
    """True when the last pattern that matches the path is not a negation (`!`)."""
    result = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        if _pattern_regex(pattern[1:] if negated else pattern).match(path):
            result = not negated
    return result


def is_docs_only(files, docs):
    return bool(files) and all(matches(path, docs) for path in files)


# --- the map file -------------------------------------------------------------------------------

def load_manifest(path):
    try:
        data = tomllib.loads(Path(path).read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ManifestError(f"cannot read {path}: {error}") from error
    if data.get("version") != 1:
        raise ManifestError("version must be 1")
    selection = data.get("selection", {})
    components = data.get("components", {})
    scopes = data.get("scopes", {})
    jobs = data.get("jobs", {})
    for name, job in jobs.items():
        unknown = set(job) - JOB_KEYS
        if unknown:
            raise ManifestError(f"job {name}: unknown key {sorted(unknown)[0]}")
    checks, seen = [], set()
    for raw in data.get("check", []):
        name = raw.get("id", "?")
        unknown = set(raw) - CHECK_KEYS
        if unknown:
            raise ManifestError(f"check {name}: unknown key {sorted(unknown)[0]}")
        for key in ("id", "job", "run"):
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                raise ManifestError(f"check {name}: {key} must be a non-empty string")
        if name in seen:
            raise ManifestError(f"check {name}: duplicate id")
        seen.add(name)
        if raw["job"] not in jobs:
            raise ManifestError(f"check {name}: unknown job {raw['job']}")
        scope = raw.get("scope", "code")
        if scope not in ("code", "always") and scope not in scopes:
            raise ManifestError(f"check {name}: unknown scope {scope}")
        check_tiers = tuple(raw.get("tiers", ["full"]))
        if not check_tiers or any(t not in ("full", "nightly") for t in check_tiers):
            raise ManifestError(f"check {name}: tiers may list only full and nightly")
        fast = raw.get("fast")
        if fast is not None:
            if "full" not in check_tiers:
                raise ManifestError(f"check {name}: fast needs the check in the full tier")
            if isinstance(fast, list):
                missing = [c for c in fast if c not in components]
                if missing:
                    raise ManifestError(f"check {name}: unknown component {missing[0]}")
            elif fast != "always":
                raise ManifestError(f"check {name}: fast must be \"always\" or a list of components")
        checks.append(Check(name, raw["job"], raw["run"], scopes.get(scope, scope), fast, check_tiers,
                            bool(raw.get("advisory", False))))
    empty = [name for name in jobs if not any(c.job == name for c in checks)]
    if empty:
        raise ManifestError(f"job {empty[0]} has no checks")
    return Manifest(list(selection.get("docs", [])), list(selection.get("escalate", [])),
                    int(selection.get("max_components", 3)), components, scopes, jobs, checks)


# --- selection ----------------------------------------------------------------------------------

# The events of a change under development. Only these apply the documentation-only rule of the
# `code` scope; a post-merge, scheduled or manual run keeps every `code` check.
DEVELOPMENT_EVENTS = ("change-request", "branch", "local")


def _in_scope(check, files, docs_only):
    if files is None or check.scope == "always":
        return True
    if check.scope == "code":
        return not docs_only
    return any(matches(path, check.scope) for path in files)


def _full(manifest, files, event):
    docs_only = files is not None and event in DEVELOPMENT_EVENTS and is_docs_only(files, manifest.docs)
    return [c for c in manifest.checks if "full" in c.tiers and _in_scope(c, files, docs_only)]


def _unsure(manifest, files):
    """Return why a fast run cannot trust its selection, or an empty string."""
    if files is None:
        return "the change is unknown"
    if not files:
        return "the change is empty"
    touched = set()
    for path in files:
        if matches(path, manifest.escalate):
            return f"{path} is a build, CI, script or shared file"
        owners = [name for name, patterns in manifest.components.items() if matches(path, patterns)]
        if owners:
            touched.update(owners)
        elif not matches(path, manifest.docs):
            return f"{path} belongs to no component"
    if len(touched) > manifest.max_components:
        return f"{len(touched)} components changed, more than {manifest.max_components}"
    return ""


def components_of(manifest, files):
    return {name for path in files for name, patterns in manifest.components.items() if matches(path, patterns)}


def plan(manifest, tier, files, event="change-request"):
    """Select the checks of a tier for a change (a list of paths, or None when unknown).

    `event` is the CI event of ci_context(); the documentation-only rule of the `code` scope
    applies only to the events in DEVELOPMENT_EVENTS.
    """
    if tier == "nightly":
        return Plan(tier, [c for c in manifest.checks])
    full = _full(manifest, files, event)
    if tier == "full":
        return Plan(tier, full)
    reason = _unsure(manifest, files)
    if reason:
        return Plan(tier, full, fallback=True, reason=reason)
    touched = components_of(manifest, files)
    chosen = [c for c in full if c.fast == "always" or (isinstance(c.fast, list) and touched & set(c.fast))]
    return Plan(tier, chosen)


# --- the change ---------------------------------------------------------------------------------

def _git(root, *arguments):
    return subprocess.run(["git", *arguments], cwd=root, capture_output=True, text=True, check=False)


def _resolve(root, base):
    if _git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode == 0:
        return base
    if base.startswith("origin/"):
        branch = base[len("origin/"):]
        _git(root, "fetch", "--no-tags", "--quiet", "origin", f"+refs/heads/{branch}:refs/remotes/{base}")
    else:
        _git(root, "fetch", "--no-tags", "--quiet", "origin", base)
    if _git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode == 0:
        return base
    return None


def changed_files(root, base):
    """List the files a change touches, against the merge base with `base` when history allows.

    Without a merge base the plain tree comparison is used, which can only list more files.
    Renames count as a deletion and an addition, so a file moved into the documentation still
    counts as a code change.
    """
    if not base or ZERO_SHA.match(base):
        return Change(None, note="no comparison base")
    resolved = _resolve(root, base)
    if resolved is None:
        return Change(None, note=f"comparison base {base} not found")
    merge_base = _git(root, "merge-base", resolved, "HEAD")
    diff_base = merge_base.stdout.strip() if merge_base.returncode == 0 else resolved
    result = _git(root, "diff", "--name-only", "--no-renames", diff_base, "HEAD")
    if result.returncode != 0:
        return Change(None, note=f"git diff against {base} failed")
    files = sorted(line for line in result.stdout.splitlines() if line)
    return Change(files, _git(root, "rev-parse", diff_base).stdout.strip())


# --- the CI system ------------------------------------------------------------------------------

def ci_context(env):
    """Return (tier, base, event) for `auto` from the environment of GitHub Actions or Jenkins."""
    default = env.get("CRUX_CI_DEFAULT_BRANCH", "main")
    if env.get("GITHUB_ACTIONS") == "true":
        event = {}
        if env.get("GITHUB_EVENT_PATH"):
            try:
                event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text())
            except (OSError, ValueError):
                event = {}
        name = env.get("GITHUB_EVENT_NAME", "")
        default = event.get("repository", {}).get("default_branch") or default
        if name == "schedule":
            return "nightly", None, "scheduled"
        if name == "pull_request":
            draft = bool(event.get("pull_request", {}).get("draft"))
            return ("fast" if draft else "full"), f"origin/{env.get('GITHUB_BASE_REF', default)}", "change-request"
        if name == "merge_group":
            return "full", event.get("merge_group", {}).get("base_sha"), "merge-queue"
        if name == "push":
            if env.get("GITHUB_REF") == f"refs/heads/{default}":
                before = event.get("before") or ""
                return "full", (None if not before or ZERO_SHA.match(before) else before), "post-merge"
            return "fast", f"origin/{default}", "branch"
        return "full", None, "manual"
    if env.get("JENKINS_URL"):
        if env.get("CRUX_CI_TRIGGER") == "timer":
            return "nightly", None, "scheduled"
        if env.get("CHANGE_ID"):
            return "full", f"origin/{env.get('CHANGE_TARGET', default)}", "change-request"
        if env.get("BRANCH_NAME") == default:
            previous = env.get("GIT_PREVIOUS_SUCCESSFUL_COMMIT")
            # The first build of the branch has nothing to compare with; it runs every check.
            return ("full", previous, "post-merge") if previous else ("full", None, "first-build")
        return "fast", f"origin/{default}", "branch"
    return "fast", f"origin/{default}", "local"


# --- running ------------------------------------------------------------------------------------

def _banner(title, github):
    if github:
        print(f"::group::{title}", flush=True)
    else:
        print(f"==> {title}", flush=True)


def _end_banner(github):
    if github:
        print("::endgroup::", flush=True)


def _run_check(check, root, env, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        process = subprocess.Popen(["bash", "-eo", "pipefail", "-c", check.run], cwd=root, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for raw in process.stdout:
            line = raw.decode("utf-8", errors="replace")
            sys.stdout.write(line)
            log.write(line)
        sys.stdout.flush()
        code = process.wait()
    return code, time.monotonic() - started


def _write_junit(path, job, results):
    suites = ET.Element("testsuites")
    failures = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    suite = ET.SubElement(suites, "testsuite", name=f"crux-ci.{job}", tests=str(len(results)),
                          failures=str(failures), skipped=str(skipped),
                          time=f"{sum(r['time'] for r in results):.1f}")
    for r in results:
        case = ET.SubElement(suite, "testcase", classname=f"crux-ci.{job}", name=r["id"], time=f"{r['time']:.1f}")
        if r["status"] == "failed":
            ET.SubElement(case, "failure", message=f"exit {r['code']}").text = f"log: {r['log']}"
        elif r["status"] == "skipped":
            ET.SubElement(case, "skipped", message="not run: an earlier check failed")
        elif r["status"] == "warning":
            ET.SubElement(case, "system-out").text = f"advisory check failed (exit {r['code']}); log: {r['log']}"
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suites).write(path, encoding="utf-8", xml_declaration=True)


def run_job(manifest, job, checks, root, tier, change, event, rerun):
    github = os.environ.get("GITHUB_ACTIONS") == "true"
    env = dict(os.environ)
    for key, value in manifest.jobs[job].get("env", {}).items():
        env.setdefault(key, value)
    env.update({"CRUX_CI_TIER": tier, "CRUX_CI_EVENT": event, "CRUX_CI_JOB": job})
    if change.diff_base:
        env["CRUX_CI_DIFF_BASE"] = change.diff_base
    else:
        env.pop("CRUX_CI_DIFF_BASE", None)
    results, failed = [], None
    for check in checks:
        log_path = root / "build/ci/logs" / job / f"{check.id}.log"
        relative = log_path.relative_to(root)
        if failed and not check.advisory:
            results.append({"id": check.id, "status": "skipped", "time": 0.0, "code": None, "log": relative})
            continue
        _banner(f"{job}: {check.id}", github)
        code, seconds = _run_check(check, root, env, log_path)
        _end_banner(github)
        status = "passed" if code == 0 else ("warning" if check.advisory else "failed")
        results.append({"id": check.id, "status": status, "time": seconds, "code": code, "log": relative})
        print(f"--- {check.id}: {status} in {seconds / 60:.1f} min", flush=True)
        if status == "warning":
            print(f"warning: advisory check {check.id} failed (exit {code}); the job continues. "
                  f"Log: {relative}", file=sys.stderr)
        elif status == "failed" and failed is None:
            failed = (check, code)
    _write_junit(root / "build/ci" / f"{job}.junit.xml", job, results)
    if failed:
        check, code = failed
        print(f"error: CI check {check.id} failed (exit {code}). "
              f"Rerun it: {rerun} --job {job} --check {check.id}. See {DOC}", file=sys.stderr)
        return 1
    return 0


# --- command line -------------------------------------------------------------------------------

def _parser():
    parser = argparse.ArgumentParser(prog="scripts/ci/run-tier.sh",
                                     description=f"Run one CI tier. See {DOC}.")
    parser.add_argument("tier", help="fast, full, nightly, or auto (decided from the CI environment)")
    parser.add_argument("--job", action="append", default=[], help="run only this job (repeatable)")
    parser.add_argument("--check", action="append", default=[], help="run only this check, selected or not")
    parser.add_argument("--base", help="compare the change with this ref or commit")
    parser.add_argument("--plan", action="store_true", help="print the selection and run nothing")
    parser.add_argument("--count", action="store_true", help="print how many checks would run")
    parser.add_argument("--list-jobs", action="store_true", help="print the job names")
    parser.add_argument("--manifest", help=argparse.SUPPRESS)
    parser.add_argument("--root", help=argparse.SUPPRESS)
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    root = Path(args.root or Path(__file__).resolve().parents[2])
    manifest_path = Path(args.manifest or root / "scripts/ci/checks.toml")
    try:
        manifest = load_manifest(manifest_path)
        if args.list_jobs:
            print("\n".join(manifest.jobs))
            return 0
        auto_tier, auto_base, event = ci_context(os.environ)
        tier = auto_tier if args.tier == "auto" else args.tier
        if tier not in TIERS:
            raise UsageError(f"unknown tier {args.tier}: use fast, full, nightly or auto")
        unknown_jobs = [j for j in args.job if j not in manifest.jobs]
        if unknown_jobs:
            raise UsageError(f"unknown job {unknown_jobs[0]}: see --list-jobs")
        known = {c.id for c in manifest.checks}
        unknown_checks = [c for c in args.check if c not in known]
        if unknown_checks:
            raise UsageError(f"unknown check {unknown_checks[0]}: see scripts/ci/checks.toml")
        base = args.base if args.base is not None else os.environ.get("CRUX_CI_BASE") or auto_base
        change = Change(None, note="nightly runs every check") if tier == "nightly" else changed_files(root, base)
        if args.check:
            selected = Plan(tier, [c for c in manifest.checks if c.id in args.check])
        else:
            selected = plan(manifest, tier, change.files, event)
        jobs = args.job or list(manifest.jobs)
        checks = [c for c in selected.checks if c.job in jobs]
    except (ManifestError, UsageError) as error:
        print(f"error: {error}. See {DOC}.", file=sys.stderr)
        return 2
    if args.count:
        print(len(checks))
        return 0
    header = f"Tier {tier} ({event})"
    if change.files is not None:
        header += f": {len(change.files)} changed files since {change.diff_base[:12] if change.diff_base else base}"
    elif change.note:
        header += f": {change.note}"
    print(header)
    if selected.fallback:
        print(f"Falling back to the full tier: {selected.reason}.")
    if args.plan:
        for check in checks:
            print(f"{check.job}: {check.id}")
        return 0
    if not checks:
        print("No checks selected.")
        return 0
    status = 0
    rerun = f"scripts/ci/run-tier.sh {tier}"
    for job in jobs:
        job_checks = [c for c in checks if c.job == job]
        if not job_checks:
            continue
        status = max(status, run_job(manifest, job, job_checks, root, tier, change, event, rerun))
    return status


if __name__ == "__main__":
    sys.exit(main())
