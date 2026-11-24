# Crux Controller

Crux Controller is an Apache-2.0 reference consumer firmware of
[Crux](https://github.com/wonny-labs/crux-pilot), an embedded software platform for Zephyr RTOS firmware. It targets
the NXP RT1060-EVKB Rev B evaluation board (EVKB for short), and its workload is synthetic. It uses Crux through
public headers, public CMake targets and published composition interfaces only, one capability per build
configuration, so that a product team can read how each Crux capability is composed.

## Quick start

You do not need a board. Supported: x86_64 Linux with Docker Engine, through the Dev Container;
[Set up without the Dev Container](docs/native-setup.md) is the alternative on Ubuntu 24.04.

1. Clone the repository and open the Dev Container, as [Getting started](docs/getting-started.md#set-up-the-dev-container)
   says: **Dev Containers: Reopen in Container** in VS Code, or `bash scripts/dev-shell.sh` on the command line.
2. Wait for the automatic set-up to finish; you do not run it. It checks the folder layout, fetches Zephyr and the
   modules with west and installs the Zephyr SDK, with a `setup:` line for each piece of work it does. It ends with
   `setup: workspace <folder>, Zephyr SDK <version>, West version: <version>`, or with `setup: failed during <step>`
   and the command that reruns it. In VS Code, each attach prints `bootstrap: workspace   ok` and
   `bootstrap: Zephyr SDK  ok`.
3. Follow the [Tutorial](docs/tutorial.md): the host tests, one run of the `native_sim` scenarios with Twister
   (Zephyr's test runner) and one EVKB build.

Look a failure up by its message in [troubleshooting](docs/troubleshooting.md).

## Capabilities

Each build configuration adds one Crux capability to the base image `app/prj.conf`, through the fragment
`app/conf/<name>.conf` and, where it needs one, the overlay `app/boards/<name>.overlay`.

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
| Understand the source trees, the zones, the threads and how Crux is consumed | [Architecture](docs/architecture.md), with the [glossary](docs/glossary.md) |
| Know what is built and what has run on a board | [Roadmap](docs/roadmap.md) |
| Make a first change, from a branch to a pull request | [First change](docs/first-change.md), then [CONTRIBUTING.md](CONTRIBUTING.md) |
| Add a capability | [Adding a capability](docs/adding-a-capability.md) and [the composition zone](docs/composition-zone.md) |
| Review a change | [Reviewing](docs/reviewing.md) |
| Run an image on a board | [Board bring-up](docs/board-bring-up.md) |
| Build a product of your own on Crux | Crux's guides at the pinned revision: [Choosing an API](https://github.com/wonny-labs/crux-pilot/blob/ea16f99f1416085e52bacfa69a22d09e4d057b73/docs/choosing-an-api.md), [Composition interfaces](https://github.com/wonny-labs/crux-pilot/blob/ea16f99f1416085e52bacfa69a22d09e4d057b73/docs/composition-interfaces.md), the [Product Composition Guide](https://github.com/wonny-labs/crux-pilot/blob/ea16f99f1416085e52bacfa69a22d09e4d057b73/docs/product-composition.md) with its [product template](https://github.com/wonny-labs/crux-pilot/blob/ea16f99f1416085e52bacfa69a22d09e4d057b73/templates/product/README.md), and [Component readiness](https://github.com/wonny-labs/crux-pilot/blob/ea16f99f1416085e52bacfa69a22d09e4d057b73/docs/component-readiness.md) |
| Find any other page by task | [Documentation map](docs/README.md) |

## Status

There is no release. CI builds every configuration, and the [roadmap](docs/roadmap.md) says what has run on a board.

## Contributing

Ask a question or report a problem as an issue at <https://github.com/wonny-labs/crux-controller/issues>. Read
[CONTRIBUTING.md](CONTRIBUTING.md) for the rules of a change, and [CHANGELOG.md](CHANGELOG.md) for what each change
added.

## Licence, support and ownership

- Licence: Apache-2.0. See `LICENSE`.
- Ownership: the repository owner, the account in `CODEOWNERS` ([glossary](docs/glossary.md#people-and-board-procedures)).
- Support and security reports: `SECURITY.md`. Releases: `RELEASE.md`.
