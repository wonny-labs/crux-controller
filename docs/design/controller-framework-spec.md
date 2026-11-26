# Controller framework specification

This page specifies the controller framework: its requirements, application interface, operating model, recovery, build options, verification and decisions.
The [overview](controller-framework.md) explains what the framework is, who does what and how a product joins it.
The [platform gaps](controller-framework-platform-gaps.md) hold the Crux and Zephyr constraints C1 to C13.
The page changes no source code; the [architecture](../architecture.md) and the [capabilities](../capabilities.md) describe the current images.

## 1. Scope and conventions

Crux is read at the revision that [`west.yml`](../../west.yml) pins ("the pin"), and Zephyr at the release that this Crux revision pins.
A Crux fact holds at the pin unless it carries one of these status words:

| Status word | Meaning |
|---|---|
| Crux `main` | Holds on Crux `main`, not at the pin |
| Planned in Crux | Crux has decided the change; it is on neither the pin nor `main` |
| Crux change needed | The framework needs the change; Crux has not decided it |
| Deferred by Crux | Crux has decided to postpone the change |

A Crux change carries its issue link where Crux has one.
Each rule carries one label:

| Label | Meaning |
|---|---|
| Established mechanism | A documented mechanism of Zephyr, west or Crux, used as its documentation describes or recommends |
| Decision (Dn) | A choice of this framework among valid options; [section 9](#9-decision-register) holds decision Dn |
| Platform constraint or interim | Forced by Crux or Zephyr at the pin, or a state accepted until a planned or needed platform change exists; the [platform gaps](controller-framework-platform-gaps.md) name the change |
| Reference configuration | Values for the RT1060-EVKB reference board, which a product tunes |
| Product decision | A choice that the framework leaves to each product |

A heading's label applies to every rule under it that carries no label of its own.
Where a decision lets a product choose differently, the text says so.
[Section 10](#10-terms) defines the terms of these pages; the [glossary](../glossary.md) defines the others.

## 2. Requirements

The criteria are in [section 8.4](#84-criteria).

| # | Functional requirement | Criteria |
|---|---|---|
| F1 | The framework composes the Crux services of the [overview](controller-framework.md#services) and starts them in a defined order from one start function. | 1, 6 |
| F2 | The base image runs every framework service with no application. | 1, 2, 3, 15 |
| F3 | An application joins only through the interface of section 3, and the framework imposes no execution model on it. | 4, 5, 8, 14, 20, 21, 22, PR6 |
| F4 | Device management offers HTTPS web management and a serial command line, and SSH in builds that carry its licensed stack. | 26 |
| F5 | The framework and the application register configuration parameters and status items, which device management shows. | 4 |
| F6 | The product selects the build options of section 7.1 with Kconfig. | 27 |

| # | Reliability requirement | Criteria |
|---|---|---|
| R1 | The hardware watchdog supervises the controller from startup step 2 of the start function on, through startup and runtime (section 4). | 6, 7, 9, 19, 20, 21, PR1 |
| R2 | A hang ends in a reset, after which the next boot reports the reset cause as far as the hardware reports it and a detailed fault record only when one could be written before the reset, while a failure that is not a hang degrades the controller and is reported. | 7, 8, 9, 16, 18, PR1 |
| R3 | Repeated fault resets lead to safe mode, a minimal service set from which an operator can recover the controller, and a fault in safe mode's own services is recovered by the boot loader or the product's recovery path (section 5.2). | 10, 11, 17 |
| R4 | The product declares start prerequisites, which the framework checks before every application start, and runtime dependencies, which the framework reports while the application runs (section 4.7). | 6, 10, 23 |
| R5 | In product builds, the application does not start when the hardware watchdog cannot be armed. | 10, 19 |
| R6 | Every startup step of a normal boot has a bounded, measured duration, and first-boot key generation belongs to device preparation. | 31 |
| R7 | Configuration that the framework or the application saves survives a reset and a power cut, and the application data cannot fill the space of the settings file and the credential store (section 5.4). | 12, 24, PR1, PR2 |

| # | Security requirement | Criteria |
|---|---|---|
| S1 | No default password exists, and the first account is created over a trusted path (IEC 62443-4-2 CR 1.5; ETSI EN 303 645 provision 5.1). | 28 |
| S2 | A factory reset needs an authorised operator or a physical presence that the product defines, and no unauthenticated serial command erases the device. | 29, PR4 |
| S3 | The items of section 6.2 are decided before the Product Ready milestone. | PR5 |

IEC 62443-4-2 and the EU Cyber Resilience Act give the security items their direction; these pages claim compliance with neither.

| # | Portability requirement | Criteria |
|---|---|---|
| P1 | Nothing in the framework or the interface names a board or SoC, and per-board values live in board files (section 7.2). | 30 |
| P2 | The framework core (states, supervision policy, boot counter, application contract) is portable C with host tests, and OS-specific code lives in the adapter and composition zones (section 7.3). | 10, 13 |
| P3 | Linux functions are a later delivery stage, coordinated with Crux, in which the framework runs natively on Linux through Crux's Linux providers and not through `native_sim` (section 7.3). | A later specification |

## 3. Application interface

The application interface holds only what the framework owns (D1).
Its names are open, decided at implementation.

### 3.1 Descriptor

The product's `main()` passes the descriptor to the start function.
Each entry is specified by the results it guarantees and the time it may take; how the application reaches them, including threads or work items of its own, is the application's choice.

- `init(ctx)` is mandatory and returns within its step deadline.
  - On success, every channel requirement, status item and parameter table that the application needs is registered, and none is registered later in the boot.
  - It may read its data root within the deadline; it does not depend on configuration, time, web management or the command line, which start after it.
  - On failure, nothing that `init` started is still running.
- `start(ctx)` is mandatory and returns within its step deadline.
  - On success, the threads that feed the activated channels run and feed within their reload periods.
  - On failure, every thread that `start` created has ended before it returns.
- `stop(ctx, reason)` is mandatory and returns within its deadline; on return, every thread of the application has ended, so the framework can release its channels.
- `safe_state(ctx)` is mandatory, puts outputs into the product's defined safe state and never blocks.

### 3.2 Context

The framework gives through `ctx` what it owns:

- registration of task watchdog channel requirements, and the handle that feeds each channel, with the lifecycle of section 4.4;
- registration of status items, which the framework adds to the status service;
- registration of a parameter table, which the framework adds to the configuration service;
- the assigned application data root of Crux File;
- read-only controller state and service health.

The application calls Crux's public APIs directly for logging, time, sockets, file access under its data root and configuration reads, and Zephyr directly for threads and synchronisation.
The framework does not wrap them, following the repository rule against pass-through wrappers.

### 3.3 Call order and concurrency

| Rule | Detail |
|---|---|
| One caller | The framework calls `init`, `start` and `stop` from one framework thread, in that order, never concurrently with each other |
| Once | `init` runs once per boot; `start` runs once per transition to running; `stop` runs only in the running state |
| `safe_state` callers | After a normal stop (an operator stop or a planned reset); on a recoverable application fault; from the supervisor on a deadline overrun or a channel expiry when the application has been initialised (section 4.8) |
| `safe_state` constraints | It may run concurrently with the application's threads, so it is idempotent, takes no lock, allocates nothing and logs nothing |
| Partial `init` failure | The framework releases the registrations (requirements dropped, status items and parameters marked unavailable), calls `safe_state`, enters fault and calls neither `start` nor `stop` |
| Partial `start` failure | When activation or `start` fails, the framework deletes the channels it activated, calls `safe_state`, enters fault and releases the registrations; threads that `start` created are the application's to end before it returns its error |
| Thread clean-up | The framework never aborts an application thread; `stop` ends them, and the framework then releases their channels (section 4.4); a `stop` that passes its deadline is a hang (section 4.8) |
| Second start function call | Refused, as is a descriptor without a mandatory entry |
| Framework boundaries | The application may not block framework threads, take framework locks or call device management |

Safe state is best effort.
The framework calls `safe_state` in the cases above, but not from the fatal error handler and not after a CPU lockup.
During and across a reset, outputs keep a safe state only through the board's hardware default, which the product designs and documents.
IEC 61508-4 defines "safe state" for functional safety; these pages use the word in that sense and claim no safety integrity.

### 3.4 Stability

- The interface starts at the lowest stability tier, because no consumer exists to confirm its shape.
- It is validated against a first real runtime consumer (a product's control software or a third-party application runtime, not the fixture application) before its tier is raised.
- This repository defines no stability tiers; the tiers are open, decided at implementation, modelled on Crux ADR-0001 Decision 4.
- A framework-owned periodic task that calls an application entry point is not part of the first version; if a consumer needs one, it can be added later as an optional helper on top of this interface.

## 4. Operating model

This section defines the startup steps, the supervision periods, runtime supervision, the channel lifecycle, the application and controller states, service health and the reactions to faults.
[Section 5](#5-recovery-storage-and-device-preparation) holds the mechanisms of recovery.

### 4.1 Startup steps

The product's `main()`, or the base image's, calls the start function once; the start function runs these steps in order, logs each step's name and result, and returns.

| # | Step | On failure |
|---|---|---|
| 1 | Read the Crux monotonic clock; read the reset cause once, keep the copy and clear the flags ([C2](controller-framework-platform-gaps.md#c2-one-reset-cause-owner)); read and check the retained record; update the boot counter and decide normal boot or safe mode (section 5.2). | A missing clock stops startup; otherwise log, continue without the copy, and count a bad record as empty. |
| 2 | Start the supervisor thread, which arms the hardware watchdog with the one timeout T ([C3](controller-framework-platform-gaps.md#c3-one-watchdog-activation-per-boot)) and supervises the startup steps. | The watchdog is "not armed"; startup continues, and the application does not start unless the build allows it (D14). |
| 3 | Mount the volume once with the keep policy and bind the application data root and the credential store roots; on a volume that device preparation wrote, check that the device identity exists. | Storage failed, and step 4 fails with it. A missing device identity on a prepared volume sets safe mode for this boot, unless the build has the TLS identity option (section 5.5). |
| 4 | Start security events, the realtime clock, the credential store and Access. | Access failed; device management that needs accounts stays off (section 5.3). |
| 5 | Unless in safe mode or with no application: call the application's `init`, which registers the application's requirements (section 3.1). | Application fault, with the clean-up of a partial `init` (section 3.3). |
| 6 | Start the configuration service with the framework and application parameter tables. | Configuration failed. |
| 7 | Start the status service with the copy from step 1 and the framework and application items. | Status failed. |
| 8 | Start time synchronisation, outside safe mode. | Time stays unsynchronised. |
| 9 | Register the framework's command tables with `crux_cli_init()` and start the configured command line transports; `crux_cli_serial_start()` refuses a registry that is not ready (`components/cli/ports/zephyr/include/crux/cli_zephyr.h:36-40`). | Command line failed. |
| 10 | Load and register the TLS key and certificate written by device preparation, then start sessions, web management and the listener. | Web management failed; without a device identity, web management stays off (step 3). |
| 11 | Check the start prerequisites (section 4.7). | A start prerequisite is not healthy: the application is held, and the controller is degraded. |
| 12 | Unless in safe mode, with an application fault, with a start prerequisite that is not healthy, without an armed watchdog in a build that refuses it, or with no application: activate the application's registered channels and call the application's `start` (section 4.4). | Application fault, with the clean-up of a partial start (section 3.3). |

Startup watchdog rules (established mechanism for the parts that Crux and Zephyr provide; D4 for the step deadlines):

- The hardware watchdog is armed in step 2, before the first step that touches a medium or the network, so a hang in steps 3 to 12 ends in a reset.
- Step 1 only reads and writes registers and retained RAM, touches no storage medium or network, and is bounded.
- Each step from 3 on has a software deadline (Kconfig, reference values from board measurement); the deadlines of steps 5 and 12 bound `init` and `start`.
- While the current step is within its deadline, the supervisor feeds the watchdog at a period shorter than T.
- When a step passes its deadline, the supervisor writes the retained record with the step name and stops feeding, and the watchdog resets the device.
- The supervisor thread has a higher priority than the thread that runs the start function, so a long step cannot starve it (section 7.4).
- Zephyr's default main thread priority (`CONFIG_MAIN_THREAD_PRIORITY`, 0) is above the supervisor, so the base image and each product set it into the startup band.
- T is one value for the whole boot (C3): it covers the supervisor's feed period plus a scheduling margin, inside the provider's supported range; the step deadlines are independent of T.
- Comparable practice: MCUboot's Zephyr port feeds the watchdog during long boot loader operations (`CONFIG_BOOT_WATCHDOG_FEED`).

Key generation is part of device preparation (D11), so a normal boot has no long step.
Only a development or reference build with the TLS identity option generates a missing key and certificate in step 10, with its own deadline set from a measurement on the board for the key type; the status service then reports that the certificate was made at boot.

### 4.2 Supervision periods (D4)

| Period | From | Until | What the supervisor feeds by |
|---|---|---|---|
| Before framework startup | Reset | The start function | Outside R1: boot ROM, boot loader and kernel initialisation; the watchdog policy from the boot loader to the application is coordinated with Crux's secure boot work (D7) |
| Not armed | The start function | Step 2 arms the hardware watchdog | Nothing; step 1 only reads and writes registers and retained RAM and touches no storage medium or network |
| Startup supervision | Step 2 | `start` returns, or step 12 decides not to call `start` | Each startup step within its deadline (section 4.1), and every active channel |
| Runtime supervision | The end of startup supervision | A reset | Every active channel has made progress and none has expired |
| Feeding stopped | A step passes its deadline, `stop` passes its deadline, or a channel expires | The hardware watchdog resets the device | Nothing |

When step 2 cannot arm the watchdog, Crux System reports it as unavailable or faulted, the status service shows "not armed", and no period above applies; the application then starts only in a build that allows it (D14).

### 4.3 Runtime supervision

The pattern is Crux's documented one for supervising several activities (Crux `main`, `docs/superpowers/specs/2026-10-24-system-health-design.md`, section "Supervising several activities"; at the pin, the System build already refuses the option it forbids).

| Rule | What the framework does | Label |
|---|---|---|
| One supervisor | One supervisor thread holds the single `crux_watchdog_t` token from `crux_watchdog_start()` and calls `crux_watchdog_feed()` only while every supervised activity has made progress | Established mechanism (Crux System contract) |
| Task watchdog without hardware | `task_wdt_init(NULL)`; one channel per supervised thread, with the lifecycle of section 4.4; each channel callback only records the expiry and the channel identifier; the supervisor stops feeding when it sees one | Established mechanism (Zephyr task watchdog; Crux pattern) |
| No hardware fallback | `CONFIG_TASK_WDT_HW_FALLBACK=n`; the Crux System build stops when it is set (`components/system/ports/zephyr/CMakeLists.txt:19-20`) | Platform constraint or interim |
| No callback-less channel | A channel without a callback resets through `sys_reboot(SYS_REBOOT_COLD)`, which latches a software reset cause and loses the watchdog evidence; every channel has a callback | Established mechanism |
| What is supervised | The framework's threads (supervisor inputs, time synchronisation, storage worker) and each application thread that registers a channel (section 3.2) | D4 |
| Indirect health | Zephyr's threads (HTTP server, network RX and TX, deferred log processing) and Crux's (console, web workers) are not fed from inside; their health is read from link state, network buffer counters, log drop counters and a periodic local probe, until Crux offers a supervision hook ([C8](controller-framework-platform-gaps.md#c8-crux-service-threads-and-supervision)) | Platform constraint or interim |
| Policy | Degrade and report for a failure that is not a hang (SNTP rounds fail, a save fails, the link is down); reset for a hang (a channel expires, a deadline passes, a fatal error); the reactions are in section 4.8 | D4 |
| Retained record | Before it stops feeding, the supervisor writes the failing channel or step, the uptime and the reason into a retained RAM record with a checksum (Zephyr retention subsystem over `retained_mem`) | Established mechanism (Zephyr retention) |
| Fatal path record | The fatal error handler writes a minimal record; the fatal path and code in interrupt context must not block, so the fatal path writes the record without a mutex (with `CONFIG_RETENTION_MUTEXES`, `retention_write` takes one), by a mechanism that is open, decided at implementation | Established mechanism (Zephyr retention) |
| Record use | The next boot reads the record once; placement and validity rules are in section 5.1 | D4 |
| Reporting | The status service shows the controller state, the application state, each service's health, the reset cause, the boot counter, the last-fault record and the watchdog state; liveness from outside is ping, link state and a light status endpoint | D4 |

Rationale: a per-thread restart is a process-manager pattern that Zephyr threads do not support.
`k_thread_abort` leaves locks and sockets behind, Crux Access cannot reopen after an unusable store ([C9](controller-framework-platform-gaps.md#c9-access-and-an-unusable-store)), and the watchdog has one activation per boot (C3), so a hang resets the device (D4).

### 4.4 Task watchdog channel lifecycle (established mechanism for the Zephyr calls; D1 for the rules)

A **channel requirement** is a name and a reload period that `init` registers through `ctx`; an **active channel** is a Zephyr task watchdog channel that `task_wdt_add()` returned.

| Step | Rule |
|---|---|
| Register (`init`) | The framework records the requirement and creates no Zephyr channel. A requirement with a reload period of zero, a name already registered, or one more than the free capacity is refused, and `init` sees the error. |
| Capacity | `CONFIG_TASK_WDT_CHANNELS` (Zephyr default 5, range 2 to 100) bounds the framework's own channels and the application's requirements together; the framework reserves its own channels, and the product raises the value when its application needs more. The framework keeps a fixed table and has no resource manager. |
| Activate (step 12, and each operator start) | The framework calls `task_wdt_add()` for every requirement immediately before it calls `start`. `task_wdt_add()` feeds the new channel at once, so timing starts at activation, and each application thread feeds its channel within the reload period from then on. |
| Partial activation | When `task_wdt_add()` fails for one requirement, the framework deletes the channels it activated in this step with `task_wdt_delete()`, does not call `start`, calls `safe_state`, and the application enters fault. |
| Feed | An application thread feeds its own channel through the handle that its registration returned in `ctx`, because the Zephyr channel identifier may change at each activation; the supervisor feeds the hardware watchdog only while no channel has expired. |
| Release (`stop`, fault) | After `stop` returns, every application thread has ended (section 3.1), and the framework deletes every active application channel; on an application fault it deletes them after `safe_state`. The requirements stay registered for a later operator start. |
| Re-activate (operator start) | The framework checks the start prerequisites, activates the registered requirements again and calls `start`; `init` does not run again in the same boot. |
| Expire | The channel callback records the channel identifier; the supervisor writes the retained record, calls `safe_state` when the application has been initialised, and stops feeding. |
| After an expiry | Zephyr's task watchdog re-arms its timer only on the next feed or add of a channel, so the callback can repeat; recording is idempotent, the framework does not depend on further callbacks, and it neither feeds, deletes nor reuses the expired channel before the reset. |

The framework's own channels follow the same rules, activated in the step that starts the supervised thread.

### 4.5 Application lifecycle and state (D1)

The states compare with the nRF Connect SDK CAF module states and the systemd unit states.

| State | Entered when | Leaves to |
|---|---|---|
| Absent | No descriptor (the base image) | — |
| Not initialised | A descriptor, before step 5 | Initialised when `init` succeeds; fault when it fails; held when the boot is in safe mode |
| Initialised | `init` succeeded | Running when `start` succeeds; fault when activation or `start` fails; held when step 12 decides not to call `start` |
| Held | The framework decided not to start the application: safe mode, a start prerequisite that is not healthy, or a watchdog that is not armed in a build that refuses it | Running on an operator start when the reason was a start prerequisite and every start prerequisite is healthy; otherwise only a reset |
| Running | `start` succeeded | Stopped when `stop` returns within its deadline; fault when the application reports a fault |
| Stopped | An operator stop, or a planned reset, after `stop` returned | Running on an operator start, outside safe mode, when every start prerequisite is healthy |
| Fault | `init`, activation or `start` failed, or the application reported a fault | Only a reset |

A hang (a channel expiry, or `stop` past its deadline) does not end in a reported fault state: the device resets (D4).

### 4.6 Controller state (D4)

The states follow the common embedded usage of "degraded mode" and "recovery mode".

| State | Meaning |
|---|---|
| Starting | From the start function until startup supervision ends |
| Operational | A normal boot after startup supervision in which every required service is healthy, and the hardware watchdog is armed or its absence is allowed by the build; the controller then provides its defined functions whatever the application state is, so an operator stop or an application fault leaves it operational and is reported as the application state |
| Degraded | A normal boot after startup supervision in which at least one required service is degraded or failed, or the watchdog is not armed in a build that refuses it; device management runs where its services allow |
| Recovery | A boot in safe mode (section 5.2), entered when the boot counter reaches N or when a prepared device has no device identity (section 5.5); it lasts until the next reset |

A service that is not required reports its own health, and its failure does not change the controller state.
The boot counter clears after the stable period of operational state (section 5.2), and image confirmation needs the operational state (section 6.1).

### 4.7 Service health and required services

Each framework service has one health value: **healthy**, **degraded** (running with a reported failure), **failed** (start failed or stopped), or **absent** (left out at build time).

| Service | Healthy | Degraded | Failed |
|---|---|---|---|
| Network | Link up and an address assigned (static or a DHCP lease) | Link down, or no address, after the interface came up | The interface did not come up |
| Storage | Volume mounted and roots bound | A write or save answers an error, or a size limit is reached (section 5.4) | Mount or bind failed |
| Access | Credential store usable | — | Store unusable (C9) or start failed |
| Configuration | Service started with its tables; an image without a save provider reports "not persistent" as a status item (section 5.4) | The last save failed | Start failed |
| Status | Service started | — | Start failed |
| Time | Wall time synchronised and younger than the stale age | Not yet synchronised, or stale | Synchronisation could not start |
| Web management | Listener accepts TLS connections | — | Start failed, or no device identity |
| Command line | Every configured transport started | Some configured transports started | No transport started |

Reachability of a remote peer is not part of any service's health, because it depends on the network outside the device; an application that needs it reports it as its own status item.
The product's required services are of two kinds:

- **Start prerequisites**: the framework checks them in step 11 and before every operator start, and holds the application while one of them is not healthy.
- **Runtime dependencies**: the framework reports a change of their health through the status service and the read-only service health in `ctx`; the application decides its response, and the framework neither stops nor restarts the application because of it.

### 4.8 Faults and reactions (D4)

| Event | Framework reaction | `safe_state` | Afterwards |
|---|---|---|---|
| Operator stop | Calls `stop`, then releases the application's channels | After `stop` returns | Application stopped; controller state unchanged |
| Recoverable application fault: `init`, activation or `start` fails, or the application reports a fault | Releases the registrations and channels | Yes | Application fault; controller state unchanged |
| A service fails without a hang | Degrade and report; a start prerequisite holds the application before a start; a runtime dependency is reported to the application | No | Controller degraded when the service is required |
| A startup step, `init`, `start` or `stop` passes its deadline, or a channel expires | Writes the retained record and stops feeding | When the application has been initialised, from the supervisor, best effort | Reset by the hardware watchdog; a fault reset for the boot counter |
| Fatal error (`k_sys_fatal_error_handler`) | Calls no application entry; writes a minimal retained record when the retained region is usable, and resets | No | A fault reset for the boot counter |
| CPU lockup, or a handler that cannot run | Nothing runs; the unfed hardware watchdog resets the device | No | Reset cause as the SoC reports it; no record |
| N consecutive fault resets | Safe mode (section 5.2) | — | Controller in recovery |
| A hang or fatal error in safe mode's own services | The same reset; safe mode cannot escape a fault in its own services | — | Safe mode repeats; the final recovery is the boot loader or the product's recovery path (section 5.2) |

Outputs keep a safe state during and across a reset only through the board's hardware design (section 3.3).

## 5. Recovery, storage and device preparation

### 5.1 Retained region and reset classification (D4)

- **Retained region**: the boot counter and the last-fault record share one retained region with a prefix and a checksum (Zephyr retention subsystem).
  By default it sits in on-chip RAM that neither the boot ROM nor Zephyr's startup initialises, named by the board overlay; external SDRAM is not assumed to retain data, because the boot ROM initialises the SDRAM controller again at every boot.
- **Fault reset**: any one of these conditions makes a reset a fault reset, and Crux reports zero, one or several latched cause bits (`crux_reset_cause_t`):
  - the captured cause includes WATCHDOG, or a valid record names a deadline, a channel expiry or a fatal error;
  - without a valid operator reset marker, a SOFTWARE reset, or a reset whose captured cause includes CPU_LOCKUP.
- **CPU_LOCKUP with SOFTWARE**: treated as a SOFTWARE reset, because some SoCs report both from one status bit; on the RT1060-EVKB one SRC status bit serves lockup and SYSRESETREQ, and Zephyr's `drivers/hwinfo/hwinfo_mcux_src.c` reports it as both.
- **Not a fault reset**: the counter keeps its value for
  - a reset with a valid operator reset marker, unless WATCHDOG is latched or a valid record names a deadline, a channel expiry or a fatal error;
  - a PIN reset or a DEBUG reset that meets no fault reset condition.
- **Operator reset marker**: the framework writes it from Crux Reboot's policy callback at the check before the reset, and before its own operator resets (safe-mode exit and factory reset).
  Crux Reboot asks the callback twice without saying which check it is, so the framework tracks the order of the calls, or consumes a marker left by a request that never reset.
- **Power cycle**: a captured POR cause, or a region whose prefix or checksum is invalid, means that the region did not survive: the counter starts at zero and no record is reported, whatever other cause bits are latched.
  On the RT1062 a POR cause is never captured and a power-on reads as PIN, so detection of a power cycle there relies on the invalid-region rule.
- **Interrupted write**: the record and counter are written with their checksum last; a write that a reset interrupts fails the checksum on the next boot and counts as an empty region, while the captured reset cause still decides whether the reset was a fault reset.
- **Stale record**: each record carries a sequence number; the next boot reads it once, passes it to the status service and marks it consumed, so a later reset does not count or report it again.
- **Image identity**: the region stores an identifier of the image that wrote it; a boot whose image differs, after an update or after the boot loader reverted an image, clears the counter and reports the previous image's last record.

### 5.2 Boot counter and safe mode (D4)

- **Boot counter**: counts consecutive fault resets and saturates at its maximum instead of wrapping.
- **Safe mode entry**: after N consecutive fault resets (Kconfig, default 3) the next boot enters safe mode; a prepared device without its device identity also boots in safe mode (section 5.5).
- **Safe-mode service set**: network, storage, credential store, Access, configuration service (which web management needs), status, web management when the device identity exists, the serial command line and logging, plus the reset cause and last-fault record; no application, no time synchronisation and no optional service.
- **Counter reset**: the controller is operational without interruption for the stable period (Kconfig), an authorised operator command clears it, or a different image boots.
- **Safe-mode exit**: an authorised operator command clears the counter and resets into a normal boot; a different image also boots normally.
- **Fault resets in safe mode**: safe mode cannot escape a hang or fatal error in its own services; the device resets, the counter stays saturated, and safe mode repeats.
  A test image that is not confirmed is reverted by the boot loader at that reset (section 6.1); for a confirmed image, the final recovery is the boot loader's or the product's recovery path, such as a new image through the programming interface, decided with Crux's secure boot work (D7).

Comparable mechanisms: U-Boot's boot count limit (`CONFIG_BOOTCOUNT_LIMIT`, `bootlimit`, `altbootcmd`) switches to an alternative boot command after a set number of failed boots, and Zephyr's retention subsystem offers a boot mode that survives a warm reset.

### 5.3 Storage or Access failure and factory reset (D15)

- **Storage or Access failure**: device management that needs accounts stays off; the controller is degraded or in recovery, and the serial log and the status service (where it runs) show the cause.
  Access cannot reopen in the same boot (C9), so a replaced medium takes effect after a reset; recovery is device preparation again, or a factory reset by a physical-presence input if the product defines one.
- **Factory reset**: an authorised operator command through the planned Crux Access erase operation (C9) erases credentials (accounts) and configuration and returns to first-account provisioning.
  It keeps the device identity, which only device preparation replaces.
  A product may add a physical-presence input, such as a button held at boot; no unauthenticated serial command erases the device.

### 5.4 Storage and configuration

| Item | Rule | Label |
|---|---|---|
| Reference board medium | The whole microSD card is one LittleFS volume over the card's block device (`FS_LITTLEFS_BLK_DEV`) | Reference configuration (D3) |
| Product medium | A product chooses its medium (for example eMMC or NOR flash) and its Crux File provider; the framework names neither | D3 |
| Credentials on removable media | Whether the credential store may sit on a removable card is a product security decision | Product decision |
| One mount, never format | The composition mounts the volume once with the keep policy and binds the roots; no service mounts on its own; the framework never formats, so a blank or foreign medium does not mount and its data stays untouched | D11 |
| Configuration saving | Crux's Settings File provider for any power-cut-safe file system (`CRUX_CONFIGURATION_SETTINGS_FILE_ANY_FS`) on the LittleFS volume, once Crux's planned LittleFS File provider exists ([C4](controller-framework-platform-gaps.md#c4-configuration-saving-needs-a-power-cut-safe-file-system)) | Established mechanism |

For each product medium, these rules hold:

- **File system full**: a save or a file write answers an error, the status service shows it, and the application data root has a size limit so that it cannot fill the credential store and settings.
- **Power-cut integrity**: the settings file and the credential store survive a cut at any point, shown by a power-cut test on the medium.
- **Configuration compatibility after an update**: the parameter table carries a version; a new image gives new parameters their defaults, keeps stored values whose key and type match, and reports discarded values; a deliberate downgrade is a product decision.
- **Configuration compatibility after a rollback**: when the boot loader reverts an image, the earlier image reads values that the reverted image may have saved with the same rules, keeps values whose key and type match, gives defaults where they do not, reports them, and leaves keys it does not know in place; so a parameter keeps its type for as long as its key exists, and a changed type takes a new key.

LittleFS is copy-on-write: a rename replaces a file atomically, so a power cut leaves the old or the new file.
Its guarantee covers the file system, not the medium's own controller during a power cut, so a power-cut test on the board is the evidence for a medium.
A PC cannot mount the card without a LittleFS tool; files leave the device through device management.
FatFs stays a selectable Crux File provider for other products, and a build with commercially licensed Reliance Edge may select it behind the same Crux File and Configuration interfaces.

### 5.5 Device preparation (D11)

- A preparation image or a host tool (littlefs-python, littlefs-fuse) writes the volume and its layout, and the device makes and stores its TLS key and certificate (its device identity) during preparation.
- A normal boot makes no key, except in a development or reference build with the TLS identity option (section 7.1).
- In any other build, a prepared volume without a device identity puts the boot into safe mode, the status service and the serial log report the missing identity, and the recovery is device preparation again.

### 5.6 Board facts

Whether the reset cause reads WATCHDOG after a WDOG1 reset, whether the retained region survives it, whether a software reset reads CPU_LOCKUP together with SOFTWARE, with and without the marker, and whether a power cycle, which reads as PIN, leaves the region invalid are board facts of the RT1060-EVKB.
A board check early in delivery stage 2 shows them, in a run that needs its own board authorisation (section 8.2).

## 6. Update and security items

### 6.1 Update (D7)

The partition layout, image format, signing and the confirmation call come from Crux's secure boot work; the framework defines none of them.
MCUboot reverts a test image that is not confirmed only when the device next resets (MCUboot test and revert); a test image that keeps running unconfirmed is not reverted.

- **Health verdict** (framework): a test image is healthy when, during its trial, all of these hold, not uptime alone:
  - the controller is operational;
  - every start prerequisite is healthy and every device management service that the build includes has started;
  - the application, when present and not stopped by an operator, has been running for the stable period;
  - no fault reset happened since the test image first booted;
  - the configuration loaded with a compatible version (section 5.4).
- **Confirmation** (update component): when the verdict is healthy, the update component confirms the image through Crux's image state contract ([C10](controller-framework-platform-gaps.md#c10-image-state)).
- **Trial deadline** (update component, on the framework's verdict): when the verdict is not healthy by the trial deadline (Kconfig, counted on the monotonic clock from the start of the boot), the update component requests a planned reset, and the boot loader reverts the image at that reset; the configuration rules after a rollback are in section 5.4.
  This planned reset carries no operator reset marker, so it counts as a fault reset, which has no effect because the reverted image clears the counter (section 5.1).

The verdict needs no particular device management service: a build without web management is confirmed on the same conditions.

### 6.2 Security items

| Item | Rule | Label |
|---|---|---|
| First trusted enrolment of the self-signed certificate | Device preparation records the certificate fingerprint (on a label or in the preparation record), and the serial command line shows it, so the operator checks it at the first connection instead of trusting on first use (RFC 7435); a product may install a certificate from its own CA instead | D11 |
| Serial command line in production | Every command needs an Access login after the first account; the product chooses whether the console is composed in production, for provisioning only, or always; physical access to the port is part of the trust model | Product decision (D16) |
| Factory reset authority | Section 5.3 | D15 |
| HTTPS file transfer | Confined to the application data root, with limits on file size, total size, concurrent transfers and file names; it needs Crux's web adapter for the File service ([crux-pilot#188](https://github.com/wonny-labs/crux-pilot/issues/188)) | D10 |
| Audit persistence | Crux security events are drained to the log at the pin; the product chooses when they reach storage (for example at once for authentication failures and account changes, batched for others), weighing loss at a power cut against medium wear; timestamps come from unauthenticated SNTP (IEC 62443-4-2 CR 2.8 to 2.11, as direction) | Product decision (D16) |

## 7. Build options, boards, source zones and priority bands

### 7.1 Build options

The product sets each option with Kconfig, and each value is a product decision; the symbol names are open, decided at implementation.
The last column names the decision or constraint that defines the option.

| Option | Values | Default | Rule | Defined by |
|---|---|---|---|---|
| Command line transport | serial, SSH, both | serial | SSH only with Crux's Wolf TLS profile, which needs a commercial or GPL-3.0-or-later licence, and only when Crux offers Access on the Wolf profile and an SSH composition interface | D6, [C7](controller-framework-platform-gaps.md#c7-ssh-and-tls-profiles) |
| HTTPS TLS profile | Crux Mbed profile, Crux Wolf profile | Mbed | One profile per image; the Wolf value needs Crux Access on the Wolf profile | C7 |
| Console and logging UART | separate, shared | separate | Shared only with Crux's planned build option | D5, [C6](controller-framework-platform-gaps.md#c6-console-and-logging-uart) |
| Start prerequisites | Any of network, storage, Access, configuration, time, web management, command line | network, storage, Access, configuration | Checked before every application start (section 4.7) | D4 |
| Runtime dependencies | The same set | the start prerequisites | Reported while the application runs; the application responds (section 4.7) | D4 |
| Start without a watchdog | allowed, refused | refused | Allowed only by an explicit option in `native_sim` and bench builds | D14 |
| Safe-mode threshold N | 1 to a small maximum | 3 | Section 5.2 | D4 |
| Stable period | seconds | open, decided at implementation | Clears the boot counter (section 5.2) | D4 |
| Startup step deadlines | milliseconds per step, including `init`, `start` and `stop` | from board measurement | Section 4.1 | Reference configuration |
| Image trial deadline | seconds | open, decided at implementation | Section 6.1 | D7 |
| TLS identity at boot | off, on | off | On only in development and reference builds; a product build refuses it (section 5.5) | D11 |
| Leave out a device management service | per service | all built | Least functionality | IEC 62443-4-2 CR 7.7, as direction |

### 7.2 Boards and variants

| Rule | Mechanism | Label |
|---|---|---|
| Per-board values live in board files | `app/boards/<board>.conf`, merged with `prj.conf` when `CONF_FILE` is unset, and `app/boards/<board>.overlay`, in the base image and in each product | Established mechanism (Zephyr application development) |
| Variants are fragments | `EXTRA_CONF_FILE`, `EXTRA_DTC_OVERLAY_FILE`, `FILE_SUFFIX` with fallback | Established mechanism |
| Roles by devicetree | Aliases `crux-serial0` (console) and `crux-watchdog0` (watchdog), `chosen` `zephyr,log-uart` (logging), node label `controller_storage` (storage) | Established mechanism |
| No board name in sources | Nothing in the framework module, the base image's sources or the application interface names a board or SoC (P1) | D9 |
| Snippets only for cross-cutting settings | Debug and the RAM disk CI form; never per-board values | Established mechanism (Zephyr snippets) |
| Generic Kconfig dependencies | `CRUX_CONTROLLER_FILE` depends on `CRUX_FILE_FATFS_RT1060` (`app/Kconfig:40`); it changes to a generic "Crux File provider present" symbol or a `DT_HAS_*_ENABLED` test when Crux offers one | Platform constraint or interim |
| Board as a build input | `scripts/build-board.sh` builds the RT1060-EVKB only; the board target becomes an input, and builds go to `build/<board folder>/<configuration>` | D9 |

Adding a board takes, in this order: the board's `.conf` and `.overlay`, the aliases and `chosen` nodes, the partition layout from the secure boot work, a CI row, and the smallest build configuration as its first passing build.
A second board is outside the current scope (D9), and the SoC gates of [C12](controller-framework-platform-gaps.md#c12-soc-gates) apply.

All RAM of the reference board configuration (`mimxrt1060_evk@B/mimxrt1062/qspi`) is the 32 MB SDRAM; the on-chip regions are unused, except the retained region (section 5.1), which the board overlay places in on-chip RAM.
The per-configuration sizes are in the roadmap, [Static size per configuration](../roadmap.md#static-size-per-configuration).
The 25 percent free margin of `budgets/limits.json` is a budget of the reference board; a product sets its own budget for its board.

| Variant | Why | Mechanism |
|---|---|---|
| Base image | The framework with no application | The base image's `prj.conf` plus one fragment, with the board files |
| RAM disk form | CI runners and benches without a medium; never saves configuration | One snippet |
| Debug form | Stack and thread analysis | `FILE_SUFFIX=debug` or one snippet |
| Per board | Different nodes and drivers | The board's own `.conf` and `.overlay` only |

The fixture application is a test, not an image or variant: it has no board build and no `Budget` row, and it is not a product template.

### 7.3 Source zones and OS neutrality (D17)

`scripts/check_boundary.py` checks only the trees in its `RULES` (`app/src`, `workload`, `app/compose`, `app/os`; lines 125-162), and `check()` scans only those trees (lines 308-313).
A framework source outside them would escape the check, so every source of the module, the base image and the fixture application lives in a checked zone; the paths are open, decided at implementation.

| Tree | Holds | May include |
|---|---|---|
| `include/` | The application interface header that a product includes | ISO C and public `<crux/NAME.h>` headers |
| `framework/src` (portable core) | States, supervision policy, boot counter, safe mode, retained record format, startup step table, time synchronisation and management policy, and the port headers | The current rules of `app/src`, with no Zephyr header |
| `framework/compose` (composition zone) | Storage mount, management start, command line start | The current rules of `app/compose`, plus `zephyr/fs/littlefs.h` and `<crux/cli_zephyr.h>` |
| `framework/os` (adapter zone) | Supervisor thread, task watchdog, retained record access, fatal error handler, SNTP adapter | The current rules of `app/os`, plus `zephyr/task_wdt/task_wdt.h`, `zephyr/retention/retention.h`, `zephyr/fatal.h`, `zephyr/devicetree.h` and `zephyr/device.h` |
| `app/` (base image) | `main()` | ISO C and the header of `include/` |
| `tests/` fixture application | The contract test application (section 8.1) | ISO C, the header of `include/`, public `<crux/NAME.h>` headers and the Zephyr headers that its threads need |

- `RULES` gains one rule per tree, and a source file of the module that no rule covers fails the check.
- Each new header is a separate reviewed boundary change under CONTRIBUTING "The boundary", with its reason in [composition-zone.md](../composition-zone.md) and a case in `tests/tooling/test_boundary.py`.
- The composition zone gains `zephyr/fs/littlefs.h`, for the LittleFS mount, unless Crux's planned LittleFS provider mounts the volume itself, and `<crux/cli_zephyr.h>`, which `COMPOSITION_CRUX_HEADERS` does not list.
- The adapter zone gains `zephyr/task_wdt/task_wdt.h`, `zephyr/retention/retention.h` (the framework uses the retention API, not the `retained_mem` driver header), `zephyr/fatal.h`, and `zephyr/device.h` and `zephyr/devicetree.h`, which find the retained region.

The portable core runs in host tests with fake ports, and the Zephyr adapter and composition zones are the only OS-specific code.
The portable core, the separated OS-specific zones and the host tests hold in every delivery stage, and the framework adds no abstraction for Linux before it has a Linux function to serve (P1, P2).
Linux functions (P3, delivery stage 6) need Linux providers for the Crux components that have Zephyr providers only ([C13](controller-framework-platform-gaps.md#c13-linux-providers)), which Crux designs when its first Linux product is defined (Crux ADR-0003 R5).

### 7.4 Priority bands (reference configuration)

Zephyr priorities, where a lower number is a higher priority; a product tunes the values for its deadlines, jitter, network load and priority inversion.

| Band | Priority | Threads |
|---|---|---|
| Application | 3 to 6 | Threads the application creates |
| Supervisor | 7 | The health supervisor |
| Startup | 8 | The thread that runs the start function |
| Framework services | 9 to 10 | Time synchronisation, storage worker, status updates |
| Device management | 11 to 13 | Crux web session and management workers, the console, the reboot and network settings workers, the security event drain |
| Zephyr threads | as Zephyr sets them | HTTP server (lowest preemptive), network RX and TX, deferred log processing (14) |

- Crux's service workers default to priority 6 at the pin (`zephyr/Kconfig:85-135`: security event drain, reboot worker, network settings worker, web session worker, web management worker and console), inside the application band, so the framework sets each of those Kconfig priorities into the device management band.
- The supervisor sits below the application band, so an application thread that holds the CPU starves the supervisor and ends in a reset.
- The supervisor sits above the startup thread and device management, so a long step, a TLS handshake or key generation cannot starve it.
- Zephyr mutexes apply priority inheritance and semaphores do not, so a shared resource between bands uses a mutex.
- Verification checks the bands against the priorities of Zephyr's network threads and measures jitter under network and TLS load on the board (section 8.1).
- A Zephyr userspace or MPU partition for the application is later work.

## 8. Verification

### 8.1 Layers (D8)

| Layer | What it shows | Where |
|---|---|---|
| Crux component tests | Crux behaviour | Crux's CI |
| Framework unit | The portable core: the states and lifecycles of section 4, policies, boot counter and retained record rules, startup step table, health verdict and trial deadline | Host tests, every pull request |
| Framework integration | Composition, startup order, startup and runtime supervision, safe mode, the application contract through the fixture application, the scenarios of section 8.4 | `native_sim`, every pull request |
| Reference image | The base image builds for the board within its budget and runs on `native_sim`, with image-level regression tests | CI, every pull request |
| Product integration | An independent west workspace imports the framework as a product would (T2), builds and runs on `native_sim` | The nightly tier of a tiered CI as Crux documents it (Crux `main`, `docs/ci.md`, "Use in a product repository") |
| Hardware | The board facts of section 5.6 (early in delivery stage 2); power cut on the medium, timing and jitter of application threads, TLS sessions under application load, output state during a reset | The board, in approved runs only |

- The image keeps essential system-level regression tests even where Crux tests the component: an HTTPS login, the TLS-only listener and the start order in the base image.
- The `native_sim` scenarios keep code of this repository and those image-level checks; a case that only repeats Crux behaviour in detail is dropped.
- The host tests stay and gain the portable core.
- The smallest board build (`prj.conf` alone) stays as the first build a new board must pass; it takes another name than `base` (D13).
- The board builds of `workload`, `net`, `file`, `system`, `sntp` and `management` are replaced by the base image.
- `budgets/limits.json` gains a row for the base image; its `_comment` makes a change there a reviewed change.

### 8.2 Delivery stages

| Stage | Content | Ends with |
|---|---|---|
| 1. Foundation | The Zephyr module, the repository role (D12), service composition, the base image, the boundary check of section 7.3 and the consumer integration job; it shows that a product imports the module and that the base services compose | Criteria 1 to 3, 13, 14 and 26 to 30 |
| 2. Reliability | First, the board check of section 5.6; then the startup and runtime watchdog, the channel lifecycle, the supervisor, boot counter, safe mode, retained record and diagnostics | Criteria 6, 7, 10, 11 and 16 to 19 |
| 3. Application integration | The application contract of sections 3 and 4, shown through the fixture application | Criteria 4, 5, 8, 9 and 20 to 23 |
| 4. Framework completion | Persistence on LittleFS and the other [platform gaps](controller-framework-platform-gaps.md), as Crux closes them | Criteria 12 and 24 on LittleFS, criterion 25, and the end of every interim state that section 8.5 does not accept for Framework Complete |
| 5. Product readiness | Per product: secure boot and update, factory reset, hardware validation, security hardening, and validation of the application interface with a first real runtime consumer | PR1 to PR6 and criterion 31 |
| 6. Linux functions (later) | A Linux adapter over Crux's Linux providers, coordinated with Crux | A later specification |

Criterion 15 holds in every delivery stage.
Later items:

| Item | Rule |
|---|---|
| Configuration backup and restore | Through device management, once configuration saving exists (IEC 62443-4-2 CR 7.3 and 7.4, as direction) |
| Applying changed network settings | Crux's network settings service has a no-op apply port only; the framework implements the apply port, and saving needs the save provider |
| Core dump and log persistence | Zephyr core dump to a partition and log persistence need a partition decision; the retained last-fault record covers the reset evidence |
| Stack high-water reporting | Part of the diagnostics of delivery stage 2, shown in the status service |
| Turning services on and off at runtime | Through configuration, once configuration saving exists; build-time removal is in section 7.1 |
| Integration guide | A page that explains how a product joins the framework and links the fixture application under `tests/` as the code reference; no separate example code or example image |

### 8.3 Milestones

| Milestone | Reached when | Interim states |
|---|---|---|
| Framework MVP | Delivery stages 1 to 3 end: criteria 1 to 11, 13 to 23 and 26 to 30 | Every interim state of section 8.5 is accepted |
| Framework Complete | Delivery stage 4 ends: every mandatory function and platform dependency, including persistence on LittleFS; criteria 1 to 30 | Only the interim states that section 8.5 accepts for Framework Complete |
| Product Ready | Delivery stage 5 ends, per product on its board: PR1 to PR6 and criterion 31 | None of section 8.5 for the functions the product uses |

### 8.4 Criteria

Framework MVP:

| # | Requirement | Criterion |
|---|---|---|
| 1 | F1, F2 | The base image enables every service of the [overview](controller-framework.md#services) that its TLS profile allows (C7), with no application, and the framework's Kconfig has no exclusion between services beyond those of the TLS profile. |
| 2 | F2 | The RT1060-EVKB build of the base image passes in CI with `-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`, and its `Budget` row keeps at least 25 percent free in every region; the 25 percent is a budget of the reference board (section 7.2). |
| 3 | F2 | The base image builds and runs on `native_sim` in CI. |
| 4 | F3, F5 | A fixture application under `tests/`, with its own `main()`, `prj.conf` and descriptor, builds for `native_sim` in CI with this repository as a Zephyr module (`EXTRA_ZEPHYR_MODULES`) and runs: the log shows `init`, `start` and `stop` in order, a thread that the application created with Zephyr, a registered and activated watchdog channel, a status item and a parameter in device management, and a file under its data root. |
| 5 | F3 | A second call of the start function, and a descriptor without a mandatory entry, are refused; a host or `native_sim` test checks both. |
| 6 | F1, R1, R4 | A `native_sim` scenario of the start order: the reset cause is read once, the status service receives the captured copy, the flags are cleared after the capture, the watchdog is armed before the storage mount, the start prerequisites are checked, and the application starts last; startup supervision ends when `start` returns. |
| 7 | R1, R2 | A `native_sim` scenario with an injected startup step that passes its deadline: the supervisor writes the retained record with the step name and stops feeding, and the simulated watchdog restarts the image (reset cause SOFTWARE, [C11](controller-framework-platform-gaps.md#c11-simulated-watchdog-on-native_sim)). |
| 8 | F3, R2 | A `native_sim` scenario with an injected `init` failure after a registration: the application reports fault, `safe_state` ran, the registration is released, the controller state is unchanged, and device management answers. |
| 9 | R1, R2 | A `native_sim` scenario with an injected stall of a registered application thread: the channel expiry is recorded, `safe_state` ran, the supervisor stops feeding, and the simulated watchdog restarts the image. |
| 10 | R3, R4, R5, P2 | Host tests of the portable core: N consecutive fault resets enter safe mode; the stable period, the operator command and a different image clear the counter; the retained region's checksum rejects a damaged region; the state transitions of section 4; a start prerequisite that is not healthy holds the application; a watchdog that does not arm holds the application in a product build and not with the explicit option. |
| 11 | R3 | A `native_sim` scenario of safe mode: the minimal service set runs, the application is not initialised, device management answers, and the exit command leads to a normal boot. |
| 13 | P2 | `scripts/check_boundary.py` checks every source tree of section 7.3; a source that no rule covers fails the check; the portable core has no Zephyr include; each new allow-list entry is a separate reviewed change. |
| 14 | F3 | The product integration job of section 8.1 imports the framework into an independent west workspace, builds and runs on `native_sim` in the nightly tier. |
| 15 | F2 | The repository holds no control algorithm; the architecture, capabilities and roadmap pages describe the framework and the base image; no page claims a board run until one is approved and recorded. |
| 16 | R2 | Fatal-error reset: a `native_sim` scenario with an injected fatal error in a framework thread shows that the handler calls no application entry, writes the minimal record and restarts the image; host tests show that the next boot counts it as a fault reset. |
| 17 | R3 | Framework fault in safe mode: a `native_sim` scenario that boots in safe mode and stalls a safe-mode service thread shows that the supervisor stops feeding and the image restarts; host tests show that the counter stays saturated and the next boot is again in safe mode. |
| 18 | R2 | Host tests of the reset rules of section 5.1: several latched cause bits, POR together with other bits, a SOFTWARE reset with and without the operator reset marker, CPU_LOCKUP together with SOFTWARE, with and without the marker, a consumed record, an interrupted write, counter saturation, and a different image identifier after an update and after a rollback. |
| 19 | R1, R5 | Production watchdog configuration: a build test shows that a product build has `CONFIG_TASK_WDT_HW_FALLBACK=n`, a callback on every channel, neither the start-without-watchdog option nor the TLS identity option, and a timeout T inside the provider's range; a `native_sim` scenario of that configuration with an unavailable watchdog holds the application. |
| 20 | F3, R1 | Start timeout: a `native_sim` scenario in which `start` passes its deadline: the supervisor writes the record with the step name, calls `safe_state`, stops feeding, and the image restarts. |
| 21 | F3, R1 | Operator stop and restart: a `native_sim` scenario in which an operator stop calls `stop`, then `safe_state`, and releases the application's channels while the controller stays operational; an operator start checks the start prerequisites, activates the channels again without calling `init`, and calls `start`; a `stop` that passes its deadline restarts the image. |
| 22 | F3 | Partial start failure: a `native_sim` scenario in which a channel activation fails and one in which `start` returns an error: the activated channels are deleted, `safe_state` ran, the application is in fault, the controller state is unchanged, and device management answers; host tests show that a requirement beyond the channel capacity and a duplicate name are refused in `init`. |
| 23 | R4 | Required-service failure: a `native_sim` scenario in which a start prerequisite fails at boot: the application is held, the controller is degraded, and after the service recovers an operator start runs the application; and one in which a runtime dependency fails while the application runs: the change is reported through the status service and `ctx`, the application keeps running, and the controller is degraded. |
| 26 | F4 | Device management: a `native_sim` scenario of the base image answers an HTTPS login through web management and a command through the serial command line; an image with SSH is checked once Crux offers the conditions of D6. |
| 27 | F6 | Build options: a build test sets each option of section 7.1 to a value other than its default and builds, and shows that a value the rule column refuses (SSH with the Mbed profile, the TLS identity option in a product build) fails the build. |
| 28 | S1 | First account: a `native_sim` scenario shows that a new image has no account and accepts no login, that first-account setup over the serial command line creates the first account, and that setup is refused after that first save. |
| 29 | S2 | No unauthenticated erase: a `native_sim` scenario shows that, after the first account exists, the serial command line refuses every command without an Access login, so no unauthenticated command erases credentials or configuration. |
| 30 | P1 | No board name: a check fails when a C source or header of the framework module, the base image or the application interface names a board or an SoC; board files are outside the check. |

Framework Complete adds:

| # | Requirement | Criterion |
|---|---|---|
| 12 | R7 | A `native_sim` scenario saves a parameter on LittleFS, restarts on a file-backed disk and reads it back. |
| 24 | R7 | Storage full: a `native_sim` scenario on LittleFS in which the application data root reaches its size limit: a file write answers an error, a parameter save still succeeds, and the status service shows storage degraded. |
| 25 | D7 | Unconfirmed image timeout: host tests of the health verdict and the trial deadline with a fake image state port: a verdict that is not healthy by the deadline requests a planned reset, a healthy verdict leads to confirmation, and a build without web management is confirmed on the same conditions. |

Product Ready adds, per product on its board:

| # | Requirement | Criterion |
|---|---|---|
| PR1 | R1, R2, R7 | Hardware tests: a watchdog reset reads the reset cause WATCHDOG and advances the boot counter; the retained region survives a WDOG1 reset and a pin reset and does not survive a power cycle; power cuts on the product medium keep the settings file and the credential store; application thread timing and jitter meet the product's deadlines under TLS sessions and network load; outputs hold their safe state during a reset. |
| PR2 | R7 | Configuration persists on the product medium, and the compatibility rules of section 5.4 hold across an update and a rollback. |
| PR3 | D7 | Secure boot and update with the health-gated confirmation and the trial deadline of section 6.1, including the revert of an unconfirmed image at the reset after the deadline. |
| PR4 | S2 | Factory reset with the authority and scope of sections 5.3 and 5.5. |
| PR5 | S3 | The security items of section 6.2 are implemented. |
| PR6 | F3 | Product integration with the product's own application, which is also the first real runtime consumer that validates the application interface before its stability tier is raised (section 3.4). |
| 31 | R6 | Startup duration: on the product's board, each startup step of a normal boot is measured, stays within its deadline, and its deadline is set from that measurement. |

### 8.5 Interim states

Each interim state is accepted until its Crux change is at the pin; the [platform gaps](controller-framework-platform-gaps.md) describe each state and its replacement criterion.

| Interim state | Gap | Accepted for Framework Complete |
|---|---|---|
| FatFs serves files and the credential store, with no configuration save | C4 | No |
| The product build reaches Crux's `tests/` for the Settings File sources | [C5](controller-framework-platform-gaps.md#c5-settings-file-sources-under-a-crux-tests-path) | No |
| Crux service threads are supervised indirectly | C8 | No |
| The serial console uses a second UART | C6 | Yes; the shared UART is a build option |
| No SSH and no Wolf profile | C7 | Yes; both are build options |
| Factory reset only by device preparation | C9 | Yes; factory reset belongs to Product Ready |
| The images are prepared for MCUboot, with no health-gated confirmation | C10 | Yes; confirmation on the board belongs to Product Ready |

## 9. Decision register

D1 to D17 are decided, except D9, which is deferred, and D16, which is a product decision whose direction is decided and whose details each product settles at product readiness.

| # | Decision | State | Chosen | Not chosen | Source |
|---|---|---|---|---|---|
| D1 | Application interface | Decided | A descriptor that the product's `main()` passes to the start function, with only framework-owned items and no framework-owned execution model; the framework runs no execution thread for the application; entries specified by guaranteed results within bounded time; channels registered in `init` and activated at `start`; the lowest stability tier until a first real runtime consumer validates it; no framework-owned periodic task in the first version (sections 3 and 4.4) | Registration of the descriptor in a linker section (`STRUCT_SECTION_ITERABLE`), with a Kconfig choice of the application | Zephyr modules and iterable sections; Zephyr task watchdog; Crux ADR-0003 R2 (product code uses the OS natively); repository rule against pass-through wrappers |
| D2 | How a product consumes the framework | Decided | A workspace application whose repository is the west manifest repository (T2), which owns `app/`, `main()`, `prj.conf` and its board files and imports Crux and the framework; the framework is a Zephyr module (`zephyr/module.yml`) that one Kconfig symbol turns on (established mechanism) | Importing the whole of this repository as the application, which takes `main()`, `prj.conf` and board files from the product; copying this repository, which forks the framework in every product | Zephyr application types, west T2 topology and "Modules"; nRF Connect SDK workspace applications (`ncs-example-application`) and `CONFIG_CAF`; Crux `templates/product` |
| D3 | Medium and file system | Decided | LittleFS on the whole microSD card, for the reference board only; products choose their medium and provider (section 5.4) | LittleFS on a QSPI NOR partition; Reliance Edge under a commercial licence | C4 |
| D4 | Response to a hang | Decided | A device reset with boot counter and safe mode, safe mode after N consecutive fault resets (Kconfig, default 3); `safe_state` on a channel expiry when possible, never from the fatal error handler, which writes a minimal record and resets; a CPU lockup left to the hardware watchdog (sections 4 and 5) | Stop the application and keep the framework running: a hung Zephyr thread cannot be removed safely (section 4.3), and safe mode after N resets reaches a held application with management running | Zephyr task watchdog and fatal error handling; Crux System contract; U-Boot boot count limit |
| D5 | Console UART | Decided | Both as a build option, separate by default; shared needs the planned Crux option (C6) | — | Zephyr shell log backend; Crux Logging binding and console contract |
| D6 | SSH command line and SFTP | Decided | A command line transport option that allows SSH only with the Wolf profile under a commercial or GPL-3.0-or-later licence, Crux Access on the Wolf profile (Crux change needed) and Crux's deferred SSH composition interface | An SSH server on Mbed TLS, because it means writing a security-critical protocol implementation | Licences of wolfSSL and wolfSSH ([dependencies](../dependencies.md)); C7 |
| D7 | Firmware update | Decided | Partition layout, image format and confirmation from Crux's secure boot work; the framework gives the health verdict, the update component confirms or requests a reset at the trial deadline, and the boot loader reverts an unconfirmed image at that reset; the watchdog policy from the boot loader to the application and the final recovery path are decided with the same work (sections 4.2, 5.2 and 6.1) | A framework-owned update design | MCUboot test, confirm and revert |
| D8 | Verification | Decided | The layers of section 8.1; this repository builds one image, the base image, and a test-only fixture application under `tests/` exercises the interface | Keep every per-capability scenario and board build | Zephyr's split of applications, samples and tests |
| D9 | Second board | Deferred | The framework stays board-neutral (section 7.2) | — | C12 |
| D10 | Crux gaps | Decided | Crux changes in the priority order of the [platform gaps](controller-framework-platform-gaps.md): they are platform gaps | Workarounds in this repository | — |
| D11 | Device preparation | Decided | A preparation image or host tool writes the volume, and the TLS key and certificate are made during preparation; a normal boot never formats a medium and makes a key only in a development or reference build with an explicit option; a prepared device without its identity boots in safe mode (section 5.5) | The image formats an empty medium and makes the key at first boot: formatting destroys data, a removable medium may hold someone else's data, and a long first-boot step weakens startup supervision | Crux File providers refuse auto-format |
| D12 | Repository role | Decided | The role sentence of CONTRIBUTING changes to a controller framework module with a base image that products import, as a reviewed change of the files that state the role; the glossary entry "Product" then takes Crux's sense; with D2 | Keep "reference consumer firmware" | CONTRIBUTING role section; [glossary](../glossary.md) |
| D13 | Names | Decided | "Controller framework" for the module and "base image" for the one image, with no example image; Crux is the platform, and the documents reserve "the reference controller" for Crux's sample; the build configuration `base` (`prj.conf` alone) takes another name, for example `minimal`, as a reviewed change of the files that name it | Names with "platform" or "reference controller" | `tests/tooling/test_docs.py` |
| D14 | Application start without a hardware watchdog | Decided | In product builds the application does not start; `native_sim` and bench builds may allow it by an explicit build option | Start the application and report "watchdog not armed" | Crux System reports an unavailable watchdog as not supported |
| D15 | Recovery and factory reset authority | Decided | Factory reset by an authorised operator through Crux's planned Access erase, with an optional product-defined physical-presence input, and device preparation as the recovery when Access is unusable; it erases credentials and configuration and keeps the device identity (section 5.3) | An unauthenticated serial wipe | IEC 62443-4-2 CR 4.2, as direction |
| D16 | Serial command line in production and audit persistence | Product decision | Direction in section 6.2; each product settles the details at product readiness | — | IEC 62443-4-2 CR 2.8 to 2.11 and CR 7.7, as direction |
| D17 | Framework core structure | Decided | The framework core is portable C; OS-specific code sits behind port headers in the adapter and composition zones (section 7.3) | — | Ports and adapters (A. Cockburn, "Hexagonal architecture"); Crux ADR-0003 R2 |

## 10. Terms

| Term | Meaning here | Source |
|---|---|---|
| Controller framework | The Zephyr module of this repository: composition of the Crux services, health supervision and the application interface | These pages |
| Base image | The image of this repository: the framework with no application | These pages |
| Product | A firmware repository outside this repository that is built on Crux and the framework; the [glossary](../glossary.md) uses the word for this repository's firmware until D12 | Crux product composition guide |
| Application | Product code that joins the framework: the product's control software or a third-party application runtime | These pages |
| Third-party application runtime | Software from another vendor that runs user programs with its own scheduling and execution model | Common usage |
| Fixture application | A test-only application under `tests/` that exercises the interface in a contract test | Common test usage |
| Descriptor | The one structure an application defines, with its entry points, passed to the framework's start function | These pages |
| Startup step, step deadline | One of the twelve steps of the start function (section 4.1); the software time limit of one step | These pages |
| Supervision period | One of the periods of section 4.2, which say what the supervisor feeds the hardware watchdog by | These pages |
| Delivery stage | One of the six stages of work of section 8.2 | These pages |
| Supervisor | The one thread that holds the watchdog token and feeds only while every activity progresses | Crux System health design |
| Channel requirement, active channel | A channel that `init` registers without creating it; a Zephyr task watchdog channel that the framework added at `start` | These pages |
| Controller state | Starting, operational, degraded or recovery (section 4.6) | These pages; common embedded usage |
| Application state | Absent, not initialised, initialised, held, running, stopped or fault (section 4.5) | nRF Connect SDK CAF module states; systemd unit states |
| Service health | Healthy, degraded, failed or absent, per service (section 4.7) | Common usage |
| Start prerequisite, runtime dependency | A required service that holds the application while it is not healthy; a required service whose health the framework reports to the running application | These pages |
| Degrade and report | Keep running with a reduced function and show the condition | Common embedded usage (graceful degradation) |
| Operator | A person who uses device management after an Access login; an authorised operator holds an account that permits the action; the [glossary](../glossary.md#people-and-board-procedures) uses the word for a person at a bench | These pages |
| Operator stop, operator start | An application stop or start that an operator requests through device management | These pages |
| Operator reset | A reset that an operator requests, including the framework's resets on an operator command (safe-mode exit, factory reset); it carries the operator reset marker | These pages |
| Planned reset | A reset that software requests through Crux Reboot after the framework has called `stop` and `safe_state`; an operator reset is one, and the update component's reset at the trial deadline is one without the marker | These pages |
| Fault reset | A reset that the boot counter counts (section 5.1) | These pages |
| Boot counter, safe mode | A count of consecutive fault resets; a boot mode with a minimal service set and no application | U-Boot boot count limit; common embedded usage |
| Device preparation, device identity | Steps before first use that write the volume and make the device's TLS key and certificate; that key and certificate | Common manufacturing usage (provisioning) |
| Safe state | The defined output state on stop, fault or reset | IEC 61508-4 |
| Update component, trial deadline | The component from Crux's secure boot work that confirms an image through Crux's image state contract; the time after which an unconfirmed test image leads to a reset request | These pages; MCUboot |
| Priority band | A reserved range of thread priorities for one group of threads | Common RTOS usage |

## Sources

These sources cover this page, the [overview](controller-framework.md) and the [platform gaps](controller-framework-platform-gaps.md).

- Zephyr documentation at the release that the Crux pin names, under `doc/`: "Application Development" (application types, board files, `EXTRA_CONF_FILE`, `FILE_SUFFIX`), west "Workspaces" (topologies), "Modules (External projects)", "Shell" (logger backend), "Task Watchdog" with `subsys/task_wdt/Kconfig`, "Retention System" (boot mode), "Retained Memory", "Mutexes" (priority inheritance), "Core Dump", "Settings" and snippets.
- The Zephyr `example-application` repository README; nRF Connect SDK "Creating an application" (workspace application recommended, `ncs-example-application`) and "Common Application Framework overview" (module states).
- systemd documentation, `systemd.unit` and `systemctl` (unit active states).
- MCUboot design documentation (image test, confirm and revert) and its Zephyr port's `CONFIG_BOOT_WATCHDOG_FEED`.
- U-Boot documentation, "Boot Count Limit" (`CONFIG_BOOTCOUNT_LIMIT`, `bootlimit`, `altbootcmd`).
- A. Cockburn, "Hexagonal architecture" (ports and adapters).
- RFC 7435, "Opportunistic Security: Some Protection Most of the Time" (trust on first use).
- littlefs design notes: copy-on-write and power-loss resilience.
- Crux at the pin: `zephyr/Kconfig`, `zephyr/CMakeLists.txt`, `components/logging/ports/zephyr/`, `components/cli/ports/zephyr/include/crux/cli_zephyr.h`, `components/system/`, `components/access/include/crux/access.h`, `components/mgmt_status/include/crux/management_status.h`, `components/file/ports/zephyr/CMakeLists.txt`, `components/image_state/`, `components/*/ports/linux`, `docs/decisions/0001-application-boundary-and-api-stability.md` (Decision 4), `docs/decisions/0003-p9-result-services-keep-narrow-thread-sync.md` (R2, R5), `docs/management-in-a-product.md`, `tests/native/configuration_settings_littlefs`, `tests/native/file_littlefs`, `templates/product/README.md`.
- Crux `main`: `docs/superpowers/specs/2026-10-24-system-health-design.md`, section "Supervising several activities"; `docs/ci.md`, "Use in a product repository".
- Crux issues [#188](https://github.com/wonny-labs/crux-pilot/issues/188) and [#297](https://github.com/wonny-labs/crux-pilot/issues/297).
- This repository: `scripts/check_boundary.py`, `scripts/build-board.sh`, `budgets/limits.json`, `docs/dependencies.md`, `docs/glossary.md`, `docs/roadmap.md`.
- IEC 61508-4 (definition of safe state); IEC 62443-4-2 by clause title (CR 1.5, 2.8 to 2.11, 4.2, 7.3, 7.4, 7.7); ETSI EN 303 645, provision 5.1; the EU Cyber Resilience Act, Annex I; all as direction, not as compliance claims.
