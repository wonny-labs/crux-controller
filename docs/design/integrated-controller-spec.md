# Integrated controller specification

This page specifies one application image that holds every capability of Crux Controller and does a small but real control job.
It is the input for the design, which follows only after the owner has reviewed this page and decided the open questions at the end.
It changes no product code; the [architecture](../architecture.md) and the [capabilities](../capabilities.md) describe the current images.

Each choice carries a label:

- **standard**: what Zephyr, Crux or common embedded practice documents as the normal way;
- **documented-optional**: a documented mechanism that is one of several valid choices;
- **workaround**: a choice forced by a current gap, to be replaced when the gap closes.

The sources are listed at the end, with Zephyr read at the release that the Crux pin names (v4.4.2, `dccb0959`) and Crux at the pinned commit `bd9efbc7`.

## 1. What the controller does

The image runs one closed control loop on a simulated plant, so that a reviewer can see a controller behave without any hardware beyond the board.

| Part | Behaviour | Label |
|---|---|---|
| Simulated input | A first-order plant model (a heated tank: temperature rises with heater output and falls towards ambient) gives the process value each cycle. A fixed, documented disturbance step can be switched on for tests. | standard (textbook first-order process model) |
| Computation | A PI controller with output clamping and anti-windup computes the heater output from set point and process value. | standard (PI/PID as in IEC 61131-3 function blocks) |
| Simulated output | The output (0 to 100 percent) drives the plant model in the next cycle. The safe value is 0 percent. | standard (defined safe state) |
| Set point | One parameter, `control.setpoint`, an unsigned value in tenths of a degree with a fixed range. It is read and changed through management and kept in a file. | standard (Crux configuration service) |
| Period | The cycle period of the workload record, 100 ms by default (`workload/include/workload.h`). | standard |

The loop, the plant model and the controller are plain C in `workload/`, with host tests, so that they stay portable and testable without Zephyr (the zone rules of [composition-zone.md](../composition-zone.md)).
The control thread reads the set point with `crux_config_service_try_read()`, which polls and never waits, and keeps its last value when the service is busy (`components/config_service/include/crux/config_service.h:222-241` in Crux).
A new set point takes effect at the next cycle boundary without a jump in the output (bumpless change).
The process value, the set point, the output and the count of late cycles are published as project items of the status service (`crux_mgmt_status_config_t.project_items`, `components/mgmt_status/include/crux/management_status.h:91`).

## 2. Capabilities and how the image uses them

| Capability | Crux interface | Use in the controller | Label |
|---|---|---|---|
| `base` | Crux Time, monotonic clock | Cycle timing; every control decision uses monotonic time only | standard |
| `workload` | Crux Logging; Zephyr threads in `app/os` | The control thread, the telemetry thread, the storage thread | standard |
| `net` | Crux Sockets profile, Crux Netif | Telemetry: samples go to the TCP peer from the telemetry thread, never from the control thread | standard |
| `file` | Crux File over the microSD FatFs provider | The control record (set point and cycle settings) and the credential store of management on one volume | documented-optional (Crux bench image, microSD form) |
| `system` | Crux System | Reset cause at start, the one watchdog of the boot, fed by the control loop | standard |
| `sntp` | Crux Time authority | Wall time for logs, records and the status service; never for control | standard |
| `management` | Crux Access, configuration and status services, web server | Read status, change the set point, save it | standard |

## 3. Conflicts and resolutions

Today `CRUX_CONTROLLER_MANAGEMENT` depends on `!CRUX_CONTROLLER_FILE && !CRUX_CONTROLLER_SYSTEM` (`app/Kconfig:151`).
The reasons and two further conflicts that appear once all capabilities share one start sequence follow.

### C1. One File provider per image

- **Cause.** `file` selects the microSD provider (`app/conf/file.conf:13`, `CONFIG_CRUX_FILE_FATFS_RT1060`) and `management` selects the RAM disk provider (`app/conf/management.conf:108-110`).
  Crux allows one: the RAM disk provider depends on `!DISK_DRIVER_SDMMC` (`zephyr/Kconfig:337`) and its CMake stops the build when another File selection is on (`components/file/ports/zephyr/CMakeLists.txt:20-24`).
- **Options.** (a) Both on the microSD provider, as the microSD form of the Crux bench image does (`tests/zephyr/management_rt1060_compile/bench_guard.cmake:296-303`).
  (b) Both on the RAM disk: the control record does not survive a reset.
  (c) Keep them apart, as today.
