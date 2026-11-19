# Documentation index

This page lists every document of the repository, says what each one is for, and gives a short path for each
task. If you have not seen this repository before, start with the [README](../README.md).

The reading times are for reading only, at about 250 words a minute. A page with commands takes longer to follow.
The five pages of the reading path in the README (the README, the roadmap, the architecture, the try-on page and
CONTRIBUTING.md) take about 80 minutes together.

## Paths by task

### I want to run it

- [try-on-native-sim.md](try-on-native-sim.md): set up a workspace and run the `native_sim` scenarios, the host
  tests, the tooling tests and the boundary check without a board.
- [first-change.md](first-change.md): run the host tests and the checks that need no Zephyr, with a small example.
- [troubleshooting.md](troubleshooting.md): look up a failure by its message: its cause, its fix and the page to read next.
- [board-bring-up.md](board-bring-up.md): only an outline of a board run, which has not been run for this firmware.

### I want to change code

- [first-change.md](first-change.md): from a branch to a pull request with a small change that needs no Zephyr.
- [CONTRIBUTING.md](../CONTRIBUTING.md): the boundary, the checks, the pin, how commits and pull requests are written.
- [architecture.md](architecture.md): which directory holds what, and which headers each may include.
- [composition-zone.md](composition-zone.md): read this when the boundary check fails. There is no exception.

### I want to add a step

- [adding-a-step.md](adding-a-step.md): the recipe, the checklist and the rule for drivers and HAL.
- [architecture.md](architecture.md): the zones and the port headers that a step builds on.
- [findings/s4-system-composition.md](findings/s4-system-composition.md): a worked example, with the friction that
  step S4 met.

### I want to review

