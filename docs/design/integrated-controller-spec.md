# Controller platform image: platform services and application interface

This page specifies one application image of Crux Controller that holds the platform services of a networked controller and no product control logic.
A product adds its application logic through a defined application interface; everything else in the image is platform.
The page is the input for the design, which follows only after the owner has decided the questions of section 7.
It changes no product code; the [architecture](../architecture.md) and the [capabilities](../capabilities.md) describe the current images.

Each choice carries a label:

- **standard**: what Zephyr, Crux, IEC 61131-3 or common embedded practice documents as the normal way;
- **documented-optional**: a documented mechanism that is one of several valid choices;
- **workaround**: a choice forced by a current gap, to be replaced when the gap closes.

Zephyr is read at the release that the Crux pin names (v4.4.2, `dccb0959`), and Crux at the pinned commit `bd9efbc7`.
Where a fact is only on Crux `main` (eight commits after the pin), the text says so.
The terms are defined in the [glossary](#8-glossary) at the end.

## 1. Purpose and scope

| Item | In this image | Label |
|---|---|---|
| Platform services | Device management, health monitoring, time synchronisation, logging, configuration, network and storage (section 2) | standard (platform services of an embedded reference image, as in the nRF Connect SDK reference applications) |
| Product control logic | None. The default image builds with no application (`APP_NONE`, section 3.1) | standard (a controller runtime boots and runs its services with no user program loaded) |
| Application interface | One defined interface through which a product's application joins the image: a descriptor, entry points, context services, lifecycle states, failure rules and priority bands (section 3) | standard (IEC 61131-3 task model for the lifecycle; Zephyr modules and Kconfig for the build mechanics) |
| Example application | One minimal application, built in CI on `native_sim` and for the board, that exercises the interface, the cyclic task timing and the task watchdog (section 3.7) | standard (the reference application and samples split of the nRF Connect SDK) |
| Boards | The RT1060-EVKB is the only board built. Nothing in the image or the interface names a board; the RT1180 is the next target (section 6) | standard (Zephyr board files, devicetree aliases and `chosen` nodes) |

The image keeps no simulated plant, no control loop and no TCP peer exchange.
The `net` evidence stays in the `native_sim` scenarios, and the status service and logging are the diagnostics surface.

## 2. Platform services

| Service | Crux interface | Use in the image | Label |
|---|---|---|---|
| Device management, web | Crux Access, web server on the Mbed TLS profile (`<crux/web_zephyr.h>`), configuration and status services, a packaged page | HTTPS web UI: status, parameters, accounts, reboot | standard |
| Device management, serial | Crux console, `crux_cli_serial_start()` in `<crux/cli_zephyr.h>` | Serial command line with first-account setup (`!setup`) | standard (initial account provisioning by physical access) |
| Device management, SSH and SFTP | Crux SSH (private provider interface, wolfSSH and wolfSSL) and Crux File service | Only in the commercial line, with commercial licences (section 2.1) | documented-optional |
| Health monitoring | Crux System (one hardware watchdog token per boot, reset cause), Zephyr task watchdog | One supervisor, task watchdog channels, boot counter, safe mode, retained last-fault record (section 2.2) | standard |
| Time synchronisation | Crux Time (monotonic clock, time authority), SNTP | Wall time for logs, records and status; never for timing decisions | standard |
| Logging | Crux Logging (UART logger) | Platform and application log modules; the log drop counter is an indirect health input | standard |
| Configuration | Crux configuration service over a Crux Configuration provider | Platform parameters and the application's parameters, shown in device management | standard; the provider is decision D3 |
| Network | Zephyr network configuration library, Crux Netif, Crux Sockets profile | Interface up before `main()`; link state for health and status; sockets for the application | standard |
| Storage | Crux File, one provider, one mount | Application data root and the credential store roots (section 4) | standard; the medium is decision D3 |

### 2.1 Device management

- **HTTPS web UI.** Crux's web composition on the Mbed TLS profile, as the `management` configuration composes it, with the reboot routes added (Crux Reboot service, `CONFIG_CRUX_REBOOT`).
  The certificate is made on the device at its first start.
- **Serial command line and first account.** The image composes Crux's console on the UART of the devicetree alias `crux-serial0`; `!setup` creates the first account, and Access closes provisioning after the first save.
  No default password exists (IEC 62443-4-2 CR 1.5; ETSI EN 303 645 provision 5.1).
  Physical access to the console is trusted, and the user guide says so.
  On the RT1060-EVKB the logger owns LPUART1, so the console needs a second UART on header pins (LPUART3, the UART of Crux's console compile test); the user wires it, and the alias names it.
  Crux runs the console on `native_sim` (`tests/native/cli_console`) and compiles it for LPUART3; no board result exists.
  The product's boundary check does not list `<crux/cli_zephyr.h>` (`scripts/check_boundary.py`, `COMPOSITION_CRUX_HEADERS`), so adding it is a separate reviewed change (decision D5).
- **SSH command line and SFTP.** Only in the commercial line, built with commercially licensed wolfSSH and wolfSSL, because their open licence is GPL-3.0-or-later and the public line stays permissive.
  The public line offers no SSH; an SSH server on Mbed TLS is not an option, because it means writing and maintaining a security-critical protocol implementation.
  Open points for the commercial line (decision D6): Crux SSH has no public header and no `crux::` target, so the composition needs a Crux composition interface; the Wolf profile needs a Zephyr patch whose terms are open; one image would carry two TLS stacks (Mbed TLS for HTTPS, wolfSSL for SSH), and whether Crux allows both profiles in one image is open.
  In the public line, file transfer goes through HTTPS and the web UI, over the Crux File service's managed mode (`OPEN_MANAGED`, "for the web interface"), when Crux offers its web adapter.

### 2.2 Health monitoring

The pattern is Crux's documented one for supervising several activities (Crux `main`, `docs/superpowers/specs/2026-10-24-system-health-design.md`, section "Supervising several activities"; at the pin, the System build already refuses the option it forbids).

| Rule | What the image does | Label |
|---|---|---|
| One supervisor | One supervisor thread holds the single `crux_watchdog_t` token from `crux_watchdog_start()` and calls `crux_watchdog_feed()` only while every supervised activity has made progress | standard (Crux System contract) |
| Task watchdog without hardware | `task_wdt_init(NULL)`; one channel per supervised thread with `task_wdt_add()`; each channel callback only records the expiry and the channel identifier; the supervisor stops feeding when it sees one | standard (Zephyr task watchdog; Crux pattern) |
| No hardware fallback | `CONFIG_TASK_WDT_HW_FALLBACK=n`; the Crux System build stops when it is set (`components/system/ports/zephyr/CMakeLists.txt:20`) | standard (Crux) |
| No callback-less channel | A channel without a callback resets through `sys_reboot(SYS_REBOOT_COLD)`, which latches a software reset cause and loses the watchdog evidence; every channel has a callback | standard (Crux) |
| What is supervised | The platform-owned threads (supervisor inputs, time synchronisation, storage worker) and the application's tasks (section 3) | standard |
| Indirect health | Threads that are Zephyr's (HTTP server, network RX and TX, deferred log processing) or Crux's (console, web workers) are not fed from inside; their health is read indirectly: link state, network buffer counters, log drop counters and a periodic local probe | standard (supervising code one does not own) |
| Policy | Two values only: **degrade and report** for a failure that is not a hang (SNTP rounds fail, a save fails, the link is down), and **reset** for a hang (a channel expires, a fatal error) | standard (embedded practice; a per-service restart is a process-manager pattern that Zephyr threads do not support: `k_thread_abort` leaves locks and sockets behind, Crux Access cannot be reopened after an unusable store, `components/access/include/crux/access.h:91-93`, and the watchdog has one activation per boot) |
| Boot counter and safe mode | A counter of consecutive resets by watchdog or fatal error; after N (Kconfig, default 3) the next boot enters **safe mode**: the application is held in STOPPED and is not initialised, device management and health monitoring run. The counter clears after the application has run for a stable period (Kconfig) or by an operator command | standard (reset-loop protection) |
| Retained last-fault record | Before it stops feeding, the supervisor writes the failing channel, the uptime and the reason into a retained RAM record with a checksum (Zephyr retention subsystem over `retained_mem`); a fatal error handler writes the same record. The next boot reads it once | standard (Zephyr retention) |
| One reset-cause owner | The health service reads the reset cause once, keeps the copy, clears the flags and passes the copy to the status service and to the boot counter (C2) | standard (Crux contract) |
| Reporting | The status service shows the reset cause, the boot counter, safe mode, the last-fault record, the application state and its overrun count; liveness from outside is ping, link state and a light status endpoint | standard |

Crux service threads that block without a timeout cannot be supervised by progress; a poll-with-timeout loop in them is a Crux change, raised as a Crux issue (decision D10).
Whether the retained RAM region survives a WDOG1 reset on the RT1060-EVKB is a board fact that the first approved board run shows.

### 2.3 Time, logging, configuration, network and storage

- **Time.** Every timing decision uses Crux's monotonic clock; wall time comes from the Crux time authority over SNTP and carries its synchronisation state.
  SNTP is unauthenticated, which limits audit timestamps (IEC 62443-4-2 CR 2.11; section 5).
- **Logging.** Crux Logging on the board's logging UART; each platform service and the application have their own log module.
- **Configuration.** One parameter table for the platform and the application, served by Crux's configuration service; the application reads its values with the non-blocking read and never waits on the service.
  Saving needs a Crux Configuration provider on a file system that replaces a file atomically across a power cut (section 4, decision D3).
- **Network.** The interface comes up before `main()` through Zephyr's network configuration library; Crux Netif reports link state; the application gets the Crux Sockets profile (IPv4 client TCP and connected UDP).
  Applying changed network settings is outside the first image (section 5).
- **Storage.** One Crux File provider and one mount (C1, C4): root 0 for application data, roots 1 and 2 for the credential store, and the settings file path when a save provider exists.

### 2.4 Startup order

The main thread runs these steps in order and then ends.
A step that fails is logged with its name, and the steps after it run unless the table says otherwise.

| # | Step | On failure |
|---|---|---|
| 1 | Read the Crux monotonic clock once. | Stop: nothing can be timed. |
| 2 | Read the reset cause once, keep the copy, clear the flags (C2); read and check the retained record; update the boot counter and decide safe mode. | Log; continue without the copy; a bad record counts as empty. |
| 3 | Mount the volume once with the keep policy; bind root 0 and the store roots (C4). | Log; storage is absent, device management stays off. |
| 4 | Start security events, the realtime clock, the credential store and Access. | Device management stays off. |
| 5 | Unless in safe mode or with `APP_NONE`: call the application's `init(ctx)`, which registers its parameters and status items. | The application goes to FAULT; the platform continues. |
| 6 | Start the configuration service with the platform and application tables. | Device management stays off. |
| 7 | Start the status service with the copy from step 2 and the platform and application items. | Device management stays off. |
| 8 | Start the time synchronisation thread. | Log; time stays unsynchronised. |
| 9 | Start the serial console. | Log; no first-account path. |
| 10 | Make or load the TLS certificate, register it, start sessions, web management and the listener. | Web management stays off. |
| 11 | Start the supervisor: it arms the hardware watchdog and begins supervising the platform channels (C3). | Log; run without the watchdog. |
| 12 | Unless in safe mode, FAULT or `APP_NONE`: call the application's `start(ctx)` and start its cyclic task. | The application goes to FAULT; `safe_state()` runs. |

## 3. Application interface

**This is a new public interface of the product, and it needs the owner's decision before the design adopts it (decision D1).**
The repository's rules require escalation before adopting a new public interface, and they exclude a generic service registry, so the interface is exactly one application descriptor, not a plug-in registry.
The names below are proposals; the design fixes them.

### 3.1 Build-time selection

| Item | Rule | Label |
|---|---|---|
| Choice | A Kconfig choice selects the application: `CRUX_CONTROLLER_APP_NONE` (default), `CRUX_CONTROLLER_APP_EXAMPLE` or `CRUX_CONTROLLER_APP_EXTERNAL` | standard (Kconfig choice) |
| External application | A Zephyr module in its own west project (`zephyr/module.yml`), found by west or passed in `ZEPHYR_EXTRA_MODULES` | standard (Zephyr modules) |
| Registration | The application defines one descriptor with `STRUCT_SECTION_ITERABLE`, the pattern of Zephyr shell commands and settings handlers | standard (Zephyr iterable sections) |
| Exactly one | The build fails when more than one descriptor is linked, or when `APP_EXAMPLE` or `APP_EXTERNAL` links none | standard |
| Board files | An application module may add board files and overlays; it may not change the platform's devicetree roles | standard |

### 3.2 Descriptor and entry points

| Entry point | When | Rules |
|---|---|---|
| `init(ctx)` | Startup step 5 | Registers parameters and status items; no blocking I/O, no threads |
| `start(ctx)` | Startup step 12, after the hardware watchdog is armed | Starts the application's work; returns promptly |
| `cycle(ctx)` (optional) | Each period of the platform-owned **cyclic task** | Period and priority from Kconfig; the platform counts overruns, as IEC 61131-3 runtimes do for cyclic tasks |
| `stop(ctx, reason)` | On an operator stop or before a requested reset | Ends the application's work |
| `safe_state()` | On stop, on FAULT, before a requested reset and before the supervisor stops feeding | Puts outputs into the defined safe state; never blocks |

An application may also own threads; each such thread takes a task watchdog channel from the platform through `ctx`, and the priority bands of section 3.6 apply.

### 3.3 Context services

The platform gives the application, through `ctx`:

- a log module of its own;
- monotonic time, wall time and the synchronisation state;
- its parameters through Crux's configuration service (a product table), shown in device management;
- its status items through the status service;
- one Crux File root for application data, including data kept across a restart in the manner of IEC 61131-3 RETAIN variables;
- the Crux Sockets profile;
- its task watchdog channels;
- read-only platform health (safe mode, link state, time state).

### 3.4 Lifecycle states

INIT → READY → RUN → STOPPED or FAULT, reported in the status service (compare the nRF Connect SDK CAF module states and the IEC 61131-3 run and stop states).

| State | Entered when | Leaves to |
|---|---|---|
| INIT | Before `init` | READY on success, FAULT on failure |
| READY | `init` succeeded | RUN on `start`, STOPPED in safe mode |
| RUN | `start` succeeded | STOPPED on `stop`, FAULT on a failure rule |
| STOPPED | Operator stop, or safe mode | RUN on an operator start, outside safe mode |
| FAULT | A failure rule | Only a reset |

### 3.5 Failure rules

| Condition | Application | Platform |
|---|---|---|
| `init` or `start` fails | FAULT; `safe_state()` | Services and device management stay up |
| Cyclic deadline missed | Counted; after a Kconfig number of consecutive overruns, FAULT | Degrade and report |
| Task watchdog channel expires | `safe_state()` | Retained record written, supervisor stops feeding, hardware watchdog reset; the boot counter decides safe mode |
| Fatal error (Zephyr fatal error handler) | — | Retained record written, reset; counted like a watchdog reset |
| Platform service failure that is not a hang | Unaffected | Degrade and report |

A task watchdog expiry ends in a device reset, not in an application stop, because a hung Zephyr thread cannot be removed safely; after N resets, safe mode gives the stopped-application end state that IEC 61131-3 runtimes reach directly (decision D4).
Outputs keep their safe state across the reset only through the board's hardware default, which a product documents for its outputs.

### 3.6 Priority bands

Zephyr priorities, where a lower number is a higher priority; the values are starting points for the design (documented-optional).

| Band | Priority | Threads |
|---|---|---|
| Application | 3 to 6 | The cyclic task (default 4) and threads the application owns |
| Supervisor | 7 | The health supervisor |
| Platform services | 8 to 10 | Time synchronisation, storage worker, status updates |
| Device management | 11 to 13 | Crux web session and management workers, the console, the security event drain |
| Zephyr threads | as Zephyr sets them | HTTP server (lowest preemptive), network RX and TX, deferred log processing (14) |

The supervisor sits below the application band, so an application that holds the CPU starves the supervisor and ends in a reset, and above device management, so a long TLS handshake or key generation cannot starve it.
The application may not block platform threads, may not take platform locks and may not call device management.
A Zephyr userspace or MPU partition for the application is later work.
The design checks the bands against the priorities of Zephyr's network threads.

### 3.7 Example application

The example application (`APP_EXAMPLE`) uses only the interface:

- a cyclic task that counts cycles and measures its own period drift;
- one status item (cycle count and drift) and one parameter (the cycle period, in a fixed range);
- an injectable stall and an injectable `init` failure, selected by test-only Kconfig options.

It is built in CI on `native_sim` and for the board.
It carries no control algorithm.

## 4. Conflicts and resolutions

These conflicts appear once every service shares one image and one start sequence.

### C1. One storage provider per image

Crux allows one File provider: the RAM disk provider depends on `!DISK_DRIVER_SDMMC` (`zephyr/Kconfig`) and its CMake stops the build when another File selection is on (`components/file/ports/zephyr/CMakeLists.txt`).
**Resolution.** One provider serves the application data and the credential store (standard).
The RAM disk stays a CI form for runners without a medium.

### C2. One reset-cause owner

Crux grants one permission to clear the reset cause; the boot diagnostic owner reads once and passes what it captured (`components/system/include/crux/system.h:80-88`; `components/mgmt_status/include/crux/management_status.h`).
**Resolution.** The health service is the owner (section 2.2); the status service and the boot counter receive the copy (standard, Crux contract).

### C3. The watchdog after the platform start

Crux offers one watchdog activation per boot and no reconfiguration (`components/system/include/crux/system.h:100-115`), and the first start makes a key and a certificate.
**Resolution.** The supervisor arms the watchdog after the platform startup sequence and before the application starts (startup steps 11 and 12), so the application is always supervised.
A hang inside the startup sequence is outside the watchdog's reach; every step logs its result.

### C4. One mount, never format

**Resolution.** The composition mounts the volume once with the keep policy and binds the roots; no service mounts on its own.
The image never formats a medium (Crux's microSD provider refuses auto-format: `depends on !FS_FATFS_MOUNT_MKFS`).
A medium is prepared outside the image, by a provisioning image or a host tool (decision D11).

### C5. Configuration cannot save on FatFs (blocking)

Crux's Settings File provider of Configuration exists in two selections (`zephyr/Kconfig:438-470` at the pin):

- `CRUX_CONFIGURATION_SETTINGS_FILE` needs Reliance Edge (west group `crux-reliance`, GPLv2 in the open line, test images only);
- `CRUX_CONFIGURATION_SETTINGS_FILE_ANY_FS` refuses at CMake and in its source **any image that has `FAT_FILESYSTEM_ELM`**, because a FatFs rename removes the destination first and can lose the settings file at a power cut.

So an image with the microSD FatFs provider has no save provider, and a parameter save answers not supported; it also means an image cannot keep FatFs for files and another file system for settings.
Both selections also take corrected Settings File sources from Crux's `tests/native/configuration_settings_file`; a product image that depends on a `tests/` path of Crux is raised with Crux (decision D10).
Crux's configuration row says no production backend is adopted (`docs/component-readiness.md`).

| Option | What it needs | Evidence at the pin | Fit |
|---|---|---|---|
| (a) LittleFS on the microSD card (`FS_LITTLEFS_BLK_DEV`) | A Crux File provider selection for LittleFS on a block device (Crux change); a prepared card | Configuration on LittleFS over a block device runs on `native_sim` (`tests/native/configuration_settings_littlefs`); Crux's File core over LittleFS runs on `native_sim` on a flash simulator partition (`tests/native/file_littlefs`), with no selectable target provider | Block medium like the eMMC of Crux's reference composition; keeps the QSPI NOR for code and boot slots; the card is not readable on a PC |
| (b) LittleFS on a QSPI NOR partition | The same Crux File provider selection on a flash partition; a partition map shared with MCUboot slots; safe NOR writes while the code runs from the same flash | Zephyr's usual place for settings (NVS, ZMS or a file on LittleFS on a flash partition); Crux's storage assessment records that the pinned NOR driver discards program and erase results and polls without a deadline (`docs/storage-configuration-assessment.md`), and Crux selected microSD for its File path | Board-neutral where every board has NOR, but carries the recorded driver gaps and competes with boot slots |
| (c) Reliance Edge (commercial line) | Commercial Reliance Edge; Crux's existing providers `CRUX_FILE_RELIANCE_EDGE` and `CRUX_CONFIGURATION_SETTINGS_FILE` | Linked for the RT1060-EVKB (E3, link only); `native_sim` against an eMMC simulator; no board result | The eMMC medium of Crux's reference composition; not distributable in the open line |

**Recommendation (decision D3).** (a) for the open line on the RT1060-EVKB and (c) for the commercial line, both behind Crux File and Crux Configuration, so that the medium stays a board and line selection; one Crux issue for a LittleFS File provider on a block device.
Reason: a block medium with a power-cut-safe file system in both lines, no conflict with boot slots in the NOR, and no dependence on the NOR driver gaps that Crux recorded.
Until the provider exists, the image keeps the microSD FatFs provider for files and the credential store and runs Configuration without a save provider (workaround); the status service reports that parameters are not persistent.

## 5. Items beyond the first image

| Item | Decision | Reason |
|---|---|---|
| Firmware update with a health-gated confirm | **Now:** the image is sysbuild and MCUboot ready (partition map, signing in the build), using Crux's MCUboot sysbuild composition (build only). **Later:** the health service confirms a test image after a stable period (MCUboot test and confirm) | Crux's image state contract (`<crux/image_state.h>`) has no Zephyr or MCUboot provider; IEC 62443-4-2 EDR 3.10 and CR 3.4; EU Cyber Resilience Act Annex I |
| Secure boot hooks | **Now:** a partition map and image format that do not block signed images. **Later:** signature checking and key provisioning. **Out:** keys in this repository | Secure boot is board and line specific and follows Crux's secure boot work |
| Factory reset | **Now:** required in the design: a serial command and a pin or button held at boot, which erase credentials and configuration and return to first-account provisioning | Recovery from a lost administrator password and decommissioning (IEC 62443-4-2 CR 4.2); Crux Access offers no erase operation at the pin, so the design raises the need with Crux |
| Configuration backup and restore | **Later**, through device management | Needs a save provider first (C5); IEC 62443-4-2 CR 7.3, 7.4 |
| Audit records | **Later** | Crux security events have no persistence; they are drained to the log; time comes from unauthenticated SNTP (IEC 62443-4-2 CR 2.8, 2.9, 2.11) |
| Diagnostics | **Now:** the retained last-fault record and stack high-water reporting in the status service. **Later:** Zephyr core dump to a partition and log persistence | Core dump needs a partition decision; the retained record covers the reset evidence |
| Network settings apply | **Later** | Crux's network settings service has only a no-op apply port; the product implements the apply port, and saving needs a provider (C5) |
| Least functionality | **Now:** each device management service can be left out at build time with Kconfig. **Later:** turn services on and off through configuration | IEC 62443-4-2 CR 7.7; runtime switching needs a save provider |
| Outputs safe state across a reset | **Now:** documented in the application interface (section 3.5) | The platform cannot hold outputs through a reset; the board's hardware default does |

## 6. Boards, memory, CI and acceptance

### 6.1 Board-neutral rules

| Rule | Mechanism | Label |
|---|---|---|
| Per-board values live in board files | `app/boards/<board>.conf`, merged with `prj.conf` when `CONF_FILE` is unset, and `app/boards/<board>.overlay` | standard (Zephyr application development) |
| Variants are fragments | `EXTRA_CONF_FILE`, `EXTRA_DTC_OVERLAY_FILE`, `FILE_SUFFIX` with fallback | standard |
| Roles by devicetree | Aliases for application roles (`crux-serial0`, the watchdog, the status LED), `chosen` for system roles (console, logging, storage) | standard |
| No board name in sources | Nothing under `app/src`, `app/compose` or the application interface names a board or SoC | standard |
| Snippets only for cross-cutting settings | Debug and the RAM disk CI form; never per-board values | standard (Zephyr snippets) |
| Generic Kconfig dependencies | `CRUX_CONTROLLER_FILE` depends on `CRUX_FILE_FATFS_RT1060` (`app/Kconfig:40`); it changes to a generic "Crux File provider present" symbol or a `DT_HAS_*_ENABLED` test when Crux offers one | standard |
| Board as a build input | `scripts/build-board.sh --board <board target>` builds in `build/<board folder>/<configuration>`, as the board-neutral build change (branch `feat/board-neutral-build`) does | standard |
| Crux SoC gates are Crux issues | Logging UART, System WDOG1, File providers and entropy refuse other SoCs at the pin (section 6.4) | standard (report platform gaps) |

Adding a board takes, in this order: the board's `.conf` and `.overlay`, the aliases and `chosen` nodes, the MCUboot partition layout and sysbuild files, a CI row, and `base` as its first passing build.

### 6.2 RT1060-EVKB memory budget (`mimxrt1060_evk@B/mimxrt1062/qspi`)

All RAM of this board configuration is the 32 MB SDRAM; the on-chip regions are unused.
The per-configuration figures are the `Budget` job of `main` at `4927bb2` (GitHub Actions run 45757421275), in bytes:

| Configuration | FLASH (8 MB) | RAM (32 MB) |
|---|---|---|
| `base` | 32,440 | 4,288 |
| `workload` | 40,720 | 22,656 |
| `system` | 45,236 | 22,720 |
| `file` | 68,296 | 26,656 |
| `net` | 100,748 | 70,508 |
| `sntp` | 105,984 | 80,876 |
| `management` | 289,432 | 1,265,012 |

The combined image is not built.
The planning figure is an upper bound derived from that table, not a build result: `management`, minus the 524,288-byte RAM disk (`app/boards/management.overlay:24`), plus the deltas of `file` over `workload`, `system` over `workload` and `sntp` over `net`.
That gives at most about 327 KB of FLASH and 755 KB of RAM, before the serial console, the supervisor, the task watchdog and the example application, which no `Budget` row measures.
Both stay below 5 percent of their regions, inside the 25 percent free margin of `budgets/limits.json`.
The RAM disk CI form adds the 512 KiB disk back, about 1.3 MB of RAM; a LittleFS provider (C5) replaces the FatFs one in the figure.

### 6.3 Variants and CI test configurations

| Variant | Why | Mechanism |
|---|---|---|
| `controller` (the platform image, `APP_NONE`) | The default image | `prj.conf` plus one fragment, with the board files |
| Example form (`APP_EXAMPLE`) | Exercises the interface, timing and watchdog | One extra fragment |
| RAM disk form | CI runners and benches without a medium | One snippet |
| Debug form | Stack and thread analysis | `FILE_SUFFIX=debug` or one snippet |
| Per board | Different nodes and drivers | The board's own `.conf` and `.overlay` only |

- The `native_sim` scenarios per capability (`tests/native_sim/*`, `tests/native_sim_mbed/management`) stay as CI test configurations: they test one Crux service against its real provider, which the combined image cannot isolate.
- The host tests stay and gain the policy code: boot counter, safe mode, overrun threshold and the retained record format.
- `base` stays as the smallest board build, the first one a new board must pass.
- The board builds of `workload`, `net`, `file`, `system`, `sntp` and `management` are replaced by the platform image and its example form, unless decision D8 keeps some for build isolation.
- `budgets/limits.json` gains a `controller` row; changing it is a reviewed change ([CONTRIBUTING](../../CONTRIBUTING.md)).

### 6.4 RT1180

| Target | Code | Data | Ethernet | Fit |
|---|---|---|---|---|
| `mimxrt1180_evk/mimxrt1189/cm33` | XIP from 16 MB QSPI NOR (`w25q128jw`) | 8 MB HyperRAM in XIP mode, `zephyr,sram` | NETC (`enetc_psi0`, PHY at address 3) | Fits the planning figure with a wide margin |
| `mimxrt1180_evk/mimxrt1189/cm7` | ITCM, 256 KB by default | DTCM, 256 KB | Not in the board's supported list | A second image that the CM33 starts (dual-core, sysbuild) |

The figures come from the Zephyr board files at v4.4.2 (`boards/nxp/mimxrt1180_evk/`).
The CM33 runs at 240 MHz, so key generation and TLS handshakes take longer than on the RT1060, and C3 matters more there.

At the pinned Crux, these refuse an RT1180 image, by reading the source:

| Where | What refuses | Services blocked |
|---|---|---|
| `components/logging/ports/zephyr/logging_binding.c:12-31` | "Crux Logging unsupported UART resource": only RT1062 LPUARTs and the `native_sim` UART | Logging, and every configuration on it |
| `components/system/ports/zephyr/system_binding.c` (the final `#error`) | "Crux System unsupported SoC or watchdog resource": only the RT1062 WDOG1; the RT1180 has `nxp,rtwdog` instances | Health monitoring, device management |
| `zephyr/Kconfig:307-348` | Every target File provider of FatFs depends on `SOC_MIMXRT1062`; the board-neutral Reliance Edge provider links GPLv2 source in the open line | Storage, device management |
| `app/management/entropy.cmake:16-20` (product) | Needs `CONFIG_ENTROPY_MCUX_TRNG`; the RT1180 devicetree at v4.4.2 has no entropy node | Device management |
| `app/boards/*.overlay`, `app/conf/management.conf` (product) | Name RT1060 nodes and RT1060 Ethernet driver options | Network, health monitoring, device management |

Crux Time, Sockets and Netif have no SoC gate at the pinned commit, so `base` is the only configuration expected to build for the RT1180 there; the product rows move into board files under section 6.1.

### 6.5 Acceptance criteria

1. One configuration, `controller`, enables every platform service with `APP_NONE`; `app/Kconfig` has no exclusion between services.
2. The RT1060-EVKB builds of `controller` and its example form pass in CI with `-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`, and the `Budget` row keeps at least 25 percent free in every region.
3. The example form builds and runs on `native_sim` in CI.
4. A build that links two descriptors, or `APP_EXAMPLE` with none, fails; CI checks it.
5. A `native_sim` scenario of the start order: the reset cause is read once, the status service receives the captured copy, the flags are cleared after the capture, the watchdog is armed after the platform start and before `start(ctx)`, and the application starts last.
6. A `native_sim` scenario with the injected `init` failure: the application reports FAULT, `safe_state()` ran, and device management answers.
7. A `native_sim` scenario with the injected stall: the channel expiry is recorded, the supervisor stops feeding, and the simulated watchdog of `native_sim` (`CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG`) resets the image.
8. Host tests of the policy: N consecutive watchdog or fatal resets enter safe mode; a stable period clears the counter; the retained record's checksum rejects a damaged record; consecutive overruns past the threshold give FAULT.
9. The cyclic task's overrun count appears in the status service on `native_sim`.
10. With the provider of decision D3, a `native_sim` scenario saves a parameter, restarts on a file-backed disk and reads it back; without it, a save answers not supported and the status service says parameters are not persistent.
11. `scripts/check_boundary.py` passes with no new allow-list entry, or each entry is a separate reviewed change.
12. An RT1180 CM33 build of `base` passes, and the build of `controller` stops at a refusal of section 6.4 and at nothing else.
13. The repository holds no control algorithm; the example application uses only the interface of section 3.
14. The architecture, capabilities and roadmap pages describe the platform image; no page claims a board run until one is approved and recorded.

## 7. Owner decisions

| # | Decision | Options | Recommendation | Standard or source |
|---|---|---|---|---|
| D1 | Adopt the application interface of section 3 as a new public interface of the product | (a) Adopt the shape as the design input; (b) document a hook with no defined API; (c) no interface, products edit the image | (a), with the lowest stability tier until a product uses it | IEC 61131-3 task model; Zephyr modules, Kconfig and iterable sections; nRF Connect SDK CAF |
| D2 | How a product consumes the platform | (a) The product's manifest imports crux-controller as a west project, which imports Crux; the application is a Zephyr module selected by `APP_EXTERNAL`; (b) the product copies crux-controller like Crux's `templates/product` | (a): platform fixes reach products through a pin update, and the product owns only its module; (b) forks the platform in every product | Zephyr west manifest imports; the nRF Connect SDK workspace model; Crux `templates/product` is the copy model |
| D3 | Medium and file system for parameters and credentials | (a) LittleFS on microSD; (b) LittleFS on QSPI NOR; (c) Reliance Edge in the commercial line | (a) in the open line on the RT1060-EVKB and (c) in the commercial line, behind Crux File and Configuration; one Crux issue for a LittleFS File provider; FatFs and no save until then (workaround) | Crux `zephyr/Kconfig` Settings File selections; Zephyr settings and LittleFS documentation; section 4, C5 |
| D4 | Response to a task watchdog expiry | (a) `safe_state()`, then a device reset, with boot counter and safe mode; (b) stop the application and keep the platform running | (a): a hung Zephyr thread cannot be removed safely, and safe mode after N resets reaches the state of (b) | Zephyr task watchdog; Crux System contract; IEC 61131-3 runtime stop behaviour |
| D5 | First-account path | (a) Crux's serial console on a second UART (`crux-serial0`), with `<crux/cli_zephyr.h>` added to the boundary allow-list in a reviewed change; (b) per-device passwords set at factory provisioning | (a) now, and a factory-provisioning hook for products later | IEC 62443-4-2 CR 1.5; ETSI EN 303 645 provision 5.1 |
| D6 | SSH command line and SFTP | (a) Commercial line only, with commercial wolfSSH and wolfSSL, composition code kept in the commercial line, and HTTPS file transfer in the open line; (b) an SSH server on Mbed TLS | (a), and record the cost of two TLS stacks in one image; (b) is not an option | Licences of wolfSSL and wolfSSH (GPL-3.0-or-later or commercial); IEC 62443-4-1 secure development obligations for a protocol implementation |
| D7 | Firmware update | (a) Sysbuild and MCUboot ready now, health-gated confirm when Crux has an image state provider; (b) no boot loader until then | (a): the partition map is hard to change later | MCUboot test and confirm; IEC 62443-4-2 EDR 3.10; EU Cyber Resilience Act Annex I |
| D8 | CI matrix | (a) Platform image and example form on the board and `native_sim`, plus `base`; all `native_sim` scenarios kept; (b) keep the per-capability board builds as well | (a): fewer board builds and the same service tests | The nRF Connect SDK application and samples split |
| D9 | RT1180 core | (a) CM33; (b) CM7 | (a): Ethernet and the full image fit it; the CM7 needs a second image | Zephyr board files of `mimxrt1180_evk` |
| D10 | Crux gaps | (a) Raise Crux issues: the RT1180 refusals of section 6.4, a LittleFS File provider, the `tests/` path of the Settings File sources, poll-with-timeout loops in Crux service threads, an SSH composition interface, a web adapter for the File service, an Access erase operation; (b) product workarounds | (a): they are platform gaps | Crux component readiness; repository role of reporting platform gaps |
| D11 | Preparing a medium | (a) A provisioning image or a host tool prepares and lays out the medium; the platform image never formats; (b) the image formats an empty medium | (a): formatting destroys data, and a removable medium may hold someone else's data | Crux File providers refuse auto-format |
| D12 | Repository role | (a) Change the role sentence of CONTRIBUTING to "controller platform image that products import", as a reviewed change; (b) keep "reference consumer firmware" and treat the platform image as one of its images | (a), if D2 is (a): products then depend on this repository | CONTRIBUTING role section |
| D13 | Name of the image | (a) "Controller platform image"; (b) a name with "reference controller" | (a): the documents reserve "the reference controller" for Crux's sample | `tests/tooling/test_docs.py` |

## 8. Glossary

| Term | Meaning here | Source |
|---|---|---|
| Platform services | Device management, health monitoring, time, logging, configuration, network and storage | Common embedded usage; Crux documentation |
| Platform image | The image of this page: platform services, the application interface and, by default, no application | This page |
| Reference application, sample | A complete image built from SDK parts; a minimal demonstration of one feature | nRF Connect SDK documentation |
| Application interface (API) | The defined entry points, context and rules through which product code joins the image | Common usage |
| Application framework | Platform-owned lifecycle and services that host application modules | nRF Connect SDK Common Application Framework (CAF) |
| Descriptor | The one structure an application defines, with its entry points | Zephyr iterable sections (`STRUCT_SECTION_ITERABLE`) |
| Task, cyclic task | A scheduled execution unit; the periodic variant has a period, a priority and overrun monitoring | IEC 61131-3 |
| Overrun | A cycle that did not finish within its period | IEC 61131-3 runtimes |
| RETAIN data | Values kept across a warm restart | IEC 61131-3 |
| Lifecycle states | INIT, READY, RUN, STOPPED, FAULT | nRF Connect SDK CAF `MODULE_STATE_*`; IEC 61131-3 run and stop |
| Safe state | The defined output state on stop, fault or reset | IEC 61131 runtimes; functional safety usage |
| Hardware watchdog | The one native watchdog, owned by Crux System, one activation per boot | Zephyr watchdog API; Crux System |
| Task watchdog, channel | A software watchdog with one channel per supervised thread | Zephyr task watchdog |
| Supervisor | The one thread that holds the watchdog token and feeds only when every activity progressed | Crux System health design |
| Indirect health | Health of code one does not own, read from counters, link state or a local probe | Common usage |
| Degrade and report | Keep running with a reduced function and show the condition | Common embedded usage |
| Boot counter, safe mode | A count of consecutive fault resets; a boot mode that holds the application and keeps management | Common embedded usage |
| Retained RAM | Memory whose contents survive a warm reset, used for the last-fault record | Zephyr retention subsystem, `retained_mem` |
| Priority band | A reserved range of thread priorities for one group of threads | Common RTOS usage; rate-monotonic assignment |
| Device management | Remote and local administration: web, command line, file transfer | Common usage (LwM2M, mcumgr) |
| Initial account provisioning | Creating the first credential by a trusted path, with no default password | IEC 62443-4-2 CR 1.5; ETSI EN 303 645 5.1 |
| Factory reset | Return to the provisioning state by erasing credentials and configuration | Common usage; IEC 62443-4-2 CR 4.2 |
| Power-cut safe | A file system whose rename replaces a file atomically across a power cut | Crux `zephyr/Kconfig` Settings File help |
| Test image, confirm | An update image booted once on trial and made permanent by the running image | MCUboot |
| Sysbuild | Zephyr's build of several images, such as MCUboot and the application | Zephyr sysbuild |
| Board files, snippets | Per-board configuration and overlay; settings reused across applications | Zephyr application development and snippets |
| Devicetree alias, `chosen` | A named role for a node: application roles and system roles | Zephyr devicetree |
| West project, Zephyr module | A repository in the workspace manifest; a repository that adds code, Kconfig or board roots to a build | Zephyr west and modules |
| Open line, commercial line | The permissively licensed public build; the build with commercially licensed components | Common licensing usage |

## Sources

- Zephyr v4.4.2 (`dccb0959`): `doc/develop/application/index.rst` (board files, `EXTRA_CONF_FILE`, `FILE_SUFFIX`), `doc/build/snippets/index.rst`, `doc/build/sysbuild/index.rst`, `doc/develop/west/manifest.rst` (manifest imports), `doc/develop/modules.rst`, `doc/services/task_wdt/index.rst`, `doc/services/storage/retention/index.rst`, `doc/hardware/peripherals/retained_mem.rst`, `doc/services/debugging/coredump.rst`, `doc/services/storage/settings/index.rst`, `subsys/task_wdt/Kconfig`, `boards/nxp/mimxrt1180_evk/`.
- Crux at `bd9efbc7`: `zephyr/Kconfig`, `components/system/`, `components/access/include/crux/access.h`, `components/cli/ports/zephyr/include/crux/cli_zephyr.h`, `components/file/ports/zephyr/CMakeLists.txt`, `components/image_state/`, `components/network_settings/`, `docs/component-readiness.md`, `docs/file-service-contract.md`, `docs/boot-composition.md`, `docs/storage-configuration-assessment.md`, `tests/native/configuration_settings_littlefs`, `tests/native/file_littlefs`, `templates/product/README.md`.
- Crux `main` (after the pin): `docs/superpowers/specs/2026-10-24-system-health-design.md`, section "Supervising several activities".
- The nRF Connect SDK documentation: applications and samples, and the Common Application Framework module states.
- MCUboot design documentation: image test and confirm.
- IEC 61131-3, programmable controllers, programming languages: tasks, RETAIN variables, run and stop.
- IEC 62443-4-2 by clause title (CR 1.5, 2.8, 2.9, 2.11, 3.4, 4.2, 7.3, 7.4, 7.7; EDR 3.10) and IEC 62443-4-1.
- ETSI EN 303 645, provision 5.1; the EU Cyber Resilience Act, Annex I.
- C. L. Liu and J. W. Layland, "Scheduling Algorithms for Multiprogramming in a Hard-Real-Time Environment", Journal of the ACM, 1973.
