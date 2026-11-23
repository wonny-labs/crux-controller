# Board route for the RT1060-EVKB Rev B

**Untested on hardware.** This page describes a route from a build to a run of this firmware on the NXP
RT1060-EVKB Rev B: the probe attached to WSL2 with usbipd, the Dev Container with the SEGGER J-Link software, a
read-only compare of the flash first, then `west flash` and `west debug` with the J-Link runner. Nobody has
followed this route with this repository's firmware on any board. The only board runs this repository records
are the two S2 runs in [docs/findings/s2-first-board-run.md](findings/s2-first-board-run.md); they followed a
gated procedure with another tool (a target test driver of `crux-pilot`), not this route. The probe, container
and host steps are Crux's, and [Crux's board guide](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/docs/board-jlink-usbipd.md) says what has run there. Read the
[roadmap](roadmap.md) for what has run here, and the [glossary](glossary.md) for the terms.

**Authorisation.** Physical programming, reset and any other operation on the board need the project
owner's explicit authorisation for each task (for example one run of one image), a verified target, probe and flash configuration, and a
safe setup. Nothing on this page grants that authorisation, and an earlier approval does not carry over to a
new task. If the authorisation is missing or unclear, stop before touching the board.

Where this page states a fact, it names the file it comes from. Where it proposes something, it says
"proposed". Every command that reaches the probe or the board is untested.

## The route at a glance

