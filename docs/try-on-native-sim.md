# How to try it without a board

This page is for a teammate who wants to see the firmware's tests run and has no RT1060-EVKB at hand.
Terms are in the [glossary](glossary.md), the layout is in the [architecture](architecture.md), and what has
and has not run on a board is in the [roadmap](roadmap.md).

**These commands are copied from the CI workflow (`.github/workflows/ci.yml`) and from
[CONTRIBUTING.md](../CONTRIBUTING.md); the page's author did not run them locally.** The commands in
`ci.yml` are the ones CI runs, on `ubuntu-24.04`. [CONTRIBUTING.md](../CONTRIBUTING.md) says: "The Zephyr
builds and the Twister runs happen in CI only. This repository describes no local Zephyr build". So this
page does not promise that the Zephyr commands work on your machine, and it makes no statement about how
long they take or how much disk they use, because nothing in the repository says.

## What `native_sim` is

`native_sim` is a simulated Zephyr board. Zephyr builds the application into an ordinary program that runs
on the build host, with emulated devices instead of hardware. It is not a board: no Ethernet PHY, no
microSD card, no watchdog peripheral and no RT1060 is involved. A passing `native_sim` run is not a board
run, and the roadmap says so for every step.

In this repository the `native_sim` scenarios are Zephyr ztest applications under `tests/native_sim`, one
directory per step from S1 to S5. Each one compiles chosen sources of `app/` and `workload/`; none boots the
board image (see the glossary entry for `native_sim`). The scenarios are run through Twister, Zephyr's test
runner, for the platform `native_sim/native/64`.

## What you need first

At a high level, as the workflow sets it up:

- A west workspace. The repository is the west manifest repository: it imports `crux-pilot` at a pinned
  commit, which brings Zephyr and the Zephyr modules, and adds the test-only project `picolibc` for the S2
  scenario (the S5 scenario's `prj.conf` also selects it). `docs/dependencies.md` explains the manifest and the pin, and the pin section of
  [CONTRIBUTING.md](../CONTRIBUTING.md) explains how it moves.
- The Python packages of Zephyr's base, build-test and run-test requirements, `west` 1.4.0, CMake 3.28.4 and
  Ninja 1.11.1 (the versions that the `S1` job installs).
- A host toolchain and the host packages that the `S1` job installs, listed in the first block below.
- The job also installs a Zephyr SDK, version 1.0.1, with the `arm-zephyr-eabi` toolchain. Whether a
  `native_sim` run alone needs it is not verified here.

The `S1` job's setup, copied from `ci.yml`. In CI the repository is checked out into a directory named
`crux-controller` in the workspace directory, and the commands below run from the workspace directory, one
level above the checkout:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  build-essential gcc-multilib ca-certificates device-tree-compiler file gperf git \
  libmagic1 libsdl2-dev pkg-config python3-dev wget xz-utils
```

```bash
python -m pip install cmake==3.28.4 ninja==1.11.1 west==1.4.0
```

```bash
west init -l crux-controller
west update
python -m pip install -r zephyr/scripts/requirements-base.txt \
  -r zephyr/scripts/requirements-build-test.txt \
  -r zephyr/scripts/requirements-run-test.txt
```

The SDK step of the job, which runs from the `zephyr` directory, only when its cache misses, with
`SDK_VERSION` set to `"1.0.1"` and `GH_TOKEN` set to the workflow's token. `ZEPHYR_SDK_INSTALL_DIR` is
`<workspace>/sdk/zephyr-sdk-1.0.1`:

```bash
west sdk install --version "$SDK_VERSION" --install-base "$GITHUB_WORKSPACE/sdk" \
  --gnu-toolchains arm-zephyr-eabi --personal-access-token "$GH_TOKEN"
```

## Run the S1 to S5 scenarios

One command runs every scenario, because it points Twister at the whole `tests/native_sim` directory. The
job sets `ZEPHYR_BASE` to `<workspace>/zephyr` for it:

```bash
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim \
  --inline-logs --clobber-output -O twister-out
```

The repository contains no command that runs one scenario alone, and this page does not invent one.

The scenarios that this command finds, by their ids in the `testcase.yaml` files:

| Step | Twister ids |
|---|---|
| S1 | `controller.s1.native_sim` |
| S2 | `controller.s2.native_sim` |
| S3 | `controller.s3.native_sim.not_ready`, `.mounted_not_bound`, `.mount_failure`, `.roundtrip`, `.bind_failure` |
| S4 | `controller.s4.native_sim.reset_cause`, `.watchdog_unsupported`, `.period_out_of_range` |
| S5 | `controller.s5.native_sim.first_sync`, `.kiss_of_death`, `.late_answer`, `.out_of_range`, `.step_refused_then_resync`, `.correction_and_threshold`, `.stale_after_silence` |

S3, S4 and S5 build one image per case (a build variable such as `S5_CASE`), so one `west twister` run builds
one image per Twister id in the table. What a scenario can and cannot show is stated in its findings note and in the
header of its test source; for example, the simulator has no watchdog, so S4's scenario shows no feed cycle.

What a passing run looks like: no file in the repository states what a passing Twister run prints, so this
page does not either. The CI job runs the command above as one step and its next steps build for the board;
read the checks of a commit on GitHub for the real outcome.

## Run the host tests

These are plain C tests of the portable core, the S2 exchange and the policy code, built with CMake on the build host.
They need no Zephyr. The `Host tests` job runs them twice, once with the sanitizers off and once on. The
commands, copied from `ci.yml` with the matrix value filled in (`OFF`, then `ON`):

```bash
cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=OFF
cmake --build build/host
ctest --test-dir build/host --output-on-failure
```

```bash
cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=ON
cmake --build build/host
ctest --test-dir build/host --output-on-failure
```

In these two commands the second run reuses the build directory of the first (in CI each matrix leg
starts on a fresh runner); whether to delete it between runs is not stated
anywhere in the repository. These commands run from the repository root (the `Host tests` job checks the
repository out without a separate path). The host tests are `tests/host/test_workload.c`,
`test_net_client.c`, `test_health_policy.c` and `test_time_sync_policy.c`. Each of the four ends by printing
`<n> checks, <m> failures` and returns a non-zero exit status when `m` is not zero; that is what their
source says. So a passing host test prints `0 failures`.

## Run the tooling tests and the boundary check

These are Python tests of the scripts, workflows, documents and build files, plus the include check.
[CONTRIBUTING.md](../CONTRIBUTING.md) describes them as the checks that run locally. The commands, as it
gives them (CI installs `pyyaml` and runs the same `unittest` command with Python 3.12):

```bash
python3 -m venv .venv && . .venv/bin/activate && python -m pip install pyyaml
python -m unittest discover -s tests/tooling -v
python scripts/check_boundary.py
```

## If something fails

CI is the reference. The checks of a commit on GitHub show the same jobs that these commands come from. A
failure that appears only on your machine may be a difference in the host, the toolchain or the workspace
that this page cannot predict; it has no list of such differences. Any change to the boundary lists, the
workflows or the other protected files is a reviewed change under [CONTRIBUTING.md](../CONTRIBUTING.md), not
a fix for a local failure.
