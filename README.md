# Crux Controller

Crux Controller is an Apache-2.0 reference consumer firmware of
[Crux](https://github.com/wonny-labs/crux-pilot), an embedded software platform. It targets the NXP
RT1060-EVKB Rev B evaluation board (EVKB for short) and runs on the Zephyr RTOS.

It is built the way a product is built: on top of Crux's public interfaces, one small step at a time, S0 to S6.
A missing or awkward public interface shows up as a *finding*, a recorded note in
[docs/findings/](docs/findings/README.md). The workload is synthetic, and the firmware has no real control logic.

Crux Controller is the official reference consumer firmware for ongoing integration,
evaluation and regression testing of Crux Platform capabilities through public and approved
composition interfaces. It may provide supporting evidence for relevant platform milestones, but it
is not a mandatory exit criterion for any of them.

## State

Steps S0 to S6 are on `main`, and there is no release. CI builds every step for the EVKB and checks its declared
resource limits. CI also runs the `native_sim` scenarios of S1 to S6 on Zephyr's simulated board. Step S2 ran twice
on a board, on one bench. Nothing else has run on a board. S5 sets the clock from an SNTP server (Simple Network
Time Protocol).

| Step | What it adds | `native_sim` scenario | RT1060-EVKB build | On a board |
|---|---|---|---|---|
| S0 | The clock of Crux Time | no | yes | not run |
| S1 | The workload on Zephyr threads and a message queue (adapter zone `app/os`), with Crux Time and Logging | yes | yes | not run |
| S2 | A TCP exchange over the Crux Sockets profile | yes, over loopback | yes | ran twice, reproduced on one bench (link up, ping answered, one exchange echoed) |
| S3 | A configuration record in a file through Crux File, mounted by the composition zone | yes, simulator provider on a RAM disk | yes, FatFs provider, microSD, no card used | not run |
| S4 | The reset cause logged at boot and a watchdog fed once for each pass of the workload that has cycles due, through Crux System | yes, the boot line and a watchdog that the scenario does not enable; no feed cycle | yes, WDOG1 named by a devicetree alias | not run |
| S5 | The Crux Time realtime clock set from an SNTP server by a low-priority thread, with a product policy for what an answer may do (on the S2 network) | yes, a responder over loopback: seven cases, no failed native write | yes, on the S2 base | not run |
| S6 | Management over HTTPS on the S2 network: Crux Access, the web server on the Mbed TLS profile, the status and configuration services and a packaged page, on a RAM disk (no account, so no login) | yes, one image of ten cases with an in-process TLS client; no successful login, fake entropy | yes, on the S2 base, with the Mbed TLS group switched on in the job's own runner | not run |

What each step taught is in its finding: [S2 board runs](docs/findings/s2-first-board-run.md),
[S3](docs/findings/s3-file-composition.md), [S4](docs/findings/s4-system-composition.md), step S5
([s5-time-synchronisation.md](docs/findings/s5-time-synchronisation.md)) and
[S6](docs/findings/s6-https-management.md). The [roadmap](docs/roadmap.md) says what is not yet possible and why,
and gives the static size of each step.

## How to try it

You do not need a board: the `native_sim` scenarios run on a host, with Twister (Zephyr's test runner).
On Windows with WSL2 and Docker Engine (no Docker Desktop), or on an x86_64 Linux older than Ubuntu 24.04, use the
dev container (only an x86_64 host was exercised, and only in CI; nobody has run it on WSL2 yet). Its
[quick start](docs/try-on-native-sim.md#quick-start), in short:

1. Install Docker Engine and add yourself to the `docker` group.
2. Clone into `~/work/crux-controller-workspace/crux-controller`, a parent folder of its own.
3. Run `bash scripts/dev-shell.sh west --version`: the first run downloads several GiB.
4. Run the Twister command of the quick start for all `native_sim` scenarios.

A proxy, a company certificate or an error: see [docs/troubleshooting.md](docs/troubleshooting.md). To make a first
change without Zephyr, follow [docs/first-change.md](docs/first-change.md). CI stays the reference for Zephyr
builds and Twister runs ([why](docs/try-on-native-sim.md#why-the-evidence-comes-from-ci)).

## Reading path

Read these five documents in this order. They take about 70 minutes in full.

1. This README (about 4 minutes).
2. [docs/roadmap.md](docs/roadmap.md) (about 11 minutes): what each step does, what has run on a board and what
   has not.
3. [docs/architecture.md](docs/architecture.md) (about 12 minutes): the four source trees, the threads and how
   Crux is used.
4. [docs/try-on-native-sim.md](docs/try-on-native-sim.md) (about 32 minutes to read, longer to follow): the
   commands that run the tests without a board.
5. [CONTRIBUTING.md](CONTRIBUTING.md) (about 9 minutes): the boundary, the checks, the pin and how a change is
   reviewed.

[docs/README.md](docs/README.md) is the index of every page, with a path for each task. For a task, go to
[docs/adding-a-step.md](docs/adding-a-step.md), [docs/reviewing.md](docs/reviewing.md) or the
[known limits](docs/README.md#known-limits-not-scheduled). Words used in a particular sense are in the
[glossary](docs/glossary.md).

## Where the rules are

- [CONTRIBUTING.md](CONTRIBUTING.md): the boundary, the checks, the pin, commits, pull requests and review.
- [docs/composition-zone.md](docs/composition-zone.md): the include rules in detail.
- [docs/dependencies.md](docs/dependencies.md): what `west.yml` fetches, at which pinned commit and licence.
- [CHANGELOG.md](CHANGELOG.md): what each change added.
- [docs/history/](docs/history/README.md): the project history that left the main documents.

## Licence, support and ownership

- Licence: Apache-2.0. See `LICENSE`.
- Support: no support period is promised. Only the latest release is supported.
- Ownership: the repository owner, the account in `CODEOWNERS`, decides what the documents reserve, such as
  merges, tags, releases and any run on a board ([glossary](docs/glossary.md#people-and-board-procedures)).
- Problems and questions: open an issue at <https://github.com/wonny-labs/crux-controller/issues>.
- Security reports: see `SECURITY.md`, and do not use a public issue for them.
- Releases: see `RELEASE.md`.
