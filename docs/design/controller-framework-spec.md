# Controller framework: base image and application interface

This page specifies the controller framework of Crux Controller: a Zephyr module that composes the Crux services of a networked controller, supervises the controller's health and defines how an application joins it.
This repository builds one image with it, the **base image**, which runs every framework service and no application.
On this page, a **product** is a firmware repository outside this repository, in the sense of Crux's product composition guide, that imports Crux and the controller framework and adds an application.
An **application** is the product code that joins the framework: the product's own control software or a third-party application runtime.
Code in this repository is called "this repository" or "Crux Controller".
The page is the input for the design; the design adopts an item only when its decision in [section 6](#6-decisions) is taken.
It changes no source code; the [architecture](../architecture.md) and the [capabilities](../capabilities.md) describe the current images.

Zephyr is read at the release that the Crux pin names (v4.4.2, `dccb0959`), and Crux at the pinned commit `bd9efbc7`.
A fact that holds only on Crux `main` says "Crux `main`".
A Crux change that Crux has decided and that is on neither the pin nor `main` says "planned in Crux".
A Crux change that the framework needs and that Crux has not decided says "Crux change needed".
A Crux change that Crux has decided to postpone says "deferred by Crux".
Each Crux change carries its issue link, or "issue TBD" where Crux has none.
The terms are defined in the [glossary](#7-glossary).

Each choice carries one label:

| Label | Meaning |
|---|---|
| Established mechanism | A documented mechanism of Zephyr, west or Crux, used as its documentation describes |
| Recommended practice | The option that the Zephyr or nRF Connect SDK documentation recommends among several valid ones |
| Architecture decision | A choice of this framework among valid options; section 6 holds its decision |
| Current platform constraint | Forced by Crux or Zephyr at the pin; it changes when the platform changes |
| Interim workaround | A state that the framework accepts until a planned or needed platform change exists |
| Recovery policy decision | How the controller reacts to a fault; a product may choose differently where the text says so |
| Configurable design decision | A design choice whose value is a build option |
| Reference configuration | Values for the RT1060-EVKB reference board, which a product tunes |
| Product decision | A choice that the framework leaves to each product |

## 1. Requirements

### 1.1 Responsibilities

| Party | Responsible for | Not responsible for |
|---|---|---|
| Crux | Hardware and OS abstraction, and reusable platform services: Access, command line, web, configuration, status, logging, time, file, sockets, system (reset cause and watchdog) | The startup order of a controller, its health policy and the application contract |
| Controller framework | Startup and composition of the Crux services; controller health supervision (watchdog, boot counter, safe mode, diagnostics); the application integration contract | How an application schedules and executes its work |
| Application or third-party application runtime | Its own scheduling and execution model: its threads, their priorities, periods and timing | Startup of the platform services and the hardware watchdog |
| Product | The recovery policy choices that the framework offers (start prerequisites, runtime dependencies and the application's response to them, safe-mode threshold, watchdog policy); the output safe state and output protection during a reset, together with its hardware; the storage medium; device preparation; its board files | The framework's internal policy |

### 1.2 Functional requirements

| # | Requirement |
|---|---|
| F1 | The framework composes the Crux services of section 4.1 and starts them in a defined order from one start function. |
| F2 | The base image runs every framework service with no application. |
| F3 | An application joins through the interface of section 4.5 only; the framework imposes no execution model on it. |
| F4 | Device management offers HTTPS web management and a serial command line, and SSH in builds that carry its licensed stack (section 4.1). |
| F5 | The framework and the application register configuration parameters and status items, which device management shows. |
| F6 | The product selects the build options of section 4.1 with Kconfig. |

### 1.3 Reliability requirements

| # | Requirement |
|---|---|
| R1 | The hardware watchdog supervises the controller from phase 2 of the framework's start function on, through startup and runtime (sections 4.2 to 4.4); phase 1, which only reads registers and retained RAM and is bounded, runs before the watchdog is armed (section 4.2). The boot before `main()` (boot ROM, boot loader, kernel initialisation) is outside R1; the watchdog policy from the boot loader to the application is coordinated with Crux's secure boot work (decision D7). |
| R2 | A hang ends in a reset. The next boot reports the reset cause as far as the hardware reports it, and a detailed fault record only when one could be written before the reset. A failure that is not a hang degrades the controller and is reported. |
| R3 | Repeated fault resets lead to safe mode, which runs a minimal service set from which an operator can recover the controller (section 4.6). A fault in safe mode's own services is recovered by the boot loader or the product's recovery path (section 4.4). |
| R4 | The product declares start prerequisites, which the framework checks before every application start, and runtime dependencies, which the framework reports while the application runs (section 4.4). |
| R5 | In product builds, the application does not start when the hardware watchdog cannot be armed. |
| R6 | Every phase of a normal boot has a bounded, measured duration; first-boot key generation belongs to device preparation. |

### 1.4 Security requirements

| # | Requirement |
|---|---|
| S1 | No default password; the first account is created over a trusted path (IEC 62443-4-2 CR 1.5; ETSI EN 303 645 provision 5.1). |
| S2 | A factory reset needs an authorised operator or physical presence that the product defines; no unauthenticated serial command erases the device. |
| S3 | The items of section 4.9 are decided before the Product Ready milestone. |

IEC 62443-4-2 and the EU Cyber Resilience Act give these items their direction; this page claims compliance with neither.

### 1.5 Portability requirements

| # | Requirement |
|---|---|
| P1 | Nothing in the framework or the interface names a board or SoC; per-board values live in board files (section 4.12). |
| P2 | The framework core (states, supervision policy, boot counter, application contract) is portable C with host tests; OS-specific code lives in the adapter and composition zones (section 4.11). |
| P3 | Linux functions are a later phase, coordinated with Crux: the framework then runs natively on Linux through Crux's Linux providers, not through `native_sim`. Until then the architecture keeps P1 and P2 and adds no abstraction for Linux (section 4.11). |

## 2. Architecture decisions

| # | Decision | Label | Source |
|---|---|---|---|
| A1 | The framework is a Zephyr module (`zephyr/module.yml`) that one Kconfig symbol turns on | Established mechanism | Zephyr "Modules"; the nRF Connect SDK enables its Common Application Framework with `CONFIG_CAF` |
| A2 | A product is a workspace application whose repository is the west manifest repository (T2 topology); it owns `app/`, `main()`, `prj.conf` and its board files and imports the framework and Crux | Recommended practice | Zephyr application types and west topologies; the nRF Connect SDK recommends workspace applications (`ncs-example-application`); Crux `templates/product` |
| A3 | An application joins through one descriptor that the product's `main()` passes to the framework's start function | Architecture decision (D1) | Section 4.5 |
| A4 | The framework runs no execution thread for the application; an application creates its own threads with Zephyr directly | Architecture decision (D1) | Crux ADR-0003 R2: product code uses the OS natively |
| A5 | This repository builds one image, the base image; a test-only fixture application under `tests/` exercises the interface | Architecture decision (D8, D13) | Zephyr's split of applications, samples and tests |
| A6 | The framework core is portable C; OS-specific code sits behind port headers in the adapter and composition zones | Architecture decision | Ports and adapters (A. Cockburn, "Hexagonal architecture"); Crux ADR-0003 R2 |
| A7 | A hang resets the device; the framework restarts no single thread | Recovery policy decision (D4) | Section 4.3 |
| A8 | Safe mode after N consecutive fault resets, N set by Kconfig with default 3 | Configurable design decision | U-Boot boot count limit (`CONFIG_BOOTCOUNT_LIMIT`, `bootlimit`, `altbootcmd`) |
| A9 | In product builds the application does not start without an armed hardware watchdog | Recovery policy decision (D14) | Section 4.2 |
| A10 | Thread priority bands | Reference configuration | Section 4.10 |
| A11 | Device preparation writes the volume and makes the TLS key and certificate; a normal boot never formats a medium and makes a key only in a development or reference build with an explicit option | Architecture decision (D11) | Section 4.7 |

## 3. Current constraints

Each constraint holds at the Crux pin and is a current platform constraint; it names the Crux change that lifts it.

### C1. One storage provider per image

Crux allows one File provider: the RAM disk provider depends on `!DISK_DRIVER_SDMMC` (`zephyr/Kconfig`) and its CMake stops the build when another File selection is on (`components/file/ports/zephyr/CMakeLists.txt`).
One provider therefore serves the application data, the credential store and the settings file.
The RAM disk is a CI form for runners without a medium.

### C2. One reset-cause owner

Crux grants one permission to clear the reset cause; the boot diagnostic owner reads once and passes what it captured (`components/system/include/crux/system.h:80-88`; `components/mgmt_status/include/crux/management_status.h:89-90`, `:103`).
The framework's health service is the owner, and the status service and the boot counter receive the copy.

### C3. One watchdog activation per boot

Crux System starts "the boot's single watchdog activation" with one timeout (`components/system/include/crux/system.h:100-108`) and offers no auto-arm, stop or reconfiguration (`zephyr/Kconfig:274-275`).
The supported timeout range is provider-specific.
Startup and runtime supervision therefore share one timeout, which is chosen once (section 4.2).

### C4. Configuration saving needs a power-cut-safe file system

Crux's Settings File provider of Configuration exists in two selections (`zephyr/Kconfig:438-470`):

- `CRUX_CONFIGURATION_SETTINGS_FILE` needs Reliance Edge (west group `crux-reliance`, source under GPLv2, test images only);
- `CRUX_CONFIGURATION_SETTINGS_FILE_ANY_FS` refuses at CMake and in its source **any image that has `FAT_FILESYSTEM_ELM`**, because a FatFs rename removes the destination first and can lose the settings file at a power cut.

So an image with the microSD FatFs provider has no save provider, and an image cannot keep FatFs for files and another file system for settings.
Configuration on LittleFS over a block device runs on `native_sim` in Crux (`tests/native/configuration_settings_littlefs`), and Crux's File core runs over LittleFS on a flash simulator partition (`tests/native/file_littlefs`); Crux has no selectable LittleFS File provider for a target at the pin or on `main`.
Planned in Crux: a LittleFS File provider with Configuration saving on it (issue TBD).

### C5. Settings File sources under a Crux `tests/` path

Both Settings File selections build corrected copies of Zephyr's Settings File backend from Crux's `tests/native/configuration_settings_file`, so a product build reaches a file under Crux's `tests/` (`zephyr/CMakeLists.txt:158-170`).
Crux change needed: move those sources out of `tests/` (issue TBD).

### C6. Console and logging UART

Zephyr's usual way to share one UART is the shell's log backend (`CONFIG_SHELL_LOG_BACKEND`), which queues log messages and multiplexes them with the shell's output.
Crux refuses every form of it at the pin (the same files are unchanged on `main`):

| Where | What it refuses |
|---|---|
| `components/logging/ports/zephyr/logging_binding.c:58-60` | A build with `CONFIG_CRUX_SERIAL` whose `crux-serial0` UART is the logging UART ("Crux Logging conflicts with Crux Serial") |
| `components/logging/ports/zephyr/logging_binding.c:55-57` | The Zephyr shell's serial backend on the logging UART |
| `components/logging/ports/zephyr/logging_binding.c:41-50` | The Zephyr console on the logging UART, except with logging-only routing (no shell, no console input) |
| `components/logging/ports/zephyr/CMakeLists.txt:18-24` | `CONFIG_SHELL_LOG_BACKEND` and every log backend other than the UART backend |
| `components/logging/ports/zephyr/logging_binding.c:12-18` | On the RT1060-EVK board, any logging UART other than LPUART1, so the console cannot take LPUART1 and move logging elsewhere |
| `components/cli/ports/zephyr/include/crux/cli_zephyr.h:26-27`; `zephyr/Kconfig:184`, `:193`, `:222-224` | The console owns the `crux-serial0` UART: no Zephyr console, log backend, shell or other Crux Serial user on it; Crux Serial is "one explicitly dedicated UART"; an image with the Crux command line has no Zephyr shell unless it is marked as a development image |

So the console needs a second UART at the pin: on the RT1060-EVKB, LPUART3 on header pins, connected with a USB-serial adapter and named by the alias.
Planned in Crux: a build option that selects a separate console UART or one UART shared by the console and Crux Logging (issue TBD).

### C7. SSH and TLS profiles

- Crux Access, and so every management service that depends on it (serial console, configuration service, status service, web sessions, web management, TLS certificate, reboot, File service and network settings), needs the Mbed profile of PSA Crypto: `CONFIG_CRUX_ACCESS` stops the build without `CONFIG_PSA_CRYPTO_PROVIDER_MBEDTLS` (`zephyr/CMakeLists.txt:197-201`; `zephyr/Kconfig:632-637`; Crux `docs/management-in-a-product.md:154-155`).
  An image on the Wolf profile, which SSH needs, therefore has none of these services through the module.
  Crux change needed: Crux Access on the Wolf profile (issue TBD).
- Crux SSH has a private provider interface only: no public header and no `crux::` target, so a composition outside Crux needs a Crux composition interface, which Crux has deferred.
- `CONFIG_CRUX_SSH` needs the Wolf profile; Crux refuses it together with the Mbed TLS module, because two TLS stacks are not a supported image (`zephyr/CMakeLists.txt:285-290`).
  Crux has deferred two TLS stacks in one image.
- The Wolf profile needs a Zephyr patch for its TLS socket backend, whose application in a product is open in Crux (Crux `docs/management-in-a-product.md:58`).
- wolfSSL and wolfSSH are available under GPL-3.0-or-later or a commercial licence ([dependencies](../dependencies.md), group `crux-secure-management`), and this repository is Apache-2.0.

### C8. Crux service threads and supervision

Crux service threads that block without a timeout cannot be supervised by progress.
Crux change needed: a supervision hook in Crux service threads, for example a poll-with-timeout loop that reports progress (issue TBD).

### C9. Access and an unusable store

A credential store that reports itself unusable cannot reopen Crux Access in the same boot (`components/access/include/crux/access.h:91-93`), and Access offers no erase operation at the pin.
Planned in Crux: an Access erase operation (issue TBD).

### C10. Image state

Crux's image state contract (`components/image_state`) has a host provider only, no Zephyr or MCUboot provider.
Crux change needed: an image state provider for the update path ([crux-pilot#297](https://github.com/wonny-labs/crux-pilot/issues/297)).

### C11. Simulated watchdog on `native_sim`

The simulated watchdog of `native_sim` (`CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG`) restarts the process after a missed feed, which then reads the reset cause SOFTWARE, never WATCHDOG (`zephyr/Kconfig:277-288`).
`native_sim` therefore shows only part of the boot counter's watchdog path and never the WATCHDOG cause; host tests and a board show the case with that cause.

### C12. SoC gates

At the pin, these refuse an SoC other than the RT1062, by reading the source; they become Crux changes needed when a second board enters the scope (decision D9):

| Where | What refuses | Services blocked |
|---|---|---|
| `components/logging/ports/zephyr/logging_binding.c:12-31` | "Crux Logging unsupported UART resource": only RT1062 LPUARTs and the `native_sim` UART | Logging, and every configuration on it |
| `components/system/ports/zephyr/system_binding.c` (the final `#error`) | "Crux System unsupported SoC or watchdog resource": only the RT1062 WDOG1 | Health supervision, device management |
| `zephyr/Kconfig:307-348` | Every target File provider of FatFs depends on `SOC_MIMXRT1062`; the board-neutral Reliance Edge provider links source under GPLv2 | Storage, device management |
| `app/management/entropy.cmake:16-20` (this repository) | Needs `CONFIG_ENTROPY_MCUX_TRNG` | Device management |
| `app/boards/*.overlay`, `app/conf/management.conf` (this repository) | Name RT1060 nodes and RT1060 Ethernet driver options | Network, health supervision, device management |

### C13. Linux providers

Crux has Linux providers for File, Logging, Netif, Serial, Sync, System, Thread, Time and Interrupt (`components/*/ports/linux`), and they are test providers until a Linux product is defined (Crux ADR-0003 R5).
Access, command line, Configuration, configuration service, management status, Web, Sockets, TLS certificate, credential store, Reboot, security events, SSH, File service and network settings have Zephyr providers only; the PSA ports of Access, credential store, TLS certificate and Web are crypto ports, not OS providers.

## 4. Proposed design

### 4.1 Services and build options

| Service | Crux interface | Use in the framework |
|---|---|---|
| Web management | Crux Access, web server on the selected TLS profile (`<crux/web_zephyr.h>`), configuration and status services, a packaged page, the reboot routes (`CONFIG_CRUX_REBOOT`) | HTTPS web UI: status, parameters, accounts, reboot |
| Serial command line | Crux console, `crux_cli_serial_start()` in `<crux/cli_zephyr.h>` | Command line with first-account setup (`!setup`); Access closes provisioning after the first save |
| SSH command line and SFTP | Crux SSH and Crux File service | Only with the Wolf profile and a Crux SSH composition interface (C7) |
| Health supervision | Crux System (reset cause, one hardware watchdog activation), Zephyr task watchdog | Sections 4.2, 4.3 and 4.6 |
| Time | Crux Time (monotonic clock, time authority), Zephyr SNTP | Wall time for logs, records and status; every timing decision uses the monotonic clock |
| Logging | Crux Logging (UART logger) | Framework log modules; the application uses Crux Logging directly |
| Configuration | Crux configuration service over the Crux Configuration Settings File provider | Framework and application parameters, shown in device management |
| Network | Zephyr network configuration library, Crux Netif, Crux Sockets profile | Interface up before `main()`; link state for health and status |
| Storage | Crux File, one provider, one mount (C1) | Application data root, credential store roots, settings file (section 4.7) |

Build options, set by the product with Kconfig (the design fixes the symbol names):

| Option | Values | Default | Rule | Label |
|---|---|---|---|---|
| Command line transport | serial, SSH, both | serial | SSH only with Crux's Wolf TLS profile, which needs a commercial or GPL-3.0-or-later licence, and only when Crux offers Access on the Wolf profile and an SSH composition interface (C7, decision D6) | Configurable design decision |
| HTTPS TLS profile | Crux Mbed profile, Crux Wolf profile | Mbed | One profile per image (C7; Crux `docs/management-in-a-product.md:58`); the Wolf value needs Crux Access on the Wolf profile, a Crux change needed (C7) | Configurable design decision |
| Console and logging UART | separate, shared | separate | Shared only with Crux's planned build option (C6, decision D5) | Configurable design decision |
| Start prerequisites | Any of network, storage, Access, configuration, time, web management, command line | network, storage, Access, configuration | Checked by the framework before every application start (section 4.4) | Configurable design decision |
| Runtime dependencies | The same set | the start prerequisites | Reported by the framework while the application runs; the application responds (section 4.4) | Configurable design decision |
| Start without a watchdog | allowed, refused | refused | Allowed only by an explicit option in `native_sim` and bench builds (decision D14) | Recovery policy decision |
| Safe-mode threshold N | 1 to a small maximum | 3 | Section 4.6 | Configurable design decision |
| Stable period | seconds | set by the design | Clears the boot counter (section 4.6) | Configurable design decision |
| Startup phase deadlines | milliseconds per phase, including `init`, `start` and `stop` | from board measurement | Section 4.2 | Reference configuration |
| Image trial deadline | seconds | set by the design | Section 4.8 | Configurable design decision |
| TLS identity at boot | off, on | off | On only in development and reference builds; a product build refuses it (section 4.7, decision D11) | Configurable design decision |
| Leave out a device management service | per service | all built | Least functionality (IEC 62443-4-2 CR 7.7, as direction) | Configurable design decision |

### 4.2 Startup sequence and the startup watchdog

The product's `main()`, or the base image's, calls the framework's start function once; the start function runs these phases in order and returns.
Each phase logs its name and result.
The states and lifecycles that the phases drive are defined in the operating model (section 4.4).

| # | Phase | On failure |
|---|---|---|
| 1 | Read the Crux monotonic clock; read the reset cause once, keep the copy and clear the flags (C2); read and check the retained record; update the boot counter and decide normal boot or safe mode (section 4.6). | A missing clock stops startup; otherwise log, continue without the copy, and count a bad record as empty. |
| 2 | Start the supervisor thread, which arms the hardware watchdog with the one timeout T (C3) and supervises the startup phases. | The watchdog is "not armed"; startup continues, and the application does not start unless the build allows it (decision D14). |
| 3 | Mount the volume once with the keep policy and bind the application data root and the credential store roots; on a volume that device preparation wrote, check that the device identity (TLS key and certificate) exists. | Storage failed; phase 4 fails with it. A missing device identity on a prepared volume sets safe mode for this boot, unless the build has the TLS identity option (section 4.7). |
| 4 | Start security events, the realtime clock, the credential store and Access. | Access failed; device management that needs accounts stays off (section 4.6). |
| 5 | Unless in safe mode or with no application: call the application's `init`, which registers the application's requirements (section 4.5). | Application fault, with the clean-up of a partial `init` (section 4.5). |
| 6 | Start the configuration service with the framework and application parameter tables. | Configuration failed. |
| 7 | Start the status service with the copy from phase 1 and the framework and application items. | Status failed. |
| 8 | Start time synchronisation, outside safe mode. | Time stays unsynchronised. |
| 9 | Register the framework's command tables with `crux_cli_init()` and start the configured command line transports; `crux_cli_serial_start()` refuses a registry that is not ready (`components/cli/ports/zephyr/include/crux/cli_zephyr.h:36-40`). | Command line failed. |
| 10 | Load and register the TLS key and certificate written by device preparation, then start sessions, web management and the listener. | Web management failed. Without a device identity, web management stays off (phase 3). |
| 11 | Check the start prerequisites (section 4.4). | A start prerequisite is not healthy: the application is held, and the controller is degraded. |
| 12 | Unless in safe mode, with an application fault, with a start prerequisite that is not healthy, without an armed watchdog in a build that refuses it, or with no application: activate the application's registered task watchdog channels and call the application's `start` (section 4.4). | Application fault, with the clean-up of a partial start (section 4.4). |

Startup watchdog rules (established mechanism for the parts that Crux and Zephyr provide, architecture decision for the phase deadlines):

- The hardware watchdog is armed in phase 2, before the first phase that touches a medium or the network, so a hang in phases 3 to 12 ends in a reset.
  Phase 1 only reads registers and retained RAM and is bounded.
- Each phase from 3 on has a software deadline (Kconfig, reference values from board measurement); the deadlines of phases 5 and 12 bound `init` and `start`.
  While the current phase is within its deadline, the supervisor feeds the watchdog at a period shorter than T; when a phase passes its deadline, the supervisor writes the retained record with the phase name and stops feeding, and the watchdog resets the device.
- Startup supervision stays active until `start` returns, or until phase 12 decides not to call `start`; only then does runtime supervision begin (section 4.4).
- The supervisor thread has a higher priority than the thread that runs the start function, so a long phase cannot starve it (section 4.10).
  Zephyr's default main thread priority (`CONFIG_MAIN_THREAD_PRIORITY`, 0) is above the supervisor, so the base image and each product set it into the startup band.
- T is one value for the whole boot (C3): it covers the supervisor's feed period plus a scheduling margin, inside the provider's supported range; the phase deadlines are independent of T.
- Comparable practice: MCUboot's Zephyr port feeds the watchdog during long boot loader operations (`CONFIG_BOOT_WATCHDOG_FEED`).

Key generation is part of device preparation (section 4.7, decision D11), so a normal boot has no long phase.
Only a development or reference build with the TLS identity option generates a missing key and certificate in phase 10, with its own deadline set from a measurement on the board for the key type; the status service then reports that the certificate was made at boot.

### 4.3 Runtime supervision

The pattern is Crux's documented one for supervising several activities (Crux `main`, `docs/superpowers/specs/2026-10-24-system-health-design.md`, section "Supervising several activities"; at the pin, the System build already refuses the option it forbids).

| Rule | What the framework does | Label |
|---|---|---|
| One supervisor | One supervisor thread holds the single `crux_watchdog_t` token from `crux_watchdog_start()` and calls `crux_watchdog_feed()` only while every supervised activity has made progress | Established mechanism (Crux System contract) |
| Task watchdog without hardware | `task_wdt_init(NULL)`; one channel per supervised thread, with the channel lifecycle of section 4.4; each channel callback only records the expiry and the channel identifier; the supervisor stops feeding when it sees one | Established mechanism (Zephyr task watchdog; Crux pattern) |
| No hardware fallback | `CONFIG_TASK_WDT_HW_FALLBACK=n`; the Crux System build stops when it is set (`components/system/ports/zephyr/CMakeLists.txt:19-20`) | Current platform constraint |
| No callback-less channel | A channel without a callback resets through `sys_reboot(SYS_REBOOT_COLD)`, which latches a software reset cause and loses the watchdog evidence; every channel has a callback | Established mechanism |
| What is supervised | The framework's threads (supervisor inputs, time synchronisation, storage worker) and each application thread that registers a channel (section 4.5) | Architecture decision |
| Indirect health | Threads that are Zephyr's (HTTP server, network RX and TX, deferred log processing) or Crux's (console, web workers) are not fed from inside; their health is read from link state, network buffer counters, log drop counters and a periodic local probe, until Crux offers a supervision hook (C8) | Interim workaround |
| Policy | **Degrade and report** for a failure that is not a hang (SNTP rounds fail, a save fails, the link is down); **reset** for a hang (a channel expires, a deadline passes, a fatal error); the reactions are in section 4.4 | Recovery policy decision (D4) |
| Retained last-fault record | Before it stops feeding, the supervisor writes the failing channel or phase, the uptime and the reason into a retained RAM record with a checksum (Zephyr retention subsystem over `retained_mem`); the fatal error handler writes a minimal record; the fatal path and code in interrupt context must not block, so the fatal path writes the record without a mutex (with `CONFIG_RETENTION_MUTEXES`, `retention_write` takes one), by a mechanism that the design chooses; the next boot reads it once; placement and validity rules are in section 4.6 | Established mechanism (Zephyr retention) |
| Reporting | The status service shows the controller state, the application state, each service's health, the reset cause, the boot counter, the last-fault record and the watchdog state; liveness from outside is ping, link state and a light status endpoint | Architecture decision |

A per-thread restart is a process-manager pattern that Zephyr threads do not support: `k_thread_abort` leaves locks and sockets behind, Crux Access cannot reopen after an unusable store (C9), and the watchdog has one activation per boot (C3).
So a hang resets the device (decision D4).

### 4.4 Operating model

This section defines the supervision phases, the task watchdog channel lifecycle, the application lifecycle and state, the controller state, service health and the reactions to faults.
The other sections use these definitions; section 4.6 holds the mechanisms of recovery (boot counter, retained record, safe-mode service set, factory reset).

#### Supervision phases (architecture decision)

| Phase | From | Until | What the supervisor feeds by |
|---|---|---|---|
| Before framework startup | Reset | The framework's start function | Outside R1: boot ROM, boot loader and kernel initialisation; the watchdog policy from the boot loader to the application is coordinated with Crux's secure boot work (decision D7) |
| Not armed | The start function | Phase 2 arms the hardware watchdog | Nothing; phase 1 only reads registers and retained RAM |
| Startup supervision | Phase 2 | `start` returns, or phase 12 decides not to call `start` | Each startup phase within its deadline (section 4.2), and every active channel |
| Runtime supervision | The end of startup supervision | A reset | Every active channel has made progress and none has expired |
| Feeding stopped | A phase passes its deadline, `stop` passes its deadline, or a channel expires | The hardware watchdog resets the device | Nothing |

When phase 2 cannot arm the watchdog, Crux System reports it as unavailable or faulted, the status service shows "not armed", and no phase above applies; the application then starts only in a build that allows it (decision D14).

#### Task watchdog channel lifecycle (established mechanism for the Zephyr calls, architecture decision for the rules)

A **channel requirement** is a name and a reload period that `init` registers through `ctx`; an **active channel** is a Zephyr task watchdog channel that `task_wdt_add()` returned.

| Step | Rule |
|---|---|
| Register (`init`) | The framework records the requirement and creates no Zephyr channel. A requirement with a reload period of zero, a name already registered, or one more than the free capacity is refused, and `init` sees the error. |
| Capacity | `CONFIG_TASK_WDT_CHANNELS` (Zephyr default 5, range 2 to 100) bounds the framework's own channels and the application's requirements together; the framework reserves its own channels, and the product raises the value when its application needs more. The framework keeps a fixed table and has no resource manager. |
| Activate (phase 12, and each operator start) | The framework calls `task_wdt_add()` for every requirement immediately before it calls `start`. `task_wdt_add()` feeds the new channel at once, so timing starts at activation, and each application thread feeds its channel within the reload period from then on. |
| Partial activation | When `task_wdt_add()` fails for one requirement, the framework deletes the channels it activated in this step with `task_wdt_delete()`, does not call `start`, calls `safe_state`, and the application enters fault. |
| Feed | An application thread feeds its own channel through the handle that its registration returned in `ctx`, because the Zephyr channel identifier may change at each activation; the supervisor feeds the hardware watchdog only while no channel has expired. |
| Release (`stop`, fault) | After `stop` returns, every application thread has ended (section 4.5), and the framework deletes every active application channel; on an application fault it deletes them after `safe_state`. The requirements stay registered for a later operator start. |
| Re-activate (operator start) | The framework checks the start prerequisites, activates the registered requirements again and calls `start`; `init` does not run again in the same boot. |
| Expire | The channel callback records the channel identifier; the supervisor writes the retained record, calls `safe_state` when the application has been initialised, and stops feeding. After an expiry callback, Zephyr's task watchdog re-arms its timer only on the next feed or add of a channel, so the callback can repeat; recording is idempotent, the framework does not depend on further callbacks, and it neither feeds, deletes nor reuses the expired channel before the reset. |

The framework's own channels follow the same rules, activated in the phase that starts the supervised thread.

#### Application lifecycle and state (compare the nRF Connect SDK CAF module states and systemd unit states)

| State | Entered when | Leaves to |
|---|---|---|
| Absent | No descriptor (the base image) | — |
| Not initialised | A descriptor, before phase 5 | Initialised when `init` succeeds; fault when it fails; held when the boot is in safe mode |
| Initialised | `init` succeeded | Running when `start` succeeds; fault when activation or `start` fails; held when phase 12 decides not to call `start` |
| Held | The framework decided not to start the application: safe mode, a start prerequisite that is not healthy, or a watchdog that is not armed in a build that refuses it | Running on an operator start when the reason was a start prerequisite and every start prerequisite is healthy; otherwise only a reset |
| Running | `start` succeeded | Stopped when `stop` returns within its deadline; fault when the application reports a fault |
| Stopped | An operator stop, or a planned reset, after `stop` returned | Running on an operator start, outside safe mode, when every start prerequisite is healthy |
| Fault | `init`, activation or `start` failed, or the application reported a fault | Only a reset |

A hang (a channel expiry, or `stop` past its deadline) does not end in a reported fault state: the device resets (decision D4).

#### Controller state (architecture decision; "degraded mode" and "recovery mode" in common embedded usage)

| State | Meaning |
|---|---|
| Starting | From the start function until startup supervision ends |
| Operational | A normal boot after startup supervision: every required service (start prerequisite or runtime dependency) is healthy, and the hardware watchdog is armed or its absence is allowed by the build. The controller then provides its defined functions, whatever the application state is: an operator stop or an application fault leaves the controller operational and is reported as the application state. |
| Degraded | A normal boot after startup supervision in which at least one required service is degraded or failed, or the watchdog is not armed in a build that refuses it; device management runs where its services allow |
| Recovery | A boot in safe mode (section 4.6), entered when the boot counter reaches N or when a prepared device has no device identity (section 4.7); it lasts until the next reset |

A service that is not required reports its own health, and its failure does not change the controller state.

Two rules use these states:

- the boot counter clears when the controller has been operational without interruption for the stable period (section 4.6);
- image confirmation needs the operational state and the conditions of section 4.8.

#### Service health and required services

Each framework service has one health value: **healthy**, **degraded** (running with a reported failure), **failed** (start failed or stopped), or **absent** (left out at build time).

| Service | Healthy | Degraded | Failed |
|---|---|---|---|
| Network | Link up and an address assigned (static or a DHCP lease) | Link down, or no address, after the interface came up | The interface did not come up |
| Storage | Volume mounted and roots bound | A write or save answers an error, or a size limit is reached (section 4.7) | Mount or bind failed |
| Access | Credential store usable | — | Store unusable (C9) or start failed |
| Configuration | Service started with its tables; an image without a save provider reports "not persistent" as a status item (section 4.7) | The last save failed | Start failed |
| Status | Service started | — | Start failed |
| Time | Wall time synchronised and younger than the stale age | Not yet synchronised, or stale | Synchronisation could not start |
| Web management | Listener accepts TLS connections | — | Start failed, or no device identity |
| Command line | Every configured transport started | Some configured transports started | No transport started |

Reachability of a remote peer is not part of any service's health, because it depends on the network outside the device; an application that needs it reports it as its own status item.

The product's required services are of two kinds:

- **Start prerequisites**: the framework checks them in phase 11 and before every operator start, and holds the application while one of them is not healthy.
- **Runtime dependencies**: the framework reports a change of their health through the status service and the read-only service health in `ctx`; the application decides its response, and the framework neither stops nor restarts the application because of it.

#### Faults and reactions (recovery policy decision, D4)

| Event | Framework reaction | `safe_state` | Afterwards |
|---|---|---|---|
| Operator stop | Calls `stop`, then releases the application's channels | After `stop` returns | Application stopped; controller state unchanged |
| Recoverable application fault: `init`, activation or `start` fails, or the application reports a fault | Releases the registrations and channels | Yes | Application fault; controller state unchanged |
| A service fails without a hang | Degrade and report; a start prerequisite holds the application before a start; a runtime dependency is reported to the application | No | Controller degraded when the service is required |
| A startup phase, `init`, `start` or `stop` passes its deadline, or a channel expires | Writes the retained record and stops feeding | When the application has been initialised, from the supervisor, best effort | Reset by the hardware watchdog; a fault reset for the boot counter |
| Fatal error (`k_sys_fatal_error_handler`) | Calls no application entry; writes a minimal retained record when the retained region is usable, and resets | No | A fault reset for the boot counter |
| CPU lockup, or a handler that cannot run | Nothing runs; the unfed hardware watchdog resets the device | No | Reset cause as the SoC reports it; no record |
| N consecutive fault resets | Safe mode (section 4.6) | — | Controller in recovery |
| A hang or fatal error in safe mode's own services | The same reset; safe mode cannot escape a fault in its own services | — | Safe mode repeats; the final recovery is the boot loader or the product's recovery path (section 4.6) |

Outputs during and across a reset keep a safe state only through the board's hardware design, which the product documents (section 4.5).

### 4.5 Application interface

**The application interface holds only what the framework owns (decision D1).**
The names below are proposals; the design fixes them.

The descriptor, which the product's `main()` passes to the start function.
Each entry is specified by the results it guarantees and the time it may take; how the application reaches them, including threads or work items of its own, is the application's choice:

| Entry | Guaranteed results |
|---|---|
| `init(ctx)` | Mandatory. Returns within its phase deadline. On success, every channel requirement, status item and parameter table that the application needs is registered, and none is registered later in the boot. It may read its data root within the deadline; it does not depend on configuration, time, web management or the command line, which start after it. On failure, nothing that `init` started is still running. |
| `start(ctx)` | Mandatory. Returns within its phase deadline. On success, the threads that feed the activated channels run and feed within their reload periods. On failure, every thread that `start` created has ended before it returns. |
| `stop(ctx, reason)` | Mandatory. Returns within its deadline. On return, every thread of the application has ended, so the framework can release its channels. |
| `safe_state(ctx)` | Mandatory. Puts outputs into the product's defined safe state; never blocks |

What the framework gives through `ctx`, because the framework owns it:

- registration of task watchdog channel requirements and the handle that feeds each channel, with the lifecycle of section 4.4;
- registration of status items, which the framework adds to the status service;
- registration of a parameter table, which the framework adds to the configuration service;
- the assigned application data root of Crux File;
- read-only controller state and service health.

The application calls Crux's public APIs directly for logging, time, sockets, file access under its data root and configuration reads, and Zephyr directly for threads and synchronisation.
The framework does not wrap them, following the repository rule against pass-through wrappers.

The interface starts at the lowest stability tier, because no consumer exists to confirm its shape.
It is validated against a first real runtime consumer (a product's control software or a third-party application runtime, not the fixture application) before its tier is raised.
This repository defines no stability tiers; the design defines them, modelled on Crux ADR-0001 Decision 4.

A framework-owned periodic task that calls an application entry point is not part of the first version.
If a consumer needs one, it can be added later as an optional helper on top of this interface.

Call order and concurrency:

| Rule | Detail |
|---|---|
| One caller | The framework calls `init`, `start` and `stop` from one framework thread, in that order, never concurrently with each other |
| Once | `init` runs once per boot; `start` runs once per transition to running; `stop` runs only in the running state |
| `safe_state` contexts | The framework calls `safe_state` after a normal stop (an operator stop or a planned reset), on a recoverable application fault, and from the supervisor on a deadline overrun or a channel expiry when the application has been initialised (section 4.4); it may run concurrently with the application's threads, so it is idempotent, takes no lock, allocates nothing and logs nothing |
| No call from the fatal error handler | The fatal error handler calls no application entry; it writes the minimal retained record and resets (section 4.4) |
| Partial `init` failure | When `init` fails after some registrations, the framework releases them (requirements dropped, status items and parameters marked unavailable), calls `safe_state`, enters fault and calls neither `start` nor `stop` |
| Partial `start` failure | When activation or `start` fails, the framework deletes the channels it activated, calls `safe_state`, enters fault and releases the registrations; threads that `start` created are the application's to end before it returns its error |
| Thread clean-up | The framework never aborts an application thread; `stop` ends them; when `stop` passes its deadline, the framework treats it as a hang (section 4.4) |
| Channel release | After `stop` returns, and on fault, the framework deletes every active application channel (section 4.4) |
| Second start function call | Refused, as is a descriptor without a mandatory entry |
| Framework boundaries | The application may not block framework threads, take framework locks or call device management |

Safe state is best effort.
The framework calls `safe_state` in the cases above, but not from the fatal error handler and not after a CPU lockup, and during and across a reset outputs keep a safe state only through the board's hardware default, which the product designs and documents (IEC 61508-4 defines "safe state" for functional safety; this page uses the word in that sense and claims no safety integrity).

### 4.6 Recovery

The transitions into and out of recovery are defined in section 4.4; this section holds the mechanisms.

| Item | Rule | Label |
|---|---|---|
| Retained region | The boot counter and the last-fault record share one retained region with a prefix and a checksum (Zephyr retention subsystem). By default it sits in on-chip RAM that neither the boot ROM nor Zephyr's startup initialises, named by the board overlay; external SDRAM is not assumed to retain data, because the boot ROM initialises the SDRAM controller again at every boot | Recovery policy decision |
| Fault reset | A reset whose captured cause includes WATCHDOG, or whose valid record names a deadline, a channel expiry or a fatal error; also, without a valid operator reset marker, a SOFTWARE reset or a reset whose captured cause includes CPU_LOCKUP. CPU_LOCKUP together with SOFTWARE is treated as a SOFTWARE reset, because some SoCs report both from one status bit (on the RT1060-EVKB one SRC status bit serves lockup and SYSRESETREQ, and Zephyr's `drivers/hwinfo/hwinfo_mcux_src.c` reports it as both). Crux reports zero, one or several latched cause bits (`crux_reset_cause_t`), and any one condition of this row makes the reset a fault reset | Recovery policy decision |
| Not a fault reset | A reset with a valid operator reset marker, unless WATCHDOG is latched or a valid record names a deadline, a channel expiry or a fatal error; a PIN reset or a DEBUG reset that meets no condition of the Fault reset row. The counter keeps its value. The framework writes the marker from Crux Reboot's policy callback at the check before the reset, and before its own operator resets (safe-mode exit and factory reset); Crux Reboot asks the callback twice without saying which check it is, so the framework tracks the order of the calls, or consumes a marker left by a request that never reset | Recovery policy decision |
| Power cycle | A captured POR cause, or a region whose prefix or checksum is invalid, means that the region did not survive: the counter starts at zero and no record is reported, whatever other cause bits are latched. On the RT1062 a POR cause is never captured and a power-on reads as PIN, so detection of a power cycle there relies on the invalid-region rule | Recovery policy decision |
| Boot counter | Counts consecutive fault resets; it saturates at its maximum instead of wrapping | Recovery policy decision |
| Interrupted write | The record and counter are written with their checksum last; a write that a reset interrupts fails the checksum on the next boot and counts as an empty region, while the captured reset cause still decides whether the reset was a fault reset | Recovery policy decision |
| Stale record | Each record carries a sequence number; the next boot reads it once, passes it to the status service and marks it consumed, so a later reset does not count or report it again | Recovery policy decision |
| Image identity | The region stores an identifier of the image that wrote it; a boot whose image differs, after an update or after the boot loader reverted an image, clears the counter and reports the previous image's last record | Recovery policy decision |
| Safe mode entry | After N consecutive fault resets (Kconfig, default 3) the next boot enters safe mode; a prepared device without its device identity also boots in safe mode (section 4.7) | Configurable design decision |
| Safe-mode service set | Network, storage, credential store, Access, configuration service (which web management needs), status, web management when the device identity exists, the serial command line and logging, plus the reset cause and last-fault record; no application, no time synchronisation and no optional service | Recovery policy decision |
| Counter reset | The controller is operational without interruption for the stable period (Kconfig), an authorised operator command clears it, or a different image boots | Recovery policy decision |
| Safe-mode exit | An authorised operator command clears the counter and resets into a normal boot; a different image also boots normally | Recovery policy decision |
| Fault resets in safe mode | Safe mode cannot escape a hang or fatal error in its own services: the device resets, the counter stays saturated, and safe mode repeats. A test image that is not confirmed is reverted by the boot loader at that reset (section 4.8); for a confirmed image, the final recovery is the boot loader's or the product's recovery path, such as a new image through the programming interface, decided with Crux's secure boot work (decision D7) | Recovery policy decision |
| Storage or Access failure | Device management that needs accounts stays off; the controller is degraded or in recovery, and the serial log and the status service (where it runs) show the cause; Access cannot reopen in the same boot (C9), so a replaced medium takes effect after a reset; recovery is device preparation again, or a factory reset by a physical-presence input if the product defines one | Recovery policy decision (D15) |
| Factory reset | An authorised operator command through the planned Crux Access erase operation (C9) erases credentials (accounts) and configuration and returns to first-account provisioning; it keeps the device identity (TLS key and certificate), which only device preparation replaces; a product may add a physical-presence input such as a button held at boot; no unauthenticated serial command erases the device | Recovery policy decision (D15) |

Comparable mechanisms: U-Boot's boot count limit switches to an alternative boot command after a set number of failed boots, and Zephyr's retention subsystem offers a boot mode that survives a warm reset.
Whether the reset cause reads WATCHDOG after a WDOG1 reset, whether the retained region survives it, whether a software reset reads CPU_LOCKUP together with SOFTWARE, with and without the marker, and whether a power cycle, which reads as PIN, leaves the region invalid are board facts of the RT1060-EVKB.
A board check early in phase 2 shows them, in a run that needs its own board authorisation (section 4.14).

### 4.7 Storage, configuration and device preparation

| Item | Rule | Label |
|---|---|---|
| Reference board medium | The whole microSD card is one LittleFS volume over the card's block device (`FS_LITTLEFS_BLK_DEV`) | Reference configuration (D3) |
| Product medium | A product chooses its medium (for example eMMC or NOR flash) and its Crux File provider; the framework names neither | Architecture decision |
| Credentials on removable media | Whether the credential store may sit on a removable card is a product security decision | Product decision |
| One mount, never format | The composition mounts the volume once with the keep policy and binds the roots; no service mounts on its own; the framework never formats, so a blank or foreign medium does not mount and its data stays untouched | Architecture decision |
| Configuration saving | Crux's Settings File provider for any power-cut-safe file system (`CRUX_CONFIGURATION_SETTINGS_FILE_ANY_FS`) on the LittleFS volume, once Crux's planned LittleFS File provider exists (C4) | Established mechanism |
| Interim storage | Until then, the microSD FatFs provider serves files and the credential store, Configuration has no save provider, and the status service reports that parameters are not persistent | Interim workaround |
| Device preparation | A preparation image or a host tool (littlefs-python, littlefs-fuse) writes the volume and its layout, and the device makes and stores its TLS key and certificate (its device identity) during preparation | Architecture decision (D11) |
| Identity at a normal boot | A normal boot makes no key, except in a development or reference build with the TLS identity option (section 4.1); in any other build, a prepared volume without a device identity puts the boot into safe mode, the status service and the serial log report the missing identity, and the recovery is device preparation again | Architecture decision (D11) |
| Factory reset scope | Credentials and configuration are erased; the device identity is kept (section 4.6) | Recovery policy decision (D15) |

LittleFS is copy-on-write: a rename replaces a file atomically, so a power cut leaves the old or the new file.
Its guarantee covers the file system, not the medium's own controller during a power cut, so a power-cut test on the board is the evidence for a medium.
A PC cannot mount the card without a LittleFS tool; files leave the device through device management.
FatFs stays a selectable Crux File provider for other products, and a build with commercially licensed Reliance Edge may select it behind the same Crux File and Configuration interfaces.

The design specifies, for each product medium:

- **File system full**: a save or a file write answers an error, the status service shows it, and the application data root has a size limit so that it cannot fill the credential store and settings;
- **Power-cut integrity**: the settings file and the credential store survive a cut at any point, shown by a power-cut test on the medium;
- **Configuration compatibility after an update**: the parameter table carries a version; a new image gives new parameters their defaults, keeps stored values whose key and type match, and reports discarded values; a deliberate downgrade is a product decision;
- **Configuration compatibility after a rollback**: when the boot loader reverts an image, the earlier image reads values that the reverted image may have saved, with the same rules: it keeps values whose key and type match, gives defaults where they do not, reports them, and leaves keys it does not know in place; so a parameter keeps its type for as long as its key exists, and a changed type takes a new key.

### 4.8 Secure boot and update

The partition layout, image format, signing and the confirmation call come from Crux's secure boot work (decision D7); the framework defines none of them.
MCUboot reverts a test image that is not confirmed only when the device next resets (MCUboot test and revert); a test image that keeps running unconfirmed is not reverted.

| Item | Rule | Responsible |
|---|---|---|
| Health verdict | The framework reports a test image as healthy when, during its trial, all of these hold, not uptime alone: the controller is operational; every start prerequisite is healthy and every device management service that the build includes has started; the application, when present and not stopped by an operator, has been running for the stable period; no fault reset happened since the test image first booted; the configuration loaded with a compatible version (section 4.7) | Framework (health input) |
| Confirmation | When the verdict is healthy, the update component confirms the image through Crux's image state contract (C10) | Update component |
| Trial deadline | When the verdict is not healthy by the trial deadline (Kconfig, counted on the monotonic clock from the start of the boot), the update component requests a planned reset, with `stop` and `safe_state` as for an operator reset, and the boot loader reverts the image at that reset. This planned reset carries no operator reset marker, so it counts as a fault reset, which has no effect because the reverted image clears the counter (section 4.6) | Update component, on the framework's verdict |
| Configuration after a rollback | Section 4.7 | Framework |

The verdict needs no particular device management service: a build without web management is confirmed on the same conditions.
Until Crux offers an image state provider (C10), the images are only prepared for this (interim workaround).

### 4.9 Security items to specify

| Item | Rule | Decision |
|---|---|---|
| First trusted enrolment of the self-signed certificate | Device preparation records the certificate fingerprint (on a label or in the preparation record), and the serial command line shows it, so the operator checks it at the first connection instead of trusting on first use (RFC 7435 describes trust on first use); a product may install a certificate from its own CA instead | D11 |
| Serial command line in production | Every command needs an Access login after the first account; the product chooses whether the console is composed in production, for provisioning only, or always; physical access to the port is part of the trust model | D16 |
| Factory reset authority | Section 4.6 | D15 |
| HTTPS file transfer | Confined to the application data root, with limits on file size, total size, concurrent transfers and file names; it needs Crux's web adapter for the File service ([crux-pilot#188](https://github.com/wonny-labs/crux-pilot/issues/188)) | D10 |
| Audit persistence | Crux security events are drained to the log at the pin; the design chooses when they reach storage (for example at once for authentication failures and account changes, batched for others), weighing loss at a power cut against medium wear; timestamps come from unauthenticated SNTP (IEC 62443-4-2 CR 2.8 to 2.11, as direction) | D16 |

### 4.10 Priority bands (reference configuration)

Zephyr priorities, where a lower number is a higher priority.
The values are a reference configuration for the RT1060-EVKB, and a product tunes them for its deadlines, jitter, network load and priority inversion.

| Band | Priority | Threads |
|---|---|---|
| Application | 3 to 6 | Threads the application creates |
| Supervisor | 7 | The health supervisor |
| Startup | 8 | The thread that runs the start function |
| Framework services | 9 to 10 | Time synchronisation, storage worker, status updates |
| Device management | 11 to 13 | Crux web session and management workers, the console, the reboot and network settings workers, the security event drain |
| Zephyr threads | as Zephyr sets them | HTTP server (lowest preemptive), network RX and TX, deferred log processing (14) |

Crux's service workers default to priority 6 at the pin (`zephyr/Kconfig:85-135`: security event drain, reboot worker, network settings worker, web session worker, web management worker and console), which is inside the application band, so the framework sets each of those Kconfig priorities into the device management band.
The supervisor sits below the application band, so an application thread that holds the CPU starves the supervisor and ends in a reset, and above the startup thread and device management, so a long phase, a TLS handshake or key generation cannot starve it.
Zephyr mutexes apply priority inheritance and semaphores do not, so a shared resource between bands uses a mutex.
The design checks the bands against the priorities of Zephyr's network threads and measures jitter under network and TLS load on the board (section 4.13).
A Zephyr userspace or MPU partition for the application is later work.

### 4.11 Source zones and OS neutrality

`scripts/check_boundary.py` checks only the trees in its `RULES` (`app/src`, `workload`, `app/compose`, `app/os`; lines 125-162), and `check()` scans only those trees (lines 308-313).
A framework source outside them would escape the check, so every source of the module, the base image and the fixture application lives in a checked zone (proposal; the design fixes the paths):

| Tree | Holds | May include |
|---|---|---|
| `include/` | The application interface header that a product includes | ISO C and public `<crux/NAME.h>` headers |
| `framework/src` (portable core) | States, supervision policy, boot counter, safe mode, retained record format, startup phase table, time synchronisation and management policy, and the port headers | The rules of today's `app/src`, with no Zephyr header |
| `framework/compose` (composition zone) | Storage mount, management start, command line start | The rules of today's `app/compose`, plus `zephyr/fs/littlefs.h` and `<crux/cli_zephyr.h>` |
| `framework/os` (adapter zone) | Supervisor thread, task watchdog, retained record access, fatal error handler, SNTP adapter | The rules of today's `app/os`, plus `zephyr/task_wdt/task_wdt.h`, `zephyr/retention/retention.h`, `zephyr/fatal.h`, `zephyr/devicetree.h` and `zephyr/device.h` |
| `app/` (base image) | `main()` | ISO C and the header of `include/` |
| `tests/` fixture application | The contract test application (section 4.13) | ISO C, the header of `include/`, public `<crux/NAME.h>` headers and the Zephyr headers that its threads need |

`RULES` gains one rule per tree, and a source file of the module that no rule covers fails the check.
Each new header is a separate reviewed boundary change under CONTRIBUTING "The boundary", with its reason in [composition-zone.md](../composition-zone.md) and a case in `tests/tooling/test_boundary.py`.
The composition zone gains `zephyr/fs/littlefs.h`, for the LittleFS mount, unless Crux's planned LittleFS provider mounts the volume itself, and `<crux/cli_zephyr.h>`, which `COMPOSITION_CRUX_HEADERS` does not list.
The adapter zone gains `zephyr/task_wdt/task_wdt.h`, `zephyr/retention/retention.h` (the framework uses the retention API, not the `retained_mem` driver header), `zephyr/fatal.h`, `zephyr/device.h` and `zephyr/devicetree.h`, which find the retained region.

The portable core runs in host tests with fake ports.
The Zephyr adapter and composition zones are the only OS-specific code.
Portability is a current architecture requirement (P1, P2): the portable core, the separated OS-specific zones and the host tests hold in every phase, and the framework adds no abstraction for Linux before it has a Linux function to serve.
Linux functions are a later phase (phase 6, section 4.14), coordinated with Crux: the framework then runs natively on Linux through Crux's Linux providers, not through `native_sim`.
It needs Linux providers for the Crux components that have Zephyr providers only (C13), which Crux designs when its first Linux product is defined (Crux ADR-0003 R5).

### 4.12 Boards, memory and variants

| Rule | Mechanism | Label |
|---|---|---|
| Per-board values live in board files | `app/boards/<board>.conf`, merged with `prj.conf` when `CONF_FILE` is unset, and `app/boards/<board>.overlay`, in the base image and in each product | Established mechanism (Zephyr application development) |
| Variants are fragments | `EXTRA_CONF_FILE`, `EXTRA_DTC_OVERLAY_FILE`, `FILE_SUFFIX` with fallback | Established mechanism |
| Roles by devicetree | Aliases `crux-serial0` (console) and `crux-watchdog0` (watchdog), `chosen` `zephyr,log-uart` (logging), node label `controller_storage` (storage) | Established mechanism |
| No board name in sources | Nothing in the framework module, the base image's sources or the application interface names a board or SoC | Architecture decision |
| Snippets only for cross-cutting settings | Debug and the RAM disk CI form; never per-board values | Established mechanism (Zephyr snippets) |
| Generic Kconfig dependencies | `CRUX_CONTROLLER_FILE` depends on `CRUX_FILE_FATFS_RT1060` (`app/Kconfig:40`); it changes to a generic "Crux File provider present" symbol or a `DT_HAS_*_ENABLED` test when Crux offers one | Current platform constraint |
| Board as a build input | `scripts/build-board.sh` builds the RT1060-EVKB only; the design makes the board target an input and builds in `build/<board folder>/<configuration>` | Architecture decision |

Adding a board takes, in this order: the board's `.conf` and `.overlay`, the aliases and `chosen` nodes, the partition layout from the secure boot work, a CI row, and the smallest build configuration as its first passing build.
A second board is outside the current scope (decision D9), and the SoC gates of C12 apply.

**RT1060-EVKB memory budget** (`mimxrt1060_evk@B/mimxrt1062/qspi`).
All RAM of this board configuration is the 32 MB SDRAM; the on-chip regions are unused, except the retained region of section 4.6, which the board overlay places in on-chip RAM.
The per-configuration sizes are in the roadmap, [Static size per configuration](../roadmap.md#static-size-per-configuration).
No build of the base image exists, so its planning figure is an upper bound derived from those sizes, not a build result: `management`, minus the 524,288-byte RAM disk (`app/boards/management.overlay:24`), plus the deltas of `file` over `workload`, `system` over `workload` and `sntp` over `net`.
With the roadmap's figures that gives at most about 326 KB of FLASH and 755 KB of RAM, before the serial console, the supervisor and the task watchdog, which no `Budget` row measures.
Both stay below 5 percent of their regions, inside the 25 percent free margin of `budgets/limits.json`, which is a budget of the reference board; a product sets its own budget for its board.
The RAM disk CI form adds the 512 KiB disk back, about 1.3 MB of RAM; the LittleFS provider replaces the FatFs one in the figure.

| Variant | Why | Mechanism |
|---|---|---|
| Base image | The framework with no application | The base image's `prj.conf` plus one fragment, with the board files |
| RAM disk form | CI runners and benches without a medium; never saves configuration | One snippet |
| Debug form | Stack and thread analysis | `FILE_SUFFIX=debug` or one snippet |
| Per board | Different nodes and drivers | The board's own `.conf` and `.overlay` only |

The fixture application is a test, not an image or variant: it has no board build and no `Budget` row, and it is not a product template; the integration guide links it as the code reference (section 4.16).

### 4.13 Verification

| Layer | What it shows | Where |
|---|---|---|
| Crux component tests | Crux behaviour | Crux's CI |
| Framework unit | The portable core: the states and lifecycles of section 4.4, policies, boot counter and retained record rules, startup phase table, health verdict and trial deadline | Host tests, every pull request |
| Framework integration | Composition, startup order, startup and runtime supervision, safe mode, the application contract through the fixture application, the verification scenarios of section 5.2 | `native_sim`, every pull request |
| Reference image | The base image builds for the board within its budget and runs on `native_sim`, with image-level regression tests | CI, every pull request |
| Product integration | An independent west workspace imports the framework as a product would (T2), builds and runs on `native_sim` | The nightly tier of a tiered CI as Crux documents it (Crux `main` at `62ed69f1`, `docs/ci.md`, "Use in a product repository") |
| Hardware | Watchdog reset cause and the retained region across a WDOG1 reset, a pin reset and a power cycle; the cause of a software reset (CPU_LOCKUP together with SOFTWARE, with and without the marker); an invalid region after a power cycle that reads as PIN (these early in phase 2); power cut on the medium, timing and jitter of application threads, TLS sessions under application load, output state during a reset | The board, in approved runs only |

The image keeps essential system-level regression tests even where Crux tests the component: an HTTPS login, the TLS-only listener and the start order in the base image.
The `native_sim` scenarios keep code of this repository and those image-level checks; a case that only repeats Crux behaviour in detail is dropped (decision D8).

| Scenario and cases | Code of this repository under test | Keep or drop | Reason |
|---|---|---|---|
| `native_sim/file`: `not_ready`, `mounted_not_bound`, `mount_failure`, `bind_failure` | `app/compose/storage_mount.c` through `storage_port.h` | Keep the mount and bind cases (bind before mount fails, a second mount and a second bind are refused, a kept blank volume does not mount and nothing is formatted, a failed bind can be retried) in the framework's storage composition; drop the assertions that only call `crux_file_*` and check its not-ready answer | Mount once, keep, never format and the bind order are this repository's composition; File's not-ready answers are covered by Crux's `tests/native/file_roots` and the File provider tests |
| `native_sim/file`: `roundtrip` | `app/src/config_store.c`, the workload's record | Drop | The record belongs to the workload, which leaves the framework; parameters use Crux Configuration, and the framework's save path gets the scenario of acceptance criterion 12 |
| `native_sim/net` | `app/src/net_client.c` (TCP peer exchange) | Drop | The framework keeps no TCP peer exchange; Crux Sockets and Netif have their own tests |
| `native_sim/sntp`: all seven cases | `app/src/time_sync.c`, `app/src/time_sync_policy.c`, `app/os/time_sync_zephyr.c` | Keep | The glue and policy between Zephyr's SNTP library and Crux Time (first sync, kiss-o'-death, timeout, range, step refusal, threshold, stale age) are this repository's code |
| `native_sim/system`: `reset_cause` | `app/src/health.c` | Keep, extended into the start-order scenario | The single reset-cause owner (C2) is this repository's code |
| `native_sim/system`: `watchdog_unsupported`, `period_out_of_range` | `app/src/health.c`, `app/src/health_policy.c` | Keep, in the supervisor | This repository's policy: refuse a timeout that the watchdog cannot cover before Crux is asked, and hold the application when the watchdog does not arm unless the build allows it (decision D14) |
| `native_sim/workload` | `app/src/workload_thread.c` (simulated plant) | Drop | The workload leaves the framework; the fixture application gets its own scenarios |
| `native_sim_mbed/management`: cases 01 to 03, 06, 07 | `app/compose/management_start.c`, `app/src/management_policy.c`, the route table and the packaged page | Keep | The start sequence, the certificate the composition registers, the route table behind a session and the packaged page are this repository's composition and policy |
| `native_sim_mbed/management`: cases 04, 05, 08, 09, 10 | None: Crux's web adapter and Access | Keep one case each for the TLS-only listener and a login with its poll as image-level regression; drop the rest | TLS 1.3 only, no plain HTTP answer, the queued login and its poll, and the CSRF refusal are Crux behaviour, tested in Crux's `tests/native/web_https` and `tests/native/management_services` |

- The host tests stay and gain the portable core.
- The smallest board build (`prj.conf` alone) stays as the first build a new board must pass; it takes another name than `base` (decision D13).
- The board builds of `workload`, `net`, `file`, `system`, `sntp` and `management` are replaced by the base image.
- `budgets/limits.json` gains a row for the base image; its `_comment` makes a change there a reviewed change.

### 4.14 Phases

| Phase | Content | Ends with |
|---|---|---|
| 1. Foundation | The Zephyr module, the repository role (D12), service composition, the base image, the boundary check of section 4.11, the consumer integration job; it shows that a product imports the module and that the base services compose | Criteria 1 to 3, 13 and 14 |
| 2. Reliability | First, a board check of the reset cause and the retained region (section 4.6), in a run with its own board authorisation; then the startup and runtime watchdog, the channel lifecycle, the supervisor, boot counter, safe mode, retained record and diagnostics | Criteria 6, 7, 10, 11 and 16 to 19 |
| 3. Application integration | The application contract of sections 4.4 and 4.5, shown through the fixture application | Criteria 4, 5, 8, 9 and 20 to 23; with phases 1 and 2, the Framework MVP milestone |
| 4. Framework completion | Persistence on LittleFS and the other platform dependencies of section 5.3, as Crux provides them | Criteria 12 and 24 on LittleFS, criterion 25, and the end of every interim state that section 5.3 does not accept for Framework Complete; the Framework Complete milestone |
| 5. Product readiness | Per product: secure boot and update, factory reset, hardware validation, security hardening, and validation of the application interface with a first real runtime consumer | Section 5.4; the Product Ready milestone |
| 6. Linux functions (later) | A Linux adapter over Crux's Linux providers, coordinated with Crux | A later specification |

Criterion 15 holds in every phase.

### 4.15 Crux changes in priority order

| Priority | Crux change | State |
|---|---|---|
| P1 | Settings File sources out of `tests/` (C5) | Crux change needed, issue TBD |
| P1 | Supervision hook in Crux service threads (C8) | Crux change needed, issue TBD |
| P1 | LittleFS File provider with Configuration saving on it (C4) | Planned in Crux, issue TBD |
| P2 | Access erase operation (C9) | Planned in Crux, issue TBD |
| P2 | Shared console and logging UART build option (C6) | Planned in Crux, issue TBD |
| P2 | Image state provider (C10) | Crux change needed, [crux-pilot#297](https://github.com/wonny-labs/crux-pilot/issues/297) |
| P2 | Crux Access on the Wolf profile, needed for the Wolf HTTPS profile and for SSH (C7) | Crux change needed, issue TBD |
| P3 | SSH composition interface (C7) | Deferred by Crux, issue TBD |
| P3 | Web adapter for the File service | Crux change needed, [crux-pilot#188](https://github.com/wonny-labs/crux-pilot/issues/188) |
| Deferred | SoC gates for a second board (C12) | Crux change needed when a second board is in scope, issue TBD |

The startup watchdog needs no Crux change: the framework solves it with the existing single Crux watchdog token (section 4.2), unless a board measurement shows that one timeout cannot cover both startup and runtime.

### 4.16 Later items

| Item | Rule |
|---|---|
| Configuration backup and restore | Through device management, once configuration saving exists (IEC 62443-4-2 CR 7.3 and 7.4, as direction) |
| Applying changed network settings | Crux's network settings service has a no-op apply port only; the framework implements the apply port, and saving needs the save provider |
| Core dump and log persistence | Zephyr core dump to a partition and log persistence need a partition decision; the retained last-fault record covers the reset evidence |
| Stack high-water reporting | Part of the diagnostics of phase 2, shown in the status service |
| Turning services on and off at runtime | Through configuration, once configuration saving exists; build-time removal is in section 4.1 |
| Integration guide | A page that explains how a product joins the framework and links the fixture application under `tests/` as the code reference; no separate example code or example image |

## 5. Acceptance criteria

### 5.1 Milestones

| Milestone | Reached when | Interim states |
|---|---|---|
| Framework MVP | Phases 1 to 3 end: criteria 1 to 11 and 13 to 23 | Every interim state of section 5.3 is accepted; the check of a replacement criterion is not an MVP item |
| Framework Complete | Phase 4 ends: every mandatory function and platform dependency, including persistence on LittleFS; criteria 1 to 25 | Only the interim states that section 5.3 marks as accepted for Framework Complete |
| Product Ready | Per product on its board: section 5.4 | None of section 5.3 for the functions the product uses |

### 5.2 Criteria

1. The base image enables every service of section 4.1 that its TLS profile allows (C7), with no application, and the framework's Kconfig has no exclusion between services beyond those of the TLS profile.
2. The RT1060-EVKB build of the base image passes in CI with `-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`, and its `Budget` row keeps at least 25 percent free in every region; the 25 percent is a budget of the reference board (section 4.12).
3. The base image builds and runs on `native_sim` in CI.
4. A fixture application under `tests/`, with its own `main()`, `prj.conf` and descriptor, builds for `native_sim` in CI with this repository as a Zephyr module (`EXTRA_ZEPHYR_MODULES`) and runs: the log shows `init`, `start` and `stop` in order, a thread that the application created with Zephyr, a registered and activated watchdog channel, a status item and a parameter in device management, and a file under its data root.
5. A second call of the start function, and a descriptor without a mandatory entry, are refused; a host or `native_sim` test checks both.
6. A `native_sim` scenario of the start order: the reset cause is read once, the status service receives the captured copy, the flags are cleared after the capture, the watchdog is armed before the storage mount, the start prerequisites are checked, and the application starts last; startup supervision ends when `start` returns.
7. A `native_sim` scenario with an injected startup phase that passes its deadline: the supervisor writes the retained record with the phase name and stops feeding, and the simulated watchdog restarts the image (reset cause SOFTWARE, C11).
8. A `native_sim` scenario with an injected `init` failure after a registration: the application reports fault, `safe_state` ran, the registration is released, the controller state is unchanged, and device management answers.
9. A `native_sim` scenario with an injected stall of a registered application thread: the channel expiry is recorded, `safe_state` ran, the supervisor stops feeding, and the simulated watchdog restarts the image.
10. Host tests of the portable core: N consecutive fault resets enter safe mode; the stable period, the operator command and a different image clear the counter; the retained region's checksum rejects a damaged region; the state transitions of section 4.4; a start prerequisite that is not healthy holds the application; a watchdog that does not arm holds the application in a product build and not with the explicit option.
11. A `native_sim` scenario of safe mode: the minimal service set runs, the application is not initialised, device management answers, and the exit command leads to a normal boot.
12. A `native_sim` scenario saves a parameter on LittleFS, restarts on a file-backed disk and reads it back.
13. `scripts/check_boundary.py` checks every source tree of section 4.11; a source that no rule covers fails the check; the portable core has no Zephyr include; each new allow-list entry is a separate reviewed change.
14. The product integration job of section 4.13 imports the framework into an independent west workspace, builds and runs on `native_sim` in the nightly tier.
15. The repository holds no control algorithm; the architecture, capabilities and roadmap pages describe the framework and the base image; no page claims a board run until one is approved and recorded.
16. Fatal-error reset: a `native_sim` scenario with an injected fatal error in a framework thread shows that the handler calls no application entry, writes the minimal record and restarts the image; host tests show that the next boot counts it as a fault reset.
17. Framework fault in safe mode: a `native_sim` scenario that boots in safe mode and stalls a safe-mode service thread shows that the supervisor stops feeding and the image restarts; host tests show that the counter stays saturated and the next boot is again in safe mode.
18. Host tests of the reset rules of section 4.6: several latched cause bits, POR together with other bits, a SOFTWARE reset with and without the operator reset marker, CPU_LOCKUP together with SOFTWARE, with and without the marker, a consumed record, an interrupted write, counter saturation, and a different image identifier after an update and after a rollback.
19. Production watchdog configuration: a build test shows that a product build has `CONFIG_TASK_WDT_HW_FALLBACK=n`, a callback on every channel, neither the start-without-watchdog option nor the TLS identity option, and a timeout T inside the provider's range; a `native_sim` scenario of that configuration with an unavailable watchdog holds the application.
20. Start timeout: a `native_sim` scenario in which `start` passes its deadline: the supervisor writes the record with the phase name, calls `safe_state`, stops feeding, and the image restarts.
21. Operator stop and restart: a `native_sim` scenario in which an operator stop calls `stop`, then `safe_state`, and releases the application's channels while the controller stays operational; an operator start checks the start prerequisites, activates the channels again without calling `init`, and calls `start`; a `stop` that passes its deadline restarts the image.
22. Partial start failure: a `native_sim` scenario in which a channel activation fails and one in which `start` returns an error: the activated channels are deleted, `safe_state` ran, the application is in fault, the controller state is unchanged, and device management answers; host tests show that a requirement beyond the channel capacity and a duplicate name are refused in `init`.
23. Required-service failure: a `native_sim` scenario in which a start prerequisite fails at boot: the application is held, the controller is degraded, and after the service recovers an operator start runs the application; and one in which a runtime dependency fails while the application runs: the change is reported through the status service and `ctx`, the application keeps running, and the controller is degraded.
24. Storage full: a `native_sim` scenario on LittleFS in which the application data root reaches its size limit: a file write answers an error, a parameter save still succeeds, and the status service shows storage degraded.
25. Unconfirmed image timeout: host tests of the health verdict and the trial deadline with a fake image state port: a verdict that is not healthy by the deadline requests a planned reset, a healthy verdict leads to confirmation, and a build without web management is confirmed on the same conditions.

### 5.3 Interim states

Each interim state is accepted until its Crux change is at the pin, with the replacement criterion shown.

| Interim state | Replacement criterion | Accepted for Framework Complete | Ends when |
|---|---|---|---|
| The microSD FatFs provider serves files and the credential store, with no configuration save | Criteria 12 and 24 are replaced by: a save answers not supported, and the status service says parameters are not persistent | No | Crux's LittleFS File provider (C4) |
| The product build reaches Crux's `tests/` for the Settings File sources | None | No | The sources move (C5) |
| Crux service threads are supervised indirectly | None | No | Crux's supervision hook (C8) |
| The serial console uses a second UART (LPUART3 on header pins, with a USB-serial adapter) | None | Yes; the shared UART is a build option | Crux's shared UART option (C6) |
| No SSH and no Wolf profile | None | Yes; both are build options | Crux Access on the Wolf profile and Crux's SSH composition interface (C7) |
| Factory reset only by device preparation | None | Yes; factory reset belongs to Product Ready | Crux's Access erase operation (C9) |
| The images are prepared for MCUboot, with no health-gated confirmation | Criterion 25 stays a host test | Yes; confirmation on the board belongs to Product Ready | Crux's image state provider (C10) |

### 5.4 Product ready

A separate milestone, reached per product on its board:

1. Hardware tests: a watchdog reset reads the reset cause WATCHDOG and advances the boot counter; the retained region survives a WDOG1 reset and a pin reset and does not survive a power cycle; power cuts on the product medium keep the settings file and the credential store; application thread timing and jitter meet the product's deadlines under TLS sessions and network load; outputs hold their safe state during a reset.
2. Configuration persists on the product medium, and the compatibility rules of section 4.7 hold across an update and a rollback.
3. Secure boot and update with the health-gated confirmation and the trial deadline of section 4.8, including the revert of an unconfirmed image at the reset after the deadline.
4. Factory reset with the authority and scope of sections 4.6 and 4.7.
5. The security items of section 4.9 are implemented.
6. Product integration with the product's own application, which is also the first real runtime consumer that validates the application interface before its stability tier is raised (section 4.5).

## 6. Decisions

Every decision is taken for this specification; D9 is deferred.

| # | Decision | State | Options | Decision | Source |
|---|---|---|---|---|---|
| D1 | Application interface | Decided | (a) A descriptor that the product's `main()` passes to the start function, with only framework-owned items (section 4.5); (b) registration of the descriptor in a linker section (`STRUCT_SECTION_ITERABLE`), with a Kconfig choice of the application | (a), with no framework-owned execution model; entries specified by guaranteed results within bounded time, and task watchdog channels registered in `init` and activated at `start` (sections 4.4 and 4.5); the lowest stability tier until a first real runtime consumer validates it; no framework-owned periodic task in the first version, an optional helper later if a consumer needs one | Zephyr modules and iterable sections; Zephyr task watchdog; Crux ADR-0003 R2; repository rule against pass-through wrappers |
| D2 | How a product consumes the framework | Decided | (a) A workspace application that owns `app/` and `main()` and imports Crux and the framework module; (b) importing the whole of this repository as the application; (c) copying this repository | (a): the documented Zephyr and nRF Connect SDK shape, matching Crux's `templates/product`; (b) takes `main()`, `prj.conf` and board files from the product; (c) forks the framework in every product | Zephyr application types, west T2 topology and modules; nRF Connect SDK workspace applications |
| D3 | Medium and file system | Decided | (a) LittleFS on the whole microSD card; (b) LittleFS on a QSPI NOR partition; (c) Reliance Edge under a commercial licence | (a), for the reference board only; products choose their medium and provider (section 4.7) | Section 3, C4 |
| D4 | Response to a hang | Decided | (a) A device reset, with boot counter and safe mode; (b) stop the application and keep the framework running | (a): a hung Zephyr thread cannot be removed safely (section 4.3), and safe mode after N resets reaches a held application with management running; `safe_state` runs on a task watchdog expiry when possible, never from the fatal error handler, which writes a minimal record and resets; a CPU lockup is left to the hardware watchdog (section 4.4) | Zephyr task watchdog and fatal error handling; Crux System contract |
| D5 | Console UART | Decided | (a) Shared with logging, through Crux's planned build option; (b) a separate console UART | Both as a build option, separate by default; shared is optional and needs the Crux option (C6) | Zephyr shell log backend; Crux Logging binding and console contract |
| D6 | SSH command line and SFTP | Decided | (a) A command line transport option that allows SSH only with the Wolf profile under a commercial or GPL-3.0-or-later licence, Crux Access on the Wolf profile and a Crux SSH composition interface; (b) an SSH server on Mbed TLS | (a), conditional on the licence, on Crux Access on the Wolf profile (Crux change needed) and on Crux's deferred composition interface; (b) is not an option, because it means writing a security-critical protocol implementation | Licences of wolfSSL and wolfSSH ([dependencies](../dependencies.md)); C7 |
| D7 | Firmware update | Decided | (a) Partition layout, image format and confirmation from Crux's secure boot work, with the framework's health input; (b) a framework-owned update design | (a), coordinated with the secure boot work: the framework gives the health verdict, the update component confirms or requests a reset at the trial deadline, and the boot loader reverts an unconfirmed image at that reset; the watchdog policy from the boot loader to the application and the final recovery path are decided with the same work (sections 4.4, 4.6 and 4.8) | MCUboot test, confirm and revert; section 4.8 |
| D8 | Verification | Decided | (a) The layers of section 4.13: base image on the board and `native_sim`, the fixture application, image-level regression, product integration in the nightly tier and hardware tests; (b) keep every per-capability scenario and board build | (a) | Section 4.13 |
| D9 | Second board | Deferred | — | The framework stays board-neutral (section 4.12) | C12 |
| D10 | Crux gaps | Decided | (a) Crux changes in the priority order of section 4.15; (b) workarounds in this repository | (a): they are platform gaps | Section 4.15 |
| D11 | Device preparation | Decided | (a) A preparation image or host tool writes the volume, and the TLS key and certificate are made during preparation; (b) the image formats an empty medium and makes the key at first boot | (a): formatting destroys data, a removable medium may hold someone else's data, and a long first-boot phase weakens startup supervision; key generation at a normal boot only in development and reference builds with an explicit option, and a prepared device without its identity boots in safe mode (section 4.7) | Crux File providers refuse auto-format; section 4.2 |
| D12 | Repository role | Decided | (a) Change the role sentence of CONTRIBUTING to a controller framework module with a base image that products import, as a reviewed change with the role test of `tests/tooling/test_docs.py`; the glossary entry "Product" (`docs/glossary.md:11`) then takes Crux's sense; (b) keep "reference consumer firmware" | (a), with D2 (a) | CONTRIBUTING role section; `docs/glossary.md` |
| D13 | Names | Decided | (a) "Controller framework" for the module and "base image" for the one image; (b) names with "platform" or "reference controller" | (a), with no example image: Crux is the platform, and the documents reserve "the reference controller" for Crux's sample; the build configuration `base` (`prj.conf` alone) takes another name, for example `minimal`, as a reviewed change of `scripts/build-board.sh`, `budgets/limits.json`, `.github/workflows/ci.yml`, `.github/workflows/budget.yml`, `tests/tooling/test_base_build.py`, CONTRIBUTING and the glossary | `tests/tooling/test_docs.py` |
| D14 | Application start without a hardware watchdog | Decided | (a) In product builds the application does not start; `native_sim` and bench builds may allow it by an explicit build option; (b) start the application and report "watchdog not armed" | (a) | Crux System reports an unavailable watchdog as not supported; section 4.2 |
| D15 | Recovery and factory reset authority | Decided | (a) Factory reset by an authorised operator through Crux's planned Access erase, with an optional product-defined physical-presence input, and device preparation as the recovery when Access is unusable; (b) an unauthenticated serial wipe | (a), erasing credentials and configuration and keeping the device identity, which only device preparation replaces (sections 4.6 and 4.7); (b) is not an option | Section 4.6; IEC 62443-4-2 CR 4.2, as direction |
| D16 | Serial command line in production and audit persistence | Decided | Section 4.9 | Section 4.9 | IEC 62443-4-2 CR 2.8 to 2.11 and CR 7.7, as direction |

## 7. Glossary

| Term | Meaning here | Source |
|---|---|---|
| Platform services | Device management, health supervision, time, logging, configuration, network and storage, which Crux provides | Common embedded usage; Crux documentation |
| Controller framework | The Zephyr module of this repository: composition of the Crux services, health supervision and the application interface | This page |
| Base image | The image of this repository: the framework with no application | This page |
| Application | Product code that joins the framework: the product's control software or a third-party application runtime | This page |
| Third-party application runtime | Software from another vendor that runs user programs with its own scheduling and execution model | Common usage |
| Fixture application | A test-only application under `tests/` that exercises the interface in a contract test | Common test usage |
| Contract test | A test that checks that both sides of an interface keep its rules | Common usage |
| Product | A firmware repository outside this repository that is built on Crux and the framework; `docs/glossary.md` uses the word for this repository's firmware until decision D12 | Crux product composition guide |
| Workspace application | A Zephyr application inside a west workspace, outside the Zephyr repository | Zephyr application development; nRF Connect SDK |
| T2 topology | A west workspace whose manifest repository is the application | Zephyr west workspaces |
| Descriptor | The one structure an application defines, with its entry points, passed to the framework's start function | This page |
| Execution model | How software schedules its work: threads, priorities, periods, events | Common RTOS usage |
| Ports and adapters | A structure where the core defines port interfaces and OS-specific adapters implement them | A. Cockburn, "Hexagonal architecture" |
| Source zone | A source tree with its own include rules, checked by `scripts/check_boundary.py` | CONTRIBUTING "The boundary"; [composition-zone.md](../composition-zone.md) |
| Controller state | Starting, operational, degraded or recovery (section 4.4) | This page; common embedded usage |
| Application state | Absent, not initialised, initialised, held, running, stopped or fault (section 4.4) | nRF Connect SDK CAF module states; systemd unit states |
| Service health | Healthy, degraded, failed or absent, per service | Common usage |
| Required service | A start prerequisite or a runtime dependency | This page |
| Start prerequisite | A service that the framework checks before every application start and that holds the application while it is not healthy | This page |
| Runtime dependency | A service whose health the framework reports to the application while it runs; the application decides its response | This page |
| Safe state | The defined output state on stop, fault or reset | IEC 61508-4 |
| Hardware watchdog | The one native watchdog, owned by Crux System, one activation per boot | Zephyr watchdog API; Crux System |
| Task watchdog, channel | A software watchdog with one channel per supervised thread | Zephyr task watchdog |
| Channel requirement, active channel | A channel that `init` registers without creating it; a Zephyr task watchdog channel that the framework added at `start` | This page |
| Supervisor | The one thread that holds the watchdog token and feeds only while every activity progresses | Crux System health design |
| Startup watchdog | The hardware watchdog during startup supervision, fed while each startup phase is within its deadline, until `start` returns or the framework decides not to call it | This page; MCUboot `CONFIG_BOOT_WATCHDOG_FEED` |
| Phase deadline | The software time limit of one startup phase | This page |
| Indirect health | Health of code one does not own, read from counters, link state or a local probe | Common usage |
| Degrade and report | Keep running with a reduced function and show the condition | Common embedded usage (graceful degradation) |
| Boot counter, safe mode | A count of consecutive fault resets; a boot mode with a minimal service set and no application | U-Boot boot count limit; common embedded usage |
| Retained RAM | Memory whose contents survive a warm reset, used for the last-fault record and the boot counter | Zephyr retention subsystem, `retained_mem` |
| Fault reset | A reset that the boot counter counts (section 4.6) | This page |
| Device preparation | Steps before first use: writing the volume and making the device's key and certificate | Common manufacturing usage (provisioning) |
| Device identity | The device's TLS key and certificate, made during device preparation | Common usage |
| Trust on first use | Accepting a peer's key at the first connection without prior verification | RFC 7435 |
| Priority band | A reserved range of thread priorities for one group of threads | Common RTOS usage; rate-monotonic assignment |
| Priority inversion | A higher-priority thread waits on a lower-priority one that holds a resource | Zephyr kernel documentation (mutexes) |
| Device management | Remote and local administration: web, command line, file transfer | Common usage (LwM2M, mcumgr) |
| Log backend | The output of Zephyr's logging; the shell's log backend shares the shell's UART | Zephyr logging and shell |
| Initial account provisioning | Creating the first credential by a trusted path, with no default password | IEC 62443-4-2 CR 1.5; ETSI EN 303 645 5.1 |
| Factory reset | Return to the provisioning state by erasing credentials and configuration, keeping the device identity | Common usage; IEC 62443-4-2 CR 4.2 |
| Power-cut safe | A file system whose rename replaces a file atomically across a power cut | Crux `zephyr/Kconfig` Settings File help |
| LittleFS | A copy-on-write file system for flash and block devices with power-loss resilience | littlefs project; Zephyr file systems |
| Test image, confirm | An update image booted once on trial and made permanent by the running image; MCUboot reverts it at the next reset when it is not confirmed | MCUboot |
| Trial deadline | The time after which an unconfirmed test image leads to a reset request | This page |
| Update component | The component from Crux's secure boot work that confirms an image through Crux's image state contract | This page |
| Sysbuild | Zephyr's build of several images, such as MCUboot and the application | Zephyr sysbuild |
| Board files, snippets | Per-board configuration and overlay; settings reused across applications | Zephyr application development and snippets |
| Devicetree alias, `chosen` | A named role for a node | Zephyr devicetree |
| West project, Zephyr module | A repository in the workspace manifest; a repository that adds code, Kconfig or board roots to a build | Zephyr west and modules |

## Sources

- Zephyr documentation: "Application Development" (application types, board files, `EXTRA_CONF_FILE`, `FILE_SUFFIX`), west "Workspaces" (topologies T1, T2, T3), "Modules (External projects)", "Shell" (logger backend), "Task Watchdog", "Retention System" (boot mode), "Retained Memory", "Mutexes" (priority inheritance), "Core Dump", "Settings", sysbuild and snippets; read at v4.4.2 (`dccb0959`) under `doc/`, with `subsys/task_wdt/Kconfig`.
- The Zephyr `example-application` repository README; nRF Connect SDK "Creating an application" (workspace application recommended, `ncs-example-application`) and "Common Application Framework overview" (module states).
- systemd documentation, `systemd.unit` and `systemctl` (unit active states).
- MCUboot design documentation (image test, confirm and revert) and its Zephyr port's `CONFIG_BOOT_WATCHDOG_FEED`.
- U-Boot documentation, "Boot Count Limit" (`CONFIG_BOOTCOUNT_LIMIT`, `bootlimit`, `altbootcmd`).
- A. Cockburn, "Hexagonal architecture" (ports and adapters).
- RFC 7435, "Opportunistic Security: Some Protection Most of the Time" (trust on first use).
- littlefs design notes: copy-on-write and power-loss resilience.
- Crux at `bd9efbc7`: `zephyr/Kconfig`, `zephyr/CMakeLists.txt`, `components/logging/ports/zephyr/`, `components/cli/ports/zephyr/include/crux/cli_zephyr.h`, `components/system/`, `components/access/include/crux/access.h`, `components/mgmt_status/include/crux/management_status.h`, `components/file/ports/zephyr/CMakeLists.txt`, `components/image_state/`, `components/*/ports/linux`, `docs/decisions/0001-application-boundary-and-api-stability.md` (Decision 4), `docs/decisions/0003-p9-result-services-keep-narrow-thread-sync.md` (R2, R5), `docs/management-in-a-product.md`, `tests/native/configuration_settings_littlefs`, `tests/native/file_littlefs`, `tests/native/web_https`, `tests/native/management_services`, `templates/product/README.md`.
- Crux `main`: `docs/superpowers/specs/2026-10-24-system-health-design.md`, section "Supervising several activities"; `docs/ci.md` at `62ed69f1`, "Use in a product repository".
- Crux issues [#188](https://github.com/wonny-labs/crux-pilot/issues/188) and [#297](https://github.com/wonny-labs/crux-pilot/issues/297).
- This repository: `scripts/check_boundary.py`, `scripts/build-board.sh`, `budgets/limits.json`, `docs/dependencies.md`, `docs/glossary.md`, `docs/roadmap.md`.
- IEC 61508-4 (definition of safe state); IEC 62443-4-2 by clause title (CR 1.5, 2.8 to 2.11, 4.2, 7.7) and IEC 62443-4-1; ETSI EN 303 645, provision 5.1; the EU Cyber Resilience Act, Annex I; all as direction, not as compliance claims.
- C. L. Liu and J. W. Layland, "Scheduling Algorithms for Multiprogramming in a Hard-Real-Time Environment", Journal of the ACM, 1973.
