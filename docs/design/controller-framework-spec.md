# Controller framework: base image, example image and application interface

This page specifies the controller framework of Crux Controller: a Zephyr module that composes the Crux services of a networked controller, monitors its health and offers one application interface.
A thin reference application in this repository uses the framework and builds two images: the **base image**, with no application, and the **example image**, with a minimal example application.
On this page, a **product** is a firmware repository outside this repository, in the sense of Crux's product composition guide: a Zephyr workspace application that imports Crux and the controller framework and adds its control logic through the application interface.
Code in this repository is called "this repository" or "Crux Controller".
The page is the input for the design, which follows only after the owner has decided the questions of section 7.
It changes no source code; the [architecture](../architecture.md) and the [capabilities](../capabilities.md) describe the current images.

Each choice carries a label:

- **standard**: what Zephyr, Crux, IEC 61131-3 or common embedded practice documents as the normal way;
- **documented-optional**: a documented mechanism that is one of several valid choices;
- **workaround**: a choice forced by a current gap, to be replaced when the gap closes.

Zephyr is read at the release that the Crux pin names (v4.4.2, `dccb0959`), and Crux at the pinned commit `bd9efbc7`.
Where a fact is only on Crux `main`, the text says so.
A Crux change that the framework needs is marked "Crux change needed"; its issue link is TBD.
The terms are defined in the [glossary](#8-glossary) at the end.

## 1. Purpose and scope

| Item | What it is | Label |
|---|---|---|
| Controller framework | A Zephyr module (`zephyr/module.yml`) with the composition of the Crux services, health monitoring and the application interface (sections 2 and 3) | standard (Zephyr modules; a framework of ready modules that an application enables, as the nRF Connect SDK Common Application Framework is) |
| Reference application | A thin Zephyr application in this repository that calls the framework; it builds the base image and the example image | standard (the application and samples split of Zephyr and the nRF Connect SDK) |
| Base image | The reference application with no application: every service of section 2 runs, and no control logic | standard (a controller runtime boots and runs its services with no user program loaded) |
| Example image | The reference application with the example application of section 3.7, built in CI on `native_sim` and for the board | standard |
| Product | A Zephyr workspace application in its own repository, which is the west manifest repository and owns `app/` and `main()`; it imports Crux and the controller framework (section 3.1) | standard (Zephyr application types and west T2 topology; nRF Connect SDK workspace applications) |
| Boards | The RT1060-EVKB is the only board built. Nothing in the framework or the interface names a board; a second board is outside the current scope (section 6.4) | standard (Zephyr board files, devicetree aliases and `chosen` nodes) |

The framework holds no simulated plant, no control loop and no TCP peer exchange.
The status service and logging are the diagnostics surface.

## 2. Platform services

| Service | Crux interface | Use in the framework | Label |
|---|---|---|---|
| Device management, web | Crux Access, web server on the Mbed TLS profile (`<crux/web_zephyr.h>`), configuration and status services, a packaged page | HTTPS web UI: status, parameters, accounts, reboot | standard |
| Device management, serial | Crux console, `crux_cli_serial_start()` in `<crux/cli_zephyr.h>` | Serial command line with first-account setup (`!setup`); its own UART at the pin, the logging UART once Crux offers the shared mode (section 2.1) | standard (initial account provisioning by physical access) |
| Device management, SSH and SFTP | Crux SSH (private provider interface, wolfSSH and wolfSSL) and Crux File service | Only in builds with commercially licensed wolfSSH and wolfSSL (section 2.1) | documented-optional |
| Health monitoring | Crux System (one hardware watchdog token per boot, reset cause), Zephyr task watchdog | One supervisor, task watchdog channels, boot counter, safe mode, retained last-fault record (section 2.2) | standard |
| Time synchronisation | Crux Time (monotonic clock, time authority), SNTP | Wall time for logs, records and status; never for timing decisions | standard |
| Logging | Crux Logging (UART logger) | Framework and application log modules; the log drop counter is an indirect health input | standard |
| Configuration | Crux configuration service over the Crux Configuration Settings File provider | Framework parameters and the application's parameters, shown in device management. Saved across a power cut once the LittleFS File provider exists; until then no save (workaround) | standard |
| Network | Zephyr network configuration library, Crux Netif, Crux Sockets profile | Interface up before `main()`; link state for health and status; sockets for the application | standard |
| Storage | Crux File, one provider, one mount | LittleFS on the whole microSD card once Crux offers a LittleFS File provider; until then the microSD FatFs provider (workaround). Application data root and the credential store roots (section 2.3, C5) | standard |

### 2.1 Device management

- **HTTPS web UI.** Crux's web composition on the Mbed TLS profile, as the `management` configuration composes it, with the reboot routes added (Crux Reboot service, `CONFIG_CRUX_REBOOT`).
  The certificate is made on the device at its first start.
- **Serial command line and first account.** The framework composes Crux's console on the UART of the devicetree alias `crux-serial0`; `!setup` creates the first account, and Access closes provisioning after the first save.
  No default password exists (IEC 62443-4-2 CR 1.5; ETSI EN 303 645 provision 5.1).
  Physical access to the console is trusted; the [board bring-up](../board-bring-up.md) page states it when the console is composed.
  Crux has a `native_sim` test of the console (`tests/native/cli_console`) and compiles it for LPUART3; no board result exists.
- **One UART for the console and logging is not possible at the pin (decision D5).** Zephyr's normal way to share one UART is the shell's log backend (`CONFIG_SHELL_LOG_BACKEND`), which queues log messages and multiplexes them with the shell's output.
  Crux refuses every form of it, by reading the source at `bd9efbc7` (the same files are unchanged on `main`):

  | Where | What it refuses |
  |---|---|
  | `components/logging/ports/zephyr/logging_binding.c:58-60` | A build with `CONFIG_CRUX_SERIAL` whose `crux-serial0` UART is the logging UART ("Crux Logging conflicts with Crux Serial") |
  | `components/logging/ports/zephyr/logging_binding.c:55-57` | The Zephyr shell's serial backend on the logging UART |
  | `components/logging/ports/zephyr/logging_binding.c:41-50` | The Zephyr console on the logging UART, except with logging-only routing (no shell, no console input) |
  | `components/logging/ports/zephyr/CMakeLists.txt:18` | `CONFIG_SHELL_LOG_BACKEND` and every log backend other than the UART backend |
  | `components/logging/ports/zephyr/logging_binding.c:12-18` | On the RT1060-EVK board, any logging UART other than LPUART1, so the console cannot take LPUART1 and move logging elsewhere |
  | `components/cli/ports/zephyr/include/crux/cli_zephyr.h:26-27`; `zephyr/Kconfig:184`, `:193`, `:222-224` | The console owns the `crux-serial0` UART: no Zephyr console, log backend, shell or other Crux Serial user on it; Crux Serial is "one explicitly dedicated UART"; an image with the Crux command line has no Zephyr shell unless it is marked as a development image |

  So the console needs a second UART at the pin: on the RT1060-EVKB, LPUART3 on header pins, which the user connects with a USB-serial adapter, and the alias names it (workaround).
  Crux change needed: a build option that the product selects between a separate console UART, which stays the default, and one UART shared by the console and Crux Logging, with the input line redrawn after log output in the manner of Zephyr's shell.
  With it, the framework uses the shared mode on the board's debug USB serial port (LPUART1 on the RT1060-EVKB, which is also the only logging UART Crux accepts there), so first-account setup needs no adapter.
- **SSH command line and SFTP (decision D6).** wolfSSH and wolfSSL are available under GPL-3.0-or-later or a commercial licence ([dependencies](../dependencies.md), group `crux-secure-management`), and this repository is Apache-2.0.
  Builds of this repository therefore have no SSH and no SFTP; builds that include the commercially licensed SSH stack have both, with the composition code kept outside this repository.
  An SSH server on Mbed TLS is not an option, because it means writing and maintaining a security-critical protocol implementation.
  Open points for builds with the SSH stack: Crux SSH has no public header and no `crux::` target, so the composition needs a Crux composition interface; the Wolf profile needs a Zephyr patch whose terms are open; one image would carry two TLS stacks (Mbed TLS for HTTPS, wolfSSL for SSH), and whether Crux allows both profiles in one image is open.
  An alternative is an optional west group that is off by default and brings the GPL-licensed stacks into a build whose user accepts GPL-3.0 for the image; Crux's manifest already keeps the Wolf projects in an optional group.
  Without SSH, file transfer goes through HTTPS and the web UI, over the Crux File service's managed mode (`OPEN_MANAGED`, "for the web interface"), when Crux offers its web adapter.

### 2.2 Health monitoring

The pattern is Crux's documented one for supervising several activities (Crux `main`, `docs/superpowers/specs/2026-10-24-system-health-design.md`, section "Supervising several activities"; at the pin, the System build already refuses the option it forbids).

| Rule | What the framework does | Label |
|---|---|---|
| One supervisor | One supervisor thread holds the single `crux_watchdog_t` token from `crux_watchdog_start()` and calls `crux_watchdog_feed()` only while every supervised activity has made progress | standard (Crux System contract) |
| Task watchdog without hardware | `task_wdt_init(NULL)`; one channel per supervised thread with `task_wdt_add()`; each channel callback only records the expiry and the channel identifier; the supervisor stops feeding when it sees one | standard (Zephyr task watchdog; Crux pattern) |
| No hardware fallback | `CONFIG_TASK_WDT_HW_FALLBACK=n`; the Crux System build stops when it is set (`components/system/ports/zephyr/CMakeLists.txt:20`) | standard (Crux) |
| No callback-less channel | A channel without a callback resets through `sys_reboot(SYS_REBOOT_COLD)`, which latches a software reset cause and loses the watchdog evidence; every channel has a callback | standard (Crux) |
| What is supervised | The framework-owned threads (supervisor inputs, time synchronisation, storage worker) and the application's tasks (section 3) | standard |
| Indirect health | Threads that are Zephyr's (HTTP server, network RX and TX, deferred log processing) or Crux's (console, web workers) are not fed from inside; their health is read indirectly: link state, network buffer counters, log drop counters and a periodic local probe | standard (supervising code one does not own) |
| Policy | Two values only: **degrade and report** for a failure that is not a hang (SNTP rounds fail, a save fails, the link is down), and **reset** for a hang (a channel expires, a fatal error) | standard (embedded practice; a per-service restart is a process-manager pattern that Zephyr threads do not support: `k_thread_abort` leaves locks and sockets behind, Crux Access cannot be reopened after an unusable store, `components/access/include/crux/access.h:91-93`, and the watchdog has one activation per boot) |
| Boot counter and safe mode | A counter of consecutive resets by watchdog or fatal error; after N (Kconfig, default 3) the next boot enters **safe mode**: the application is held in STOPPED and is not initialised, device management and health monitoring run. The counter clears after the application has run for a stable period (Kconfig) or by an operator command | standard (reset-loop protection) |
| Retained last-fault record | Before it stops feeding, the supervisor writes the failing channel, the uptime and the reason into a retained RAM record with a checksum (Zephyr retention subsystem over `retained_mem`); a fatal error handler writes the same record. The next boot reads it once | standard (Zephyr retention) |
| One reset-cause owner | The health service reads the reset cause once, keeps the copy, clears the flags and passes the copy to the status service and to the boot counter (C2) | standard (Crux contract) |
| Missing watchdog | When the hardware watchdog does not arm (no device, or Crux reports it as not supported), the framework starts the application, logs it once and shows "watchdog not armed" in the status service (C3, decision D14) | standard (degrade and report) |
| Reporting | The status service shows the reset cause, the boot counter, safe mode, the last-fault record, the watchdog state, the application state and its overrun count; liveness from outside is ping, link state and a light status endpoint | standard |

Crux service threads that block without a timeout cannot be supervised by progress; a poll-with-timeout loop in them is a Crux change needed (decision D10).
Whether the retained RAM region survives a WDOG1 reset on the RT1060-EVKB is a board fact that the first approved board run shows.

### 2.3 Time, logging, configuration, network and storage

- **Time.** Every timing decision uses Crux's monotonic clock; wall time comes from the Crux time authority over SNTP and carries its synchronisation state.
  SNTP is unauthenticated, which limits audit timestamps (IEC 62443-4-2 CR 2.11; section 5).
- **Logging.** Crux Logging on the board's logging UART; each framework service and the application have their own log module.
- **Configuration.** One parameter table for the framework and the application, served by Crux's configuration service; the application reads its values with the non-blocking read and never waits on the service.
  Once the LittleFS File provider exists, saving uses Crux's Settings File provider for any power-cut-safe file system (`CRUX_CONFIGURATION_SETTINGS_FILE_ANY_FS`) on the LittleFS volume; until then Configuration runs without a save provider, and the status service reports that parameters are not persistent (workaround, C5).
- **Network.** The interface comes up before `main()` through Zephyr's network configuration library; Crux Netif reports link state; the application gets the Crux Sockets profile (IPv4 client TCP and connected UDP).
  Applying changed network settings is outside the first images (section 5).
- **Storage (decision D3, decided).** The whole microSD card is one LittleFS volume over the card's block device (`FS_LITTLEFS_BLK_DEV`).
  LittleFS is copy-on-write: a rename replaces a file atomically, so a power cut leaves the old or the new file.
  One Crux File provider and one mount (C1, C4) serve root 0 for application data, roots 1 and 2 for the credential store, and the settings file.
  Crux change needed: a LittleFS File provider on a block device, with Configuration saving on it.
  Until it exists, the images use the microSD FatFs provider for files and the credential store, with no configuration save (workaround).
  FatFs stays a selectable Crux File provider for other products.
  A PC cannot mount the card without a LittleFS tool (littlefs-fuse, littlefs-python); files leave the device through device management.
  LittleFS's guarantee covers the file system, not the card's own controller during a power cut; a power-cut test on the board is the evidence for the medium, as Crux has for its eMMC path.
  The RAM disk CI form uses Crux's FatFs RAM disk provider, the only RAM disk provider, so it never saves configuration.

### 2.4 Startup order

The product's `main()`, or the reference application's, calls the framework's start function once; the start function runs these steps in order and returns.
A step that fails is logged with its name, and the steps after it run unless the table says otherwise.

| # | Step | On failure |
|---|---|---|
| 1 | Read the Crux monotonic clock once. | Stop: nothing can be timed. |
| 2 | Read the reset cause once, keep the copy, clear the flags (C2); read and check the retained record; update the boot counter and decide safe mode. | Log; continue without the copy; a bad record counts as empty. |
| 3 | Mount the volume once with the keep policy (LittleFS, or FatFs until the Crux LittleFS provider exists); bind root 0 and the store roots (C4). | Log; storage is absent, device management stays off. |
| 4 | Start security events, the realtime clock, the credential store and Access. | Device management stays off. |
| 5 | Unless in safe mode or with no application: call the application's `init(ctx)`, which registers its parameters and status items. | The application goes to FAULT; the framework continues. |
| 6 | Start the configuration service with the framework and application tables. | Device management stays off. |
| 7 | Start the status service with the copy from step 2 and the framework and application items. | Device management stays off. |
| 8 | Start the time synchronisation thread. | Log; time stays unsynchronised. |
| 9 | Pass the framework's command tables to `crux_cli_init()`, then start the serial console with `crux_cli_serial_start()`, which refuses a registry that is not ready (`components/cli/ports/zephyr/include/crux/cli_zephyr.h:36-40`). | Log; no first-account path. |
| 10 | Make or load the TLS certificate, register it, start sessions, web management and the listener. | Web management stays off. |
| 11 | Start the supervisor: it arms the hardware watchdog and begins supervising the framework channels (C3). | Log; run without the watchdog, and the status service shows "watchdog not armed". |
| 12 | Unless in safe mode, FAULT or with no application: call the application's `start(ctx)` and start its cyclic task. | The application goes to FAULT; `safe_state()` runs. |

## 3. Application interface

**A defined application interface is decided; its shape and stability tier need the owner's decision before the design adopts them (decision D1).**
The repository's rules require escalation before adopting a new public interface, and they exclude a generic service registry, so the interface is exactly one application descriptor, not a plug-in registry.
The names below are proposals; the design fixes them.

### 3.1 Consumption and build

| Item | Rule | Label |
|---|---|---|
| Product repository | A Zephyr workspace application: the product's repository is the west manifest repository (T2 topology) and owns `app/`, `main()`, `prj.conf`, its board files and its overlays | standard (Zephyr application types; west T2 topology; the nRF Connect SDK recommends workspace applications and its `ncs-example-application` template; Crux's `templates/product` has this shape) |
| Imports | The product's `west.yml` imports the controller framework repository with `import:`; the framework's manifest names the Crux revision it is tested with, and Crux's manifest brings Zephyr and its modules. A product that pins another Crux revision declares the reason, and `west crux-pins` reports it | standard (west manifest imports, where an imported manifest brings its own projects) |
| Framework | A Zephyr module found by west through `zephyr/module.yml`; one Kconfig symbol turns it on, and its options set the services, the cyclic task and the health policy | standard (Zephyr modules; the nRF Connect SDK enables its Common Application Framework with `CONFIG_CAF`) |
| Joining | The product's `main()` calls the framework's start function once with a pointer to its descriptor; the base image passes none | standard (the application owns `main()` and calls its libraries) |
| Exactly one | The start function refuses a second call and a descriptor without its mandatory entry points | standard |
| Repository layout | The framework module at the root (`zephyr/module.yml`, `CMakeLists.txt`, `Kconfig`), its sources in the zones of section 3.8, the reference application in `app/`, the example application beside it, and a `west.yml` that makes the repository its own T2 workspace for CI | standard (Zephyr's `example-application`, which is a workspace application and a module at once) |
| Board files | The product's board files set the devicetree roles that the framework reads (section 6.1); they may add nodes, never change a role's meaning | standard |

A product that copies this repository, or that imports it whole as its application, is not supported: a copy forks the framework in every product, and an imported application leaves the product without its own `main()`, `prj.conf` and board files.

### 3.2 Descriptor and entry points

| Entry point | When | Rules |
|---|---|---|
| `init(ctx)` | Startup step 5 | Registers parameters and status items; no blocking I/O, no threads |
| `start(ctx)` | Startup step 12, after the hardware watchdog is armed | Starts the application's work; returns promptly |
| `cycle(ctx)` (optional) | Each period of the framework-owned **cyclic task** | Period and priority from Kconfig; the framework counts overruns, as IEC 61131-3 runtimes do for cyclic tasks |
| `stop(ctx, reason)` | On an operator stop or before a requested reset | Ends the application's work |
| `safe_state()` | On stop, on FAULT, before a requested reset and before the supervisor stops feeding | Puts outputs into the defined safe state; never blocks |

An application may also own threads; each such thread takes a task watchdog channel from the framework through `ctx`, and the priority bands of section 3.6 apply.

### 3.3 Context services

The framework gives the application, through `ctx`:

- a log module of its own;
- monotonic time, wall time and the synchronisation state;
- its parameters through Crux's configuration service (an application table), shown in device management;
- its status items through the status service;
- one Crux File root for application data, including data kept across a restart in the manner of IEC 61131-3 RETAIN variables;
- the Crux Sockets profile;
- its task watchdog channels;
- read-only framework health (safe mode, watchdog state, link state, time state).

### 3.4 Lifecycle states

INIT → READY → RUN → STOPPED or FAULT, reported in the status service (compare the nRF Connect SDK CAF module states and the IEC 61131-3 run and stop states).

| State | Entered when | Leaves to |
|---|---|---|
| INIT | Before `init` | READY on success, FAULT on failure, STOPPED in safe mode without calling `init` |
| READY | `init` succeeded | RUN on `start` |
| RUN | `start` succeeded | STOPPED on `stop`, FAULT on a failure rule |
| STOPPED | Operator stop, or safe mode | RUN on an operator start, outside safe mode |
| FAULT | A failure rule | Only a reset |

### 3.5 Failure rules

| Condition | Application | Framework |
|---|---|---|
| `init` or `start` fails | FAULT; `safe_state()` | Services and device management stay up |
| Cyclic deadline missed | Counted; after a Kconfig number of consecutive overruns, FAULT | Degrade and report |
| Task watchdog channel expires | `safe_state()` | Retained record written, supervisor stops feeding, hardware watchdog reset; the boot counter decides safe mode |
| Fatal error (Zephyr fatal error handler) | — | Retained record written, reset; counted like a watchdog reset |
| Service failure that is not a hang | Unaffected | Degrade and report |

A task watchdog expiry ends in a device reset, not in an application stop, because a hung Zephyr thread cannot be removed safely; after N resets, safe mode gives the stopped-application end state that IEC 61131-3 runtimes reach directly (decision D4).
Outputs keep their safe state across the reset only through the board's hardware default, which a product documents for its outputs.

### 3.6 Priority bands

Zephyr priorities, where a lower number is a higher priority; the values are starting points for the design (documented-optional).

| Band | Priority | Threads |
|---|---|---|
| Application | 3 to 6 | The cyclic task (default 4) and threads the application owns |
| Supervisor | 7 | The health supervisor |
| Framework services | 8 to 10 | Time synchronisation, storage worker, status updates |
| Device management | 11 to 13 | Crux web session and management workers, the console, the reboot and network settings workers, the security event drain |
| Zephyr threads | as Zephyr sets them | HTTP server (lowest preemptive), network RX and TX, deferred log processing (14) |

Crux's service workers default to priority 6 at the pin (`zephyr/Kconfig:85-135`: security event drain, reboot worker, network settings worker, web session worker, web management worker and console), which is inside the application band.
The framework therefore sets each of those Kconfig priorities into the device management band.
The supervisor sits below the application band, so an application that holds the CPU starves the supervisor and ends in a reset, and above device management, so a long TLS handshake or key generation cannot starve it.
The application may not block framework threads, may not take framework locks and may not call device management.
A Zephyr userspace or MPU partition for the application is later work.
The design checks the bands against the priorities of Zephyr's network threads.

### 3.7 Example application

The example application uses only the interface:

- a cyclic task that counts cycles and measures its own period drift;
- one status item (cycle count and drift) and one parameter (the cycle period, in a fixed range);
- an injectable stall and an injectable `init` failure, selected by test-only Kconfig options.

The example image is built in CI on `native_sim` and for the board.
It carries no control algorithm.

### 3.8 Source zones and the boundary check

`scripts/check_boundary.py` checks only the trees in its `RULES` (`app/src`, `workload`, `app/compose`, `app/os`; lines 125-162), and `check()` scans only those trees (lines 308-313).
A framework source at the repository root would escape it, so every source of the module and the reference application lives in a checked zone (proposal; the design fixes the paths):

| Tree | Holds | May include |
|---|---|---|
| `include/` | The application interface header that a product includes | ISO C and public `<crux/NAME.h>` headers, so that application code stays as portable as `app/src` is today |
| `framework/src` | Plain C: lifecycle, boot counter, safe mode, overrun threshold, retained record format, time synchronisation and management policy | The rules of today's `app/src` |
| `framework/compose` (composition zone) | Storage mount, management start, console start | The rules of today's `app/compose`, plus `zephyr/fs/littlefs.h` and `<crux/cli_zephyr.h>` |
| `framework/os` (adapter zone) | Supervisor and cyclic task threads, task watchdog, retained record access, fatal error handler, SNTP adapter | The rules of today's `app/os`, plus `zephyr/task_wdt/task_wdt.h`, `zephyr/retention/retention.h`, `zephyr/fatal.h`, and `zephyr/devicetree.h` with `zephyr/device.h` to find the retained region |
| `app/` (reference application) | `main()` and the example application | ISO C and the header of `include/` |

`RULES` gains one rule per tree, and a source file of the module that no rule covers fails the check.
Each new header is a separate reviewed boundary change under CONTRIBUTING "The boundary", with its reason in [composition-zone.md](../composition-zone.md) and a case in `tests/tooling/test_boundary.py`: `zephyr/task_wdt/task_wdt.h`, `zephyr/retention/retention.h` (the framework uses the retention API, not the `retained_mem` driver header), `zephyr/fatal.h`, `zephyr/fs/littlefs.h`, `zephyr/device.h` and `zephyr/devicetree.h` in the adapter zone, and the composition interface `<crux/cli_zephyr.h>`, which `COMPOSITION_CRUX_HEADERS` does not list.

## 4. Conflicts and resolutions

These conflicts appear once every service shares one image and one start sequence.

### C1. One storage provider per image

Crux allows one File provider: the RAM disk provider depends on `!DISK_DRIVER_SDMMC` (`zephyr/Kconfig`) and its CMake stops the build when another File selection is on (`components/file/ports/zephyr/CMakeLists.txt`).
**Resolution.** One provider serves the application data, the credential store and the settings file (standard): LittleFS on the card once Crux offers it, the microSD FatFs provider until then.
The RAM disk stays a CI form for runners without a medium.

### C2. One reset-cause owner

Crux grants one permission to clear the reset cause; the boot diagnostic owner reads once and passes what it captured (`components/system/include/crux/system.h:80-88`; `components/mgmt_status/include/crux/management_status.h`).
**Resolution.** The health service is the owner (section 2.2); the status service and the boot counter receive the copy (standard, Crux contract).

### C3. The watchdog after the service start

Crux offers one watchdog activation per boot, with no auto-arm, stop or reconfiguration (`zephyr/Kconfig:274-275`), and the first start makes a key and a certificate.
**Resolution.** The supervisor arms the watchdog after the service startup sequence and before the application starts (startup steps 11 and 12), so the application is supervised whenever the watchdog arms.
When it does not arm, the application still starts, and the log and the status service say "watchdog not armed" (decision D14): a missing watchdog device must not block a bench or `native_sim` image, and the status makes the condition visible.
A hang inside the startup sequence is outside the watchdog's reach; every step logs its result.

### C4. One mount, never format

**Resolution.** The composition mounts the volume once with the keep policy and binds the roots; no service mounts on its own.
The framework never formats a medium, so a blank or foreign card does not mount and its data stays untouched.
A card is prepared outside the images, by a provisioning image or a host tool that writes the volume (decision D11).

### C5. Configuration saving needs a power-cut-safe file system

Crux's Settings File provider of Configuration exists in two selections (`zephyr/Kconfig:438-470` at the pin):

- `CRUX_CONFIGURATION_SETTINGS_FILE` needs Reliance Edge (west group `crux-reliance`, source under GPLv2, test images only);
- `CRUX_CONFIGURATION_SETTINGS_FILE_ANY_FS` refuses at CMake and in its source **any image that has `FAT_FILESYSTEM_ELM`**, because a FatFs rename removes the destination first and can lose the settings file at a power cut.

So an image with the microSD FatFs provider has no save provider, and an image cannot keep FatFs for files and another file system for settings.
Configuration on LittleFS over a block device runs on `native_sim` in Crux (`tests/native/configuration_settings_littlefs`), and Crux's File core runs over LittleFS on a flash simulator partition (`tests/native/file_littlefs`); Crux has no selectable LittleFS File provider for a target at the pin or on `main`.
Both Settings File selections take corrected sources from Crux's `tests/native/configuration_settings_file`; an image of this repository that depends on a `tests/` path of Crux needs a Crux change (decision D10).

**Resolution (decision D3, decided).** The whole card is LittleFS (section 2.3), and Configuration saves on it through `CRUX_CONFIGURATION_SETTINGS_FILE_ANY_FS`.
Crux change needed: a LittleFS File provider on a block device.
Until it exists, the images keep the microSD FatFs provider for files and the credential store and run Configuration without a save provider (workaround); the status service reports that parameters are not persistent.
A build with commercially licensed Reliance Edge may select it behind the same Crux File and Configuration interfaces.

## 5. Items beyond the first images

| Item | Decision | Reason |
|---|---|---|
| Firmware update with a health-gated confirm | **Now:** the images are sysbuild and MCUboot ready (partition map, signing in the build), using Crux's MCUboot sysbuild composition (build only). **Later:** the health service confirms a test image after a stable period (MCUboot test and confirm) | Crux's image state contract (`<crux/image_state.h>`) has no Zephyr or MCUboot provider; IEC 62443-4-2 EDR 3.10 and CR 3.4; EU Cyber Resilience Act Annex I |
| Secure boot hooks | **Now:** a partition map and image format that do not block signed images. **Later:** signature checking and key provisioning. **Out:** keys in this repository | Secure boot is board specific and follows Crux's secure boot work |
| Factory reset | **Now:** required in the design: a serial command and a pin or button held at boot, which erase credentials and configuration and return to first-account provisioning | Recovery from a lost administrator password and decommissioning (IEC 62443-4-2 CR 4.2); Crux Access offers no erase operation at the pin, a Crux change needed |
| Configuration backup and restore | **Later**, through device management | Needs the save provider (C5); IEC 62443-4-2 CR 7.3, 7.4 |
| Audit records | **Later** | Crux security events have no persistence; they are drained to the log; time comes from unauthenticated SNTP (IEC 62443-4-2 CR 2.8, 2.9, 2.11) |
| Diagnostics | **Now:** the retained last-fault record and stack high-water reporting in the status service. **Later:** Zephyr core dump to a partition and log persistence | Core dump needs a partition decision; the retained record covers the reset evidence |
| Network settings apply | **Later** | Crux's network settings service has only a no-op apply port; the framework implements the apply port, and saving needs the provider (C5) |
| Least functionality | **Now:** each device management service can be left out at build time with Kconfig. **Later:** turn services on and off through configuration | IEC 62443-4-2 CR 7.7; runtime switching needs the save provider |
| Outputs safe state across a reset | **Now:** documented in the application interface (section 3.5) | The framework cannot hold outputs through a reset; the board's hardware default does |

## 6. Boards, memory, CI and acceptance

### 6.1 Board-neutral rules

| Rule | Mechanism | Label |
|---|---|---|
| Per-board values live in board files | `app/boards/<board>.conf`, merged with `prj.conf` when `CONF_FILE` is unset, and `app/boards/<board>.overlay`, in the reference application and in each product | standard (Zephyr application development) |
| Variants are fragments | `EXTRA_CONF_FILE`, `EXTRA_DTC_OVERLAY_FILE`, `FILE_SUFFIX` with fallback | standard |
| Roles by devicetree | Aliases `crux-serial0` (console) and `crux-watchdog0` (watchdog), `chosen` `zephyr,log-uart` (logging), node label `controller_storage` (storage) | standard |
| No board name in sources | Nothing in the framework module, the reference application's sources or the application interface names a board or SoC | standard |
| Snippets only for cross-cutting settings | Debug and the RAM disk CI form; never per-board values | standard (Zephyr snippets) |
| Generic Kconfig dependencies | `CRUX_CONTROLLER_FILE` depends on `CRUX_FILE_FATFS_RT1060` (`app/Kconfig:40`); it changes to a generic "Crux File provider present" symbol or a `DT_HAS_*_ENABLED` test when Crux offers one | standard |
| Board as a build input | `scripts/build-board.sh --board <board target>`, building in `build/<board folder>/<configuration>`, is the change of Draft PR #104 (branch `feat/board-neutral-build`) and is not on `main` | standard |
| Crux SoC gates are Crux changes | Logging UART, System WDOG1, File providers and entropy refuse other SoCs at the pin (section 6.4) | standard (report platform gaps) |

Adding a board takes, in this order: the board's `.conf` and `.overlay`, the aliases and `chosen` nodes, the MCUboot partition layout and sysbuild files, a CI row, and the smallest build configuration as its first passing build.

### 6.2 RT1060-EVKB memory budget (`mimxrt1060_evk@B/mimxrt1062/qspi`)

All RAM of this board configuration is the 32 MB SDRAM; the on-chip regions are unused.
The per-configuration sizes are in the roadmap, [Static size per configuration](../roadmap.md#static-size-per-configuration).
The base image is not built, so its planning figure is an upper bound derived from those sizes, not a build result: `management`, minus the 524,288-byte RAM disk (`app/boards/management.overlay:24`), plus the deltas of `file` over `workload`, `system` over `workload` and `sntp` over `net`.
With the roadmap's figures that gives at most about 326 KB of FLASH and 755 KB of RAM, before the serial console, the supervisor, the task watchdog and the example application, which no `Budget` row measures.
Both stay below 5 percent of their regions, inside the 25 percent free margin of `budgets/limits.json`.
The RAM disk CI form adds the 512 KiB disk back, about 1.3 MB of RAM; the LittleFS provider (C5) replaces the FatFs one in the figure.

### 6.3 Variants and CI test configurations

| Variant | Why | Mechanism |
|---|---|---|
| Base image | The framework with no application | The reference application's `prj.conf` plus one fragment, with the board files |
| Example image | Exercises the interface, timing and watchdog | One extra fragment |
| RAM disk form | CI runners and benches without a medium; never saves configuration (section 2.3) | One snippet |
| Debug form | Stack and thread analysis | `FILE_SUFFIX=debug` or one snippet |
| Per board | Different nodes and drivers | The board's own `.conf` and `.overlay` only |

The `native_sim` scenarios keep only what tests code of this repository: composition, policies, start order, health monitoring and the application interface.
A case that only repeats Crux behaviour, which Crux's own tests cover, is dropped (decision D8).

| Scenario and cases | Code of this repository under test | Keep or drop | Reason |
|---|---|---|---|
| `native_sim/file`: `not_ready`, `mounted_not_bound`, `mount_failure`, `bind_failure` | `app/compose/storage_mount.c` through `storage_port.h` | Keep the mount and bind cases (bind before mount fails, a second mount and a second bind are refused, a kept blank volume does not mount and nothing is formatted, a failed bind can be retried), moved to the framework's storage composition; drop the assertions that only call `crux_file_*` and check its not-ready answer | Mount once, keep, never format and the bind order are this repository's composition (C4); File's not-ready answers are Crux File behaviour, covered by Crux's `tests/native/file_roots` and the File provider tests |
| `native_sim/file`: `roundtrip` | `app/src/config_store.c`, the workload's record | Drop | The record belongs to the workload, which leaves the framework; parameters move to Crux Configuration, which Crux tests on LittleFS (`tests/native/configuration_settings_littlefs`), and the framework's own save path gets the scenario of acceptance criterion 10 |
| `native_sim/net` | `app/src/net_client.c` (TCP peer exchange) | Drop | The framework keeps no TCP peer exchange, so the code leaves with it; Crux Sockets and Netif have their own tests |
| `native_sim/sntp`: all seven cases | `app/src/time_sync.c`, `app/src/time_sync_policy.c`, `app/os/time_sync_zephyr.c` | Keep | The glue and policy between Zephyr's SNTP library and Crux Time (first sync, kiss-o'-death, timeout, range, step refusal, threshold, stale age) are this repository's code; Crux has no SNTP client of its own |
| `native_sim/system`: `reset_cause` | `app/src/health.c` | Keep, extended into the start-order scenario | The single reset-cause owner (C2) is this repository's code (acceptance criterion 5) |
| `native_sim/system`: `watchdog_unsupported`, `period_out_of_range` | `app/src/health.c`, `app/src/health_policy.c` | Keep, moved to the supervisor | This repository's policy: refuse a cycle that the watchdog cannot cover before Crux is asked, and carry on without a watchdog (startup step 11, decision D14) |
| `native_sim/workload` | `app/src/workload_thread.c` (simulated plant) | Drop | The workload leaves the framework; the framework's cyclic task gets its own scenarios (acceptance criteria 7 and 9) |
| `native_sim_mbed/management`: cases 01 to 03, 06, 07 | `app/compose/management_start.c`, `app/src/management_policy.c`, the route table and the packaged page | Keep | The start sequence, the certificate the composition registers, the route table behind a session and the packaged page are this repository's composition and policy |
| `native_sim_mbed/management`: cases 04, 05, 08, 09, 10 | None: Crux's web adapter and Access | Drop | TLS 1.3 only, no plain HTTP answer, the queued login and its poll, and the CSRF refusal are Crux behaviour (the web adapter asks the socket for TLS 1.3, `app/conf/management.conf:23-24`); Crux tests them in `tests/native/web_https` and `tests/native/management_services` |

New `native_sim` scenarios test the framework's own behaviour: the start order, the injected `init` failure, the injected stall, the overrun count, the configuration save on LittleFS and the refused second start (section 6.5).

- The host tests stay and gain the policy code: boot counter, safe mode, overrun threshold and the retained record format.
- The smallest board build (`prj.conf` alone) stays as the first build a new board must pass; it takes another name than `base` (decision D13).
- The board builds of `workload`, `net`, `file`, `system`, `sntp` and `management` are replaced by the base image and the example image.
- `budgets/limits.json` gains rows for the base image and the example image; its `_comment` makes a change there a reviewed change.

### 6.4 Second board (deferred)

A second board is outside the current scope (decision D9); the framework stays board-neutral under section 6.1.
At the pinned Crux, these refuse an SoC other than the RT1062, by reading the source; they become Crux changes needed when a second board enters the scope:

| Where | What refuses | Services blocked |
|---|---|---|
| `components/logging/ports/zephyr/logging_binding.c:12-31` | "Crux Logging unsupported UART resource": only RT1062 LPUARTs and the `native_sim` UART | Logging, and every configuration on it |
| `components/system/ports/zephyr/system_binding.c` (the final `#error`) | "Crux System unsupported SoC or watchdog resource": only the RT1062 WDOG1 | Health monitoring, device management |
| `zephyr/Kconfig:307-348` | Every target File provider of FatFs depends on `SOC_MIMXRT1062`; the board-neutral Reliance Edge provider links source under GPLv2 | Storage, device management |
| `app/management/entropy.cmake:16-20` (this repository) | Needs `CONFIG_ENTROPY_MCUX_TRNG` | Device management |
| `app/boards/*.overlay`, `app/conf/management.conf` (this repository) | Name RT1060 nodes and RT1060 Ethernet driver options | Network, health monitoring, device management |

### 6.5 Acceptance criteria

1. The base image enables every service of section 2 with no application; the framework's Kconfig has no exclusion between services; until the Crux LittleFS provider exists, its storage is the microSD FatFs provider and Configuration has no save provider (workaround).
2. The RT1060-EVKB builds of the base image and the example image pass in CI with `-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`, and their `Budget` rows keep at least 25 percent free in every region.
3. The example image builds and runs on `native_sim` in CI.
4. A second call of the start function, and a descriptor without its mandatory entry points, are refused; a `native_sim` or host test checks both.
5. A `native_sim` scenario of the start order: the reset cause is read once, the status service receives the captured copy, the flags are cleared after the capture, the watchdog is armed after the service start and before `start(ctx)`, and the application starts last.
6. A `native_sim` scenario with the injected `init` failure: the application reports FAULT, `safe_state()` ran, and device management answers.
7. A `native_sim` scenario with the injected stall: the channel expiry is recorded, the supervisor stops feeding, and the simulated watchdog of `native_sim` (`CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG`) restarts the image. That restart reads the reset cause SOFTWARE, never WATCHDOG (`zephyr/Kconfig:277-288`), so the boot counter's watchdog path is shown by the host tests of criterion 8 and on a board, not end to end on `native_sim`.
8. Host tests of the policy: N consecutive watchdog or fatal resets enter safe mode; a stable period clears the counter; the retained record's checksum rejects a damaged record; consecutive overruns past the threshold give FAULT.
9. The cyclic task's overrun count appears in the status service on `native_sim`.
10. With Crux's LittleFS File provider, a `native_sim` scenario saves a parameter, restarts on a file-backed disk and reads it back; without it, a save answers not supported and the status service says parameters are not persistent.
11. `scripts/check_boundary.py` checks every source tree of the framework module and the reference application (section 3.8); a module source that no rule covers fails the check; each new allow-list entry is a separate reviewed change.
12. A CI job builds a fixture product under `tests/`, with its own `app/`, `main()`, `prj.conf` and descriptor, for `native_sim`, with this repository as a Zephyr module (`EXTRA_ZEPHYR_MODULES`), runs it, and finds the line that reports the application in RUN in the log.
13. The repository holds no control algorithm; the example application uses only the interface of section 3.
14. The architecture, capabilities and roadmap pages describe the framework and its two images; no page claims a board run until one is approved and recorded.

## 7. Owner decisions

| # | Decision | Options | Recommendation | Standard or source |
|---|---|---|---|---|
| D1 | Shape and stability tier of the application interface; a defined interface is decided | (a) A descriptor that the product's `main()` passes to the framework's start function; (b) registration of the descriptor in a linker section (`STRUCT_SECTION_ITERABLE`), with a Kconfig choice of the application | (a), at the lowest stability tier until a product uses it: one call, no section or Kconfig choice to keep consistent, and the product keeps `main()`. The framework depends on Crux interfaces at Crux's lowest stability tier (ADR-0001 Decision 4): `<crux/cli_zephyr.h>`, `<crux/web_zephyr.h>`, `CONFIG_CRUX_REBOOT`, `CONFIG_CRUX_NETWORK_SETTINGS` and `CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG`, so its tier cannot be higher than theirs | IEC 61131-3 task model; Zephyr modules and iterable sections; nRF Connect SDK CAF |
| D2 | How a product consumes the framework | (a) The product is a workspace application that owns `app/` and `main()` and imports Crux and the controller framework module (section 3.1); (b) the product imports the whole of this repository as its application and adds a module; (c) the product copies this repository | (a): it is the documented Zephyr and nRF Connect SDK shape and matches Crux's `templates/product`; framework fixes reach products through a pin update; (b) takes `main()`, `prj.conf` and board files away from the product; (c) forks the framework in every product | Zephyr application types, west T2 topology and modules; nRF Connect SDK workspace applications and `ncs-example-application`; Zephyr `example-application`; the reference design template in the sources |
| D3 | Medium and file system for parameters and credentials | (a) LittleFS on the whole microSD card; (b) LittleFS on a QSPI NOR partition; (c) Reliance Edge under a commercial licence | **Decided: (a).** FatFs stays a selectable Crux provider. Crux change needed: a LittleFS File provider on a block device, with Configuration saving on it; FatFs and no save until then (workaround) | Crux `zephyr/Kconfig` Settings File selections; Zephyr LittleFS; section 4, C5 |
| D4 | Response to a task watchdog expiry | (a) `safe_state()`, then a device reset, with boot counter and safe mode; (b) stop the application and keep the framework running | (a): a hung Zephyr thread cannot be removed safely, and safe mode after N resets reaches the state of (b) | Zephyr task watchdog; Crux System contract; IEC 61131-3 runtime stop behaviour |
| D5 | UART of the serial console | (a) One UART shared by the console and logging, through a Crux build option; (b) the console on a second UART (LPUART3 on header pins, with a USB-serial adapter), Crux's default | (a) on the debug USB serial port once Crux offers the option (Crux change needed); (b) until then, because Crux refuses (a) at the pin (section 2.1); `<crux/cli_zephyr.h>` added to the boundary allow-list in a reviewed change (section 3.8); a factory-provisioning hook for products later | Zephyr shell log backend; Crux Logging binding and console contract; IEC 62443-4-2 CR 1.5; ETSI EN 303 645 provision 5.1 |
| D6 | SSH command line and SFTP | (a) None in builds of this repository; builds that include the commercially licensed wolfSSH and wolfSSL have both, with the composition code outside this repository, and HTTPS file transfer otherwise; (b) an optional west group, off by default, that brings the GPL-licensed stacks into a build; (c) an SSH server on Mbed TLS | (a), and record the cost of two TLS stacks in one image; (b) only if a user needs SSH and accepts GPL-3.0 for the image; (c) is not an option | Licences of wolfSSL and wolfSSH (GPL-3.0-or-later or commercial; [dependencies](../dependencies.md)); IEC 62443-4-1 secure development obligations for a protocol implementation |
| D7 | Firmware update | (a) Sysbuild and MCUboot ready now, health-gated confirm when Crux has an image state provider; (b) no boot loader until then | (a): the partition map is hard to change later | MCUboot test and confirm; IEC 62443-4-2 EDR 3.10; EU Cyber Resilience Act Annex I |
| D8 | CI matrix | (a) The base image and the example image on the board and `native_sim`, the smallest board build, and only the `native_sim` cases that test code of this repository (section 6.3); (b) keep every per-capability scenario and board build | (a): Crux's tests cover the dropped cases, and each kept case tests code this repository owns | The Zephyr and nRF Connect SDK application and samples split |
| D9 | Second board | — | **Deferred:** a second board is outside the current scope; the framework stays board-neutral (section 6.1) | Section 6.4 |
| D10 | Crux gaps | (a) Crux changes needed, each with an issue link TBD: a LittleFS File provider on a block device, the shared console and logging UART option, the `tests/` path of the Settings File sources, poll-with-timeout loops in Crux service threads, an SSH composition interface, a web adapter for the File service, an Access erase operation, and the SoC refusals of section 6.4 when a second board is in scope; (b) workarounds in this repository | (a): they are platform gaps | Crux component readiness; repository role of reporting platform gaps |
| D11 | Preparing a card | (a) A provisioning image or a host tool (littlefs-python, littlefs-fuse) writes the LittleFS volume and its layout; the images never format; (b) the image formats an empty card | (a): formatting destroys data, and a removable card may hold someone else's data | Crux File providers refuse auto-format |
| D12 | Repository role | (a) Change the role sentence of CONTRIBUTING to a controller framework module with a reference application that products import, as a reviewed change with the role test of `tests/tooling/test_docs.py`; the glossary entry "Product" (`docs/glossary.md:11`) then takes Crux's sense, a firmware repository built on Crux, and local code is "this repository"; (b) keep "reference consumer firmware" and treat the framework as one of its parts | (a), with D2 (a): products then depend on this repository | CONTRIBUTING role section; `docs/glossary.md` |
| D13 | Names | (a) "Controller framework" for the module, "base image" for the image with no application, "example image" for the image with the example application; (b) names with "platform" or "reference controller" | (a): Crux is the platform, and the documents reserve "the reference controller" for Crux's sample. The build configuration `base` (`prj.conf` alone) is renamed, for example to `minimal`, so that "base" has one meaning; that is a reviewed change of `scripts/build-board.sh`, `budgets/limits.json`, `.github/workflows/ci.yml`, `.github/workflows/budget.yml`, `tests/tooling/test_base_build.py`, CONTRIBUTING (the role section's list of build configurations and the job table) and their tests, and of the glossary | `tests/tooling/test_docs.py` |
| D14 | Application start without a hardware watchdog | (a) Start the application, log it once and show "watchdog not armed" in the status service; (b) refuse to start the application | (a): a missing watchdog device must not block a bench or `native_sim` image, and the status service makes the condition visible; a product that needs (b) checks the watchdog state before it trusts its outputs | Crux System reports an unavailable watchdog as not supported; degrade and report (section 2.2) |

