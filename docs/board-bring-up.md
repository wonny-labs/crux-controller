# Board route for the RT1060-EVKB Rev B

This page is for running an image of this repository on the NXP RT1060-EVKB Rev B. The switches, probe settings, flash,
debug and recovery are on the Crux board pages; this page holds only what is specific to this repository: its
images and their build commands, the connection of the probe to its Dev Container, the Dev Container with the
J-Link software, its VS Code tasks and debug profiles, and the network and log of the `net` image. The
[glossary](glossary.md) defines the terms.

**Authorisation.** Physical programming, reset and any other operation on the board need the project
owner's explicit authorisation for each task (for example one run of one image), a verified target, probe and flash configuration, and a
safe setup; an earlier approval does not carry over to a new task. If the authorisation is missing or unclear, stop
before touching the board.

**What has been run**: the `net` image on the board, recorded in the
[roadmap](roadmap.md#what-has-run-on-a-board).
[Crux's J-Link and usbipd guide](https://github.com/wonny-labs/crux-pilot/blob/bd9efbc71c0318db2bbf3ced9932f2d872749e99/docs/board-jlink-usbipd.md)
records, on Windows with WSL2, a usbipd attach without `--auto-attach`, `west flash` and **Board: Debug** in Crux's Dev Container, and a connection check, `west flash` and `west debugserver` with an earlier, separate board Dev Container configuration.

Not run: step 2 in the form of this page, with this repository's Dev Container, the J-Link software of this repository's image with a probe,
the tasks **Board: Build**, **Board: Flash** and **Board: Clean**, and the profiles **Board: Debug**,
**Board: Attach** and **Board: Attach (external)** of this repository.

## The route

1. [Build the image](#1-build-the-image) in the Dev Container.
2. [Connect the probe](#2-connect-the-probe) to Linux.
3. [Open the Dev Container with the probe](#3-open-the-dev-container-with-the-probe).
4. [Flash, debug and restore](#4-flash-debug-and-restore) as the Crux board page describes.

## 1. Build the image

The `net` image is the one with a board record. The `net build` job of `.github/workflows/ci.yml` builds it with the
baseline gate required:

```bash
bash scripts/dev-shell.sh west build -p always -b 'mimxrt1060_evk@B//qspi' -d build/net app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON "-DEXTRA_CONF_FILE=conf/workload.conf;conf/net.conf" "-DEXTRA_DTC_OVERLAY_FILE=boards/net.overlay"
```

The image is `build/net/zephyr/zephyr.bin`, with `zephyr.elf` and `zephyr.meta` next to it. The `workload` image,
which has no network, is the build of [the Tutorial](tutorial.md#4-build-the-image-for-the-rt1060-evkb). CI uploads
no image, so the image is built where the board is. In VS Code, the task **Board: Build** builds the same
configuration in the same `build/net` ([VS Code tasks and debug profiles](#vs-code-tasks-and-debug-profiles)).

## 2. Connect the probe

The J-Link software runs in the Dev Container, so the probe must reach Linux first. On Windows with WSL2 it reaches
WSL2 through usbipd-win (<https://github.com/dorssel/usbipd-win>), as Microsoft describes in
[Connect USB devices](https://learn.microsoft.com/en-us/windows/wsl/connect-usb).
First check with `wsl -l -v` in PowerShell that the distribution shows `VERSION` `2`, because WSL 1 has no USB passthrough ([Comparing WSL versions](https://learn.microsoft.com/en-us/windows/wsl/compare-versions)).
In PowerShell, `usbipd list`
shows each USB device with its `BUSID` and `STATE`; the J-Link has vendor ID `1366`. Run `bind` only when the STATE
is `Not shared`, in an administrator PowerShell; the share persists across reboots. Skip it when the STATE is
`Shared`, and with `Attached` there is nothing to do. `attach` needs no administrator:

```powershell
usbipd list
usbipd bind --busid <BUSID>
usbipd attach --wsl --busid <BUSID>
```

The attachment ends when the probe re-enumerates, for example when J-Link software updates its firmware, and when
WSL2 restarts: run `attach` again. While the probe is attached, Windows tools cannot see it;
`usbipd detach --busid <BUSID>` gives it back.

On native Linux there is no attach. The board settings and the udev rule
([99-crux-jlink.rules](https://github.com/wonny-labs/crux-pilot/blob/bd9efbc71c0318db2bbf3ced9932f2d872749e99/.devcontainer/jlink/99-crux-jlink.rules),
in the Crux checkout, not copied here) are on the
[Crux board page](https://github.com/wonny-labs/crux-pilot/blob/bd9efbc71c0318db2bbf3ced9932f2d872749e99/docs/boards/mimxrt1060_evkb.md).

## 3. Open the Dev Container with the probe

There is one Dev Container, with and without a board. It mounts the USB bus of the host and sets a device
cgroup rule for it, and its image build installs the J-Link software. Its files:

- [.devcontainer/devcontainer.json](../.devcontainer/devcontainer.json): the VS Code configuration, with the
  `CRUX_JLINK*` build arguments and `scripts/bootstrap.sh` as the post-create step.
- [.devcontainer/Dockerfile](../.devcontainer/Dockerfile): pins the J-Link version that the build downloads
  (`CRUX_JLINK_SEGGER_VERSION`) and its SHA-256 (`CRUX_JLINK_SEGGER_SHA256`). To move to another J-Link version,
  change the two values together.
- [.devcontainer/jlink/install-jlink.sh](../.devcontainer/jlink/install-jlink.sh): installs the package from the
  first of `.devcontainer/jlink/packages/`, `CRUX_JLINK_URL` (checked against `CRUX_JLINK_DEB_SHA256`) and the
  pinned SEGGER download (checked against the pinned SHA-256, before anything is installed). When none gives a
  package that passes its check, it prints a warning and the image is built without the J-Link software;
  `CRUX_JLINK=1` makes that an error and `CRUX_JLINK=0` skips the step, including the download.
- [scripts/bootstrap.sh](../scripts/bootstrap.sh): `status` says whether the workspace, the SDK and the J-Link
  software are there.
- [.vscode/tasks.json](../.vscode/tasks.json) and [.vscode/launch.json](../.vscode/launch.json): the tasks and
  the Cortex-Debug profiles of [VS Code tasks and debug profiles](#vs-code-tasks-and-debug-profiles).

How the container reaches the probe:

- no `--privileged` and no `--device` list;
- a bind mount of the host's `/dev/bus/usb` (`-v /dev/bus/usb:/dev/bus/usb`), so that a probe that reconnects
  appears again without a restart;
- `--device-cgroup-rule` `c 189:* rmw`, which allows the USB device nodes (character major 189) and nothing else.

By default you provide nothing for the J-Link software: the image build downloads the pinned version from SEGGER's
download endpoint and installs it only if its SHA-256 matches. **The download accepts SEGGER's terms of use for
you, as clicking the download on SEGGER's page does; if you do not accept them, use one of the overrides below.**
If the download fails or the SHA-256 does not match, the build prints a warning, installs nothing and finishes without the J-Link software; a plain rebuild can reuse that cached step, so use **Dev Containers: Rebuild Container Without Cache** to try the download again.
If the build log shows a certificate error such as `curl: (60)`, a proxy re-signs HTTPS: add your organisation's root CA in `.devcontainer/certs/` first ([README](../.devcontainer/certs/README.md)).
Two overrides, in this order, win over the download:

- exactly one `JLink_Linux_<version>_x86_64.deb` in `.devcontainer/jlink/packages/` (Git ignores it);
- a copy that your organisation hosts after accepting the SEGGER licence itself: the build arguments
  `CRUX_JLINK_URL` (an `https://` URL) and `CRUX_JLINK_DEB_SHA256`.

Run **Dev Containers: Rebuild and Reopen in Container**. Without VS Code, `bash scripts/dev-shell.sh`
builds the same image and passes the USB bus too when `/dev/bus/usb` exists (it passes no proxy settings to the
image build, so behind a proxy that must be reached by the build, use VS Code, which does; see
[the Dev Container reference](dev-container.md)):

```bash
bash scripts/dev-shell.sh lsusb
```

Should show: `lsusb` lists the probe with ID `1366:<product>`, and `bash scripts/bootstrap.sh status` says
`bootstrap: J-Link software  installed`. If the probe is missing, stop and do not work around it with a privileged container.

## 4. Flash, debug and restore

Flashing with `west flash`, debugging, the read-only compare of the flash and the recovery of the board's previous
image are on the [Crux board page](https://github.com/wonny-labs/crux-pilot/blob/bd9efbc71c0318db2bbf3ced9932f2d872749e99/docs/boards/mimxrt1060_evkb.md). This repository adds its image (step 1), the network and log
values below, and the VS Code tasks and profiles.

### VS Code tasks and debug profiles

The tasks are in [.vscode/tasks.json](../.vscode/tasks.json) (**Terminal > Run Task**) and the profiles in
[.vscode/launch.json](../.vscode/launch.json) (**Run and Debug**). **Board: Build** runs
[`scripts/build-board.sh`](../scripts/build-board.sh) for the build configuration you pick, `net` by default. It
builds it in `build/<configuration>` with the CMake arguments of the `Budget` job, and after a successful build it
points the link `build/mimxrt1060_evk_B_qspi--current` at that folder. A failed build leaves the link as it was.
The other tasks and the profiles use the image behind the link, so one set serves every configuration. The
`management` configuration needs the Mbed TLS group, which the Dev Container does not switch on
([the `workload` to `sntp` scenarios](native-setup.md#run-the-workload-to-sntp-scenarios) show how).

| Task or profile | What it does |
|---|---|
| **Board: Build** | Builds the configuration you pick, incrementally after the first build |
| **Board: Flash** | Checks for the probe, then runs `west flash -d build/mimxrt1060_evk_B_qspi--current --runner jlink` in the same process: flashes the last board build. Without a probe it stops before `west flash` |
| **Board: Clean** | Deletes every `build/<configuration>` and the link; `build/host` and `twister-out` stay |
| **Board: Debug** | Checks for the probe and runs **Board: Build**, then flashes the image through the J-Link GDB Server in the container, resets the board and stops at `main` |
| **Board: Attach** | Checks for the probe, then connects through the J-Link GDB Server in the container to the image that runs, without build, reset or download. Connecting may halt the target |
| **Board: Attach (external)** | Like **Board: Attach**, without the probe check, through a GDB server that VS Code does not start, at `localhost:2331`, for example a `JLinkGDBServer` that you start in a terminal of the container |

**Board: Flash** runs the probe check in its own command.
**Board: Debug** and **Board: Attach** run it first as the hidden task **Board: Check probe** (for **Board: Debug**, before **Board: Build**), because a failing `preLaunchTask` stops the session.
When no J-Link (USB vendor ID `1366`) is visible in the container, the check stops with `No J-Link probe found`, the `usbipd attach` command for Windows with WSL2 and a pointer to [2. Connect the probe](#2-connect-the-probe).

| Build | Optimisation |
|---|---|
| **Board: Build**, flashed by **Board: Flash** | Size (`-Os`), Zephyr's default |

`scripts/build-board.sh` and the configuration files set no optimisation level, so Zephyr's default applies.
A debug optimisation level for the board builds is not decided: **Board: Debug** and the attach profiles debug the `-Os` image of **Board: Build**.

**Board: Debug** flashes the board, so it is a physical operation like **Board: Flash** and needs the
authorisation at the top of this page. The attach profiles do not build: the image on the board must be the one
behind the link. While **Board: Build** runs, VS Code shows that it is waiting for the `preLaunchTask`; that notice
is normal.

## The `net` image on the bench

| Item | Value |
|---|---|
| UART log | LPUART1 at 115200 baud (`app/boards/mimxrt1060_evk_mimxrt1062_qspi.overlay`) |
| Board address | `192.168.77.2`, static, no DHCP client (`app/conf/net.conf`, `app/Kconfig`) |
| MAC address | `02:43:52:55:58:20`, from the devicetree |
| Host peer | `192.168.77.1` on a `/24` network, listening on TCP port `42420` and echoing what it receives |

The log shows `workload:` lines `cycle=10` to `cycle=1750` in steps of 10 and `net:` lines. With no peer
listening, `net: exchange failed cycle=<n> result=-2` is the expected line, one per message; with a peer,
`net: exchange ok cycle=<n>`. The record of the two runs is
[docs/findings/s2-first-board-run.md](findings/s2-first-board-run.md).

## Known limits

- Only the `net` image has a board record ([roadmap](roadmap.md#what-has-run-on-a-board)).
- **file** needs a microSD card with a directory named `files` (`app/Kconfig`).
- **sntp** sets the Crux Time clock from an SNTP server, by default `192.168.77.1`, so the host peer needs a
  responder on UDP port 123.
- **management** serves HTTPS on `192.168.77.2` port 443 with a certificate that the board makes for itself. The
  image has no account, and nothing persists across a reset because the medium is a RAM disk.
- **system** needs a person present and a time limit decided before the board is programmed. It arms a hardware watchdog before the workload starts and feeds it from the
  producer thread, so a failed start leaves nothing feeding it and the board resets in a loop
  ([`docs/findings/s4-system-composition.md`](findings/s4-system-composition.md), friction 7). A debug session that
  halts the core also stops the feed.
