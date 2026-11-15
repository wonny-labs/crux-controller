# Crux Controller

Crux Controller is an Apache-2.0 reference consumer firmware of
[Crux](https://github.com/wonny-labs/crux-pilot), an embedded software platform, for the NXP
RT1060-EVKB Rev B on the Zephyr RTOS. It is built as a product on top of Crux's public interfaces, one
small step at a time, S0 to S5: S0 is the clock of Crux Time, S1 adds a small synthetic workload on Zephyr
threads, and each later step adds one capability that uses a Crux component (a TCP exchange, a
configuration file, a watchdog, a clock set from the network). Each step has its own build and resource
budget, and each step after S0 has its own tests. It is not a product and has no real control logic.

Crux Controller is the official reference consumer firmware for ongoing integration,
evaluation and regression testing of Crux Platform capabilities through public and approved
composition interfaces. It may provide supporting evidence for relevant platform milestones, but it
is not a mandatory exit criterion for any of them.

## Where to read next

- [docs/architecture.md](docs/architecture.md): how the repository is built (layers, zones, how Crux is used).
- [docs/glossary.md](docs/glossary.md): the terms used here, such as step, stage, adapter zone and pin.
- [docs/roadmap.md](docs/roadmap.md): what exists, what has run on a board, and what cannot be done yet.
- [docs/adding-a-step.md](docs/adding-a-step.md): how a new step is added.
- [docs/try-on-native-sim.md](docs/try-on-native-sim.md): how to see the tests run without a board.
- [docs/board-bring-up.md](docs/board-bring-up.md): an outline of a board bring-up (not yet run for this controller).
- [docs/findings/](docs/findings/): what building each step taught about using Crux, and the board-run note.

## How to try it

You do not need a board to see the firmware's tests run: the `native_sim` scenarios run on a host.
[docs/try-on-native-sim.md](docs/try-on-native-sim.md) lists what is needed and the commands, and what a
passing run does and does not show. Zephyr builds and Twister runs happen in CI; this repository describes
no local Zephyr build. Contribution rules and the Python tooling tests are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Status

Steps S0 to S5 are on `main`, and there is no release. The repository builds in CI for the NXP
RT1060-EVKB Rev B with the Zephyr baseline gate required: a synthetic workload on Zephyr threads and a
message queue behind an adapter zone, with Crux Time and Logging (step S1), a TCP exchange over the Crux Sockets profile (step S2), a
configuration record kept in a file through Crux File (step S3, built and never run on a board),
the reset cause and a single-owner watchdog through Crux System (step S4, built and never run on a board),
the Crux Time realtime clock set from an SNTP server (step S5, built and never run on a board),
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
| S4 | The reset cause logged at boot and a watchdog fed once for each pass of the workload that has cycles due, through Crux System | yes, the boot line and a watchdog that the simulator does not have; no feed cycle | yes, WDOG1 named by a devicetree alias | not run |
| S5 | The Crux Time realtime clock set from an SNTP server by a low-priority thread, with a product policy for what an answer may do (on the S2 network) | yes, a responder over loopback: seven cases, no failed native write | yes, on the S2 base | not run |

Every step is checked against its declared resource limits (`budgets/limits.json`,
placeholders). What S3 needed from the product is recorded in `docs/findings/s3-file-composition.md`, what S4 needed in `docs/findings/s4-system-composition.md` and what S5 decides and leaves open in `docs/findings/s5-time-synchronisation.md`;
what the two board runs of S2 show and do not show is recorded in `docs/findings/s2-first-board-run.md`.
Why none of the Crux management features (HTTPS, serial and SSH command line, SFTP) is built here is
recorded in `docs/findings/management-has-no-public-composition.md`.

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
`app/compose` is the one place that mounts a file system and binds it to Crux with the composition
interfaces `<crux/file_zephyr.h>` and `<crux/web_zephyr.h>` and a short allow-list of Zephyr
headers; `app/src` reaches either zone only through a product-owned port header that it declares itself. See
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
`docs/findings/`. Step S5 arrived with
[wonny-labs/crux-controller#50](https://github.com/wonny-labs/crux-controller/pull/50). Nothing has been
filed in `crux-pilot` yet; filing there needs the owner's approval.

## Licence, support and ownership

- Licence: Apache-2.0. See `LICENSE`.
- Support: no support period is promised. Only the latest release is supported.
- Contributing: see [CONTRIBUTING.md](CONTRIBUTING.md).
- Security reports: see `SECURITY.md`.
- Releases: see `RELEASE.md`. Dependencies and their licences: see `docs/dependencies.md`.
  Changes: see `CHANGELOG.md`.