## 8. Glossary

| Term | Meaning here | Source |
|---|---|---|
| Platform services | Device management, health monitoring, time, logging, configuration, network and storage, which Crux provides | Common embedded usage; Crux documentation |
| Controller framework | The Zephyr module of this repository: the composition of the Crux services, health monitoring and the application interface | This page |
| Reference application | The thin application in this repository that calls the framework and builds the base image and the example image | This page; Zephyr and nRF Connect SDK samples |
| Base image | The reference application with no application | This page |
| Example image | The reference application with the example application | This page |
| Product | On this page, a firmware repository outside this repository that is built on Crux and the framework; `docs/glossary.md` uses the word for this repository's firmware until decision D12 | Crux product composition guide |
| Workspace application | A Zephyr application inside a west workspace, outside the Zephyr repository; here the product's repository is also the manifest repository | Zephyr application development; nRF Connect SDK |
| T2 topology | A west workspace whose manifest repository is the application, which names Zephyr and the other projects | Zephyr west workspaces |
| Application interface (API) | The defined entry points, context and rules through which product code joins the framework | Common usage |
| Application framework | Platform-owned lifecycle and services that host application modules | nRF Connect SDK Common Application Framework (CAF) |
| Descriptor | The one structure an application defines, with its entry points, passed to the framework's start function | This page |
| Source zone | A source tree with its own include rules, checked by `scripts/check_boundary.py` | CONTRIBUTING "The boundary"; [composition-zone.md](../composition-zone.md) |
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
| Log backend | The output of Zephyr's logging; the shell's log backend shares the shell's UART | Zephyr logging and shell |
| Initial account provisioning | Creating the first credential by a trusted path, with no default password | IEC 62443-4-2 CR 1.5; ETSI EN 303 645 5.1 |
| Factory reset | Return to the provisioning state by erasing credentials and configuration | Common usage; IEC 62443-4-2 CR 4.2 |
| Power-cut safe | A file system whose rename replaces a file atomically across a power cut | Crux `zephyr/Kconfig` Settings File help |
| LittleFS | A copy-on-write file system for flash and block devices with power-loss resilience | littlefs project; Zephyr file systems |
| Test image, confirm | An update image booted once on trial and made permanent by the running image | MCUboot |
| Sysbuild | Zephyr's build of several images, such as MCUboot and the application | Zephyr sysbuild |
| Board files, snippets | Per-board configuration and overlay; settings reused across applications | Zephyr application development and snippets |
| Devicetree alias, `chosen` | A named role for a node: application roles and system roles | Zephyr devicetree |
| West project, Zephyr module | A repository in the workspace manifest; a repository that adds code, Kconfig or board roots to a build | Zephyr west and modules |

