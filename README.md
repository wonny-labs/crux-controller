# Crux Controller

Crux Controller is an Apache-2.0 reference consumer firmware of
[Crux](https://github.com/wonny-labs/crux-pilot), an embedded software platform, for the NXP
RT1060-EVKB Rev B on the Zephyr RTOS. It is built the way a product is built, on top of Crux's public
interfaces and one small step at a time, S0 to S6: S0 is the clock of Crux Time, S1 adds a small synthetic
workload on Zephyr threads, and each later step adds one capability that uses a Crux component (a TCP
exchange, a configuration file, a watchdog, a clock set from the network, management over HTTPS). Each step has its own build and
resource budget, and each step after S0 has its own tests. It is not a product and has no real control
logic.

Crux Controller is the official reference consumer firmware for ongoing integration,
evaluation and regression testing of Crux Platform capabilities through public and approved
composition interfaces. It may provide supporting evidence for relevant platform milestones, but it
is not a mandatory exit criterion for any of them.

## Who this is for, and where to start

This repository is for engineers who build firmware on Crux, review it or extend it, and who have not seen this
project before. Crux is a reusable embedded software platform for controller and firmware applications: portable C
components (time, logging, sockets, file, system, secure management and others) with Zephyr integration. It is
developed and validated in the separate public repository `crux-pilot`. Crux Controller is the consumer of Crux in this
sense: a small firmware that uses Crux the way a product would, so that a missing or awkward public interface shows
up as a finding. Nothing here is a product, and the workload is synthetic.

A path of about 30 minutes:

1. This README (5 minutes): what the repository is, its state and its boundary rules.
2. The "Short version" and the table "What exists on `main`" in [docs/roadmap.md](docs/roadmap.md) (5 minutes):
   what each step does, what has run on a board and what has not, and the current static sizes.
3. [docs/architecture.md](docs/architecture.md) (10 minutes): the four source trees, the threads and how Crux is used.
4. [docs/try-on-native-sim.md](docs/try-on-native-sim.md) (5 minutes to read): the commands that run the tests without a board.
5. [CONTRIBUTING.md](CONTRIBUTING.md) (5 minutes): the boundary, the checks, the pin and how a change is reviewed.

On demand: [docs/glossary.md](docs/glossary.md) for terms and roles, [docs/findings/](docs/findings/README.md) for
what building each step taught about using Crux, [docs/adding-a-step.md](docs/adding-a-step.md) to add a step,
[docs/dependencies.md](docs/dependencies.md) for what is fetched and under which licence, and
[docs/board-bring-up.md](docs/board-bring-up.md) for an outline of a board run (not yet run for this firmware).

## Roles and references

- **The owner** (also "the project owner" or "the repository owner") is the maintainer who owns this repository on
  GitHub; the account in `CODEOWNERS` is the owning account. The owner decides what the documents here reserve:
  merging a pull request, tags, GitHub Releases and forks ([CONTRIBUTING.md](CONTRIBUTING.md)), the release approval
  in `RELEASE.md`, filing a request in `crux-pilot`, a change of the pinned Crux revision, and any run on a board. A
  review `PASS` and a green CI result inform these decisions and do not replace them. To get a change reviewed, open a
  pull request as [CONTRIBUTING.md](CONTRIBUTING.md) describes.
- **The reviewer** is someone who did not write the change and who reads the files and the check results themselves.
- **The operator** is the person who runs a board procedure on a bench, for example the S2 runs in
  [docs/findings/s2-first-board-run.md](docs/findings/s2-first-board-run.md), under the owner's approval for that
  task. No CI job and no script of this repository touches a board.
- Short hashes, pull request numbers and issue numbers (for example "pull request 50", "#44") name the history of the
  public repositories `wonny-labs/crux-controller` and `wonny-labs/crux-pilot` on GitHub. A copy of this repository
  without that history cannot open them. The facts that matter are stated in the text next to them, and the
  documents do not depend on the content of an issue.
- The scripts that call Git (`scripts/check-format.sh`, `scripts/analyze_host.py`) need a Git repository. In a copy
  without `.git`, run `git init && git add -A` first.

## How to try it

You do not need a board to see the firmware's tests run: the `native_sim` scenarios run on a host.
[docs/try-on-native-sim.md](docs/try-on-native-sim.md) lists what is needed and the commands, and what a
passing run does and does not show. CI is the reference for Zephyr builds and Twister runs; the page gives the
CI commands for a local `native_sim` run on Linux or WSL2, and a local result does not replace the CI result
in a pull request. The reason is that CI builds in one pinned environment that every reviewer can open (see
[Why the evidence comes from CI](docs/try-on-native-sim.md#why-the-evidence-comes-from-ci)). Contribution rules and
the Python tooling tests are in [CONTRIBUTING.md](CONTRIBUTING.md). On Windows with WSL2 and Docker Engine (no Docker Desktop), or on any x86_64 host without Ubuntu 24.04,
a dev container can build and test it: CI runs the tooling tests, the host tests, the boundary checks, the
`native_sim` scenarios and the S1 board cross-build in it. See
[docs/try-on-native-sim.md](docs/try-on-native-sim.md#dev-container) (only an x86_64 host was exercised, and only in CI; nobody has run it on WSL2 yet).

## Status

Steps S0 to S6 are on `main`, and there is no release. The repository builds in CI for the NXP
RT1060-EVKB Rev B with the Zephyr baseline gate required: a synthetic workload on Zephyr threads and a
message queue behind an adapter zone, with Crux Time and Logging (step S1), a TCP exchange over the Crux Sockets profile (step S2), a
configuration record kept in a file through Crux File (step S3, built and never run on a board),
the reset cause and a single-owner watchdog through Crux System (step S4, built and never run on a board),
the Crux Time realtime clock set from an SNTP server (step S5, built and never run on a board),
HTTPS management on the Mbed TLS profile with Crux Access and a packaged page (step S6, built and never run on a board, with no account and no login),
and static resource use checked against declared limits. Step S2 ran twice on a board, on
9 and 12 November 2026: both times the Ethernet link came up without the MDIO correction that the
Crux sample applies, the board answered ping, and one TCP exchange with a host peer was echoed. The
second run reproduced the first on the same bench; that is two runs on one bench, not repeatability
in a statistical sense and not another board, and the TCP exchange was informational. Nothing else
has run on a board.

| Step | What it adds | `native_sim` scenario | RT1060-EVKB build | On a board |
|---|---|---|---|---|
| S0 | The clock of Crux Time | no | yes | not run |
| S1 | The workload on Zephyr threads and a message queue (adapter zone `app/os`), with Crux Time and Logging | yes | yes | not run |
| S2 | A TCP exchange over the Crux Sockets profile | yes, over loopback | yes | ran twice, reproduced on one bench (link up, ping answered, one exchange echoed) |
| S3 | A configuration record in a file through Crux File, mounted by the composition zone | yes, simulator provider on a RAM disk | yes, FatFs provider, microSD, no card used | not run |
| S4 | The reset cause logged at boot and a watchdog fed once for each pass of the workload that has cycles due, through Crux System | yes, the boot line and a watchdog that the scenario does not enable; no feed cycle | yes, WDOG1 named by a devicetree alias | not run |
| S5 | The Crux Time realtime clock set from an SNTP server by a low-priority thread, with a product policy for what an answer may do (on the S2 network) | yes, a responder over loopback: seven cases, no failed native write | yes, on the S2 base | not run |
| S6 | Management over HTTPS on the S2 network: Crux Access, the web server on the Mbed TLS profile, the status and configuration services and a packaged page, on a RAM disk (no account, so no login) | yes, one image of ten cases with an in-process TLS client; no successful login, fake entropy | yes, on the S2 base, with the Mbed TLS group switched on in the job's own runner | not run |

Every step is checked against its declared resource limits (`budgets/limits.json`,
placeholders; the static sizes that CI reads for each step are in [docs/roadmap.md](docs/roadmap.md#static-size-per-step)). What S3 needed from the product is recorded in `docs/findings/s3-file-composition.md`, what S4 needed in `docs/findings/s4-system-composition.md` and what S5 decides and leaves open in `docs/findings/s5-time-synchronisation.md`, and what S6 composed and what it leaves open in `docs/findings/s6-https-management.md`;
what the two board runs of S2 show and do not show is recorded in `docs/findings/s2-first-board-run.md`.
Why the serial and SSH command lines and SFTP are not built here, and what stood between this repository and
HTTPS management before step S6, is recorded in `docs/findings/management-has-no-public-composition.md` and
`docs/findings/s6-https-management-gaps.md`.

It is meant to exercise the Crux features together in one image on the NXP RT1060-EVKB Rev B, with
declared resource budgets, a release bundle and an SBOM, using only independently written code.

## What it is not

- It is not Crux, and it adds no Crux public interface. A gap found here is
  reported to `crux-pilot` as an issue.
- It is not evidence for any Crux security claim. That evidence lives in
  `crux-pilot`.
- It is not a mandatory exit criterion of any `crux-pilot` milestone. Where it supports a milestone,
  it is supporting evidence only.
- It contains no restricted or company-owned source and no product-specific
  control logic. Its workload is synthetic and written for this
  repository.

## Boundary

The include rules of the source trees are checked by `scripts/check_boundary.py` in CI.
`app/src` includes ISO C, the Crux Sockets profile headers, public `<crux/NAME.h>` headers (except
the four frozen ones: `<crux/thread.h>`, `<crux/sync.h>`, `<crux/queue.h>`, `<crux/serial.h>`) and its
own tree. `workload` includes ISO C and its own tree. The adapter zone `app/os` is the one place that
creates threads, queues messages and sleeps, and it calls Zephyr directly: besides ISO C, public
`<crux/NAME.h>` headers (except the frozen four), its own tree and the headers of `app/src`, it may
include exactly two Zephyr headers, `zephyr/kernel.h` and `zephyr/net/sntp.h`. The composition zone
`app/compose` is the one place that mounts a file system and binds it to Crux with
`<crux/file_zephyr.h>`; it may also include the Web composition interface `<crux/web_zephyr.h>`, and
it has a short allow-list of Zephyr headers; `app/src` reaches either zone only through a product-owned port header that it declares itself. See
[docs/architecture.md](docs/architecture.md) for a table of the four trees and
[docs/composition-zone.md](docs/composition-zone.md) for the allow-lists and the reason for each entry.

## The Crux pin

Crux is imported by `west.yml` at one pinned commit of `crux-pilot`: the `revision` of the `crux-pilot`
project. It is a commit and never a branch or a tag. A pin moves in its own pull request; the steps are
in the pin section of [CONTRIBUTING.md](CONTRIBUTING.md), and [docs/dependencies.md](docs/dependencies.md)
says what each pinned project is for and under which licence it states it is distributed.

## How it is tracked

These documents call S3 a Stage 1 step and S4 a Stage 2 step; they do not place S5. The stage is a
planning label, not a property of the code.
Stage 2 steps and their findings are tracked in this repository's own issues: the epic #44 and its
children #40 (the management finding), #41 (S4), #42 and #43. Earlier findings are recorded in
`docs/findings/`. These numbers are issues of the public GitHub repository, and their open or closed state can lag
behind the code: the documents and the CI checks of a commit are the reference for what exists. Step S5 arrived with
[pull request 50](https://github.com/wonny-labs/crux-controller/pull/50) of that repository. Nothing has been
filed in `crux-pilot` yet; filing there needs the owner's approval.

## Licence, support and ownership

- Licence: Apache-2.0. See `LICENSE`.
- Support: no support period is promised. Only the latest release is supported.
- Contributing: see [CONTRIBUTING.md](CONTRIBUTING.md).
- Security reports: see `SECURITY.md`.
- Releases: see `RELEASE.md`. Dependencies and their licences: see `docs/dependencies.md`.
  Changes: see `CHANGELOG.md`.
