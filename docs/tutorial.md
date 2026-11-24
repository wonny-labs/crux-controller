# Tutorial: your first build and run

This tutorial takes you from a working Dev Container to the host tests, the `native_sim` scenarios and a board
image. Each step gives the command and what you should see. Part A runs the host tests and the checks, Part B runs
the `native_sim` scenarios of the product, and Part C builds the image for a board and points at the board route.

## Prerequisites and the Dev Container

Finish [Getting started](getting-started.md#set-up-the-dev-container) first: the clone in a folder named
`crux-controller` under a parent folder of its own, and a first run of the Dev Container that ends with
`West version: v1.4.0`. Then pick one route for the commands of this page:

- **Command line.** Run each command through `bash scripts/dev-shell.sh`, as written below. The script runs it in
  the Dev Container with the repository as the working directory.
- **VS Code** with the Dev Containers extension. Open the clone folder and run
  **Dev Containers: Reopen in Container**. In its terminal, run the commands without the
  `bash scripts/dev-shell.sh` prefix.

Every command runs from the repository root.

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
bash scripts/dev-shell.sh python scripts/check_boundary.py --crux-root ../crux-pilot
```

The tests end with `Ran <n> tests in <t>s` and `OK` (or `OK (skipped=<m>)`), and the check prints
`boundary check passed`. The other checks of CI (format, static analysis, SPDX) run through the same script, for
example `bash scripts/dev-shell.sh bash scripts/check-format.sh`;
[Commands inside the container](dev-container.md#commands-inside-the-container) lists them.

## Part B. The `native_sim` scenarios

### 3. One `native_sim` run

`native_sim` is a simulated Zephyr board that runs as an ordinary program on the host. Twister, Zephyr's test
runner, builds and runs every scenario of `workload` to `sntp`, as the `workload` job does:

```bash
bash scripts/dev-shell.sh west twister -p native_sim/native/64 -T tests/native_sim --inline-logs --clobber-output -O twister-out
```

It ends like this (the end of each line cut):

```text
INFO    - 17 of 17 executed test configurations passed (100.00%), 0 built (not run), 0 ...
INFO    - 31 of 31 executed test cases passed (100.00%) on 1 out of total ... platforms ...
```

All 17 Twister ids of the [scenario table](native-setup.md#run-the-workload-to-sntp-scenarios) must be there and
passed. A lower count means that a scenario did not run.

Twister writes its output to `twister-out` in the clone, with a build folder for each scenario, and
`--inline-logs` prints the output of a failed scenario. The host tests build under `build/`. `.gitignore` excludes
both. The `management` scenario needs the Mbed TLS modules:
[Run the `workload` to `sntp` scenarios](native-setup.md#run-the-workload-to-sntp-scenarios) shows how.

## Part C. Run on your board

Part C builds the image for a board and hands over to the board route. Building needs no board. Running one needs
the owner's authorisation ([glossary](glossary.md#people-and-board-procedures)). The
[roadmap](roadmap.md#what-has-run-on-a-board) records the board runs.

| Board | `-b` target | Probe | Board guide |
|---|---|---|---|
| NXP RT1060-EVKB Rev B | `mimxrt1060_evk@B//qspi` | SEGGER J-Link | [Board route](board-bring-up.md) |

### 4. Build the image for the RT1060-EVKB

This is the cross-build of `workload` that the `workload` job of CI runs:

```bash
bash scripts/dev-shell.sh west build -p always -b 'mimxrt1060_evk@B//qspi' -d build/workload app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON -DEXTRA_CONF_FILE=conf/workload.conf
```

The image is `build/workload/zephyr/zephyr.bin` in the clone, next to `zephyr.meta`.

### 5. Flash and debug the board

[Board bring-up](board-bring-up.md) links the Crux board page for the probe, flash and debug, and adds this
repository's image and the log to expect.

## Next steps

- Make a first change, from a branch to a pull request: [first-change.md](first-change.md).
- Look up a failure by its message: [troubleshooting.md](troubleshooting.md).
- Pick the next page from the [README](../README.md#where-to-read-next).
