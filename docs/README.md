# Documentation map

This page finds the right page for what you want to do. Start at the [repository README](../README.md) for what
the repository is and the quick start, the [Tutorial](tutorial.md). The pages follow the documentation guidelines
of Crux: each page has one type (entry, tutorial, how-to guide, reference, explanation, record or history), says
what is true at the revision you read, and links to the one page that owns a fact. The type of each page is in
[All documents](#all-documents). Reading times assume about 250 words a minute; a page with commands takes longer
to follow.

## Paths by task

### I want to run it

The [Tutorial](tutorial.md) first. Then [Getting started](try-on-native-sim.md) for the setup details,
[troubleshooting.md](troubleshooting.md) for a failure, and [board-bring-up.md](board-bring-up.md) for a board (untested
on hardware, and it needs the owner's authorisation).

### I want to change code

[first-change.md](first-change.md), then [CONTRIBUTING.md](../CONTRIBUTING.md). [architecture.md](architecture.md) says
which directory holds what; [composition-zone.md](composition-zone.md) explains a failed boundary check.

### I want to add a step

[adding-a-step.md](adding-a-step.md), with [findings/s4-system-composition.md](findings/s4-system-composition.md) as a
worked example and [architecture.md](architecture.md) for the zones and port headers.

### I want to review

[reviewing.md](reviewing.md), the three verdicts in [CONTRIBUTING.md](../CONTRIBUTING.md#review), and the
[files that need a reviewed change](adding-a-step.md#files-that-need-a-reviewed-change).

### I want to know why

The [findings](findings/README.md), the [roadmap](roadmap.md), [why a zone](composition-zone.md#why-a-zone) and the
[history](history/README.md).

## Where decisions are recorded

- **Rules for working here** (what a change must satisfy, what needs the owner's approval): `CONTRIBUTING.md`.
  `RELEASE.md` covers tags and releases, and `SECURITY.md` covers vulnerability reports. CONTRIBUTING.md does not
  say where the owner's approval of a merge is recorded.
- **Boundary rules and the reason for each allow-list entry**: [composition-zone.md](composition-zone.md). The lists
  themselves are in `scripts/check_boundary.py`.
- **What each step taught, and the decisions taken in it**: the notes in `docs/findings/` ([index](findings/README.md)). They are kept
  as written, and each names the revision of Crux that it was read at. A later result is added as an update.
- **What exists, what ran on a board and what is not possible**: [roadmap.md](roadmap.md). Its "not yet possible" rows
  are recorded positions, not plans.
- **The pinned Crux revision**: the `revision` in `west.yml`. The comment above it and `tests/tooling/test_manifest.py`
  record the approved commit, and [CHANGELOG.md](../CHANGELOG.md) records each move.
- **Tracking**: the issues and pull requests of the public repository. Their open or closed state can lag behind the
  code. The documents and the CI checks of a commit are the reference. How the steps were tracked is in
  [history](history/board-runs-and-tracking.md).

## Known limits, not scheduled

These are known limits of what the checks and tests cover. They are facts about the files today, not a plan.
[CONTRIBUTING.md](../CONTRIBUTING.md#static-analysis-and-coding-standard) states the analysis position.

- **clang-tidy covers part of the code.** It runs over the 12 sources that the host tests build. That is 7 of the 17
  production C files in `app/` and `workload/` (the other 5 of the 12 are test files). The other production files need
  Zephyr or Crux headers or Kconfig values. `scripts/analyze_host.py` prints the sources that it did not analyse, and
  the list is printed but does not fail the job.
- **The naming check enforces nothing.** `readability-identifier-naming` is listed without options and enforces no
  naming rule (`.clang-tidy`).
- **Other languages are not linted.** There is no lint for Python, shell, YAML or CMake, and no coverage measurement.
- **Many tooling tests pin text.** Counted by module (every test of a module counts the same, counted once when this entry was written and not recounted since), the tests in `tests/tooling` that read the repository's
  documents, workflows, CMake and Kconfig files as text, and run no script on synthetic input, are between about 50
  and 70 percent of all of them. The upper figure counts three modules that mix both kinds. This is an estimate of tests per module, not of modules. A
  green tooling run shows that the text and the configuration agree with the tests, and not that the firmware
  behaves.
- **Parts of the Zephyr-side glue are not run by any test.** The start order and the decisions in `app/src/composition.c`, the
  watchdog feed path of step S4 (the S4 scenario cannot show a feed cycle) and the web page script of step S6 (the S6
  scenario serves its bytes, and nothing runs them) are never run in any test.
- **Steps S5 and S6 run only on `native_sim`, in CI, and never on a board.** Step S2 ran twice on a board, on one bench.
  Nothing else has run on a board ([roadmap](roadmap.md#what-has-run-on-a-board)).
- **The Dev Container and WSL2 were not tried by anyone.** The Dev Container was not started on a developer machine, so
  WSL2, Docker Engine in WSL2 and the proxy settings of `devcontainer.json` have not run there. The Dev Container job
  of CI covers an x86_64 runner only ([setup checks record](history/setup-checks.md)).
- **The board container and the board route are untested.** Nobody has built the optional board container in
  `.devcontainer/board/`, CI does not build it, and no step of the [board route](board-bring-up.md) has run on a board.

## All documents

### In `docs/`

| Document | Type | What it is | Reading time |
|---|---|---|---|
| [architecture.md](architecture.md) | Explanation | How the repository is built: the four source trees and their include rules, how Crux is consumed, the threads in the image and a map of the files. | 12 min |
| [roadmap.md](roadmap.md) | Reference (status) | What exists on `main`, the static size per step, what has run on a board and what is not yet possible. It promises no dates. | 11 min |
| [tutorial.md](tutorial.md) | Tutorial | The first build and run for a new team member on Linux or WSL2: clone, Dev Container, one build, the `native_sim` scenarios, host tests, tooling tests and the boundary check, with the times of the CI job. | 5 min |
| [try-on-native-sim.md](try-on-native-sim.md) | Entry (Getting started) | Getting started: setting up the Dev Container or the native route without a board, proxies and certificates, the workspace layout, and every test command with what CI checks. | 26 min |
| [troubleshooting.md](troubleshooting.md) | Reference | Look a failure up by its message: the cause, the fix and the page that explains more. | 11 min |
| [first-change.md](first-change.md) | Tutorial | A tutorial from branch to pull request with one small host-test change that needs no Zephyr. | 6 min |
| [adding-a-step.md](adding-a-step.md) | How-to guide | The recipe for adding a step, its checklist, the rule for drivers and HAL, and the files that need a reviewed change. | 16 min |
| [reviewing.md](reviewing.md) | Explanation (review guide) | A checklist for the reviewer, from CONTRIBUTING.md and from the repository's practice. | 9 min |
| [composition-zone.md](composition-zone.md) | Reference | The include rules in detail: the composition zone and the adapter zone, each allowed Zephyr header and why, the frozen Crux headers, and how to run the check. | 11 min |
| [glossary.md](glossary.md) | Reference | The words that this repository uses in a particular sense (step, stage, product, owner, composition, zones, pin, finding and more), with the file where each use can be checked. | 13 min |
| [dependencies.md](dependencies.md) | Reference | What `west.yml` fetches, why, and under which licence each project states it is distributed, and how the Crux import is narrowed. | 5 min |
| [board-bring-up.md](board-bring-up.md) | How-to guide | The board route for the RT1060-EVKB Rev B, untested on hardware: the probe on WSL2, the optional board container, a read-only compare of the flash, `west flash` and `west debug` with J-Link, a run record template, the stop conditions and the authorisation that it needs. | 13 min |

### In `docs/findings/`

| Document | Type | What it is | Reading time |
|---|---|---|---|
| [findings/README.md](findings/README.md) | Entry (index) | What a finding is, how the notes are kept, and a table of all notes with the Crux revision each was read at. | 2 min |
| [findings/file-binding-has-no-public-header.md](findings/file-binding-has-no-public-header.md) | Record | A product could not bind the File provider with public means. Closed upstream since. | 1 min |
| [findings/management-has-no-public-composition.md](findings/management-has-no-public-composition.md) | Record | Which management features had no public composition, and the licence limits. Partly overtaken by step S6. | 5 min |
| [findings/s2-first-board-run.md](findings/s2-first-board-run.md) | Record | The two runs of the S2 image on one board and bench, and what they show and do not show. | 7 min |
| [findings/s3-file-composition.md](findings/s3-file-composition.md) | Record | Step S3: composing Crux File through the composition interface, with the friction found. | 6 min |
| [findings/s4-system-composition.md](findings/s4-system-composition.md) | Record | Step S4: the reset cause and a single-owner watchdog through Crux System, and why the simulator cannot show a feed cycle. | 8 min |
| [findings/s5-time-synchronisation.md](findings/s5-time-synchronisation.md) | Record | Step S5: setting the Crux Time realtime clock from SNTP, the product policy and its limits. | 15 min |
| [findings/s6-https-management-gaps.md](findings/s6-https-management-gaps.md) | Record | Groundwork for step S6: the three gaps found by reading. Superseded by the next note, kept as recorded. | 9 min |
| [findings/s6-https-management.md](findings/s6-https-management.md) | Record | Step S6: what the product had to write for HTTPS management, the CI results at a named revision and what is open. | 10 min |

### In `docs/history/`

These pages keep text that left the main documents. They are history, not instructions.

| Document | Type | What it is | Reading time |
|---|---|---|---|
| [history/README.md](history/README.md) | Entry (index) | What the history folder holds, and the move log: each moved section, its source and its destination. | 5 min |
| [history/board-runs-and-tracking.md](history/board-runs-and-tracking.md) | History | The board-run summary, the approval wording and the tracking notes that the roadmap and the glossary carried. | 4 min |
| [history/copy-procedures.md](history/copy-procedures.md) | History | The steps for a copy without the Git history (a zip), as the install guides had them. | 6 min |
| [history/readme-before-entry-point.md](history/readme-before-entry-point.md) | History | The whole README before it became an entry point. | 10 min |
| [history/setup-checks.md](history/setup-checks.md) | History | The record of the local setup runs and the Dev Container job timing behind Getting started. | 3 min |
| [history/team-copy.md](history/team-copy.md) | History | What a team was told to change and keep in a copy of the repository without GitHub CI. | 6 min |

### Outside `docs/`

| Document | Type | What it is | Reading time |
|---|---|---|---|
| [README.md](../README.md) | Entry | What the repository is and for whom, the Crux usage step by step, the quick start, where to read next, the status and limits, contributing, the licence and ownership. | 4 min |
| [CHANGELOG.md](../CHANGELOG.md) | Record | What each change added. Everything is unreleased. | 8 min |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Reference (rules) | The boundary, build and test, the CI jobs, the pin, how to change behaviour, commits and pull requests, review, and the rules of a public repository. | 9 min |
| [RELEASE.md](../RELEASE.md) | Reference | The release dry run, what the bundle holds (hashes only) and what a tag needs. | 2 min |
| [SECURITY.md](../SECURITY.md) | Reference (policy) | How to report a vulnerability, and what the repository promises about support. | 1 min |
