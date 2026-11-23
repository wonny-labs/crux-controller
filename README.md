# Crux Controller

Crux Controller is an Apache-2.0 reference consumer firmware of
[Crux](https://github.com/wonny-labs/crux-pilot), an embedded software platform for Zephyr RTOS firmware. It targets
the NXP RT1060-EVKB Rev B evaluation board (EVKB for short), and its workload is synthetic. It uses Crux through
public headers, public CMake targets and published composition interfaces only, one capability per build
configuration, so that a product team can read how each Crux capability is composed.

## Quick start

You do not need a board. Set up with [Getting started](docs/getting-started.md), then follow the
[Tutorial](docs/tutorial.md): it takes you from a clone to the host tests, one run of the `native_sim` scenarios with
Twister (Zephyr's test runner) and one EVKB build.

On Windows with WSL2 and Docker Engine (no Docker Desktop), or on an x86_64 Linux, use the Dev Container (only an
x86_64 host was exercised, and only in CI; nobody has run it on WSL2 yet). Each command runs in it through
`bash scripts/dev-shell.sh`; [Getting started](docs/getting-started.md#set-up-the-dev-container) covers the set-up.
Look a failure up by its message in [troubleshooting](docs/troubleshooting.md).

## Capabilities

Each build configuration adds one Crux capability to the base image `app/prj.conf`. Its Kconfig fragment is
`app/conf/<name>.conf`, built on top of `workload.conf` (`sntp` and `management` also on top of `net.conf`), with a
devicetree overlay `app/boards/<name>.overlay` where the capability needs one.

| Capability | Build configuration | Code to read |
|---|---|---|
| The clock of Crux Time | `base` | `app/src/composition.c` |
| A synthetic workload on Zephyr threads and a message queue, with Crux Time and Logging | `workload` | `app/src/workload_thread.c`, `app/os/workload_os_zephyr.c`, `workload/` |
| A TCP exchange over the Crux Sockets profile | `net` | `app/src/net_client.c` |
| A configuration record in a file through Crux File, mounted by the composition zone | `file` | `app/src/config_store.c`, `app/compose/storage_mount.c` |
| The reset cause at boot and a watchdog fed by the workload, through Crux System | `system` | `app/src/health.c`, `app/src/health_policy.c` |
| The Crux Time realtime clock set from an SNTP (Simple Network Time Protocol) server, with a product policy | `sntp` | `app/src/time_sync.c`, `app/src/time_sync_policy.c`, `app/os/time_sync_zephyr.c` |
| Management over HTTPS: Crux Access, the web server on the Mbed TLS profile, status and configuration services and a packaged page | `management` | `app/compose/management_start.c`, `app/management/` |

[Architecture](docs/architecture.md#how-crux-is-consumed) lists each Crux target and header and the file that uses
it, and [Adding a capability](docs/adding-a-capability.md) shows how a configuration is put together.

## Where to read next

| You want to | Read |
|---|---|
| Find any page by task | [Documentation map](docs/README.md) |
| Understand the source trees, the zones, the threads and how Crux is consumed | [Architecture](docs/architecture.md), with the [glossary](docs/glossary.md) |
| Know what is built, what has run on a board and what is not yet possible | [Roadmap](docs/roadmap.md) |
| Make a first change, from a branch to a pull request | [First change](docs/first-change.md), then [CONTRIBUTING.md](CONTRIBUTING.md) |
| Add a capability | [Adding a capability](docs/adding-a-capability.md) and [the composition zone](docs/composition-zone.md) |
| Review a change | [Reviewing](docs/reviewing.md) |
| Run an image on a board (untested route, needs authorisation) | [Board bring-up](docs/board-bring-up.md) |
| Build a product of your own on Crux | Crux's guides at the pinned revision: [Choosing an API](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/docs/choosing-an-api.md), [Composition interfaces](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/docs/composition-interfaces.md), the [Product Composition Guide](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/docs/product-composition.md) with its [product template](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/templates/product/README.md), and [Component readiness](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/docs/component-readiness.md) |

## Status

There is no release. CI builds every configuration, the [roadmap](docs/roadmap.md) says what has run on a board, and
the [documentation map](docs/README.md#known-limits-not-scheduled) lists the known limits of the checks.

## Contributing

Ask a question or report a problem as an issue at <https://github.com/wonny-labs/crux-controller/issues>. Read
[CONTRIBUTING.md](CONTRIBUTING.md) for the rules of a change, and [CHANGELOG.md](CHANGELOG.md) for what each change
added.

## Licence, support and ownership

- Licence: Apache-2.0. See `LICENSE`.
- Support: no support period is promised. Only the latest release is supported.
- Ownership: the repository owner, the account in `CODEOWNERS`, decides merges, tags, releases and any run on a
  board ([glossary](docs/glossary.md#people-and-board-procedures)).
- Security reports: see `SECURITY.md`, and do not use a public issue for them. Releases: see `RELEASE.md`.
