# Getting started

This page sets up the environment and takes you to a first working command, on x86_64 Linux without a board.
The Dev Container is the route: one Docker image with the tools of the CI jobs. The [Tutorial](tutorial.md)
continues from here. The words west, workspace, Twister, `native_sim`, pin and Dev Container are defined in the
[glossary](glossary.md).

## Prerequisites

- An x86_64 Linux machine with Docker Engine. This is the supported route: the `devcontainer` workflow builds the
  image and runs the checks in it ([what CI runs](dev-container.md#what-the-container-is)).
- Git, and several GiB of free disk (see [Host notes](#host-notes)).
- Network access to the hosts that the setup contacts, or a proxy configured as in
  [Behind a proxy or with a company certificate](dev-container.md#behind-a-proxy-or-with-a-company-certificate).
- If your network's proxy re-signs TLS, downloads in the image build or in the container fail with a certificate
  error such as `curl: (60) SSL certificate problem: unable to get local issuer certificate`, or the same from pip,
  Git or west. Put your organisation's root CA as a PEM `.crt` file in `.devcontainer/certs/` before the first
  run, never in a commit; the [folder README](../.devcontainer/certs/README.md) gives the steps.

CI is the reference: a local result does not replace the CI result that a pull request cites
([why](architecture.md#why-the-evidence-comes-from-ci)). See the
[setup checks record](history/setup-checks.md).

## Dev Container

### Set up the Dev Container

Behind a company proxy? Do the host part of
[Behind a proxy or with a company certificate](dev-container.md#behind-a-proxy-or-with-a-company-certificate) first:
the first run already pulls an image.

1. Install Docker Engine, as Docker describes for Ubuntu (<https://docs.docker.com/engine/install/ubuntu/>) and for
   running `docker` without `sudo` (<https://docs.docker.com/engine/install/linux-postinstall/>), then check it:

   ```bash
   sudo usermod -aG docker "$USER"
   docker run --rm hello-world
   ```

2. Choose a parent folder of its own, empty apart from the clone, and put the sources in a folder named exactly
   `crux-controller` in it, for example `~/work/crux-controller-workspace/crux-controller`. Replace
   `<repository-url>` with the address of the repository in your organisation; `core.autocrlf=false` keeps the LF
   line ends that the shell scripts need:

   ```bash
   mkdir -p ~/work/crux-controller-workspace && cd ~/work/crux-controller-workspace
   git clone -c core.autocrlf=false <repository-url> crux-controller
   cd crux-controller
   ```

3. First run. This builds the image, then runs `.devcontainer/setup.sh` in the container: it creates the virtual
   environment, fetches Zephyr and the modules with `west init -l` and `west update`, installs the Python
   requirements of Zephyr and installs the Zephyr SDK. It downloads several GiB (see
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

The commands of the [Tutorial](tutorial.md) and the checks listed in the
[Dev Container reference](dev-container.md#commands-inside-the-container) run through the same script. The VS Code
route, the folder layout and what to do after a pin or SDK change are in the
[Dev Container reference](dev-container.md).

## Host notes

- **Proxy.** Behind a proxy of your organisation, or with its certificate, see
  [Behind a proxy or with a company certificate](dev-container.md#behind-a-proxy-or-with-a-company-certificate).
- **Network.** The hosts that the setup contacts are in
  [Network and prerequisites](dev-container.md#network-and-prerequisites).
- **Disk.** The first run needs several GiB. [Layout](dev-container.md#layout) says where each part is and how to
  free it.

## Without the Dev Container

An alternative to the Dev Container, on Ubuntu 24.04 on x86_64: install the tools of the CI image on the host, with no
Docker. Zephyr 4.4 needs Python 3.12, which Ubuntu 22.04 does not have. [Set up without the Dev Container](native-setup.md) gives every
command, and the commands of the tests on that route. It is done when `west --version` answers in the virtual
environment, as in the Dev Container:

```text
West version: v1.4.0
```

On macOS only part of this runs natively: the Python tooling tests, the boundary check, the SPDX check, the format
check (clang-format 18.1.8 from pip) and the host tests, in a Git clone. The Zephyr builds and the Twister runs need
Linux or the Dev Container.

## If you use a board

Nothing here needs a board. For the probe, the J-Link software, flash and debug on the RT1060-EVKB, follow
[Board bring-up](board-bring-up.md), which links the Crux board page and adds this repository's own image, tasks,
debug profiles and expected log. Its [Connect the probe](board-bring-up.md#2-connect-the-probe) step comes before
the first J-Link check.

## If something fails

Look the message up in [troubleshooting.md](troubleshooting.md). After a fix, run the same command again: the setup
skips what is done.

## Next steps

Follow the [Tutorial](tutorial.md): the host tests, the `native_sim` scenarios and the board build.