- **Recommendation.** (a) for the integrated image.
  Keys, accounts and the set point then persist, which a controller needs.
  (b) stays a CI form for runners without a card (decision D2).

### C2. Two owners of the reset cause

- **Cause.** `system` reads the reset cause, logs it and clears the flags (`app/src/health.c:67` and `:85`), and it runs before management (`app/src/composition.c:135` and `:153`).
  Management reads the cause again for the status service (`app/compose/management_start.c:232`), so it would see cleared flags.
  Crux grants one permission to clear and says that the boot diagnostic owner reads once and passes what it captured (`components/mgmt_status/include/crux/management_status.h:104`; `components/system/include/crux/system.h:83-88`).
- **Options.** (a) One owner: the health code reads once, keeps the result, clears, and the composition passes the captured cause to the management port.
  (b) Start management before the health code.
  (c) Never clear.
- **Recommendation.** (a), standard by the Crux contract.
  (b) ties the order of two unrelated capabilities together; (c) loses the next boot's evidence.

### C3. The watchdog runs while the start sequence is long

- **Cause.** The watchdog starts at `app/src/composition.c:136` with a timeout of about ten cycles, at least 2000 ms (`app/src/health_policy.h:95-101`), and only the producer thread feeds it.
  Management starts on the main thread before the workload threads exist (`app/src/composition.c:153-155`) and makes a key and a certificate on its first start.
  With both on, nothing feeds the watchdog during that time, and a slow first start ends in a reset.
- **Options.** (a) Arm the watchdog after the start sequence, just before the control thread starts.
  (b) Arm it first with a long timeout: Crux offers one activation per boot and no reconfiguration (`components/system/include/crux/system.h:100-108`), so the control loop would keep that long timeout.
  (c) Feed from the main thread during the start.
- **Recommendation.** (a).
  A hang inside the start sequence is then outside the watchdog's reach; every step logs its result, and the sequence is bounded (decision D4).

### C4. One volume, two mount policies

- **Cause.** Both capabilities mount the same devicetree entry `controller_storage` (`app/boards/file.overlay:16`, `app/boards/management.overlay:31`).
  `file` mounts with `STORAGE_PORT_KEEP_VOLUME` and never formats (`app/src/composition.c:73`); management mounts with `STORAGE_PORT_FORMAT_ON_FAILED_MOUNT` (`app/compose/management_start.c:207`) and creates its two store directories.
  A second mount returns `-EBUSY`, which the port reports as `STORAGE_PORT_ERR_ALREADY_MOUNTED` (`app/compose/storage_mount.c:76-77`), and management refuses at the step "medium".
- **Options.** (a) Mount once in the composition, with the keep policy, then bind root 0 for the product's files and roots 1 and 2 for the credential store.
  (b) Let each capability treat "already mounted" as success.
