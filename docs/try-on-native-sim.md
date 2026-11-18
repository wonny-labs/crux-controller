# How to try it without a board

This page is for a teammate who wants to see the firmware's tests run and has no RT1060-EVKB at hand.
Terms are in the [glossary](glossary.md), the layout is in the [architecture](architecture.md), and what has
and has not run on a board is in the [roadmap](roadmap.md).

Everything below runs on Linux: Ubuntu 24.04 (the CI image), native or under WSL2. On Windows use WSL2 and work
in the Linux file system (your home directory), not under `/mnt/c`: the builds are slow and file modes can
differ there. Clone with `git clone -c core.autocrlf=false` if your Git for Windows settings could reach the
clone, because CRLF line ends make `scripts/check-format.sh` fail. CI runs on x86_64 only.

If your distribution is older than Ubuntu 24.04 (Zephyr 4.4 needs Python 3.12, and Ubuntu 22.04 has 3.10) or you
would rather not install the tools on the host, use the [dev container](#dev-container) instead of the setup below.

The commands come from the CI workflow (`.github/workflows/ci.yml`, job `S1`, on `ubuntu-24.04`) and from
[CONTRIBUTING.md](../CONTRIBUTING.md), with the CI-only variables replaced by local values. What was run
locally, and what was not, is in [What has been checked](#what-has-been-checked). CI stays the reference:
a local result is a convenience and does not replace the CI result that a pull request cites.

## Why the evidence comes from CI

[CONTRIBUTING.md](../CONTRIBUTING.md) says that CI is the reference for the Zephyr builds and the Twister runs, that
this page gives the CI commands for a local `native_sim` run, that a local result does not replace CI, and that a
change to `app/`, `conf`, overlays or `tests/native_sim` takes its evidence from CI, with the pull request saying so.
It states the rule and gives no reason. What the repository's own files show:

- CI is one environment with pinned versions: `ubuntu-24.04` on x86_64, Python 3.12, CMake 3.28.4, Ninja 1.11.1,
  west 1.4.0, the Zephyr SDK 1.0.1 and a fixed package list (`.github/workflows/ci.yml`). A reviewer can open the
  same job logs for every change, and a number in them (a size, a Twister count, an image hash) was produced under
  the same conditions as the one before it.
- A local environment differs in ways that matter. For example, GCC in CI rejected a comparison between constants of two
  anonymous enums (`-Werror=enum-compare`) that the Apple clang on a developer's machine had accepted
  ([adding-a-step.md](adding-a-step.md)). CI covers only x86_64 Ubuntu, and so does the job that runs the
  [dev container](#dev-container). Apart from the setup steps listed under
  [What has been checked](#what-has-been-checked), arm64 and WSL2 are untested, and nobody has run the dev container
  on WSL2.
- A Zephyr workspace is large. `west update` and the SDK install take a long time and a lot of disk (see
  [What you need first](#what-you-need-first)), so a local build is optional.

GitHub Actions logs expire (the default retention is 90 days), so the run numbers in the Recorded rows of the
findings will stop resolving, and so will the logs behind the roadmap table; that is why the results themselves are
copied into those notes.

So the commands below are a convenience for finding a failure before you push. A local pass does not replace the
CI result in a pull request, and a local failure that CI does not show is a difference in your host to look at, not
a reason to change a check.

## What `native_sim` is

`native_sim` is a simulated Zephyr board. Zephyr builds the application into an ordinary program that runs
on the build host, with emulated devices instead of hardware. It is not a board: no Ethernet PHY, no
microSD card, no watchdog peripheral and no RT1060 is involved. A passing `native_sim` run is not a board
run, and the roadmap says so for every step.

In this repository the `native_sim` scenarios are Zephyr ztest applications under `tests/native_sim`, one
directory per step from S1 to S5, and the S6 scenario in `tests/native_sim_mbed`, which needs the Mbed TLS modules of the Crux manifest and is run by its own CI job. Each one compiles chosen sources of `app/` and `workload/`; none boots the
board image (see the glossary entry for `native_sim`). The scenarios are run through Twister, Zephyr's test
runner, for the platform `native_sim/native/64`.

## What you need first

- A west workspace. The repository is the west manifest repository: it imports `crux-pilot` at a pinned
  commit, which brings Zephyr and the Zephyr modules, and adds the test-only project `picolibc` for the S2
  scenario (the S5 scenario's `prj.conf` also selects it). `docs/dependencies.md` explains the manifest and
  the pin, and the pin section of [CONTRIBUTING.md](../CONTRIBUTING.md) explains how it moves.
- The Python packages of Zephyr's base, build-test and run-test requirements, `west` 1.4.0, CMake 3.28.4 and
  Ninja 1.11.1 (the versions that the `S1` job installs), in one virtual environment for the workspace.
- A host toolchain and the host packages that the `S1` job installs, plus `python3-venv`, which the job does
  not need because `actions/setup-python` provides Python. Ubuntu 24.04 refuses `pip install` into the system
  Python (PEP 668), so do not skip the virtual environment.
- The Zephyr SDK 1.0.1 with the `arm-zephyr-eabi` toolchain, which the `S1` job installs before it runs
  Twister. It is needed for the board build. Whether a `native_sim` run alone needs it was not tested;
  install it anyway, as CI does.
- Free disk space for Zephyr, its modules and the SDK. Nothing in the repository states a size.

The workspace directory holds the clone, the `.west` directory, `zephyr/`, `modules/` and the virtual
environment. The clone must be named `crux-controller`, because `west.yml` sets `self: path: crux-controller`
and a test pins it. Do not clone into your home directory itself: `west init -l` would put `.west`, `zephyr/`
and `modules/` there.

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  build-essential gcc-multilib ca-certificates device-tree-compiler file gperf git \
  libmagic1 libsdl2-dev pkg-config python3-dev python3-venv wget xz-utils
```

`gcc-multilib` is in the CI list, and CI runs on x86_64 only. The package does not exist on arm64 hosts, and
whether `native_sim/native/64` builds and runs on an arm64 host was not checked.

```bash
mkdir -p ~/crux-ws && cd ~/crux-ws
git clone https://github.com/wonny-labs/crux-controller.git crux-controller
python3 -m venv .venv && . .venv/bin/activate
python -m pip install cmake==3.28.4 ninja==1.11.1 west==1.4.0
west init -l crux-controller
west update
python -m pip install -r zephyr/scripts/requirements-base.txt \
  -r zephyr/scripts/requirements-build-test.txt \
  -r zephyr/scripts/requirements-run-test.txt
```

`west update` fetches Zephyr and the modules from GitHub. It takes a while and uses a lot of disk.

The SDK step. CI runs it from the `zephyr` directory, with the version and the install base taken from the
workflow's variables, and passes the workflow's token. Locally the values are concrete, and the token is not
needed (it only avoids GitHub's rate limit for anonymous requests; add `--personal-access-token` with your own
token if you hit it):

```bash
cd zephyr
west sdk install --version 1.0.1 --install-base "$HOME" --gnu-toolchains arm-zephyr-eabi
cd ..
export ZEPHYR_SDK_INSTALL_DIR="$HOME/zephyr-sdk-1.0.1"
export ZEPHYR_BASE="$PWD/zephyr"
```

The two `export` lines mirror the `env` of the CI steps. Every later command on this page runs from
`~/crux-ws` with the virtual environment active (`. .venv/bin/activate`) and, for Twister, with these two
variables set, unless a section says to use the repository root. Paths such as
`crux-controller/tests/native_sim` are relative to `~/crux-ws`.

## Run the S1 to S5 scenarios

One command runs every scenario, because it points Twister at the whole `tests/native_sim` directory. The
job sets `ZEPHYR_BASE` to `<workspace>/zephyr` for it, as the `export` above does:

```bash
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim \
  --inline-logs --clobber-output -O twister-out
```

To run one scenario, point `-T` at its directory. This is ordinary Twister usage and was not run for this
page (each directory holds one `testcase.yaml`; S3, S4 and S5 build one image per case):

```bash
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim/s1 \
  --inline-logs --clobber-output -O twister-out-s1
```

A pass ends with lines like these. They are quoted from the CI log of the `ci` run for `main` at revision `fa11293` of the public
repository (17 November 2026), where Twister ran the whole directory:

```text
INFO    - 17 of 17 executed test configurations passed (100.00%), 0 built (not run), 0 ...
INFO    - 31 of 31 executed test cases passed (100.00%) on 1 out of total ... platforms ...
```

Counts change when a scenario is added, so read them as an example. The tail of the Twister output is what to
compare, together with the Twister ids in the table below: all 17 must be present and passed, and a count
lower than the table lists means that a scenario did not run.

The S6 scenario is in a sibling directory, `tests/native_sim_mbed`, so that this command never selects it in a
workspace that has no Mbed TLS modules. The default workspace above does not have them: the group
`crux-secure-management` is off in `west.yml`, and the S6 build fails without the modules. The `S6 build` job
switches the group on in its own runner, after `scripts/check_mbed_only.py` has checked that only the Mbed TLS
modules would be fetched. To run S6 locally, repeat those steps (from `ci.yml`) in your workspace, with the
virtual environment active:

```bash
west list --all -f '{name} {active}' > list-default.txt
python crux-controller/scripts/check_mbed_only.py --mode default < list-default.txt
west config --local manifest.group-filter -- +crux-secure-management
west list --all -f '{name} {active}' > list-mbed.txt
python crux-controller/scripts/check_mbed_only.py --mode mbed --baseline list-default.txt < list-mbed.txt
west update
for name in wolfssl wolfssh wolfpsa; do test ! -e "modules/crypto/$name" || echo "unexpected $name"; done
for name in mbedtls tf-psa-crypto; do test -d "modules/crypto/$name" || echo "missing $name"; done
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim_mbed \
  --inline-logs --clobber-output -O twister-out-s6
west config --local -d manifest.group-filter
```

The two `for` loops are CI's check after the fetch (CI exits on a finding; here they print a line): no wolf
project may be on disk and both Mbed modules must be. The checks before `west update` stop the run if the group would fetch anything beyond the Mbed TLS modules. The
fetch adds Mbed TLS and TF-PSA-Crypto, which are distributed as Apache-2.0 OR GPL-2.0-or-later. The last line
puts the workspace back to the default filter; the fetched modules stay on disk. CI also installs the same
Python requirement files after this `west update`, which the first setup already did. A passing run prints
`1 of 1 executed test configurations passed` and `10 of 10 executed test cases passed`, as in the CI log of
the same run.

It is one image with ten ordered cases: the start sequence, the certificate, a TLS 1.3 handshake that the client
verifies, a TLS 1.2-only client that is refused, plain HTTP that is not answered, the page bytes and four requests of
the login path. It shows none of a successful login, handshake time, stack use, key strength (the simulator's
entropy is a fake source) or a browser.

Case 4 connects a control client with a TLS 1.3 suite first, and then a client with only a TLS 1.2 suite, which must fail
with an errno that is neither a refused connection nor a timeout. A refusal on the client side cannot be fully excluded in one
process, because the client and the server share the TLS library, the credentials and the clock. Crux's own check of the
version refusal uses `openssl s_client` against its listener (`docs/https-composition.md` in `crux-pilot`, "Checked on the
wire"), and this case does not replace it.

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
header of its test source; for example, S4's scenario does not enable the simulated watchdog of the pinned Crux, so it shows no feed
cycle.

The `S1` job runs the command above as one step and its next steps build for the board. Read the checks of
a commit on GitHub for the real outcome.

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
cmake -S tests/host -B build/host-asan -G Ninja -DWORKLOAD_SANITIZE=ON
cmake --build build/host-asan
ctest --test-dir build/host-asan --output-on-failure
```

Use a different build directory for the second run (for example `build/host-asan`) so that it does not reuse the
first one; CI starts each matrix leg on a fresh runner. These commands run from the repository root
(`~/crux-ws/crux-controller`; the `Host tests` job checks the repository out without a separate path). They need
CMake 3.20 or newer, Ninja and a C compiler; the virtual environment above provides the first two. One host
test, `test_net_client`, listens on the fixed address `127.0.0.1:42431`, so two runs at the same time fail
with "cannot listen".

The host tests are `tests/host/test_workload.c`, `test_net_client.c`, `test_health_policy.c`,
`test_time_sync_policy.c` and `test_management_policy.c`. Each of the five ends by printing
`<n> checks, <m> failures` and returns a non-zero exit status when `m` is not zero; that is what their
source says. A passing run of the five prints `0 failures` for each, and CTest ends with
`100% tests passed, 0 tests failed out of 5` (the line in the CI log of the run named above).

## Run the tooling tests and the boundary check

These are Python tests of the scripts, workflows, documents and build files, plus the include check.
[CONTRIBUTING.md](../CONTRIBUTING.md) describes them as the checks that run locally. They need only PyYAML. From
the repository root, with the workspace virtual environment active (or a new one, as CONTRIBUTING shows):

```bash
cd ~/crux-ws/crux-controller
python -m pip install pyyaml
python -m unittest discover -s tests/tooling -v
python scripts/check_boundary.py
```

A pass ends the test run with `Ran <n> tests` and `OK`, and the check prints `boundary check passed`.

CI runs a stronger form of the boundary check, against the headers of the pinned `crux-pilot`, and a second
check from `crux-pilot`. From the workspace directory:

```bash
cd ~/crux-ws
python crux-controller/scripts/check_boundary.py --repo crux-controller --crux-root crux-pilot
python crux-pilot/templates/product/check_domain_includes.py --product crux-controller
```

Run from the wrong directory, `check_boundary.py` finds none of its trees and fails with status 2 and a message;
it does not print a pass. [composition-zone.md](composition-zone.md#running-the-check) explains both commands.

## Dev container

A dev container is a Docker image with the host packages and tools of the CI jobs, an Ubuntu 24.04 userland and
Python 3.12, plus a script that fetches the west workspace and the Zephyr SDK. It is for a teammate whose Linux is
older than 24.04, for example an Ubuntu 22.04 distribution under WSL2, and it needs **Docker Engine only: no Docker
Desktop**.

**Nobody has run it on WSL2 yet.** Neither the Dev Containers extension in VS Code nor Docker Engine in a WSL2
distribution has been used with these files, and only an x86_64 host was exercised, and only in CI. What does run
is CI: the workflow `devcontainer.yml` builds the same image on an Ubuntu 24.04 x86_64 runner, runs
`scripts/dev-shell.sh` and, inside the container, the tooling tests, the format check, the static analysis, the host
tests (sanitizers off and on), both boundary checks, the `native_sim` scenarios of
[the S1 to S5 section](#run-the-s1-to-s5-scenarios) and the RT1060-EVKB cross-build of step S1 (with the baseline
gate required) with its output and configuration checks, using the Zephyr SDK that `setup.sh` installs. That is a
run of the image and the scripts, not of VS Code or of WSL2 (see [What has been checked](#what-has-been-checked)).
If a step fails for you, open an issue with the output.

The container is not the CI runner. It uses Ubuntu's Python 3.12 (not pinned to a patch release) where CI uses
`actions/setup-python`, a devcontainers base image where CI uses the runner image, pip's cmake and ninja where the
`Host tests` job uses the runner's, `clang-tidy-18` installed without its recommended packages, the extra packages
`python3-venv` (for the virtual environment), `curl` and `sudo` (for the setup script), and PyYAML pinned. The
Zephyr requirement files are not pinned, as in CI.

The files are `.devcontainer/devcontainer.json` (for VS Code), `.devcontainer/Dockerfile` (the image, with the base
image pinned by digest), `.devcontainer/requirements-tools.txt` (the pinned Python tools),
`.devcontainer/setup.sh` (the workspace and SDK setup) and `scripts/dev-shell.sh` (the same without VS Code). The
versions follow `ci.yml`, and a tooling test compares them.

### What you need

1. WSL2 with a Linux distribution, and your files in its Linux file system (not under `/mnt/c`).
2. Docker Engine inside the distribution, installed as Docker describes for Ubuntu:
   <https://docs.docker.com/engine/install/ubuntu/>. Do not install Docker Desktop. Then add yourself to the
   `docker` group and start a new WSL session, so that `docker` works without `sudo`:

   ```bash
   sudo usermod -aG docker "$USER"
   # in PowerShell: wsl --shutdown, then open the distribution again
   docker run --rm hello-world
   ```

   The Docker service must be running in the distribution. If it is not started for you (WSL2 needs systemd
   enabled for that), start it with `sudo service docker start`. The image is `linux/amd64`, the architecture of a
   Windows PC, and only an x86_64 host was exercised, and only in CI. On an arm64 host Docker Engine needs amd64
   emulation (binfmt handlers for QEMU) registered first, or the build fails with "exec format error"; that was not
   tested.
4. Memory and CPUs for WSL2. Zephyr builds and parallel Twister runs need more than a small default. WSL2 gets a
   share of the machine's memory and all its logical processors unless `%UserProfile%\.wslconfig` on Windows says
   otherwise, for example (the numbers are an example, not a measured requirement):

   ```ini
   [wsl2]
   memory=12GB
   processors=6
   ```

   Run `wsl --shutdown` in PowerShell for a change to apply.
3. For VS Code: Visual Studio Code on Windows with the WSL extension and the Dev Containers extension.

Nothing in the files uses `host.docker.internal`, the Docker socket or a mount of your home directory.

### Layout

The dev container mounts the parent folder of the clone as the west workspace, so that `.west/`, `zephyr/` and
`modules/` (several GiB; no size was measured) are on your Linux file system and survive a rebuild of the image.
Use a folder of its own, and name the clone `crux-controller`, because `west.yml` requires that name. The setup
script stops with a message if the clone has another name or if the parent folder is a home directory.

```bash
mkdir -p ~/work/controller-ws && cd ~/work/controller-ws
git clone -c core.autocrlf=false https://github.com/wonny-labs/crux-controller.git crux-controller
```

Inside the container the workspace is `/workspaces/ws` and the repository is `/workspaces/ws/crux-controller`. The
Zephyr SDK and the virtual environment (cmake, ninja, west, clang-format, PyYAML and the Python requirements of
Zephyr) are in a Docker volume of this workspace folder (`crux-controller-dev-cache-<id>`, see `docker volume ls`),
mounted at `/opt/crux-cache`. The variables
`ZEPHYR_BASE` and `ZEPHYR_SDK_INSTALL_DIR` are set, as the CI steps set them.

### With VS Code

Open the clone from a WSL terminal, so that VS Code runs in WSL and finds Docker there:

```bash
cd ~/work/controller-ws/crux-controller
code .
```

Run "Dev Containers: Reopen in Container". The first start builds the image and runs `.devcontainer/setup.sh`,
which does `west init -l crux-controller` and `west update` only when the workspace does not exist yet, installs the
Python requirements of Zephyr and runs `west sdk install` for the SDK version of the CI jobs. That takes a long time
and downloads several GiB; watch the creation log. Later starts and rebuilds find all of it already there. If the
creation fails or is interrupted, run `bash .devcontainer/setup.sh` in a terminal of the container: it carries on,
and it runs `west update` again if the first one did not finish. After a change of the pin in `west.yml`, run `west update` by hand: the setup script does not run it
again.

### Without VS Code

```bash
cd ~/work/controller-ws/crux-controller
scripts/dev-shell.sh            # a shell in the container, in the repository
scripts/dev-shell.sh <command>  # one command, with the repository as working directory
```

The script builds the image, runs `.devcontainer/setup.sh` and then your command, as the same numeric user as
yours, so that the files it writes into the workspace belong to you. Set `GH_TOKEN` to avoid GitHub's rate limit
for the SDK download.

### Commands inside the container

Run them in the container's terminal (or after `scripts/dev-shell.sh`). The scenarios run from the workspace
directory, as in the sections above.

```bash
cd /workspaces/ws
# S1 to S5, all scenarios of tests/native_sim, as the S1 job does
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim \
  --inline-logs --clobber-output -O twister-out
# S1 only
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim/s1 \
  --inline-logs --clobber-output -O twister-out-s1
# S2 only
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim/s2 \
  --inline-logs --clobber-output -O twister-out-s2
```

From the repository (`/workspaces/ws/crux-controller`):

```bash
cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=OFF
cmake --build build/host && ctest --test-dir build/host --output-on-failure
python -m unittest discover -s tests/tooling -v
./scripts/check-format.sh
python scripts/analyze_host.py
cd .. && python crux-controller/scripts/check_boundary.py --repo crux-controller --crux-root crux-pilot
```

The board build of step S1, as the `S1` job runs it (the SDK is already installed):

```bash
cd /workspaces/ws
west build -p always -b 'mimxrt1060_evk@B//qspi' -d crux-controller/build/s1 \
  crux-controller/app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON -DEXTRA_CONF_FILE=conf/s1.conf
```

`CLANG_TIDY` is set in the image, as the static analysis job needs it. The optional S6 steps, the stronger boundary
check and the product include check of the sections above work unchanged from `/workspaces/ws` (the pinned
`crux-pilot` contains the product include check); the container does not switch the Mbed TLS group on by itself. The container does not reach a board: there is no USB or probe
passthrough, and a `native_sim` run is not a board run.

### If the dev container fails

- `permission denied` on `/var/run/docker.sock`: you are not in the `docker` group yet, or the session predates the
  change. Restart WSL as above.
- "the clone is in a folder named ...": rename the clone folder to `crux-controller`.
- If the creation of the container failed, open a terminal in it (or run `scripts/dev-shell.sh`) and run
  `bash .devcontainer/setup.sh` again. It skips what is done and repeats an interrupted `west update`.
- To start from nothing, remove the cache volume of the workspace (`docker volume ls`, then
  `docker volume rm crux-controller-dev-cache-<id>`, with no container using it). The workspace folder next to the clone is yours: delete `.west/`, `zephyr/` and `modules/` there only if you
  want a new `west init`.
- CI is still the reference for a pull request. The Native route in the sections above stays valid on Ubuntu 24.04.

## If something fails

CI is the reference. The checks of a commit on GitHub show the same jobs that these commands come from. A
failure that appears only on your machine may be a difference in the host, the toolchain or the workspace
that this page cannot predict; it has no list of such differences. Any change to the boundary lists, the
workflows or the other files that CONTRIBUTING.md treats as reviewed (a reading aid is in
[adding-a-step.md](adding-a-step.md#files-that-need-a-reviewed-change)) is a reviewed change under
[CONTRIBUTING.md](../CONTRIBUTING.md), not a fix for a local failure.

## What has been checked

- The venv block (`python3 -m venv`, `pip install` of the pinned tools, `west init -l`)
  was run in a fresh `ubuntu:24.04` container on 18 November 2026 (arm64, Python 3.12.3), after
  `apt-get install python3-venv python3-dev git ca-certificates`. The clone was copied in from a local checkout,
  so the `git clone` command and the full `apt-get` package list were not run. It confirmed that there is no
  `python` command before the virtual environment exists, that `west 1.4.0` installs in it and that
  `west init -l crux-controller` creates `.west` in the workspace directory.
- WSL2 was not tested. Only that arm64 `ubuntu:24.04` container ran those steps.
- Not run for this page: `west update`, the SDK install, Twister, the S6 group steps and the host tests on
  a fresh machine. Their commands are those of the CI jobs with the variables replaced, and the tooling
  tests and the boundary commands ran on a macOS host. If a step here fails on your machine, open an issue
  with the output.
- The dev container (`.devcontainer/`, `scripts/dev-shell.sh`) was not started on a developer machine at all, and
  nobody has used it with WSL2, Docker Engine in WSL2 or the Dev Containers extension. Its files were checked by
  tooling tests (versions against `ci.yml`, the base image digest, no Docker Desktop feature, no write permission or
  upload in the workflow), and the workflow `devcontainer.yml` runs the image and `scripts/dev-shell.sh` on an
  Ubuntu 24.04 x86_64 GitHub runner (the checks listed in the dev container section, including the S1 cross-build). The result of that job for the revision that you are reading is in the checks of the
  commit on GitHub.