- [reviewing.md](reviewing.md): the reviewer checklist.
- [CONTRIBUTING.md](../CONTRIBUTING.md#review): the three verdicts and what a `PASS` does not grant.
- [adding-a-step.md](adding-a-step.md#files-that-need-a-reviewed-change): the files whose change needs particular care.

### I want to know why

- [findings/README.md](findings/README.md): what building each step taught about using Crux, with the revision
  that each note was read at.
- [roadmap.md](roadmap.md): what exists, what has run on a board, what is not yet possible and why.
- [composition-zone.md](composition-zone.md#why-a-zone): why the boundary has zones and an exact allow-list.

### I keep a copy of the repository

- [team-copy.md](team-copy.md): what to change and what to keep in a copy without the Git history or GitHub CI.

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
  record the approved commit, and `CHANGELOG.md` records each move.
- **Tracking**: the issues and pull requests of the public repository. Their open or closed state can lag behind the
  code. The documents and the CI checks of a commit are the reference ([README](../README.md#how-it-is-tracked)).

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
- **Many tooling tests pin text.** Counted by module (every test of a module counts the same, at the head of this change), the tests in `tests/tooling` that read the repository's
  documents, workflows, CMake and Kconfig files as text, and run no script on synthetic input, are between about 50
  and 70 percent of all of them. The upper figure counts three modules that mix both kinds. This is an estimate of tests per module, not of modules. A
  green tooling run shows that the text and the configuration agree with the tests, and not that the firmware
  behaves.
- **Parts of the Zephyr-side glue are not run by any test.** The start order and the decisions in `app/src/composition.c`, the
  watchdog feed path of step S4 (the S4 scenario cannot show a feed cycle) and the web page script of step S6 (the S6
  scenario serves its bytes, and nothing runs them) are never run in any test.
- **Steps S5 and S6 run only on `native_sim`, in CI, and never on a board.** Step S2 ran twice on a board, on one bench.
  Nothing else has run on a board ([roadmap](roadmap.md#what-has-run-on-a-board)).
- **The dev container and WSL2 were not tried by anyone.** The dev container was not started on a developer machine, so
  WSL2, Docker Engine in WSL2 and the proxy settings of `devcontainer.json` have not run there. The dev container job
  of CI covers an x86_64 runner only ([try-on-native-sim.md](try-on-native-sim.md#what-has-been-checked)).

## All documents

### In `docs/`

| Document | What it is | Reading time |
|---|---|---|
| [architecture.md](architecture.md) | How the repository is built: the four source trees and their include rules, how Crux is consumed, the threads in the image and a map of the files. | 12 min |
| [roadmap.md](roadmap.md) | What exists on `main`, the static size per step, what has run on a board and what is not yet possible. It promises no dates. | 12 min |
| [try-on-native-sim.md](try-on-native-sim.md) | How to run the tests without a board: setup, the `native_sim` scenarios, the host and tooling tests, the dev container, and what has and has not been checked. | 35 min |
| [troubleshooting.md](troubleshooting.md) | Look a failure up by its message: the cause, the fix and the page that explains more. | 11 min |
| [first-change.md](first-change.md) | A tutorial from branch to pull request with one small host-test change that needs no Zephyr. | 6 min |
| [adding-a-step.md](adding-a-step.md) | The recipe for adding a step, its checklist, the rule for drivers and HAL, and the files that need a reviewed change. | 16 min |
| [reviewing.md](reviewing.md) | A checklist for the reviewer, from CONTRIBUTING.md and from the repository's practice. | 9 min |
| [team-copy.md](team-copy.md) | What to change and what to keep when a team holds a copy of the repository without GitHub CI. | 6 min |
| [composition-zone.md](composition-zone.md) | The include rules in detail: the composition zone and the adapter zone, each allowed Zephyr header and why, the frozen Crux headers, and how to run the check. | 11 min |
| [glossary.md](glossary.md) | The words that this repository uses in a particular sense (step, stage, product, owner, composition, zones, pin, finding and more), with the file where each use can be checked. | 13 min |
| [dependencies.md](dependencies.md) | What `west.yml` fetches, why, and under which licence each project states it is distributed, and how the Crux import is narrowed. | 5 min |
| [board-bring-up.md](board-bring-up.md) | An outline, not yet run for this firmware, of a bring-up on the RT1060-EVKB Rev B and the authorisation that it needs. | 8 min |

### In `docs/findings/`

| Document | What it is | Reading time |
|---|---|---|
| [findings/README.md](findings/README.md) | What a finding is, how the notes are kept, and a table of all notes with the Crux revision each was read at. | 2 min |
| [findings/file-binding-has-no-public-header.md](findings/file-binding-has-no-public-header.md) | A product could not bind the File provider with public means. Closed upstream since. | 1 min |
| [findings/management-has-no-public-composition.md](findings/management-has-no-public-composition.md) | Which management features had no public composition, and the licence limits. Partly overtaken by step S6. | 5 min |
| [findings/s2-first-board-run.md](findings/s2-first-board-run.md) | The two runs of the S2 image on one board and bench, and what they show and do not show. | 7 min |
| [findings/s3-file-composition.md](findings/s3-file-composition.md) | Step S3: composing Crux File through the composition interface, with the friction found. | 6 min |
| [findings/s4-system-composition.md](findings/s4-system-composition.md) | Step S4: the reset cause and a single-owner watchdog through Crux System, and why the simulator cannot show a feed cycle. | 8 min |
| [findings/s5-time-synchronisation.md](findings/s5-time-synchronisation.md) | Step S5: setting the Crux Time realtime clock from SNTP, the product policy and its limits. | 15 min |
| [findings/s6-https-management-gaps.md](findings/s6-https-management-gaps.md) | Groundwork for step S6: the three gaps found by reading. Superseded by the next note, kept as recorded. | 9 min |
| [findings/s6-https-management.md](findings/s6-https-management.md) | Step S6: what the product had to write for HTTPS management, the CI results at a named revision and what is open. | 10 min |

### Outside `docs/`

| Document | What it is | Reading time |
|---|---|---|
| [README.md](../README.md) | What the repository is, its state, the boundary in short, roles and where to start. | 10 min |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | The boundary, build and test, the CI jobs, the pin, how to change behaviour, commits and pull requests, review, and the rules of a public repository. | 9 min |
| [CHANGELOG.md](../CHANGELOG.md) | What each change added. Everything is unreleased. | 8 min |
| [RELEASE.md](../RELEASE.md) | The release dry run, what the bundle holds (hashes only) and what a tag needs. | 2 min |
| [SECURITY.md](../SECURITY.md) | How to report a vulnerability, and what the repository promises about support. | 1 min |
