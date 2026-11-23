# Crux Controller

Crux Controller is an Apache-2.0 reference consumer firmware of
[Crux](https://github.com/wonny-labs/crux-pilot), an embedded software platform for Zephyr RTOS firmware. It targets
the NXP RT1060-EVKB Rev B evaluation board (EVKB for short). The workload is synthetic, and the firmware has no real
control logic.

It is for developers who build a product on Crux and want a working example: it uses Crux through public headers,
public CMake targets and published composition interfaces only, one capability per step, S0 to S6. To start, follow
the [Tutorial](docs/tutorial.md); it needs no board.

Crux Controller is the official reference consumer firmware for ongoing integration,
evaluation and regression testing of Crux Platform capabilities through public and approved
composition interfaces. It may provide supporting evidence for relevant platform milestones, but it
is not a mandatory exit criterion for any of them.

## What it provides

Each step adds one Crux capability. S0 is the base configuration `app/prj.conf`; each later step adds its fragment
`app/conf/s<N>.conf` at build time, on top of S1 (S5 and S6 also on top of S2). A missing or awkward
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
| S6 | Management over HTTPS: Crux Access, the web server on the Mbed TLS profile, the status and configuration services and a packaged page | `app/compose/management_start.c`, `app/management/` | [step S6](docs/findings/s6-https-management.md) | yes, ten cases, no login, fake entropy | not run |

[docs/architecture.md](docs/architecture.md#how-crux-is-consumed) lists each Crux target and header and the file
that uses it.

## Quick start

You do not need a board. Follow the [Tutorial](docs/tutorial.md): it takes you from a clone to one EVKB build, one
run of the `native_sim` scenarios with Twister (Zephyr's test runner) and the local checks.

On Windows with WSL2 and Docker Engine (no Docker Desktop), or on an x86_64 Linux, use the Dev Container (only an
x86_64 host was exercised, and only in CI; nobody has run it on WSL2 yet). Each command runs in it through
`bash scripts/dev-shell.sh`. [Getting started](docs/getting-started.md#set-up-the-dev-container) covers the
set-up, a proxy and the route without Docker. Look a failure up by its message in
[docs/troubleshooting.md](docs/troubleshooting.md). CI stays the reference for Zephyr builds and Twister runs.

## Where to read next

| You want to | Read |
|---|---|
| Set up, then run the host tests, the `native_sim` scenarios and a board build | [Getting started](docs/getting-started.md), then the [Tutorial](docs/tutorial.md); every set-up variant is in the [Dev Container reference](docs/dev-container.md) and [Set up without the Dev Container](docs/native-setup.md) |
| Find any page by task | [Documentation map](docs/README.md) |
| Understand the source trees, the zones, the threads and how Crux is consumed | [docs/architecture.md](docs/architecture.md), with the [glossary](docs/glossary.md) for words used in a particular sense |
| Know what works, what has run on a board and what is not yet possible | [docs/roadmap.md](docs/roadmap.md) |
| Make a first change, from a branch to a pull request | [docs/first-change.md](docs/first-change.md), then [CONTRIBUTING.md](CONTRIBUTING.md) |
| Add a step | [docs/adding-a-step.md](docs/adding-a-step.md) and [docs/composition-zone.md](docs/composition-zone.md) |
| Review a change | [docs/reviewing.md](docs/reviewing.md) |
| Run an image on a board (untested route, needs authorisation) | [docs/board-bring-up.md](docs/board-bring-up.md) |
| Build a product of your own on Crux | Crux's guides at the pinned revision: [Choosing an API](https://github.com/wonny-labs/crux-pilot/blob/1c4cf2848c3dca1997bf3be0193e4b38374e7759/docs/choosing-an-api.md) (where code goes), [Composition interfaces](https://github.com/wonny-labs/crux-pilot/blob/1c4cf2848c3dca1997bf3be0193e4b38374e7759/docs/composition-interfaces.md), the [Product Composition Guide](https://github.com/wonny-labs/crux-pilot/blob/1c4cf2848c3dca1997bf3be0193e4b38374e7759/docs/product-composition.md) with its [product template](https://github.com/wonny-labs/crux-pilot/blob/1c4cf2848c3dca1997bf3be0193e4b38374e7759/templates/product/README.md), and [Component readiness](https://github.com/wonny-labs/crux-pilot/blob/1c4cf2848c3dca1997bf3be0193e4b38374e7759/docs/component-readiness.md) |

## Status and limits

Steps S0 to S6 are on `main`, and there is no release. CI builds every step for the EVKB and checks its declared
resource limits. CI also runs the `native_sim` scenarios of S1 to S6. Step S2 ran twice on a board, on one bench.
Nothing else has run on a board. The [roadmap](docs/roadmap.md) gives the detail and the static size of each step,
and the [documentation map](docs/README.md#known-limits-not-scheduled) lists the known limits of the checks.

## Contributing

Ask a question or report a problem as an issue at <https://github.com/wonny-labs/crux-controller/issues>. Read
[CONTRIBUTING.md](CONTRIBUTING.md) for the boundary, the checks, the pin, commits, pull requests and review. The
include rules are in [docs/composition-zone.md](docs/composition-zone.md), what `west.yml` fetches is in
[docs/dependencies.md](docs/dependencies.md), what each change added is in [CHANGELOG.md](CHANGELOG.md), and the
project history that left the main documents is in [docs/history/](docs/history/README.md).

## Licence, support and ownership

- Licence: Apache-2.0. See `LICENSE`.
- Support: no support period is promised. Only the latest release is supported.
- Ownership: the repository owner, the account in `CODEOWNERS`, decides what the documents reserve, such as
  merges, tags, releases and any run on a board ([glossary](docs/glossary.md#people-and-board-procedures)).
- Security reports: see `SECURITY.md`, and do not use a public issue for them.
- Releases: see `RELEASE.md`.