1. [Build the image](#1-build-the-image) in the default Dev Container.
2. [Attach the probe to WSL2](#2-attach-the-probe-to-wsl2) and prepare the Linux side (on a Linux machine, plug it in).
3. [Open the Dev Container with the probe](#3-open-the-dev-container-with-the-probe).
4. [Compare the flash first, read-only](#4-compare-the-flash-first-read-only).
5. [Flash the image](#5-flash-the-image) with `west flash` and the J-Link runner.
6. [Observe the log and the network](#6-observe-the-log-and-the-network).
7. [Debug, if needed](#7-debug-if-needed) with `west attach` or `west debug`.
8. [Restore the accepted normal image](#8-restore-the-accepted-normal-image).
9. [Write the run record](#9-write-the-run-record).

The [stop conditions](#stop-conditions) apply to every step.

## What is needed

| Item | What the repository says |
|---|---|
| The board | NXP RT1060-EVKB Rev B. CI builds for `mimxrt1060_evk@B//qspi`. |
| Power | Not recorded in this repository. |
| Board settings (boot switches, jumpers) | Not recorded in this repository. Check the board documentation. Proposed: write the settings down in the run record before the first write. |
| A J-Link probe | Proposed: a SEGGER J-Link on the board's debug port, either an external probe or the board's on-board debug probe if it runs J-Link firmware. The S2 runs programmed and reset the board through a probe; which probe and which tool is not recorded here. |
| The UART log | The S1 base image writes the log to LPUART1 at 115200 baud (`app/boards/mimxrt1060_evk_mimxrt1062_qspi.overlay`). Which cable and adapter carry that UART is not recorded here. |
| Ethernet link | A cable from the board to the host peer. The S2 image has a static address and no DHCP client. |
| A host peer | A host with the address `192.168.77.1` on a `/24` network, able to listen on TCP port `42420` and echo what it receives. The board's address is `192.168.77.2` (`app/conf/s2.conf`, `app/Kconfig`, `docs/findings/s2-first-board-run.md`). |
| On Windows | WSL2 with the Dev Container working ([Getting started](getting-started.md#set-up-the-dev-container)), and usbipd-win on the Windows side to pass the probe to WSL2. |
| The J-Link software | Nothing to download by hand: the Dev Container build downloads the pinned version of the "J-Link Software and Documentation Pack" for Linux, 64-bit DEB installer, from SEGGER itself. A package you place or a copy that your organisation hosts overrides it ([step 3](#3-open-the-dev-container-with-the-probe)). The repository never commits it. |
| The accepted normal image | The image that was on the board before and that is put back afterwards. The S2 note records its SHA-256 (`ad729684749181f0c26853828550187a2c3e60dbb28cf3ee2194a7984141e02f`) and size (107,872 bytes). Proposed: have it available before you start. |
| A written run record | See [Write the run record](#9-write-the-run-record). The S2 runs kept host command output, probe logs, the raw capture and the peer record, privately, as the S2 note says. |

## 1. Build the image

Build in the default Dev Container ([the Tutorial](tutorial.md)), from the workspace folder. The S2 image is
the one with recorded board runs. The `S2 build` job of `.github/workflows/ci.yml` builds it with the baseline
gate required:

```bash
bash scripts/dev-shell.sh bash -s <<'SH'
set -euo pipefail
cd /workspaces/ws
west build -p always -b 'mimxrt1060_evk@B//qspi' -d crux-controller/build/s2 \
  crux-controller/app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON \
  "-DEXTRA_CONF_FILE=conf/s1.conf;conf/s2.conf" \
  "-DEXTRA_DTC_OVERLAY_FILE=boards/s2.overlay"
SH
```

The S1 image, which has no network, is the build of [the Tutorial](tutorial.md#4-build-the-image-for-the-rt1060-evkb)
(`crux-controller/build/s1`). CI uploads no image, and a tooling test fails if a workflow uploads an artifact, so
the image is built where the board is. For the S2 runs, the image was approved by its SHA-256 hash
(`e7c588c79c31d113ef3b0464731f17dfb4cc453874831b8bc20f9dd7da55b56c`, 103,180 bytes, at the source the S2 note
names), a local rebuild gave that hash and two local builds were byte-identical. Proposed: do the same, and stop
if the hash of the image to be programmed is not the approved one. From the workspace folder:

```bash
sha256sum crux-controller/build/s2/zephyr/zephyr.bin
```

Should show: `zephyr.bin` and `zephyr.meta` exist in `crux-controller/build/s2/zephyr` (the CI job checks both).

## 2. Attach the probe to WSL2

Untested here. WSL2 sees no USB device until usbipd-win passes it in. On a Linux machine without WSL2, skip the
PowerShell part. In PowerShell on Windows, as administrator for `bind`:

```powershell
winget install --interactive --exact dorssel.usbipd-win
usbipd list
usbipd bind --busid <busid>
usbipd attach --wsl --busid <busid> --auto-attach
```

`usbipd list` shows the probe with the SEGGER vendor id `1366`; `<busid>` is its first column. `bind` is needed
once per device. Keep the window of `attach --auto-attach` open: it attaches the probe again when it
re-enumerates, and run it again after every `wsl --shutdown`. `usbipd detach --busid <busid>` gives the probe back
to Windows. Once a device is attached, `/dev/bus/usb` exists in WSL2.

Then, in a shell of the WSL2 distribution or the Linux machine, in the clone, outside the container, one host
script prepares the Linux side (it installs `usbutils` if `lsusb` is missing, checks that a J-Link is listed,
installs the udev rule once and checks that the container user can open the probe):

```bash
scripts/bootstrap.sh board-host
```

This runs the step of the Crux checkout in the workspace folder (`crux-pilot/scripts/bootstrap.sh board-host`),
so the Dev Container must have been created once, which fetches Crux; the script says so when it is not there.
It never talks to the probe or the board, and it refuses to run inside the container. A probe that
re-enumerates gets a new device node, so run it again after a reattach. The rule
([99-crux-jlink.rules](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/.devcontainer/jlink/99-crux-jlink.rules), in the Crux checkout; this repository keeps no copy) gives the SEGGER vendor id to the group
`plugdev` with mode `0660`, not `0666`. [Crux's board guide](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/docs/board-jlink-usbipd.md) lists what each result of the script means
and how the node permissions look on WSL2.

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
- [.vscode/launch.json](../.vscode/launch.json): the two Cortex-Debug profiles of the debug step.

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
`bootstrap: J-Link software  installed`. Nothing has touched the board yet. If the probe is missing, stop: see
[Stop conditions](#stop-conditions).

## 4. Compare the flash first, read-only

Before anything is written, read the flash where the accepted normal image lies and compare it with that image.
The S2 runs did the same with their own tool (status `IDENTIFIED`, matching the accepted normal image, and a
read-back that said `Verify successful.`).

The J-Link settings come from Zephyr's `boards/nxp/mimxrt1060_evk/board.cmake` (read at Zephyr v4.4.0; check it
in your workspace): the J-Link device `MIMXRT1062xxx6A`, and for the QSPI flash of Rev B the loader
`BankAddr=0x60000000&Loader=QSPI`. The loader is used for programming (`west flash`); the read-only compare below
reads the memory-mapped flash with `JLinkExe` and does not use it. That the accepted normal image starts at the base of the flash, `0x60000000`,
is an assumption, not recorded in this repository: check it before you rely on the result.

Write a J-Link Commander script that only reads. The size is that of the accepted normal image in hexadecimal;
`0x1A560` is the 107,872 bytes that the S2 note records:

```jlink
savebin /workspaces/ws/board-run/flash-before.bin, 0x60000000, 0x1A560
exit
```

Save it as `/workspaces/ws/board-run/compare.jlink`, put the accepted normal image next to it as
`accepted-normal.bin`, and run, inside the Dev Container:

```bash
JLinkExe -device MIMXRT1062xxx6A -if SWD -speed auto -autoconnect 1 -NoGui 1 \
  -CommanderScript /workspaces/ws/board-run/compare.jlink
sha256sum /workspaces/ws/board-run/flash-before.bin /workspaces/ws/board-run/accepted-normal.bin
```

The speed is `auto`, as in [step 7](#7-debug-if-needed); if the connection fails, use 4000, then 400, then 100 as
there. Should show: the two hashes are equal. If they differ, stop. Connecting the probe may halt the core; whether
this read leaves the board's image running has not been checked, and the read is an operation on the board that
needs the authorisation like any other. The `board-run` folder is in the workspace folder, outside the clone.

## 5. Flash the image

Proposed: only with the project owner's explicit yes immediately before the board is overwritten, and with a
check that the probe and board are the verified ones before each probe step (the S2 note records both for its
runs). Zephyr's default runner for this board is LinkServer (the first runner that `board.cmake` includes), so
name the J-Link runner:

```bash
cd /workspaces/ws
west flash -d crux-controller/build/s2 --runner jlink
```

Then read the image back without writing, with a copy of the compare script of step 4 in which both values change:
the output file (for example `flash-after.bin` instead of `flash-before.bin`) and the size, which becomes that of
`zephyr.bin` (103,180 bytes is `0x1930C`). Compare the hash of the read-back with that of `zephyr.bin`. Should show: the hashes are equal (the S2
runs recorded status `M5_PROGRAMMED_VERIFIED_STARTED`: loaded, verified and started).

## 6. Observe the log and the network

1. **Log lines.** Capture the UART for a fixed window; the S2 runs used 180 seconds. Open the capture before the
   load only if you accept that its first lines belong to the previous image (the S2 note, friction 2). Should
   show, from the S2 note: lines of the S2 image with Zephyr's `[hh:mm:ss.mmm,uuu]` timestamps, `workload:` lines
   `cycle=10` to `cycle=1750` in steps of 10 (the first at about 4.8 seconds of uptime in run 2, which says this
   was as in run 1), and `net:` lines. With no peer listening, `net: exchange failed cycle=<n> result=-2` is the
   expected line, one per message; the S2 image logs no link line.
2. **Link and ping from the host.** Should show, from the S2 note: the host adapter's interface reports
   `status: active` and `100baseTX <full-duplex>`, there is a host route to `192.168.77.2`, and ping is answered 5
   of 5 times. The board answers ARP with the MAC from its devicetree (`02:43:52:55:58:20`).
3. **One TCP exchange.** Start the host peer once, for one exchange, on `192.168.77.1:42420`. Should show: the peer
   records a connection from `192.168.77.2` and echoes the 8 bytes, and the board logs `net: exchange ok cycle=<n>`.
   The S2 note says this exchange was informational and not a pass criterion; proposed: keep it that way.

## 7. Debug, if needed

Optional and untested. Both commands start the J-Link GDB server of the J-Link package and the debugger of the
Zephyr SDK, from the workspace folder in the Dev Container:

```bash
cd /workspaces/ws
west attach -d crux-controller/build/s2 --runner jlink
west debug -d crux-controller/build/s2 --runner jlink
```

`west attach` connects to the running image without writing it. `west debug` loads the image into the flash
first, so it is a write: it needs the same explicit yes as [step 5](#5-flash-the-image), and the image it loads
must be the approved one. A halted core stops the workload and the network; record any debug session in the run
record.

In VS Code, [.vscode/launch.json](../.vscode/launch.json) has two Cortex-Debug profiles for the J-Link probe over
SWD (device `MIMXRT1062xxx6A`, the ELF `build/s2/zephyr/zephyr.elf`): **Board: Flash and run to main** builds with
the task **Build firmware**, loads the image (a write, with the same yes) and runs to `main`, and **Board: Attach
(no reset)** connects to the running image without a reset or a download. Neither has been run. The **Board:
Build and flash** task of [.vscode/tasks.json](../.vscode/tasks.json) builds and then runs the `west flash`
command of step 5; nothing starts it unless you choose it. `.devcontainer/devcontainer.json` lists Cortex-Debug's
dependency extensions before it; if the first creation still shows "Cannot activate the 'Cortex-Debug' extension", run
**Developer: Reload Window** once.

The probe speed is `auto`: the profiles pass `-speed auto` and `west flash` is given no `--speed`, so the J-Link
runner uses its default. If a connection fails, try 4000, then 400, then 100 kHz (with `west flash --speed <kHz>`
and the `-speed` entry of `serverArgs` in the profile). Which speed works with this board has not been checked here.

## 8. Restore the accepted normal image

Program it back, verify it with the read-only compare of step 4, start it, and capture its boot line for a short
window (the S2 note used 15 seconds). Proposed, with the same runner:

```bash
cd /workspaces/ws
west flash -d crux-controller/build/s2 --runner jlink --file /workspaces/ws/board-run/accepted-normal.bin
```

Untested: check with `west flash --runner jlink --help` in your workspace how the runner places a `.bin` file (its
load address) before the run. Should show: the compare of step 4 gives equal hashes, and the capture shows the boot
identity line of the accepted normal image. One accepted diagnostic is recorded: the probe tool printed
`****** Error: Could not start CPU core. (ErrorCode: -1)` after a successful load and verify, and the run's rules
accepted exactly that when the exit status was 0 and the read-back succeeded. Do not widen it to other errors.
The board is not left in a bring-up state until this step succeeds.

## 9. Write the run record

Proposed: copy this table into the run record and fill every row before and during the run. Write "not run" for
a step that did not run. Do not report anything that was not run as passing. Two boots on one bench are evidence
collection and not qualification, as the S2 note says.

| Row | Value |
|---|---|
| Authorisation | Who approved which task, when, and its limits |
| Revisions | This repository, `crux-pilot` (the pin in `west.yml`), Zephyr |
| Image | Step (S1, S2, ...), path, SHA-256 and size; the approved hash |
| Accepted normal image | SHA-256 and size |
| Board and bench | Board revision, switch and jumper settings, power, cables, probe and its firmware |
| Tools | J-Link package version, usbipd-win version, the revision of the Dev Container files |
| Step 4, compare before | Hashes, the command output |
| Step 5, flash | The command output, the read-back hashes |
| Step 6, observation | Capture length and window, line counts, link, ping, exchange |
| Step 7, debug | Whether a debug session ran, and what it wrote |
| Step 8, restore | The command output, the compare hashes, the boot line |
| Failures and stops | Every failure, every stop condition met, every skipped step |

## Other images

Only the S2 image has a recorded board run. This page does not describe a run of the others.

- **S1** has no network and writes its log to the UART. It was never run on a board.
- **S3** keeps a record in a file on a microSD card. It was never run on a board and no card was used. It
  needs a card with a directory named `files` (`app/Kconfig`).
- **S5** sets the Crux Time clock from an SNTP server, by default `192.168.77.1` (the S2 peer). It was never
  run on a board. A run would need a responder for SNTP (UDP port 123) on the host peer; this page does not
  describe one.
- **S6** serves HTTPS management on `192.168.77.2` port 443 with a certificate that the board makes for itself. It was
  never run on a board. The image has no account, so nobody could log in, and nothing persists across a reset because the
  medium is a RAM disk. This page does not describe a run of it.
- **S4** is described below.

### S4 needs supervision

S4 has never run on a board (`docs/findings/s4-system-composition.md`). It starts a hardware watchdog and
feeds it from the workload's producer thread. For the default 100 ms cycle the interval is 2000 ms. The
finding's friction 7 records the risk: the watchdog is armed before the workload starts, so if the workload
start fails, or the producer thread ends, nothing feeds it, the board resets, and because no reset cause
stops the product from arming it again, it would keep resetting. The finding marks this **Open**, because no
board has run it, and says: "Any future board run must be supervised and time-limited."

So an S4 board run, if it is ever authorised, must be supervised by a person who is present, with a time
limit and a way to stop it decided and written down before the board is programmed. Proposed: also write
down, beforehand, what a reset loop looks like in the capture (the boot lines repeat and the uptime restarts)
and what the operator does then. How to stop a reset loop on the bench is not recorded in this repository.
A debug session that halts the core also stops the producer thread, and with it the watchdog feed.

## Stop conditions

Stop and do not continue to the next step if any of these happens. The first column says where the item
comes from.

| Source | Stop when |
|---|---|
| Proposed | There is no explicit authorisation for the current task, or it does not cover the step. |
| Proposed | The target, probe or flash configuration is not what was verified, or you are unsure which board or probe is attached. |
| Proposed | `lsusb` in the Dev Container does not list the probe, or the J-Link tools cannot open it. Do not work around it with a privileged container. |
| Proposed | The hash of the image to be programmed is not the approved one. |
| S2 note, identify step | The board's current image does not match the accepted normal image (step 4), or the read-back does not say `Verify successful.`. |
| S2 note, restore | A probe tool error other than the one accepted diagnostic above, or a non-zero exit status. |
| Proposed | The flash step does not report the image as loaded and verified, or the read-back hash differs from `zephyr.bin`. |
| S4 note, friction 7 | The log shows boot lines repeating with the uptime restarting, or no log at all, after the image should have started. Treat it as a reset loop. |
| Proposed | The capture has gaps or non-ASCII bytes that the S2 runs did not have (they had none), so that the evidence cannot be trusted. |
| Proposed | The link does not come up, or ping is not answered, within the window. Record it as a finding; do not retry in a loop. |
| Proposed | Anything on the bench behaves unexpectedly: heat, smell, a probe that disconnects, or a power supply that drops. |
| S2 note, restore | The accepted normal image cannot be restored and verified. Leave the board as it is, record the state, and ask the project owner. |
| Proposed | The time limit of the run is reached. |

Stopping is not failing. A stopped run with an honest record is worth more than a completed run with a
doubtful one.

## What this page does not cover

- The authorisation itself. The commands on this page are untested and grant nothing.
- A qualification, a performance measurement, or the physical behaviour of the board beyond what the S2 note
  records.
- A run of any image other than S2 (S1, S3, S4, S5 and S6 are mentioned above only to say they have not run).
- A cold power cycle. The S2 note lists it as not shown: its runs restarted the image by programming and
  reset.
- Other probes and runners (LinkServer, pyOCD), which `board.cmake` also configures.
- A check that the J-Link software is in the image. The `devcontainer` workflow builds the image with the default
  build arguments, so its build tries the pinned SEGGER download, but a failed download only warns: a green job does
  not show that the J-Link software was installed. The tooling tests run `install-jlink.sh` with a stand-in for
  `curl` and no network.
