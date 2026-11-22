# Crux Controller

Crux Controller is an Apache-2.0 reference consumer firmware of
[Crux](https://github.com/wonny-labs/crux-pilot), an embedded software platform for Zephyr RTOS firmware. It targets
the NXP RT1060-EVKB Rev B evaluation board (EVKB for short). Read it to see how a product uses Crux: through public
headers, public CMake targets and published composition interfaces only, one capability per step, S0 to S6. The
workload is synthetic, and the firmware has no real control logic.

Crux Controller is the official reference consumer firmware for ongoing integration,
evaluation and regression testing of Crux Platform capabilities through public and approved
composition interfaces. It may provide supporting evidence for relevant platform milestones, but it
is not a mandatory exit criterion for any of them.

## Quick start

You do not need a board. Follow [docs/first-hour.md](docs/first-hour.md): it takes you from a clone to one EVKB
build, one run of the `native_sim` scenarios with Twister (Zephyr's test runner) and the local checks.

On Windows with WSL2 and Docker Engine (no Docker Desktop), or on an x86_64 Linux, use the dev container (only an
x86_64 host was exercised, and only in CI; nobody has run it on WSL2 yet). Each command runs in it through
`bash scripts/dev-shell.sh`. The setup details, a proxy and the route without Docker are in
[docs/try-on-native-sim.md](docs/try-on-native-sim.md#quick-start). Look a failure up by its message in
[docs/troubleshooting.md](docs/troubleshooting.md). CI stays the reference for Zephyr builds and Twister runs.

## Learn Crux usage step by step

Each step adds one Crux capability, chosen at build time by its fragment `app/conf/s<N>.conf`. A missing or awkward
public interface is not worked around: it becomes a *finding*, a recorded note in
[docs/findings/](docs/findings/README.md). Read a step's code, then its finding.

| Step | What it shows | Where to look | Finding | `native_sim` scenario | On a board |
|---|---|---|---|---|---|
| S0 | The clock of Crux Time | `app/src/composition.c` | none | no | not run |
| S1 | Crux Time and Logging, with the workload on Zephyr threads and a message queue in the adapter zone `app/os` | `app/src/workload_thread.c`, `app/os/workload_os_zephyr.c`, `workload/` | none | yes | not run |
| S2 | A TCP exchange over the Crux Sockets profile | `app/src/net_client.c` | [S2 board runs](docs/findings/s2-first-board-run.md) | yes, over loopback | ran twice, on one bench |
| S3 | A configuration record in a file through Crux File, mounted by the composition zone | `app/src/config_store.c`, `app/compose/storage_mount.c` | [step S3](docs/findings/s3-file-composition.md) | yes, on a RAM disk | not run |
| S4 | The reset cause logged at boot, and a watchdog fed once for each pass of the workload that has cycles due, through Crux System | `app/src/health.c`, `app/src/health_policy.c` | [step S4](docs/findings/s4-system-composition.md) | yes, without a feed cycle | not run |
| S5 | The Crux Time realtime clock set from an SNTP (Simple Network Time Protocol) server, with a product policy for what an answer may do | `app/src/time_sync.c`, `app/src/time_sync_policy.c`, `app/os/time_sync_zephyr.c` | [step S5](docs/findings/s5-time-synchronisation.md) | yes, seven cases | not run |
| S6 | Management over HTTPS: Crux Access, the web server on the Mbed TLS profile, the status and configuration services and a packaged page | `app/compose/management_start.c`, `app/management/` | [step S6](docs/findings/s6-https-management.md) | yes, ten cases, no login | not run |

[docs/architecture.md](docs/architecture.md#how-crux-is-consumed) lists each Crux target and header and the file
that uses it. To build a product of your own, Crux's guides at the pinned revision are the canonical place:
[Choosing an API](https://github.com/wonny-labs/crux-pilot/blob/2c017f685e0215e0e269d4bc77272889d06a07d8/docs/choosing-an-api.md)
(where code goes),
[Composition interfaces](https://github.com/wonny-labs/crux-pilot/blob/2c017f685e0215e0e269d4bc77272889d06a07d8/docs/composition-interfaces.md),
the [Product Composition Guide](https://github.com/wonny-labs/crux-pilot/blob/2c017f685e0215e0e269d4bc77272889d06a07d8/docs/product-composition.md)
with its [product template](https://github.com/wonny-labs/crux-pilot/blob/2c017f685e0215e0e269d4bc77272889d06a07d8/templates/product/README.md),
and [Component readiness](https://github.com/wonny-labs/crux-pilot/blob/2c017f685e0215e0e269d4bc77272889d06a07d8/docs/component-readiness.md).

## Where to read next

| You want to | Read |
|---|---|
| Understand the source trees, the zones, the threads and how Crux is consumed | [docs/architecture.md](docs/architecture.md), with the [glossary](docs/glossary.md) for words used in a particular sense |
| Know what works, what has run on a board and what is not yet possible | [docs/roadmap.md](docs/roadmap.md) |
| Make a first change, from a branch to a pull request | [docs/first-change.md](docs/first-change.md), then [CONTRIBUTING.md](CONTRIBUTING.md) |
| Add a step | [docs/adding-a-step.md](docs/adding-a-step.md) and [docs/composition-zone.md](docs/composition-zone.md) |
| Review a change | [docs/reviewing.md](docs/reviewing.md) |
| Run an image on a board (untested route, needs authorisation) | [docs/board-bring-up.md](docs/board-bring-up.md) |
| Find any page, or the [known limits](docs/README.md#known-limits-not-scheduled) of the checks | [docs/README.md](docs/README.md) |

## Status

Steps S0 to S6 are on `main`, and there is no release. CI builds every step for the EVKB and checks its declared
resource limits. CI also runs the `native_sim` scenarios of S1 to S6. Step S2 ran twice on a board, on one bench.
Nothing else has run on a board. The [roadmap](docs/roadmap.md) gives the detail and the static size of each step.

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
