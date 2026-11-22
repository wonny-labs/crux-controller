# The README before it became an entry point

This page keeps the whole `README.md` as it was before it was rewritten as a developer entry point. It is history:
it is kept as written and is not updated. The sections that the new README dropped (Terms, Roles and references,
Boundary, The Crux pin, How it is tracked, the board-run summary of Status and the copy instructions) are here and
nowhere else in this wording; the facts that a developer needs are stated in the current
[README](../../README.md), the [glossary](../glossary.md), the [composition zone](../composition-zone.md), the
[dependencies](../dependencies.md) and the [roadmap](../roadmap.md). The [move log](README.md#move-log) maps each
section to its place.

Only the targets of relative links were rewritten so that they resolve from this folder, the headings are one level
lower, and the example workspace folder reads `crux-controller-workspace`, the name used when the page was moved.

## Crux Controller

Crux Controller is an Apache-2.0 reference consumer firmware of
[Crux](https://github.com/wonny-labs/crux-pilot), an embedded software platform. It targets the NXP
RT1060-EVKB Rev B evaluation board (EVKB for short) and runs on the Zephyr RTOS.

It is built the way a product is built: on top of Crux's public interfaces, one small step at a time, S0 to S6.

- S0 is the clock of Crux Time.
- S1 adds a small synthetic workload on Zephyr threads.
- Each later step adds one capability that uses a Crux component: a TCP exchange, a configuration file, a
  watchdog, a clock set from the network, management over HTTPS.

Each step has its own build and resource budget, and each step after S0 has its own tests. It is not a product in
the commercial sense and has no real control logic.

Crux Controller is the official reference consumer firmware for ongoing integration,
evaluation and regression testing of Crux Platform capabilities through public and approved
composition interfaces. It may provide supporting evidence for relevant platform milestones, but it
is not a mandatory exit criterion for any of them.

Some words are used in one particular sense here: product, platform, composition, stage and owner. The
[glossary](../glossary.md) defines them. "Composition" has four meanings; see
[Composition](../glossary.md#product-platform-and-composition).

### Who this is for, and where to start

This repository is for engineers who build, review or extend firmware on Crux and have not seen this project
before.

Crux is a reusable embedded software platform for controller and firmware applications. It offers portable C
components (time, logging, sockets, file, system, secure management and others) with Zephyr integration. It is
developed and validated in the separate public repository `crux-pilot`.

Crux Controller is a consumer of Crux: a small firmware that uses Crux the way a product would. A missing or
awkward public interface then shows up as a *finding*, a recorded note (see
[docs/findings/](../findings/README.md)). The workload is synthetic.

Read these five documents in this order. They take about 80 minutes in full.
[docs/README.md](../README.md) is the index: it lists every page with its reading time and gives a short path
for each task (run it, change code, add a step, review, understand why).

1. This README (about 10 minutes): what the repository is, its state and its boundary rules.
2. [docs/roadmap.md](../roadmap.md) (about 12 minutes): what each step does, what has run on a board and what
   has not. If you are short of time, read "Short version" and "What exists on `main`" first.
3. [docs/architecture.md](../architecture.md) (about 12 minutes): the four source trees, the threads and how
   Crux is used.
4. [docs/try-on-native-sim.md](../try-on-native-sim.md) (about 35 minutes to read, longer to follow): the
   commands that run the tests without a board.
5. [CONTRIBUTING.md](../../CONTRIBUTING.md) (about 9 minutes): the boundary, the checks, the pin and how a change is
   reviewed.

Then take the page for your task:

- To make a first change, with a small example from branch to pull request:
  [docs/first-change.md](../first-change.md).
- To add a step: [docs/adding-a-step.md](../adding-a-step.md).
- To review a change: [docs/reviewing.md](../reviewing.md).
- For what the checks and tests do not cover: [known limits](../README.md#known-limits-not-scheduled).
- To keep a copy of this repository in your own repository: [docs/team-copy.md](team-copy.md).
- For terms and roles: [docs/glossary.md](../glossary.md).
- For what building each step taught about using Crux: [docs/findings/](../findings/README.md).
- For what is fetched and under which licence: [docs/dependencies.md](../dependencies.md).
- For an outline of a board run, which has not been run for this firmware:
  [docs/board-bring-up.md](../board-bring-up.md).

### Terms used below

- **`native_sim`**: Zephyr's simulated board. It runs the firmware's tests on a host computer.
- **ztest**: Zephyr's test framework. Each `native_sim` scenario is a ztest application.
- **Twister**: Zephyr's test runner. It builds and runs the scenarios.
- **SNTP**: the Simple Network Time Protocol, with which a client asks a network time server for the time. Step S5
  uses it.
- **MDIO**: the management bus through which the Ethernet controller configures the Ethernet PHY chip.
- **SBOM**: a software bill of materials, a list of the components of a build.
- **`PASS`, `REVISE` and `ESCALATE`**: the three results of a review. `PASS` means that the reviewer found no
  blocking problem. `REVISE` means that the author fixes the blocking problems and gets one re-check. `ESCALATE`
  means that the owner decides. See [docs/reviewing.md](../reviewing.md).

The [glossary](../glossary.md) has these terms and more.

### Roles and references

- **The owner** (also "the project owner" or "the repository owner") is whoever owns this repository on GitHub.
  The account in `CODEOWNERS` is the owning account. The owner decides what the documents here reserve:
  - merging a pull request, tags, GitHub Releases and forks ([CONTRIBUTING.md](../../CONTRIBUTING.md));
  - the release approval in `RELEASE.md`;
  - filing a request in `crux-pilot`;
  - any run on a board.

  A review `PASS` and a green CI result inform these decisions and do not replace them. No rule reserves a change
  of the pinned Crux revision to the owner. In practice the owner has approved each one (`west.yml` and
  `tests/tooling/test_manifest.py` record the approval of the current pin). To get a change reviewed, open a
  pull request as [CONTRIBUTING.md](../../CONTRIBUTING.md) describes. In a copy of this repository, the owner is
  whoever approves merges and releases in that copy ([docs/team-copy.md](team-copy.md)).
- **The reviewer** is someone who did not write the change and who reads the files and the check results
  themselves. [docs/reviewing.md](../reviewing.md) has a checklist.
- **The operator** is the person who runs a board procedure on a bench, for example the S2 runs in
  [docs/findings/s2-first-board-run.md](../findings/s2-first-board-run.md), under the owner's approval for that
  task. No CI job and no script of this repository touches a board.
- Short hashes, pull request numbers and issue numbers (for example "pull request 50", "#44") name the history of the
  public repositories `wonny-labs/crux-controller` and `wonny-labs/crux-pilot` on GitHub. A copy of this repository
  without that history cannot open them. The facts that matter are stated in the text next to them, and the
  documents do not depend on the content of an issue.
- The scripts that call Git (`scripts/check-format.sh`, `scripts/analyze_host.py`) need a Git repository. In a copy
  without `.git`, run `git init && git add -A` first.

### How to try it

You do not need a board to see the firmware's tests run: the `native_sim` scenarios run on a host.
[docs/try-on-native-sim.md](../try-on-native-sim.md) has the commands and says what a passing run does and does
not show. CI is the reference for Zephyr builds and Twister runs, and a local result does not replace it
([why](../architecture.md#why-the-evidence-comes-from-ci)).
On Windows with WSL2 and Docker Engine (no Docker Desktop), or on an x86_64 Linux older than Ubuntu 24.04, use the
dev container (only an x86_64 host was exercised, and only in CI; nobody has run it on WSL2 yet). Its
[quick start](../try-on-native-sim.md#set-up-the-dev-container), in short:

1. Install Docker Engine in the distribution and add yourself to the `docker` group.
2. Put the sources in an empty folder named `crux-controller` under a parent of its own, such as `~/work/crux-controller-workspace/crux-controller` (a copy without `.git` needs `git init` and `git add -A` first).
3. Run `bash scripts/dev-shell.sh west --version`: the first run downloads several GiB.
4. Run the Twister command of the quick start for all `native_sim` scenarios.
5. A proxy, a company certificate or an error: see [docs/troubleshooting.md](../troubleshooting.md). Contribution rules and the Python tooling tests are in [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Status

Steps S0 to S6 are on `main`, and there is no release.

The repository builds in CI for the EVKB with the Zephyr baseline gate required. It contains:

- a synthetic workload on Zephyr threads and a message queue behind an adapter zone, with Crux Time and Logging
  (step S1);
- a TCP exchange over the Crux Sockets profile (step S2);
- a configuration record kept in a file through Crux File (step S3, built and never run on a board);
- the reset cause and a single-owner watchdog through Crux System (step S4, built and never run on a board);
- the Crux Time realtime clock set from an SNTP server (step S5, built and never run on a board);
- HTTPS management on the Mbed TLS profile with Crux Access and a packaged page (step S6, built and never run on a
  board, with no account and no login);
- static resource use checked against declared limits.

Step S2 ran twice on a board, on 9 and 12 November 2026:

- Both times the Ethernet link came up without the MDIO correction that the Crux sample applies.
- The board answered ping, and one TCP exchange with a host peer was echoed.
- The second run reproduced the first on the same bench. That is two runs on one bench: not repeatability in a
  statistical sense, and not another board. The TCP exchange was informational.

Nothing else has run on a board.

| Step | What it adds | `native_sim` scenario | RT1060-EVKB build | On a board |
|---|---|---|---|---|
| S0 | The clock of Crux Time | no | yes | not run |
| S1 | The workload on Zephyr threads and a message queue (adapter zone `app/os`), with Crux Time and Logging | yes | yes | not run |
| S2 | A TCP exchange over the Crux Sockets profile | yes, over loopback | yes | ran twice, reproduced on one bench (link up, ping answered, one exchange echoed) |
| S3 | A configuration record in a file through Crux File, mounted by the composition zone | yes, simulator provider on a RAM disk | yes, FatFs provider, microSD, no card used | not run |
| S4 | The reset cause logged at boot and a watchdog fed once for each pass of the workload that has cycles due, through Crux System | yes, the boot line and a watchdog that the scenario does not enable; no feed cycle | yes, WDOG1 named by a devicetree alias | not run |
| S5 | The Crux Time realtime clock set from an SNTP server by a low-priority thread, with a product policy for what an answer may do (on the S2 network) | yes, a responder over loopback: seven cases, no failed native write | yes, on the S2 base | not run |
| S6 | Management over HTTPS on the S2 network: Crux Access, the web server on the Mbed TLS profile, the status and configuration services and a packaged page, on a RAM disk (no account, so no login) | yes, one image of ten cases with an in-process TLS client; no successful login, fake entropy | yes, on the S2 base, with the Mbed TLS group switched on in the job's own runner | not run |

Every step is checked against its declared resource limits (`budgets/limits.json`, placeholders). The static
sizes that CI reads for each step are in [docs/roadmap.md](../roadmap.md#static-size-per-step).

The findings record what each step taught and what the board runs show:

- What S3 needed from the product: `docs/findings/s3-file-composition.md`.
- What S4 needed: `docs/findings/s4-system-composition.md`.
- What S5 decides and leaves open: `docs/findings/s5-time-synchronisation.md`.
- What S6 composed and what it leaves open: `docs/findings/s6-https-management.md`.
- What the two board runs of S2 show and do not show: `docs/findings/s2-first-board-run.md`.
- Why the serial and SSH command lines and SFTP are not built here, and what stood between this repository and
  HTTPS management before step S6: `docs/findings/management-has-no-public-composition.md` and
  `docs/findings/s6-https-management-gaps.md`.

It is meant to exercise the Crux features together in one image on the EVKB, with declared resource budgets, a
release bundle and an SBOM, using only independently written code.

### What it is not

- It is not Crux, and it adds no Crux public interface. A gap found here is
  reported to `crux-pilot` as an issue.
- It is not evidence for any Crux security claim. That evidence lives in
  `crux-pilot`.
- It is not a mandatory exit criterion of any `crux-pilot` milestone. Where it supports a milestone,
  it is supporting evidence only.
- It contains no restricted or company-owned source and no product-specific
  control logic. Its workload is synthetic and written for this
  repository.

### Boundary

`scripts/check_boundary.py` checks the include rules of the source trees in CI. In short:

- `app/src` includes ISO C, the Crux Sockets profile headers, public `<crux/NAME.h>` headers and its own tree.
  Four public headers are frozen and not allowed: `<crux/thread.h>`, `<crux/sync.h>`, `<crux/queue.h>` and
  `<crux/serial.h>`.
- `workload` includes ISO C and its own tree.
- The adapter zone `app/os` is the one place that creates threads, queues messages and sleeps. It calls Zephyr
  directly. Besides ISO C, public `<crux/NAME.h>` headers (except the frozen four), its own tree and the headers of
  `app/src`, it may include exactly two Zephyr headers, `zephyr/kernel.h` and `zephyr/net/sntp.h`.
- The composition zone `app/compose` is the one place that mounts a file system and binds it to Crux with
  `<crux/file_zephyr.h>`. It may also include the Web composition interface `<crux/web_zephyr.h>`, and it has a
  short allow-list of Zephyr headers.
- `app/src` reaches either zone only through a product-owned port header that it declares itself.

See [docs/architecture.md](../architecture.md) for a table of the four trees and
[docs/composition-zone.md](../composition-zone.md) for the allow-lists and the reason for each entry. "Zone" and
"composition" are defined in the [glossary](../glossary.md#boundary-and-zones).

### The Crux pin

Crux is imported by `west.yml` at one pinned commit of `crux-pilot`: the `revision` of the `crux-pilot`
project. It is a commit and never a branch or a tag. A pin moves in its own pull request; the steps are
in the pin section of [CONTRIBUTING.md](../../CONTRIBUTING.md), and [docs/dependencies.md](../dependencies.md)
says what each pinned project is for and under which licence it states it is distributed.

### How it is tracked

These documents call S3 a Stage 1 step and S4 a Stage 2 step; they do not place S5. The stage is a
planning label, not a property of the code ([glossary](../glossary.md#steps-and-stages)).
Stage 2 steps and their findings are tracked in this repository's own issues: the epic #44 and its children #40 (the management finding), #41 (S4), #42 and #43. Earlier findings are recorded in `docs/findings/`. These numbers are issues of the public GitHub repository, and their open or closed state can lag
behind the code: the documents and the CI checks of a commit are the reference for what exists. The pull request that added step S5 is
[pull request 50](https://github.com/wonny-labs/crux-controller/pull/50) of that repository. Nothing has been
filed in `crux-pilot` yet; filing there needs the owner's approval.

### Licence, support and ownership

- Licence: Apache-2.0. See `LICENSE`.
- Support: no support period is promised. Only the latest release is supported.
- Problems and questions: open an issue at <https://github.com/wonny-labs/crux-controller/issues>.
- Contributing: see [CONTRIBUTING.md](../../CONTRIBUTING.md).
- Security reports: see `SECURITY.md`, and do not use a public issue for them.
- Releases: see `RELEASE.md`. Dependencies and their licences: see `docs/dependencies.md`.
  Changes: see `CHANGELOG.md`.
- A copy of this repository in your own repository: see [docs/team-copy.md](team-copy.md).
