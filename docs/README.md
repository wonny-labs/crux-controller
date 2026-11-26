# Documentation map

This page finds the right page for what you want to do. Start at the [repository README](../README.md) for what
the repository is and the quick start, the [Tutorial](tutorial.md). Each page has one type, listed in
[All documents](#all-documents), and links to the one page that owns a fact; the
[documentation guidelines](documentation-guidelines.md) say how.

## Paths by task

### I want to run it

[Getting started](getting-started.md) first, then the [Tutorial](tutorial.md). The [Dev Container reference](dev-container.md) and [Set up without the Dev Container](native-setup.md) hold the setup details;
[troubleshooting.md](troubleshooting.md) is for a failure, and [board-bring-up.md](board-bring-up.md) for a board.

### I want to change code

[first-change.md](first-change.md), then [CONTRIBUTING.md](../CONTRIBUTING.md). [architecture.md](architecture.md) says
which directory holds what; [composition-zone.md](composition-zone.md) explains a failed boundary check.

### I want to add a capability

[adding-a-capability.md](adding-a-capability.md), with [findings/s4-system-composition.md](findings/s4-system-composition.md) as a
worked example and [architecture.md](architecture.md) for the zones and port headers.

### I want to review

[reviewing.md](reviewing.md), the three verdicts in [CONTRIBUTING.md](../CONTRIBUTING.md#review), and the
[files that need a reviewed change](adding-a-capability.md#files-that-need-a-reviewed-change).

### I want to look up how a capability behaves

[capabilities.md](capabilities.md) is the reference for `sntp`, `system` and `management`.

### I want to know why

The [capabilities](capabilities.md), the [findings](findings/README.md), the [roadmap](roadmap.md), [why a zone](composition-zone.md#why-a-zone) and the
[history](history/README.md).

## Where decisions are recorded

- **Rules for working here**: `CONTRIBUTING.md`. `RELEASE.md` covers tags and releases, and `SECURITY.md` covers
  vulnerability reports.
- **Boundary rules and the reason for each allow-list entry**: [composition-zone.md](composition-zone.md). The lists
  themselves are in `scripts/check_boundary.py`.
- **What building each capability taught, and the decisions taken in it**: the notes in `docs/findings/`
  ([index](findings/README.md)).
- **What exists and what ran on a board**: [roadmap.md](roadmap.md).
- **The pinned Crux revision**: the `revision` in `west.yml`. [CHANGELOG.md](../CHANGELOG.md) records each move.
- **Tracking**: the issues and pull requests of the public repository. How the work was tracked is in
  [history](history/board-runs-and-tracking.md).

## All documents

### In `docs/`

| Document | Type | What it is |
|---|---|---|
| [architecture.md](architecture.md) | Explanation | How the repository is built: the source trees, how Crux is consumed, the threads, and why the evidence comes from CI. |
| [capabilities.md](capabilities.md) | Reference | How `sntp`, `system` and `management` behave: policy, settings and limits. |
| [roadmap.md](roadmap.md) | Reference | What is built on `main`, the static size per build configuration and what has run on a board. |
| [tutorial.md](tutorial.md) | Tutorial | The first build and run: the host tests, the `native_sim` scenarios and the board image. |
| [getting-started.md](getting-started.md) | Entry | Prerequisites, the Dev Container set-up and a first command. |
| [dev-container.md](dev-container.md) | Reference | The Dev Container in detail: requirements, hosts, proxies, layout, VS Code and commands. |
| [native-setup.md](native-setup.md) | How-to guide | Set up on Ubuntu 24.04 without the Dev Container and run the scenarios and checks. |
| [troubleshooting.md](troubleshooting.md) | Reference | A failure looked up by its message: cause, fix and the page that explains more. |
| [first-change.md](first-change.md) | Tutorial | One small host-test change from branch to pull request. |
| [adding-a-capability.md](adding-a-capability.md) | How-to guide | Add a capability and its build configuration, with the checklist. |
| [reviewing.md](reviewing.md) | Explanation | A checklist for the reviewer. |
| [composition-zone.md](composition-zone.md) | Reference | The include rules of the composition and adapter zones. |
| [glossary.md](glossary.md) | Reference | The words that this repository uses in a particular sense. |
| [documentation-guidelines.md](documentation-guidelines.md) | Reference | The checklist, page types and homes for every page, and the check that guards them. |
| [dependencies.md](dependencies.md) | Reference | What `west.yml` fetches, why, under which licence, and how the Crux import is narrowed. |
| [board-bring-up.md](board-bring-up.md) | How-to guide | The RT1060-EVKB Rev B board route. |
| [design/controller-framework.md](design/controller-framework.md) | Explanation | The controller framework: what it is, who does what, its services and how a product joins it. |
| [design/controller-framework-spec.md](design/controller-framework-spec.md) | Reference | The controller framework's requirements, application interface, operating model, verification and decisions. |
| [design/controller-framework-platform-gaps.md](design/controller-framework-platform-gaps.md) | Reference | The Crux constraints on the controller framework at the pin, with the Crux change that lifts each one. |

### In `docs/findings/`

| Document | Type | What it is |
|---|---|---|
| [findings/README.md](findings/README.md) | Entry (index) | The map from step ids to build configurations, and a table of all notes. |
| [findings/file-binding-has-no-public-header.md](findings/file-binding-has-no-public-header.md) | Record | A product could not bind the File provider with public means. |
| [findings/management-has-no-public-composition.md](findings/management-has-no-public-composition.md) | Record | Which management features had no public composition, and the licence limits. |
| [findings/s2-first-board-run.md](findings/s2-first-board-run.md) | Record | The two runs of the `net` image on one board and bench. |
| [findings/s3-file-composition.md](findings/s3-file-composition.md) | Record | The `file` capability: Crux File through the composition interface. |
| [findings/s4-system-composition.md](findings/s4-system-composition.md) | Record | The `system` capability: the reset cause and a single-owner watchdog. |
| [findings/s5-time-synchronisation.md](findings/s5-time-synchronisation.md) | Record | The `sntp` capability: the Crux Time realtime clock from SNTP, and the product policy. |
| [findings/s6-https-management-gaps.md](findings/s6-https-management-gaps.md) | Record | Groundwork for `management`: the three gaps found by reading. |
| [findings/s6-https-management.md](findings/s6-https-management.md) | Record | The `management` capability: what the product wrote, the CI results and what is open. |

### In `docs/history/`

| Document | Type | What it is |
|---|---|---|
| [history/README.md](history/README.md) | Entry (index) | What the history folder holds. |
| [history/board-runs-and-tracking.md](history/board-runs-and-tracking.md) | History | The board-run summary, the approval wording and the tracking notes. |
| [history/setup-checks.md](history/setup-checks.md) | History | The local setup runs and the Dev Container job timing behind Getting started. |

### Outside `docs/`

| Document | Type | What it is |
|---|---|---|
| [README.md](../README.md) | Entry | What the repository is, the quick start, the capability table and where to read next. |
| [CHANGELOG.md](../CHANGELOG.md) | Record | What each change added. |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Reference | The boundary, build and test, the CI jobs, the pin, review, and the rules of a public repository. |
| [RELEASE.md](../RELEASE.md) | Reference | The release dry run, what the bundle holds and what a tag needs. |
| [SECURITY.md](../SECURITY.md) | Reference | How to report a vulnerability and what the repository promises about support. |