## Sources

- Fetched pages: Zephyr "Application Development" (application types: repository, workspace, freestanding), Zephyr west "Workspaces" (topologies T1, T2, T3), Zephyr "Modules (External projects)", Zephyr "Shell" (logger backend, obscured input), the Zephyr `example-application` repository README, nRF Connect SDK "Creating an application" (application types, workspace application recommended, `ncs-example-application`), the `ncs-example-application` repository README, nRF Connect SDK "Common Application Framework overview".
- A reference design template that is a T2 workspace application importing its SDK module, which in turn imports the nRF Connect SDK and Zephyr: <https://github.com/golioth/reference-design-template> (`west.yml`).
- Zephyr v4.4.2 (`dccb0959`): `doc/develop/application/index.rst` (board files, `EXTRA_CONF_FILE`, `FILE_SUFFIX`), `doc/build/snippets/index.rst`, `doc/build/sysbuild/index.rst`, `doc/develop/west/manifest.rst` (manifest imports), `doc/develop/modules.rst`, `doc/services/task_wdt/index.rst`, `doc/services/storage/retention/index.rst`, `doc/hardware/peripherals/retained_mem.rst`, `doc/services/debugging/coredump.rst`, `doc/services/storage/settings/index.rst`, `subsys/task_wdt/Kconfig`.
- Crux at `bd9efbc7` (and unchanged on `main` for the logging and console files): `zephyr/Kconfig`, `components/logging/ports/zephyr/logging_binding.c`, `components/logging/ports/zephyr/CMakeLists.txt`, `components/cli/ports/zephyr/include/crux/cli_zephyr.h`, `components/cli/ports/zephyr/cli_serial_start.c`, `components/system/`, `components/access/include/crux/access.h`, `components/file/ports/zephyr/CMakeLists.txt`, `components/image_state/`, `components/network_settings/`, `components/web/ports/zephyr/include/crux/web_zephyr.h`, `docs/cli-contract.md`, `docs/component-readiness.md`, `docs/file-service-contract.md`, `docs/boot-composition.md`, `docs/storage-configuration-assessment.md`, `tests/native/configuration_settings_littlefs`, `tests/native/file_littlefs`, `tests/native/web_https`, `tests/native/management_services`, `templates/product/README.md`.
- Crux `main`: `docs/superpowers/specs/2026-10-24-system-health-design.md`, section "Supervising several activities".
- This repository: `scripts/check_boundary.py`, `budgets/limits.json`, `docs/dependencies.md`, `docs/glossary.md`, `docs/roadmap.md`.
- MCUboot design documentation: image test and confirm.
- littlefs design notes: copy-on-write and power-loss resilience.
- IEC 61131-3, programmable controllers, programming languages: tasks, RETAIN variables, run and stop.
- IEC 62443-4-2 by clause title (CR 1.5, 2.8, 2.9, 2.11, 3.4, 4.2, 7.3, 7.4, 7.7; EDR 3.10) and IEC 62443-4-1.
- ETSI EN 303 645, provision 5.1; the EU Cyber Resilience Act, Annex I.
- C. L. Liu and J. W. Layland, "Scheduling Algorithms for Multiprogramming in a Hard-Real-Time Environment", Journal of the ACM, 1973.
