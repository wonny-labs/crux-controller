# Board route for the RT1060-EVKB Rev B

This page is for running an image of this repository on the NXP RT1060-EVKB Rev B. The switches, probe, flash,
debug and recovery are on the Crux board pages; this page holds only what is specific to this repository: its
images, their build commands, the Dev Container with the J-Link software and the network and log of the `net`
image. The [glossary](glossary.md) defines the terms.

**Authorisation.** Physical programming, reset and any other operation on the board need the project
owner's explicit authorisation for each task (for example one run of one image), a verified target, probe and flash configuration, and a
safe setup; an earlier approval does not carry over to a new task. If the authorisation is missing or unclear, stop
before touching the board.

## The route

1. [Build the image](#1-build-the-image) in the Dev Container.
2. [Connect the probe](#2-connect-the-probe) as the Crux board pages describe.
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
no image, so the image is built where the board is. The VS Code tasks **Build firmware** and **Board: Build and
flash** in [.vscode/tasks.json](../.vscode/tasks.json) run from the workspace folder (`-d crux-controller/build/net`)
and write the same `build/net`.

## 2. Connect the probe

The board settings, the probe, usbipd-win on Windows with WSL2 and the Linux side (`scripts/bootstrap.sh
board-host`) are on the [Crux board page](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/docs/boards/mimxrt1060_evkb.md) and in [Crux's J-Link and usbipd guide](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/docs/board-jlink-usbipd.md). The udev
rule ([99-crux-jlink.rules](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/.devcontainer/jlink/99-crux-jlink.rules), in the Crux checkout) is not copied here.

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
- [.vscode/launch.json](../.vscode/launch.json): the two Cortex-Debug profiles of [step 4](#4-flash-debug-and-restore).

How the container reaches the probe:

- no `--privileged` and no `--device` list;
- a bind mount of the host's `/dev/bus/usb` (`-v /dev/bus/usb:/dev/bus/usb`), so that a probe that reconnects
  appears again without a restart;
- `--device-cgroup-rule` `c 189:* rmw`, which allows the USB device nodes (character major 189) and nothing else.

By default you provide nothing for the J-Link software: the image build downloads the pinned version from SEGGER's
download endpoint and installs it only if its SHA-256 matches. **The download accepts SEGGER's terms of use for
you, as clicking the download on SEGGER's page does; if you do not accept them, use one of the overrides below.**
If the download fails or the SHA-256 does not match, the build prints a warning, installs nothing and finishes
without the J-Link software; a plain rebuild can reuse that cached step, so use **Dev Containers: Rebuild Container
Without Cache** to try the download again. Two overrides, in this order, win over the download:

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
image are on the [Crux board page](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/docs/boards/mimxrt1060_evkb.md). This repository adds its image (step 1), the network and log
values below and the two VS Code profiles of [.vscode/launch.json](../.vscode/launch.json), **Board: Flash and run to
main** and **Board: Attach (no reset)**, which use `build/net/zephyr/zephyr.elf`.

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
