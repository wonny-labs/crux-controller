# Tutorial: your first build and run

This tutorial takes you from a working Dev Container to the host tests, the `native_sim` scenarios and a board
image, on Linux or on Windows with WSL2. Each step gives the command and what you should see. Part A runs the host
tests and the checks in minutes, Part B runs the `native_sim` scenarios of the product, and Part C builds the image
for a board and points at the board route.

**What is untested.** Nobody has run the Dev Container on WSL2 yet, and nobody has timed these steps on a
developer machine. The commands are the ones that the `devcontainer` workflow of CI runs through
`scripts/dev-shell.sh` on an x86_64 Ubuntu runner, and the times below come from that job. A local result
does not replace the CI result of a pull request ([why](architecture.md#why-the-evidence-comes-from-ci)).

## Prerequisites and the Dev Container

Finish [Getting started](getting-started.md#set-up-the-dev-container) first: the clone in a folder named
`crux-controller` under a parent folder of its own, and a first run of the Dev Container that ends with
`West version: v1.4.0`. Then pick one route for the commands of this page:

- **Command line.** Run each command through `bash scripts/dev-shell.sh`, as written below. The script runs it in
  the Dev Container with the repository as the working directory.
- **VS Code** with the Dev Containers extension. Open the clone folder and run
  **Dev Containers: Reopen in Container**. If VS Code asks which configuration to use, pick "Crux Controller
  (Ubuntu 24.04 amd64)"; the other one is the optional [board container](board-bring-up.md). In its terminal, run
  the commands without the `bash scripts/dev-shell.sh` prefix.

`/workspaces/ws` in the container is the parent folder of your clone, the workspace.

## How long it takes

The times are those of the `devcontainer` job of CI for `main` at revision `890ee75`, on a fresh GitHub runner
with a fast network. The first setup of the Dev Container, about 3 min in CI, is part of Getting started; on your
machine it depends on your connection and has not been timed outside CI.

| Step | In CI |
|---|---|
| 1. Host tests, sanitizers off and on | under 1 min |
| 2. Tooling tests and the boundary check | under 1 min |
| 3. One `native_sim` run: all scenarios of S1 to S5 | about 3 min |
| 4. One build: S1 for the RT1060-EVKB | under 1 min |

## Part A. Host tests

### 1. Host tests

Plain C tests of the portable code, with no Zephyr, from the repository root:

```bash
bash scripts/dev-shell.sh bash -c 'cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=OFF && cmake --build build/host && ctest --test-dir build/host --output-on-failure'
```

A pass ends with `100% tests passed`. CI also runs them with the sanitizers on, in another build folder:

```bash
bash scripts/dev-shell.sh bash -c 'cmake -S tests/host -B build/host-asan -G Ninja -DWORKLOAD_SANITIZE=ON && cmake --build build/host-asan && ctest --test-dir build/host-asan --output-on-failure'
```

[Run the host tests](native-setup.md#run-the-host-tests) has the details.

### 2. Tooling tests and the boundary check

The tooling tests read the repository's scripts, workflows, build files and documents. The boundary check
checks the include rules of the source trees against the headers of the pinned `crux-pilot`:

```bash
bash scripts/dev-shell.sh python -m unittest discover -s tests/tooling
bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && python crux-controller/scripts/check_boundary.py --repo crux-controller --crux-root crux-pilot'
```

The tests end with `Ran <n> tests in <t>s` and `OK` (or `OK (skipped=<m>)`), and the check prints
`boundary check passed`. The other checks of CI (format, static analysis, SPDX) run through the same script, for
example `bash scripts/dev-shell.sh bash scripts/check-format.sh`;
[Commands inside the container](dev-container.md#commands-inside-the-container) lists them.

## Part B. The `native_sim` scenarios

### 3. One `native_sim` run

`native_sim` is a simulated Zephyr board that runs as an ordinary program on the host. Twister, Zephyr's test
runner, builds and runs every scenario of steps S1 to S5, as the `S1` job does:

```bash
bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && west twister -p native_sim/native/64 -T crux-controller/tests/native_sim --inline-logs --clobber-output -O twister-out'
```

It ends like this (quoted from a CI log, with the end of each line cut):

```text
INFO    - 17 of 17 executed test configurations passed (100.00%), 0 built (not run), 0 ...
INFO    - 31 of 31 executed test cases passed (100.00%) on 1 out of total ... platforms ...
```

All 17 Twister ids of the [scenario table](native-setup.md#run-the-s1-to-s5-scenarios) must be there and
passed. A lower count means that a scenario did not run.

To run one scenario, here step S1, point `-T` at its directory (this form is ordinary Twister usage and was not
run for this page):

```bash
bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && west twister -p native_sim/native/64 -T crux-controller/tests/native_sim/s1 --inline-logs --clobber-output -O twister-out-s1'
```

The Twister folders (`twister-out`, `twister-out-s1`) are in the workspace folder, next to the clone
(`~/work/crux-controller-workspace`), because the commands ran there; each scenario has its own build folder in
them, and `--inline-logs` prints the output of a failed scenario. Builds of the repository itself (for example
`build/host` of the host tests) are under `build/` in the clone, which `.gitignore` excludes. The S6 scenario
needs the Mbed TLS modules: [Run the S1 to S5 scenarios](native-setup.md#run-the-s1-to-s5-scenarios) shows
how.

No board? Parts A and B run every sample and test.

## Part C. Run on your board

Part C builds the image for a board and hands over to the board route. Building needs no board; programming one
does, together with the project owner's explicit authorisation for the task. The [roadmap](roadmap.md#what-has-run-on-a-board) records the
board runs.

| Board | `-b` target | Probe | Board guide |
|---|---|---|---|
| NXP RT1060-EVKB Rev B | `mimxrt1060_evk@B//qspi` | SEGGER J-Link | [Board route](board-bring-up.md) |

### 4. Build the image for the RT1060-EVKB

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

### 5. Program the board and read its log

Follow the [board route](board-bring-up.md) from its step 2: attach the probe, open the board container, compare
the flash read-only first, then `west flash`, observe the log and the network, restore the accepted normal
image and write the run record. Its stop conditions apply at every step. The route is untested on hardware, and nothing may touch a board without the project owner's explicit
authorisation for the task.

## Next steps

- Make a first change, from a branch to a pull request: [first-change.md](first-change.md).
- Pick the next page from the [README](../README.md#where-to-read-next), starting with the
  [roadmap](roadmap.md) and the [architecture](architecture.md).
- Look up a failure by its message: [troubleshooting.md](troubleshooting.md).
- The setup without the Dev Container and the S6 scenario: [Set up without the Dev Container](native-setup.md).
- The rules for a change: [CONTRIBUTING.md](../CONTRIBUTING.md).
