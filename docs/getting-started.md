# Getting started

This page sets up the environment and takes you to a first working command, on Linux or on Windows with WSL2,
without a board. The Dev Container is the route: one Docker image with the tools of the CI jobs. The
[Tutorial](tutorial.md) continues from here. The words west, workspace, Twister, `native_sim`, pin and Dev Container
are defined in the [glossary](glossary.md).

## Prerequisites

- An x86_64 Linux machine with Docker Engine, or Windows 11 with WSL2, an Ubuntu distribution (22.04 is fine) and
  Docker Engine inside it. Docker Desktop is not used.
- Git, and several GiB of free disk (see [Disk](#disk)).
- Network access to the hosts that the setup contacts, or a proxy configured as in [Proxy](#proxy).

**What is untested.** Nobody has run it on WSL2 yet. Not tested by anyone: the Dev Container on WSL2, Docker
Engine in a WSL2 distribution, the VS Code route, systemd in `/etc/wsl.conf`, a proxy or a company certificate,
and a run without a network. The Dev Container was not started on a developer machine at all. Only an x86_64 host
was exercised, and only in CI: the `devcontainer` workflow builds the image and runs the checks in it
([what CI runs](dev-container.md#what-the-container-is)). CI stays the reference: a local result does not replace
the CI result that a pull request cites ([why](architecture.md#why-the-evidence-comes-from-ci)).

## Dev Container

### Set up the Dev Container

For a teammate on Windows 11 with WSL2 and an Ubuntu 22.04 distribution; the same steps apply to a Linux machine
with Docker Engine. Run the commands in a WSL terminal, not in PowerShell, unless a step says PowerShell.

Behind a company proxy? Do the host part of
[Behind a proxy or with a company certificate](dev-container.md#behind-a-proxy-or-with-a-company-certificate) first: step 2 already
pulls an image.

1. Install Docker Engine in the distribution, as Docker describes for Ubuntu
   (<https://docs.docker.com/engine/install/ubuntu/>). Do not install Docker Desktop. Add yourself to the
   `docker` group, then close the terminal, run `wsl --shutdown` in PowerShell and open the distribution again,
   so that `docker` works without `sudo`:

   ```bash
   sudo usermod -aG docker "$USER"
   ```

2. Start the Docker daemon and check it. If systemd is enabled in the distribution, the daemon starts by itself.
   If not, start it after every `wsl --shutdown` and every reboot. Enabling systemd (`systemd=true` under
   `[boot]` in `/etc/wsl.conf`, then `wsl --shutdown`) is an option that nobody has tested here.

   ```bash
   sudo service docker start
   docker run --rm hello-world
   ```

3. Choose a parent folder of its own in the Linux home directory (not under `/mnt/c`), empty apart from the
   clone, and put the sources in a folder named exactly `crux-controller` in it, for example
   `~/work/crux-controller-workspace/crux-controller`. Replace `<repository-url>` with the address of the
   repository in your organisation; `core.autocrlf=false` keeps the LF line ends that the shell scripts need:

   ```bash
   mkdir -p ~/work/crux-controller-workspace && cd ~/work/crux-controller-workspace
   git clone -c core.autocrlf=false <repository-url> crux-controller
   cd crux-controller
   ```

4. First run. This builds the image, then runs `.devcontainer/setup.sh` in the container: it creates the virtual
   environment, fetches Zephyr and the modules with `west init -l` and `west update`, installs the Python
   requirements of Zephyr and installs the Zephyr SDK. It downloads several GiB and takes a long time (see
   [Network and prerequisites](dev-container.md#network-and-prerequisites)). Later runs find all of it already there.

   ```bash
   bash scripts/dev-shell.sh west --version
   ```

   It is done when the command returns with status 0 after these lines (the SDK and west versions are those of
   `.devcontainer/Dockerfile` and `.devcontainer/requirements-tools.txt`):

   ```text
   setup: workspace /workspaces/ws, Zephyr SDK 1.0.1, West version: v1.4.0
   West version: v1.4.0
   ```

   If it stops, the last line names the step:

   ```text
   setup: failed during <step>; rerun: bash .devcontainer/setup.sh
   ```

   Read the lines above it, fix the cause and run the same command again: the setup carries on where it stopped.

The checks that the `devcontainer` CI job runs also run through the same script; the
[Dev Container reference](dev-container.md#commands-inside-the-container) lists them. The VS Code route, the folder
layout and what to do after a pin or SDK change are in the [Dev Container reference](dev-container.md).

## Host notes

### WSL2

Work in a WSL terminal and in the Linux file system (your home directory), not under `/mnt/c`: builds are slow
there and file modes can differ. Zephyr builds and parallel Twister runs need more memory and CPUs than a small
default; set them in `%UserProfile%\.wslconfig` on Windows (`memory=` and `processors=` under `[wsl2]`) and run
`wsl --shutdown` in PowerShell for a change to apply. The [Dev Container reference](dev-container.md#what-you-need)
has an example.

### Proxy

Behind a proxy of your organisation, or with its certificate, do the host part of
[Behind a proxy or with a company certificate](dev-container.md#behind-a-proxy-or-with-a-company-certificate)
before step 2 of the set-up, because step 2 already pulls an image. The hosts that the setup contacts are listed
in [Network and prerequisites](dev-container.md#network-and-prerequisites).

### Disk

The first run needs several GiB: the image, the workspace folder with Zephyr and the modules, and the cache volume
with the Zephyr SDK and the virtual environment. Nothing in the repository states an exact size, and the first run
was not timed on a developer machine. [Layout](dev-container.md#layout) says where each part is and how to free it.

## Without the Dev Container

On Ubuntu 24.04 on x86_64 you can install the tools of the CI image on the host instead, with no Docker. A
distribution older than Ubuntu 24.04 cannot do it: Zephyr 4.4 needs Python 3.12, and Ubuntu 22.04 has 3.10. In
short, from a workspace folder of its own (`~/crux-ws`) with the clone in `crux-controller`:

1. Install the host packages of the `S1` job and `python3-venv`.
2. Create a virtual environment and install `cmake==3.28.4`, `ninja==1.11.1` and `west==1.4.0` in it.
3. Run `west init -l crux-controller` and `west update`, then install Zephyr's Python requirements.
4. Install the Zephyr SDK 1.0.1 with the `arm-zephyr-eabi` toolchain and set `ZEPHYR_SDK_INSTALL_DIR` and
   `ZEPHYR_BASE`.

It is done when `west --version` answers in the virtual environment, as in the Dev Container:

```text
West version: v1.4.0
```

[Set up without the Dev Container](native-setup.md) gives every command, and the commands of the tests on that
route. On macOS only part of this runs natively: the Python tooling tests, the boundary check, the SPDX check, the
format check (clang-format 18.1.8 from pip) and the host tests (sanitizers off and on), in a Git clone. The Zephyr
builds and the Twister runs need Linux or the Dev Container. Docker on macOS was not tried. The runs behind these
statements are in the [setup checks record](history/setup-checks.md).

## If you use a board

Nothing here needs a board. To run an image on the RT1060-EVKB you also need:

- a SEGGER J-Link probe on the board's debug port (an external probe, or the on-board debug probe if it runs
  J-Link firmware), and a way to read the UART log, as [What is needed](board-bring-up.md#what-is-needed) lists;
- on Windows, usbipd-win on the Windows side to pass the probe's USB device to WSL2;
- the J-Link software in the Dev Container, which the image build downloads and installs, as the board route's [J-Link step](board-bring-up.md#3-open-the-dev-container-with-the-probe) says. Without it the Dev Container works for everything except a board.

The [board route](board-bring-up.md) gives the steps. It is untested on hardware, and nothing may touch a board
without the project owner's explicit authorisation for the task.

## If something fails

Look the message up in [troubleshooting.md](troubleshooting.md); it lists every message of `scripts/dev-shell.sh`,
`.devcontainer/setup.sh` and `.devcontainer/check-host.sh` with the cause and the fix. After a fix, run the same
command again: the setup skips what is done. A failure that appears only on your machine may be a difference in the
host; CI is the reference.

## Next steps

Follow the [Tutorial](tutorial.md): the host tests, the `native_sim` scenarios and the board build.
