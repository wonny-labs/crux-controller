# Your first hour

This page takes a new team member on Linux or on Windows with WSL2 from nothing to one build, one
`native_sim` run and the local checks, in the dev container. It is the short path. The details, the native
route without Docker and every variant are in [try-on-native-sim.md](try-on-native-sim.md), which this page
links to instead of copying.

**What is untested.** Nobody has run the dev container on WSL2 yet, and nobody has timed these steps on a
developer machine. The commands are the ones that the `devcontainer` workflow of CI runs through
`scripts/dev-shell.sh` on an x86_64 Ubuntu runner, and the times below come from that job. A local result
does not replace the CI result of a pull request ([why](try-on-native-sim.md#why-the-evidence-comes-from-ci)).

## Before you start

- An x86_64 Linux machine, or Windows 11 with WSL2 and an Ubuntu distribution. Work in a WSL terminal and in
  the Linux file system (your home directory), not under `/mnt/c`.
- Docker Engine, not Docker Desktop, with your user in the `docker` group, so that `docker run --rm hello-world`
  works without `sudo`. Steps 1 and 2 of the [quick start](try-on-native-sim.md#quick-start) show how on WSL2.
- Git, and several GiB of free disk for Zephyr, its modules and the Zephyr SDK. Nothing in the repository
  states an exact size.
- Behind a proxy of your organisation, or with its certificate? Do the host part of
  [Behind a proxy or with a company certificate](try-on-native-sim.md#behind-a-proxy-or-with-a-company-certificate)
  first.

## How long it takes

The times are those of the `devcontainer` job of CI for `main` at revision `890ee75` (21 November 2026), on a
fresh GitHub runner with a fast network. On your machine the first setup is the long part: it downloads several
GiB, so it depends on your connection, and it has not been timed outside CI. Later runs reuse what it fetched.

| Step | In CI |
|---|---|
| 1. Clone | not timed |
| 2. Open the dev container, first time (image, workspace, Zephyr SDK) | about 3 min |
| 3. One build: S1 for the RT1060-EVKB | under 1 min |
| 4. One `native_sim` run: all scenarios of S1 to S5 | about 3 min |
| 5. Host tests, sanitizers off and on | under 1 min |
| 6. Tooling tests and the boundary check | under 1 min |

## 1. Clone

Make a parent folder of its own and clone into a folder named exactly `crux-controller` in it. The dev
container mounts the parent folder as the west workspace, and `west init` puts `.west`, `zephyr/` and
`modules/` next to the clone. Replace `<repository-url>` with the address of the repository in your
organisation:

```bash
mkdir -p ~/work/crux-controller-workspace && cd ~/work/crux-controller-workspace
git clone -c core.autocrlf=false <repository-url> crux-controller
cd crux-controller
```

`core.autocrlf=false` keeps the LF line ends that the shell scripts need.

## 2. Open the dev container

Pick one route. Both use the same image (`.devcontainer/Dockerfile`) and the same setup script
(`.devcontainer/setup.sh`).

- **Command line.** `scripts/dev-shell.sh` builds the image and runs the setup, then the command you give it:

  ```bash
  bash scripts/dev-shell.sh west --version
  ```

- **VS Code** with the Dev Containers extension. Open the clone folder and run
  **Dev Containers: Reopen in Container**. If VS Code asks which configuration to use, pick "Crux Controller (Ubuntu 24.04 amd64)"; the
  other one is the optional [board container](board-bring-up.md). VS Code runs `.devcontainer/check-host.sh`
  on the host first and the setup script after the container is created. In its terminal, run the commands
  of the next steps without the `bash scripts/dev-shell.sh` prefix.

It is done when the setup prints its last line and `west --version` answers:

```text
setup: workspace /workspaces/ws, Zephyr SDK 1.0.1, West version: v1.4.0
West version: v1.4.0
```

If it stops, the last line names the step (`setup: failed during <step>; rerun: bash .devcontainer/setup.sh`).
Fix the cause and run the same command again: the setup carries on where it stopped. The messages are in
[troubleshooting.md](troubleshooting.md).

## 3. One build: S1 for the RT1060-EVKB

This is the cross-build of step S1 that the `S1` job of CI runs, from the workspace folder (`/workspaces/ws` in
the container is your `~/work/crux-controller-workspace`):

```bash
bash scripts/dev-shell.sh bash -s <<'SH'
set -euo pipefail
cd /workspaces/ws
west build -p always -b 'mimxrt1060_evk@B//qspi' -d crux-controller/build/s1 \
  crux-controller/app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON \
  -DEXTRA_CONF_FILE=conf/s1.conf
SH
```

The image is `build/s1/zephyr/zephyr.bin` in the clone, next to `zephyr.meta`. A build is not a run on a board.

## 4. One `native_sim` run

`native_sim` is a simulated Zephyr board that runs as an ordinary program on the host. Twister, Zephyr's test
runner, builds and runs every scenario of steps S1 to S5, as the `S1` job does:

```bash
bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && west twister -p native_sim/native/64 -T crux-controller/tests/native_sim --inline-logs --clobber-output -O twister-out'
```

A pass ends with `17 of 17 executed test configurations passed` and `31 of 31 executed test cases passed`.
The scenario table, one-scenario runs and the S6 scenario are in
[Run the S1 to S5 scenarios](try-on-native-sim.md#run-the-s1-to-s5-scenarios).

## 5. Host tests

Plain C tests of the portable code, with no Zephyr, from the repository root:

```bash
bash scripts/dev-shell.sh bash -c 'cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=OFF && cmake --build build/host && ctest --test-dir build/host --output-on-failure'
```

A pass ends with `100% tests passed`. CI also runs them with the sanitizers on, in another build folder:

```bash
bash scripts/dev-shell.sh bash -c 'cmake -S tests/host -B build/host-asan -G Ninja -DWORKLOAD_SANITIZE=ON && cmake --build build/host-asan && ctest --test-dir build/host-asan --output-on-failure'
```

[Run the host tests](try-on-native-sim.md#run-the-host-tests) has the details.

## 6. Tooling tests and the boundary check

The tooling tests read the repository's scripts, workflows, build files and documents. The boundary check
checks the include rules of the source trees against the headers of the pinned `crux-pilot`:

```bash
bash scripts/dev-shell.sh python -m unittest discover -s tests/tooling
bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && python crux-controller/scripts/check_boundary.py --repo crux-controller --crux-root crux-pilot'
```

The tests end with `OK` (or `OK (skipped=<m>)`), and the check prints `boundary check passed`. The other checks
of CI (format, static analysis, SPDX) are in
[Commands inside the container](try-on-native-sim.md#commands-inside-the-container).

## What next

- Make a first change, from a branch to a pull request: [first-change.md](first-change.md).
- Pick the next page from the [README](../README.md#where-to-read-next), starting with the
  [roadmap](roadmap.md) and the [architecture](architecture.md).
- Look up a failure by its message: [troubleshooting.md](troubleshooting.md).
- Everything about the setup, the native route on Ubuntu 24.04 without Docker, the S6 scenario and what has been
  checked: [try-on-native-sim.md](try-on-native-sim.md).
- A board: [board-bring-up.md](board-bring-up.md) describes the board route and its optional board container.
  It is untested on hardware, and nothing may touch a board without the project owner's explicit
  authorisation for the task.
- The rules for a change: [CONTRIBUTING.md](../CONTRIBUTING.md).