- **Recommendation.** (a).
  A card is never formatted by the image (standard for removable media: Crux's provider refuses auto-format, `zephyr/Kconfig:315`).
  Whether the image may create missing directories on a card is decision D6.

### C5. The product's own Kconfig exclusion

With C1 to C4 resolved, the `depends on` line of `app/Kconfig:151` loses its two negations.
`CRUX_CONTROLLER_FILE` keeps its board-specific dependency on `CRUX_FILE_FATFS_RT1060` (`app/Kconfig:40`), which the board-neutral build branch already marks as the one place to change when Crux gains a board-neutral provider.

## 4. Startup order

The main thread runs these steps in order and then ends.
A step that fails is logged with its name, and the steps after it run unless the table says otherwise.

| # | Step | On failure |
|---|---|---|
| 1 | Read the Crux monotonic clock once. | Stop: nothing can be timed. |
| 2 | Read the reset cause once, log it, keep the copy, clear the flags (C2). The health policy decides whether the watchdog may start. | Log; continue without the copy. |
| 3 | Mount the volume once with the keep policy, bind root 0 and the two store roots (C4). | Log; storage is absent (section 7). |
| 4 | Load the control record (two slots, section 6); use the defaults when none is valid. | Defaults. |
| 5 | Start security events, the realtime clock, the credential store and Access. | Management stays off; control runs. |
| 6 | Start the configuration service with the product's table (`control.setpoint` and the cycle settings, loaded in step 4). | Management stays off; control uses its loaded values. |
| 7 | Start the status service with the copy from step 2 and the project items. | Management stays off. |
| 8 | Start the time synchronisation thread. | Log; time stays unsynchronised. |
| 9 | Make or load the TLS certificate, register it, start sessions, management and the listener. | Management stays off. |
| 10 | Arm the watchdog (C3), then start the control, telemetry and storage threads. | Watchdog: log and run without it, as today. |

The network interface comes up before `main()` through Zephyr's network configuration library, as in `net` today (`app/conf/net.conf`, standard).

## 5. Threads and priorities

Zephyr priorities, where a lower number is a higher priority.
The shortest period gets the highest priority (rate-monotonic assignment, standard).

| Thread | Priority | Period or trigger | Work | Blocks on |
|---|---|---|---|---|
| control | 5 | the cycle period | read input, compute, write output, publish the snapshot, feed the watchdog | nothing: no network, file or log wait |
| telemetry | 8 | samples from the control thread through a bounded queue | send to the TCP peer; drop and count when the queue is full | network |
| storage | 9 | a changed set point | write the control record; retry with a growing delay | file |
| time synchronisation | 10 | `CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S` | SNTP query and policy, as today | network |
| web session, web management, security event drain | 11 | requests | Crux workers, as today | storage, crypto |
| HTTP server | lowest preemptive | connections | TLS handshake and requests (Zephyr's own thread) | network |
| log processing | 14 | log records | deferred logging to the UART | UART |

The control thread feeds the watchdog once per cycle that ran on time; a stalled control thread therefore ends in the watchdog's reset.
Network loss is a normal state of a controller and does not stop the feed.
Stack sizes are starting values until a board run reads them (`CONFIG_INIT_STACKS`, `CONFIG_THREAD_STACK_INFO`, already in `app/conf/management.conf`).

## 6. Set point persistence

The configuration service keeps accepted values in memory; saving goes through a Crux Configuration provider.
Crux's Settings File provider refuses FatFs, because its rename does not replace a file atomically across a power cut (`zephyr/Kconfig:453-468`), so the microSD image has no save provider and a save ends as not supported.

The image therefore keeps the control record itself (workaround until a provider exists on the chosen file system):

- two record files, written alternately, each with a sequence number and a CRC; the newest valid one wins at start (the same two-slot idea as the credential store's two roots, `app/src/storage_port.h:62-63`);
- `crux_file` `CREATE_REPLACE` truncates in place and promises no rollback (`components/file/include/crux/file.h:58-63`), which is why one slot alone is not enough;
- the storage thread writes after an accepted change; the control thread never writes.

The save route of management then reports the record's state through a status item, until Crux offers a save provider for this medium (decision D3).

## 7. Failure behaviour

| Condition | Control loop | Other parts | Visible as |
|---|---|---|---|
| Control cycle late beyond the watchdog timeout | stops being fed | hardware reset by the watchdog; the next boot reports cause WATCHDOG | reset cause line, status item |
| Simulated input outside its plausible range | output to the safe value until the input is plausible again | none | log line, status item |
| No card, card does not mount, or no layout | runs with the defaults; set point changes stay in memory | management stays off, because Access cannot be reopened after an unusable store (`components/access/include/crux/access.h:91-94`) | log lines |
| Record write fails | keeps the accepted value | storage thread retries with a growing delay | status item "unsaved" |
| Link down or peer absent | unaffected | telemetry drops and counts; SNTP rounds fail; management unreachable | log lines, Netif status item |
| Time not synchronised | unaffected (monotonic time only) | logs and records use the monotonic time; the certificate keeps the module's default validity start (`app/compose/management_start.c:152-171`) | Time status item |
| Management start refused at any step | unaffected; set point from the record | no change until the next start | log line naming the step |
| Set point out of range | old value kept | the service answers rejected (`CRUX_CONFIG_SERVICE_ERR_REJECTED`) | answer to the client |

## 8. Memory budget

### RT1060-EVKB (`mimxrt1060_evk@B/mimxrt1062/qspi`)

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

Planning figure for the integrated image, derived from that table as an upper bound and not a build result: `management`, minus the 524,288-byte RAM disk (`app/boards/management.overlay:24`), plus the whole deltas of `file` over `workload`, `system` over `workload` and `sntp` over `net`.
That gives at most about 327 KB of FLASH and 755 KB of RAM, before the control code and the telemetry and storage stacks (about 20 KB of RAM).
Both stay below 5 percent of their regions, inside the 25 percent free margin of `budgets/limits.json`.
The RAM disk form of decision D2 adds the 512 KiB disk back, about 1.3 MB of RAM.

### MIMXRT1180-EVK

| Target | Code | Data | Ethernet | Fit |
|---|---|---|---|---|
| `mimxrt1180_evk/mimxrt1189/cm33` | XIP from 16 MB QSPI NOR (`w25q128jw`) | 8 MB HyperRAM in XIP mode, `zephyr,sram` | NETC (`enetc_psi0`, PHY at address 3), `netif:eth` in the board file | fits the planning figure with a wide margin |
| `mimxrt1180_evk/mimxrt1189/cm7` | ITCM, 256 KB by default; flash or HyperRAM through board overlays | DTCM, 256 KB | not in the board's supported list | does not fit by default; it is a second image that the CM33 starts (dual-core, sysbuild) |

The figures come from the Zephyr board files at v4.4.2 (`boards/nxp/mimxrt1180_evk/`: the two `.dts` and `.yaml` files, `cm7_flash_boot.overlay`, `cm7_code_hyperram.overlay` and `doc/index.rst`).
The CM33 runs at 240 MHz and the CM7 at 792 MHz in those files, so key generation and TLS handshakes take longer on the CM33 than on the RT1060; C3 matters more there.
The recommendation is the CM33 (decision D9).

At the pinned Crux, these refuse an RT1180 image, by reading the source:

| Where | What refuses | Capabilities blocked |
|---|---|---|
| `components/logging/ports/zephyr/logging_binding.c:12-31` | build assertion "Crux Logging unsupported UART resource": only RT1062 LPUARTs and the `native_sim` UART are accepted; on another SoC the console may not share the logging UART (`:52`) | `workload` and every configuration on it |
| `components/system/ports/zephyr/system_binding.c` (the final `#error`) | "Crux System unsupported SoC or watchdog resource": only the RT1062 WDOG1 at `0x400b8000`; the RT1180 has `nxp,rtwdog` instances | `system`, `management` |
| `zephyr/Kconfig:307-348`, `components/file/ports/zephyr/file_native.c:27-36` | every target File provider depends on `SOC_MIMXRT1062`; the board-neutral Reliance Edge provider links GPL source and is for tests only | `file`, `management` |
| `app/management/entropy.cmake:16-20` (product) | needs `CONFIG_ENTROPY_MCUX_TRNG`; the RT1180 devicetree at v4.4.2 has no entropy node (the `nxp,ele-trng` binding exists, used on another SoC family) | `management` |
| `app/boards/net.overlay`, `system.overlay`, `management.overlay` (product) | name RT1060 nodes (`enet_mac`, `green_led`, `phy`, `wdog0`) | `net`, `system`, `management` |
| `app/conf/management.conf` (product) | `CONFIG_ETH_NXP_ENET_RX_BUFFERS` belongs to the RT1060 Ethernet driver | `management` |

Crux Time, Sockets and Netif have no SoC gate at the pinned commit, so `base` is the only configuration expected to build for the RT1180 there.

## 9. Variants

Rule: one application, `app/`, and one Kconfig option per capability.
A variant is a configuration fragment or an overlay of that application, chosen only where memory or purpose forces it (standard: Zephyr `EXTRA_CONF_FILE`, `EXTRA_DTC_OVERLAY_FILE` and `FILE_SUFFIX`; the application-and-samples split of the nRF Connect SDK).
A separate application exists only for a different purpose, such as a provisioning or factory test image or a bootloader (standard: Zephyr sysbuild builds several images).

| Variant | Why | Mechanism |
|---|---|---|
| `controller` (the integrated image) | the product | `prj.conf` plus one fragment, board files from `app/boards/<board>.conf` and `<board>.overlay`, which Zephyr picks by board name |
| RAM disk form | CI runners and benches without a card | one extra fragment and overlay (decision D2) |
| debug form | stack and thread analysis on a board | `FILE_SUFFIX=debug` or one extra fragment |
| per board | different nodes and drivers | the board's own `.conf` and `.overlay` only; no board name in `app/src` |

Board-specific nodes that today sit in capability overlays (Ethernet, watchdog alias, fstab) move into the board overlay, because the integrated image always has them.
This fits the board-neutral build branch (`feat/board-neutral-build`): `scripts/build-board.sh` takes `--board` and builds in `build/<board folder>/<configuration>`, so `controller` becomes one more entry of its configuration list, and the branch's own note that a second board needs per-board fragments and overlays is met by the board files above.

## 10. What stays a CI test configuration

- The `native_sim` scenarios per capability (`tests/native_sim/*`, `tests/native_sim_mbed/management`) stay: they test one capability against the real Crux provider, which the integrated image cannot isolate.
- The host tests stay and gain the control loop.
- `base` stays as the smallest board build, the first one a new board must pass.
- The board builds of `workload`, `net`, `file`, `system`, `sntp` and `management` are replaced by the integrated image, unless decision D8 keeps some for build isolation.
- `budgets/limits.json` gains a `controller` row; changing it is a reviewed change ([CONTRIBUTING](../../CONTRIBUTING.md)).

## 11. Acceptance criteria

1. One configuration, `controller`, enables every capability; `app/Kconfig` has no exclusion between capabilities.
2. The RT1060-EVKB build passes in CI with `-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`, and its `Budget` row keeps at least 25 percent free in every region.
3. Host tests of the plant model and the controller: a set point step settles within a stated number of cycles; the output stays in 0 to 100 percent; anti-windup holds; a set point change does not jump the output; an out-of-range set point is refused.
4. A `native_sim` scenario of the start order: the reset cause is read once, the status service receives the captured copy, the flags are cleared after the capture, and the watchdog is armed after the management start.
5. A `native_sim` scenario changes the set point through the configuration service, sees it applied at the next cycle, restarts on a file-backed disk and finds it again; a cut between the two record slots leaves the older value.
6. A `native_sim` scenario per row of section 7: the control loop keeps its period, and the log or the status item shows the condition.
7. A stalled control thread ends in a reset on the simulated watchdog of `native_sim` (`CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG`).
8. `scripts/check_boundary.py` passes with no new allow-list entry, or the entry is a separate reviewed change.
9. An RT1180 CM33 build of `base` passes, and the build of `controller` stops at a refusal of section 8 and at nothing else.
10. The architecture, capabilities and roadmap pages describe the integrated image; no page claims a board run until one is approved and recorded.

## 12. Open decisions for the owner

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | The control example: a simulated heated tank with a PI controller | Adopt | Small, testable on the host, shows a real control loop |
| D2 | Persistent medium on the RT1060-EVKB | microSD for the integrated image; the RAM disk only as a CI form | Keys, accounts and the set point must survive a reset |
| D3 | Set point persistence | The product's two-slot record through Crux File (workaround), and a Crux issue for a save provider on a power-cut-safe file system | Crux's Settings provider refuses FatFs |
| D4 | When to arm the watchdog | After the start sequence | One activation per boot; a long start must not cost a reset |
| D5 | Owner of the reset cause | The health code reads once and passes the copy to management | Crux's documented contract |
| D6 | Missing directories on a card | Create the three directories when missing, never format | Creating a directory destroys nothing; formatting would |
| D7 | The first account | A serial console on a second UART through Crux's console, as a separate change; tests create the account through the Access API | Logging owns the first UART, and management is unusable without an account |
| D8 | CI matrix | Integrated image plus `base` on the board; all `native_sim` scenarios kept | Fewer board builds, the same capability tests |
| D9 | RT1180 core | CM33 | Ethernet and the full image fit it; the CM7 needs a second image |
| D10 | RT1180 refusals in Crux | Raise one Crux issue that lists the four Crux refusals of section 8; no product workaround | They are platform gaps, and this repository exists to report them |
| D11 | The TCP peer exchange | Keep it as telemetry on its own thread | Keeps the `net` evidence and takes network waits out of the control path |

## Sources

- Zephyr v4.4.2 (`dccb0959`): `doc/develop/application/index.rst` (`EXTRA_CONF_FILE`, `FILE_SUFFIX`, board files), `doc/build/sysbuild/index.rst`, `doc/develop/test/twister.rst` (`extra_args`), `doc/services/task_wdt/index.rst`, `doc/hardware/peripherals/hwinfo.rst`, `boards/nxp/mimxrt1180_evk/`.
- Crux at `bd9efbc7`: `zephyr/Kconfig`, `components/file/ports/zephyr/CMakeLists.txt`, `components/system/`, `components/logging/ports/zephyr/logging_binding.c`, `components/config_service/include/crux/config_service.h`, `components/mgmt_status/include/crux/management_status.h`, `components/access/include/crux/access.h`, `tests/zephyr/management_rt1060_compile/bench_guard.cmake`, `templates/product/README.md`.
- The nRF Connect SDK documentation on applications and samples: an application is a complete reference design built from configuration variants, a sample shows one feature.
- Rate-monotonic priority assignment: C. L. Liu and J. W. Layland, "Scheduling Algorithms for Multiprogramming in a Hard-Real-Time Environment", Journal of the ACM, 1973.
- IEC 61131-3 for the PI/PID function block of programmable controllers.
