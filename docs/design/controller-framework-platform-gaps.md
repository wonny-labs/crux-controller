# Controller framework: platform gaps

This page lists the constraints that Crux and Zephyr put on the [controller framework](controller-framework.md) at the Crux revision that [`west.yml`](../../west.yml) pins, and the Crux change that lifts each one.
It is the appendix of the [specification](controller-framework-spec.md), which refers to the constraints as C1 to C13.
A statement holds at the pin unless it carries a Crux status word of [specification section 1](controller-framework-spec.md#1-scope-and-conventions).
Priority 1 is the most urgent Crux change; the [interim states](controller-framework-spec.md#85-interim-states) say which states each milestone accepts.
When the pin moves, each constraint is checked again, and a constraint whose Crux change is at the pin leaves this page.

## Storage and configuration

### C1. One storage provider per image

- Evidence: Crux allows one File provider; the RAM disk provider depends on `!DISK_DRIVER_SDMMC` (`zephyr/Kconfig`), and its CMake stops the build when another File selection is on (`components/file/ports/zephyr/CMakeLists.txt`).
- Effect: one provider serves the application data, the credential store and the settings file; the RAM disk is a CI form for runners without a medium.
- Crux change: none.

### C4. Configuration saving needs a power-cut-safe file system

- Evidence: Crux's Settings File provider of Configuration exists in two selections (`zephyr/Kconfig:438-470`):
  - `CRUX_CONFIGURATION_SETTINGS_FILE` needs Reliance Edge (west group `crux-reliance`, source under GPLv2, test images only);
  - `CRUX_CONFIGURATION_SETTINGS_FILE_ANY_FS` refuses, at CMake and in its source, any image that has `FAT_FILESYSTEM_ELM`, because a FatFs rename removes the destination first and can lose the settings file at a power cut.
- Evidence: Configuration on LittleFS over a block device runs on `native_sim` in Crux (`tests/native/configuration_settings_littlefs`), and Crux's File core runs over LittleFS on a flash simulator partition (`tests/native/file_littlefs`); Crux has no selectable LittleFS File provider for a target, at the pin or on Crux `main`.
- Effect: an image with the microSD FatFs provider has no save provider, and an image cannot keep FatFs for files and another file system for settings.
- Crux change: a LittleFS File provider with Configuration saving on it. State: planned in Crux. Priority 1.
- Interim state: the microSD FatFs provider serves files and the credential store, Configuration has no save provider, and the status service reports that parameters are not persistent.
- Replacement criterion: criteria 12 and 24 are replaced by: a save answers not supported, and the status service says that parameters are not persistent.

### C5. Settings File sources under a Crux `tests/` path

- Evidence: both Settings File selections build corrected copies of Zephyr's Settings File backend from Crux's `tests/native/configuration_settings_file`, so a product build reaches a file under Crux's `tests/` (`zephyr/CMakeLists.txt:158-170`).
- Crux change: move those sources out of `tests/`. State: planned in Crux. Priority 1.
- Interim state: the product build reaches Crux's `tests/` for the Settings File sources. Replacement criterion: none.

### C9. Access and an unusable store

- Evidence: a credential store that reports itself unusable cannot reopen Crux Access in the same boot (`components/access/include/crux/access.h:91-93`), and Access offers no erase operation.
- Crux change: an Access erase operation. State: planned in Crux. Priority 2.
- Interim state: factory reset only by device preparation. Replacement criterion: none.

## Supervision and reset

### C2. One reset-cause owner

- Evidence: Crux grants one permission to clear the reset cause; the boot diagnostic owner reads once and passes what it captured (`components/system/include/crux/system.h:80-88`; `components/mgmt_status/include/crux/management_status.h:89-90`, `:103`).
- Effect: the framework's health service is the owner, and the status service and the boot counter receive the copy.
- Crux change: none.

### C3. One watchdog activation per boot

- Evidence: Crux System starts "the boot's single watchdog activation" with one timeout (`components/system/include/crux/system.h:100-108`) and offers no auto-arm, stop or reconfiguration (`zephyr/Kconfig:274-275`); the supported timeout range is provider-specific.
- Effect: startup and runtime supervision share one timeout T, which is chosen once ([specification section 4.1](controller-framework-spec.md#41-startup-steps)).
- Crux change: none; the framework solves startup supervision with the single Crux watchdog token, unless a board measurement shows that one timeout cannot cover both startup and runtime.

### C8. Crux service threads and supervision

- Evidence: Crux service threads that block without a timeout cannot be supervised by progress.
- Crux change: a supervision hook in Crux service threads, for example a poll-with-timeout loop that reports progress. State: planned in Crux. Priority 1.
- Interim state: Crux service threads are supervised indirectly ([specification section 4.3](controller-framework-spec.md#43-runtime-supervision)). Replacement criterion: none.

### C11. Simulated watchdog on `native_sim`

- Evidence: the simulated watchdog of `native_sim` (`CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG`) restarts the process after a missed feed, which then reads the reset cause SOFTWARE, never WATCHDOG (`zephyr/Kconfig:277-288`).
- Effect: `native_sim` shows only part of the boot counter's watchdog path and never the WATCHDOG cause; host tests and a board show the case with that cause.
- Crux change: none.

## Console and logging

### C6. Console and logging UART

Zephyr's usual way to share one UART is the shell's log backend (`CONFIG_SHELL_LOG_BACKEND`), which queues log messages and multiplexes them with the shell's output.
Crux refuses every form of it, at the pin and on Crux `main`:

| Where | What it refuses |
|---|---|
| `components/logging/ports/zephyr/logging_binding.c:58-60` | A build with `CONFIG_CRUX_SERIAL` whose `crux-serial0` UART is the logging UART ("Crux Logging conflicts with Crux Serial") |
| `components/logging/ports/zephyr/logging_binding.c:55-57` | The Zephyr shell's serial backend on the logging UART |
| `components/logging/ports/zephyr/logging_binding.c:41-50` | The Zephyr console on the logging UART, except with logging-only routing (no shell, no console input) |
| `components/logging/ports/zephyr/CMakeLists.txt:18-24` | `CONFIG_SHELL_LOG_BACKEND` and every log backend other than the UART backend |
| `components/logging/ports/zephyr/logging_binding.c:12-18` | On the RT1060-EVK board, any logging UART other than LPUART1, so the console cannot take LPUART1 and move logging elsewhere |
| `components/cli/ports/zephyr/include/crux/cli_zephyr.h:26-27` | Any Zephyr console, log backend, shell or other Crux Serial user on the console's `crux-serial0` UART |
| `zephyr/Kconfig:184`, `:193` | More than "one explicitly dedicated UART" for Crux Serial |
| `zephyr/Kconfig:222-224` | A Zephyr shell in an image with the Crux command line, unless the image is marked as a development image |

- Effect: the console needs a second UART; on the RT1060-EVKB that is LPUART3 on header pins, connected with a USB-serial adapter and named by the alias.
- Crux change: a build option that selects a separate console UART or one UART shared by the console and Crux Logging. State: planned in Crux. Priority 2.
- Interim state: the serial console uses a second UART (LPUART3 on header pins, with a USB-serial adapter). Replacement criterion: none.

## Security profiles

### C7. SSH and TLS profiles

- Evidence: `CONFIG_CRUX_ACCESS` stops the build without `CONFIG_PSA_CRYPTO_PROVIDER_MBEDTLS` (`zephyr/CMakeLists.txt:197-201`; `zephyr/Kconfig:632-637`; Crux `docs/management-in-a-product.md:154-155`).
  So Crux Access, and every management service that depends on it (serial console, configuration service, status service, web sessions, web management, TLS certificate, reboot, File service and network settings), needs the Mbed profile of PSA Crypto, and an image on the Wolf profile, which SSH needs, has none of them through the module.
- Evidence: Crux SSH has a private provider interface only, with no public header and no `crux::` target, so a composition outside Crux needs a Crux composition interface.
- Evidence: `CONFIG_CRUX_SSH` needs the Wolf profile, and Crux refuses it together with the Mbed TLS module, because two TLS stacks are not a supported image (`zephyr/CMakeLists.txt:285-290`).
- Evidence: the Wolf profile needs a Zephyr patch for its TLS socket backend, whose application in a product is open in Crux (Crux `docs/management-in-a-product.md:58`).
- Evidence: wolfSSL and wolfSSH are available under GPL-3.0-or-later or a commercial licence ([dependencies](../dependencies.md), group `crux-secure-management`), and this repository is Apache-2.0.
- Crux change: Crux Access on the Wolf profile, needed for the Wolf HTTPS profile and for SSH. State: Crux change needed. Priority 2.
- Crux change: an SSH composition interface. State: deferred by Crux. Priority 3.
- Crux change: two TLS stacks in one image. State: deferred by Crux.
- Interim state: no SSH and no Wolf profile. Replacement criterion: none.

## Update

### C10. Image state

- Evidence: Crux's image state contract (`components/image_state`) has a host provider only, with no Zephyr or MCUboot provider.
- Crux change: an image state provider for the update path ([crux-pilot#297](https://github.com/wonny-labs/crux-pilot/issues/297)). State: Crux change needed. Priority 2.
- Interim state: the images are prepared for MCUboot, with no health-gated confirmation. Replacement criterion: criterion 25 stays a host test.

## Boards and operating systems

### C12. SoC gates

These refuse an SoC other than the RT1062, by reading the source:

| Where | What refuses | Services blocked |
|---|---|---|
| `components/logging/ports/zephyr/logging_binding.c:12-31` | "Crux Logging unsupported UART resource": only RT1062 LPUARTs and the `native_sim` UART | Logging, and every configuration on it |
| `components/system/ports/zephyr/system_binding.c` (the final `#error`) | "Crux System unsupported SoC or watchdog resource": only the RT1062 WDOG1 | Health supervision, device management |
| `zephyr/Kconfig:307-348` | Every target File provider of FatFs depends on `SOC_MIMXRT1062`; the board-neutral Reliance Edge provider links source under GPLv2 | Storage, device management |
| `app/management/entropy.cmake:16-20` (this repository) | Needs `CONFIG_ENTROPY_MCUX_TRNG` | Device management |
| `app/boards/*.overlay`, `app/conf/management.conf` (this repository) | Name RT1060 nodes and RT1060 Ethernet driver options | Network, health supervision, device management |

- Crux change: board-neutral gates. State: Crux change needed when a second board enters the scope (decision D9). Priority: deferred.

### C13. Linux providers

- Evidence: Crux has Linux providers for File, Logging, Netif, Serial, Sync, System, Thread, Time and Interrupt (`components/*/ports/linux`), and they are test providers until a Linux product is defined (Crux ADR-0003 R5).
- Evidence: Access, command line, Configuration, configuration service, management status, Web, Sockets, TLS certificate, credential store, Reboot, security events, SSH, File service and network settings have Zephyr providers only; the PSA ports of Access, credential store, TLS certificate and Web are crypto ports, not OS providers.
- Crux change: Linux providers for those components, which Crux designs when its first Linux product is defined (Crux ADR-0003 R5).

## Other Crux changes

- A web adapter for the File service, which HTTPS file transfer needs ([specification section 6.2](controller-framework-spec.md#62-security-items)). [crux-pilot#188](https://github.com/wonny-labs/crux-pilot/issues/188). State: Crux change needed. Priority 3.
