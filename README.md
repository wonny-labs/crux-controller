# Crux Controller _(crux-controller)_

Crux Controller is a controller framework for products built on [Crux](https://github.com/wonny-labs/crux).

Crux is an embedded software platform for Zephyr RTOS firmware.
Crux Controller is for developers who build a networked controller product on Crux.
It is a Zephyr module that a product imports, and its base image runs the framework services with no application.
It uses Crux only through public headers and approved composition interfaces.
It is not a product and not Crux, and it adds no public interface to Crux.

## Capabilities

The table lists the build configurations, `minimal` to `base`.
The configurations from `workload` to `management` build on a synthetic workload written for this repository.
`base` runs the framework with no workload and no application.

| Capability | Build configuration | Code to read |
|---|---|---|
| The clock of Crux Time | `minimal` | `app/src/composition.c` |
| A synthetic workload on Zephyr threads and a message queue, with Crux Time and Logging | `workload` | `app/src/workload_thread.c`, `app/os/workload_os_zephyr.c`, `workload/` |
| A TCP exchange over the Crux Sockets profile | `net` | `app/src/net_client.c` |
| A configuration record in a file through Crux File, mounted by the composition zone | `file` | `app/src/config_store.c`, `framework/compose/storage_mount.c` |
| The reset cause at boot and a watchdog fed by the workload, through Crux System | `system` | `app/src/health.c`, `app/src/health_policy.c` |
| The Crux Time realtime clock set from an SNTP (Simple Network Time Protocol) server, with a product policy | `sntp` | `framework/src/time_sync.c`, `framework/src/time_sync_policy.c`, `framework/os/time_sync_zephyr.c` |
| Management over HTTPS: Crux Access, the web server on the Mbed TLS profile, status and configuration services and a packaged page | `management` | `framework/compose/management_start.c`, `framework/management/` |
| The controller framework: its start function composes web management, the serial command line and time synchronisation, with no application | `base` | `framework/src/framework.c`, `framework/src/startup.c`, `zephyr/`, `include/controller/framework.h` |

[Architecture](docs/architecture.md#how-crux-is-consumed) lists each Crux target and header and the file that uses
it, and [Adding a capability](docs/adding-a-capability.md) shows how a configuration is put together.

## Status and limits

- There is no release.
- Only the `net` image has run on a board, on one bench. The other build configurations are built only in continuous integration (CI).
- The `base` image has no application. Watchdog supervision and the application interface are not in it yet.
- CI measures static size only. Stack use, heap use and timing are not measured.
- It is not evidence for any Crux security claim. That evidence is in Crux.

The [roadmap](docs/roadmap.md) gives the details and the reason for each limit.

## Supported boards

| Board | Board target | Probe | Page |
|---|---|---|---|
| NXP RT1060-EVKB Rev B evaluation board (EVKB for short) | `mimxrt1060_evk@B/mimxrt1062/qspi` | SEGGER J-Link | [Board bring-up](docs/board-bring-up.md) |

CI writes the same board target as `mimxrt1060_evk@B//qspi`, with the default SoC left out; Zephyr resolves both to the same target.
[Other boards](docs/board-bring-up.md#other-boards) says what a second board needs.

## Quick start

You do not need a board, and building the board image needs none either.
Supported: x86_64 Linux with Docker Engine, through the Dev Container;
[Set up without the Dev Container](docs/native-setup.md) is the alternative on Ubuntu 24.04.

1. Clone the repository and open it in the Dev Container, as [Getting started](docs/getting-started.md#set-up-the-dev-container) describes.
   Use **Dev Containers: Reopen in Container** in VS Code, or `bash scripts/dev-shell.sh` on the command line.
2. The first run sets up the workspace, Zephyr and the Zephyr SDK by itself, which downloads several gibibytes (GiB).
   It is done when it prints `setup: workspace <folder>, Zephyr SDK <version>, West version: <version>`; in VS Code, each attach prints `bootstrap: workspace   ok` and `bootstrap: Zephyr SDK  ok`.
   If it stops with `setup: failed during <step>`, fix the cause and run the same command again; [Getting started](docs/getting-started.md#set-up-the-dev-container) has the details.
3. Follow the [Tutorial](docs/tutorial.md): the host tests, one run of the `native_sim` scenarios with Twister (Zephyr's test runner) and one build for the EVKB.

Look a failure up by its message in [troubleshooting](docs/troubleshooting.md).

## Build a product on Crux

A product is a firmware repository outside this one.
It imports Crux and this module, and adds its own application.
[`tests/product_integration/west.yml`](tests/product_integration/west.yml) is the manifest of a fixture product that imports this repository in that way, and `run.sh` in the same folder builds and runs it on `native_sim`.
Read the Crux guides at the revision that `west.yml` pins:

- [Choosing an API](https://github.com/wonny-labs/crux/blob/05a50475653becf7e4867686f4f88747173e1c21/docs/choosing-an-api.md)
- [Composition interfaces](https://github.com/wonny-labs/crux/blob/05a50475653becf7e4867686f4f88747173e1c21/docs/composition-interfaces.md)
- [Product Composition Guide](https://github.com/wonny-labs/crux/blob/05a50475653becf7e4867686f4f88747173e1c21/docs/product-composition.md), with its [product template](https://github.com/wonny-labs/crux/blob/05a50475653becf7e4867686f4f88747173e1c21/templates/product/README.md)
- [Component readiness](https://github.com/wonny-labs/crux/blob/05a50475653becf7e4867686f4f88747173e1c21/docs/component-readiness.md)

## Where to read next

| You want to | Read |
|---|---|
| Understand the source trees, the zones, the threads and how Crux is consumed | [Architecture](docs/architecture.md), with the [glossary](docs/glossary.md) |
| Know what is built and what has run on a board | [Roadmap](docs/roadmap.md) |
| Make a first change, from a branch to a pull request | [First change](docs/first-change.md), then [CONTRIBUTING.md](CONTRIBUTING.md) |
| Add a capability | [Adding a capability](docs/adding-a-capability.md) and [the composition zone](docs/composition-zone.md) |
| Review a change | [Reviewing](docs/reviewing.md) |
| Run an image on a board, with the authorisation that the board page requires | [Board bring-up](docs/board-bring-up.md) |
| Find any other page by task | [Documentation map](docs/README.md) |

## Contributing

Ask a question or report a problem as an issue at <https://github.com/wonny-labs/crux-controller/issues>.
Changes come as pull requests, under the rules of [CONTRIBUTING.md](CONTRIBUTING.md); [CHANGELOG.md](CHANGELOG.md) records each change.

## Licence, support and ownership

- Licence: Apache-2.0. See `LICENSE`.
- Ownership: the repository owner, the account in `CODEOWNERS` ([glossary](docs/glossary.md#people-and-board-procedures)).
- Support: no support period is promised, and only the latest release, if one exists, is supported.
  Report security issues privately, as `SECURITY.md` describes. Releases: `RELEASE.md`.
