# Controller framework: platform gaps

This page lists the constraints that Crux and Zephyr put on the [controller framework](controller-framework.md) at the Crux revision that [`west.yml`](../../west.yml) pins, the Crux change that lifts each one, and the Crux interface behind each framework service.
It is the appendix of the [specification](controller-framework-spec.md), which refers to the constraints as C1 to C19.
A statement holds at the pin unless it carries a Crux status word of [specification section 1](controller-framework-spec.md#1-scope-and-conventions).
Priority 1 is the most urgent Crux change, and the delivery dependency names the first delivery stage or milestone that needs the change; the two are independent.
The [interim states](controller-framework-spec.md#85-interim-states) say which states each milestone accepts.
When the pin moves, each gap is checked again; a gap whose Crux change is at the pin takes the state Resolved with the Crux revision, keeps its number, evidence and references, and moves its interim state and replacement criterion out of force.

## Summary

| Gap | Crux change | State | Priority | Delivery dependency |
|---|---|---|---|---|
| [C1](#c1-one-storage-provider-per-image) | None | — | — | None |
| [C2](#c2-one-reset-cause-owner) | None | — | — | None |
| [C3](#c3-one-watchdog-activation-per-boot) | None | — | — | None |
| [C4](#c4-configuration-saving-needs-a-power-cut-safe-file-system) | A LittleFS File provider with Configuration saving on it | Crux `main` | 1 | Delivery stage 4 (criteria 12 and 24); Framework Complete |
| [C5](#c5-settings-file-sources-under-a-crux-tests-path) | Settings File sources outside Crux's `tests/` | Crux `main` | 1 | Delivery stage 4 (criterion 32); Framework Complete |
| [C6](#c6-console-and-logging-uart) | A shared console and Logging UART | Crux `main` | 2 | None; a build option |
| [C7](#c7-ssh-and-tls-profiles) | Access on the Wolf profile; an SSH composition interface; two TLS stacks | Crux change needed; deferred by Crux; deferred by Crux | 2; 3; — | Product Ready of a product that selects SSH or the Wolf profile |
| [C8](#c8-crux-service-threads-and-supervision) | A progress hook in Crux service threads | Crux `main` | 1 | Delivery stage 4 (criterion 33); Framework Complete |
| [C9](#c9-access-and-an-unusable-store) | A credential store erase; an erase that keeps the device identity; a TLS certificate start setting that requires an existing device identity | Crux `main`; Planned in Crux; Planned in Crux | 2 | Delivery stage 4 (criterion 42) for the erase; delivery stage 5 (PR4) for keeping the device identity and for requiring it at boot |
| [C10](#c10-image-state) | An image state provider for the update path | Crux change needed | 2 | Delivery stage 5 (PR3) |
| [C11](#c11-simulated-watchdog-on-native_sim) | None | — | — | None |
| [C12](#c12-soc-gates) | Board-neutral driver gates | Crux change needed when a second board enters the scope (D9) | Deferred | A second board |
| [C13](#c13-linux-providers) | Linux providers | Designed with Crux's first Linux product | — | Delivery stage 6 |
| [C14](#c14-operator-reset-marker-and-crux-reboot) | None | — | — | None |
| [C15](#c15-size-limit-of-the-application-data-root) | A size limit per File root | Planned in Crux | 1 | Delivery stage 4 (criterion 24); Framework Complete |
| [C16](#c16-security-counter) | A security counter in the image state contract and its storage | Crux change needed | 2 | Delivery stage 5 (PR7) |
| [C17](#c17-security-event-persistence) | A composition-level reader of security events | Crux change needed | 2 | Delivery stage 4 (criterion 44); Framework Complete |
| [C18](#c18-request-rate-limit) | A request rate limit in Crux Web | Crux change needed | 3 | Delivery stage 4 (criterion 45); Framework Complete |
| [C19](#c19-credential-store-at-rest) | A hardware-bound key basis for the credential store | Crux change needed when a product's record (S9) asks for it | 3 | Product Ready of that product |
| [Web adapter](#other-crux-changes) | A web adapter for the File service | Crux change needed | 3 | Product Ready of a product that offers HTTPS file transfer |

The pin is Crux `62ed69f1`; the Crux `main` changes above are at `05a50475` and not at the pin.

## Service mapping

| Service | Crux interface | Use in the framework | At the pin | Target |
|---|---|---|---|---|
| Web management | Crux Access, web server on the selected TLS profile (`<crux/web_zephyr.h>`), configuration and status services, a packaged page, the reboot routes (`CONFIG_CRUX_REBOOT`) | HTTPS web UI: status, parameters, accounts, reboot | Mbed TLS profile only | Also the Wolf profile ([C7](#c7-ssh-and-tls-profiles)) |
| Serial command line | Crux console, `crux_cli_serial_start()` in `<crux/cli_zephyr.h>` | Command line with first-account setup (`!setup`); Access closes provisioning after the first save | On a second UART ([C6](#c6-console-and-logging-uart)) | Separate or shared UART as a build option |
| SSH command line and SFTP | Crux SSH and Crux File service | Command line and file transfer over SSH | None (C7) | A build option with the Wolf profile and a Crux SSH composition interface |
| Health supervision | Crux System (reset cause, one hardware watchdog activation, `crux_system_reset()`), Zephyr task watchdog | [Specification section 4](controller-framework-spec.md#4-operating-model) | Crux service threads supervised indirectly ([C8](#c8-crux-service-threads-and-supervision)) | Every Crux service thread supervised by progress |
| Time | Crux Time (monotonic clock, time authority), Zephyr SNTP | Wall time for logs, records and status; every timing decision uses the monotonic clock | Available | Unchanged |
| Logging | Crux Logging (UART logger) | Framework log modules; the application uses Crux Logging directly | Available | Unchanged |
| Configuration | Crux configuration service over the Crux Configuration Settings File provider | Framework and application parameters, shown in device management | Not persistent ([C4](#c4-configuration-saving-needs-a-power-cut-safe-file-system)) | Saved on LittleFS |
| Network | Zephyr network configuration library, Crux Netif, Crux Sockets profile | Interface up before `main()`; link state for health and status | Available | Unchanged |
| Storage | Crux File, one provider, one mount ([C1](#c1-one-storage-provider-per-image)) | Application data root, credential store roots, settings file | microSD FatFs provider (C4) | LittleFS on the reference board's microSD card |
| Factory reset | Crux credential store erase (`<crux/credential_store_zephyr.h>`) | Erase of accounts, then the settings file, then a reset ([specification section 5.3](controller-framework-spec.md#53-storage-or-access-failure-and-factory-reset-d15)) | Device preparation only ([C9](#c9-access-and-an-unusable-store)) | An erase that keeps the device identity |
| Update | Crux image state contract | Health verdict for the confirmation of a test image | Images prepared for MCUboot, no confirmation ([C10](#c10-image-state)) | Health-gated confirmation with a security counter ([C16](#c16-security-counter)) |
| Security events | Crux security events (`<crux/security_event.h>`) | The event list of [specification section 6.2](controller-framework-spec.md#62-security-items), with framework identifiers from 0x8000 | A RAM ring drained to the log ([C17](#c17-security-event-persistence)) | Persisted, with an opt-out |

## Access controls at the pin

These Crux facts back [specification section 6.2](controller-framework-spec.md#62-security-items); Crux Access is the same on Crux `main` at `06813519`.

| Control | Crux at the pin | Source |
|---|---|---|
| Failed logins | Delay buckets per source and per name: 5 free attempts, then a window that doubles from 1 s to 60 s, cleared after 15 minutes without a failure; a success clears the name bucket; no account lockout | `docs/access-contract.md` "Bounds"; `components/access/src/access_delay.c` |
| Login events | `access.login_failed`, `access.delayed`, `access.permission_denied`, account and provisioning events | `components/security_event/src/security_event_ids.inc` |
| Roles | Named roles with exact permission lists from the product policy, with no wildcards or inheritance; at least one role holds `access.manage`; the last enabled administrator cannot be removed | `components/access/include/crux/access.h` |
| Sessions | Idle and absolute limits from the product policy; 8 sessions with slot 0 reserved for serial, 3 per account, as compile-time defaults | `access.h`; `docs/access-contract.md` "Bounds" |
| Password rule | 12 to 128 bytes by default, or a product function; a PBKDF2-HMAC-SHA256 verifier with a default of 10,000 iterations, which the product measures and sets | `access.h`; `docs/access-contract.md` "Bounds" |
| Web route access | Each route declares an access class, enforced before the handler; `@public` is reserved for the login, its attempt result and static sign-in assets; the session module owns the CSRF and Origin rules | `components/web/include/crux/web.h:32-35`, `:74-80` |
| Request limits | A body limit per route up to `CRUX_WEB_BODY_BUFFER`, with 413 above it; a request deadline; `CONFIG_HTTP_SERVER_MAX_CLIENTS` and `CONFIG_CRUX_WEB_BACKLOG`; no request rate limit ([C18](#c18-request-rate-limit)) | `web.h`; `components/web/ports/zephyr/web_http_server.c:97-130` |
| TLS policy | The listener asks for TLS 1.3 alone with `TLS_AES_128_GCM_SHA256`, on both TLS profiles | `web_http_server.c:102-121` |

## Storage and configuration

### C1. One storage provider per image

- Evidence: Crux allows one File provider; the RAM disk provider depends on `!DISK_DRIVER_SDMMC` (`zephyr/Kconfig`), and its CMake stops the build when another File selection is on (`components/file/ports/zephyr/CMakeLists.txt`).
- Effect: one provider serves the application data, the credential store and the settings file; the RAM disk is a CI form for runners without a medium.
- Crux change: none.

### C4. Configuration saving needs a power-cut-safe file system

- Evidence: Crux's Settings File provider of Configuration exists in two selections (`zephyr/Kconfig:471-503`):
  - `CRUX_CONFIGURATION_SETTINGS_FILE` needs Reliance Edge (west group `crux-reliance`, source under GPLv2, test images only);
  - `CRUX_CONFIGURATION_SETTINGS_FILE_ANY_FS` refuses, at CMake and in its source, any image that has `FAT_FILESYSTEM_ELM`, because a FatFs rename removes the destination first and can lose the settings file at a power cut.
- Evidence: Crux has no selectable LittleFS File provider for a target at the pin.
- Crux `main`: `CRUX_FILE_LITTLEFS_BLK_DEV` is a File provider on LittleFS over an SD card or eMMC disk on any board (`zephyr/Kconfig:461-486`); it mounts and formats nothing, so the composition mounts the volume, and `CRUX_CONFIGURATION_SETTINGS_FILE_ANY_FS` saves Configuration on it, shown on `native_sim` (`zephyr/Kconfig:571-587`).
- Effect at the pin: an image with the microSD FatFs provider has no save provider, and an image cannot keep FatFs for files and another file system for settings.
- Crux change: a LittleFS File provider with Configuration saving on it. State: Crux `main`. Priority 1.
- Interim state: the microSD FatFs provider serves files and the credential store, Configuration has no save provider, and the status service reports that parameters are not persistent.
- Replacement criterion: criteria 12 and 24 are replaced by: a save answers not supported, and the status service says that parameters are not persistent.

### C5. Settings File sources under a Crux `tests/` path

- Evidence: both Settings File selections build corrected copies of Zephyr's Settings File backend from Crux's `tests/native/configuration_settings_file`, so a product build reaches a file under Crux's `tests/` (`zephyr/CMakeLists.txt:158-170`).
- Crux `main`: the module prepares the corrected copies with `zephyr/settings_file.cmake` and `zephyr/prepare_settings_file.py` from `patches/zephyr/settings-file-error.patch` and `patches/zephyr/settings-store-error.patch` (`zephyr/CMakeLists.txt:161-176`; `patches/zephyr/README.md`).
- Crux change: move those sources out of `tests/`. State: Crux `main`. Priority 1.
- Interim state: the product build reaches Crux's `tests/` for the Settings File sources. Replacement criterion: none.
- Acceptance: criterion 32, at a pin that contains the change.

### C9. Access and an unusable store

- Evidence: a credential store that reports itself unusable cannot reopen Crux Access in the same boot (`components/access/include/crux/access.h:91-93`), and Crux offers no erase operation at the pin.
- Crux `main`: `crux_credential_erase()` (`components/credential/ports/zephyr/include/crux/credential_store_zephyr.h`, target `crux::credential_store_zephyr`) is a composition interface that erases the credential store for a factory reset; it checks no permission, so the caller's trigger is the protection, the store is unusable until the next reset, and the settings file and files are the product's to remove.
- Evidence (Crux `main`): the erase removes the accounts, the TLS key and certificate and the SSH host key, and Crux makes the device keys again at the next start, while [specification section 5.3](controller-framework-spec.md#53-storage-or-access-failure-and-factory-reset-d15) keeps the device identity and section 5.5 puts a prepared device without its identity into safe mode.
- Crux change: an erase for a factory reset. State: Crux `main`. Priority 2.
- Crux change: an erase that keeps the TLS key and certificate. State: Planned in Crux. Priority 2.
- Evidence: `crux_tls_certificate_start()` ensures the device's TLS key, which makes a key when none is stored, makes and stores a self-signed certificate when none is stored, and then returns `CRUX_TLS_CERTIFICATE_GENERATED`, with no option that refuses instead (`components/tls_certificate/include/crux/tls_certificate_start.h:72-80`, `components/tls_certificate/src/tls_certificate.c:291-294` and `:361-374`, at the pin and on Crux `main`).
- Evidence: Crux reads the credential store records only through its private adapter (`components/credential/adapter/crux_credential_adapter.h`), so the framework cannot check for the device identity before that call.
- Effect: a boot of a prepared volume without the device identity makes a new identity instead of entering the safe mode of [specification section 5.5](controller-framework-spec.md#55-device-preparation-d11).
- Crux change: a setting of the TLS certificate start that refuses a missing key or certificate and writes nothing to the credential store. State: Planned in Crux. Priority 2.
- Interim state: until the credential store erase is at the pin, factory reset is only by device preparation. Replacement criterion: none; criterion 42 needs the erase.
- Interim state: with the erase at the pin and no identity-keeping erase, a factory reset also removes the device identity, and recovery of the identity is device preparation ([specification section 5.5](controller-framework-spec.md#55-device-preparation-d11)). Replacement criterion: none; PR4 needs the identity-keeping erase.
- Interim state: until the setting is at the pin, Crux makes a missing device identity in step 10 of every build, and the framework reports a certificate made at boot instead of entering safe mode (specification section 5.5).
- Replacement criterion: none; PR4 needs the setting, and criterion 42 shows the report while this interim state applies.

### C15. Size limit of the application data root

- Evidence: Crux File reports a full volume as `CRUX_FILE_ERR_NO_SPACE` and offers no size limit per root, at the pin or on Crux `main` (Crux `docs/file-contract.md`); with one provider and one mount (C1), the application data, the credential store and the settings file share one volume.
- Effect: the application calls Crux File directly (specification section 3.2), so the framework cannot enforce the size limit of [specification section 5.4](controller-framework-spec.md#54-storage-and-configuration) without a Crux mechanism; the framework owns the rule, and the product sets the limit.
- Crux change: a size limit per File root. State: Planned in Crux. Priority 1.
- Interim state: the application data root has no size limit, and a full volume can stop a configuration save. Replacement criterion: none; criterion 24 needs the change.

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

- Evidence: Crux service threads that block without a timeout cannot be supervised by progress at the pin.
- Crux `main`: `crux_service_progress_register()` (`components/service_priority/ports/zephyr/include/crux/service_priority_zephyr.h`, target `crux::service_priority_zephyr`) registers one function that each started Crux service thread calls once per pass of its loop, at least about once a second when idle: the security event drain, the reboot worker, the network settings worker, the web session and web management workers and the console.
- Evidence (Crux `main`): the HTTP server thread and the SSH threads are not Crux service threads and do not report, so they stay indirectly supervised with Zephyr's network and logging threads.
- Crux change: a supervision hook in Crux service threads. State: Crux `main`. Priority 1.
- Interim state: Crux service threads are supervised indirectly ([specification section 4.3](controller-framework-spec.md#43-runtime-supervision)). Replacement criterion: none.
- Acceptance: criterion 33, at a pin that contains the change.

### C11. Simulated watchdog on `native_sim`

- Evidence: the simulated watchdog of `native_sim` (`CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG`) restarts the process after a missed feed, which then reads the reset cause SOFTWARE, never WATCHDOG (`zephyr/Kconfig:277-288`).
- Effect: `native_sim` shows only part of the boot counter's watchdog path and never the WATCHDOG cause; host tests and a board show the case with that cause.
- Crux change: none.

### C14. Operator reset marker and Crux Reboot

- Evidence: Crux Reboot asks the composition's policy callback when a request arrives, on the requesting thread, and again just before the reset, on the thread that carries out the request; the callback "may be called more than once for one request" and receives no argument that names the check (`components/reboot/include/crux/reboot.h:19-21`, `:92-102`, at the pin and on Crux `main`).
- Evidence: Crux Reboot offers no call that runs once immediately before the reset.
- Evidence: the order of the calls does not identify the last check, because a request that fails before the second check (`CRUX_REBOOT_FAILURE_NO_TIMER`, `CRUX_REBOOT_FAILURE_SAVE_IN_FLIGHT`) makes no second call, a request made while another is pending runs no policy, and the always-allow policy calls no callback (`components/reboot/src/reboot.c:227-228`, `:263` and `:393-403` at the pin).
- Evidence: `crux_reboot_work_once()` carries out the accepted request on the calling thread: the delay, the bounded wait for events and saves, the second policy check, then the reset; a composition with no worker thread calls it itself (`reboot.h:178-185`, `:223-231`).
- Evidence: after a second check that allows the restart, the next step is the reset, and the call returns only when no reset happened (`reboot.c:409-415` at the pin, `:413-419` on Crux `main`).
- Evidence (Crux `main`): the settle wait inside `crux_reboot_work_once()` reports progress as `CRUX_SERVICE_THREAD_REBOOT_WORKER` on the calling thread (`reboot.c:348-351`), although `service_priority_zephyr.h` says that a thread that is not started never reports, so the framework's progress function ignores that identifier; project-specific workaround ([C8](#c8-crux-service-threads-and-supervision)).
- Effect: the framework starts no Crux reboot worker, and its own reboot thread calls `crux_reboot_work_once()`, so a policy call on that thread is the last step before the reset ([specification section 5.1](controller-framework-spec.md#51-retained-region-and-reset-classification-d4)); documented but optional (`reboot.h:178-180`).
- Effect: the delay and the settle wait of one call are 1 s and 15 s (`reboot.c:38-46`), so the reload period of the reboot thread's channel ([specification section 4.4](controller-framework-spec.md#44-task-watchdog-channel-lifecycle-established-mechanism-for-the-zephyr-calls-d1-for-the-rules)) covers them.
- Crux change: none.
- Interim state: none.

## Console and logging

### C6. Console and logging UART

Zephyr's usual way to share one UART is the shell's log backend (`CONFIG_SHELL_LOG_BACKEND`), which queues log messages and multiplexes them with the shell's output.
Crux refuses every form of it, at the pin and on Crux `main`; the line references are at the pin:

| Where | What it refuses |
|---|---|
| `components/logging/ports/zephyr/logging_binding.c:45` | A build with `CONFIG_CRUX_SERIAL` whose `crux-serial0` UART is the logging UART ("Crux Logging conflicts with Crux Serial") |
| `components/logging/ports/zephyr/logging_binding.c:42` | The Zephyr shell's serial backend on the logging UART |
| `components/logging/ports/zephyr/logging_binding.c:31-39` | The Zephyr console on the logging UART, except with logging-only routing (no shell, no console input) |
| `components/logging/ports/zephyr/CMakeLists.txt:15-24` | `CONFIG_SHELL_LOG_BACKEND` and every log backend other than the UART backend |
| `components/cli/ports/zephyr/include/crux/cli_zephyr.h:26-27` | Any Zephyr console, log backend, shell or other Crux Serial user on the console's `crux-serial0` UART |
| `zephyr/Kconfig:184` | More than "one explicitly dedicated UART" for Crux Serial |
| `zephyr/Kconfig:193`, `:236-243` | A Zephyr shell in an image with the Crux command line, unless the image is marked as a development image |

- Crux `main`: `CONFIG_CRUX_CLI_CONSOLE_UART_SHARED` puts the console and Crux Logging on one UART through a Crux Logging backend that queues log text and lets the console print it while it waits for input (`zephyr/Kconfig:237-266`); the separate UART stays the default.
- Effect at the pin: the console needs a second UART; on the RT1060-EVKB that is LPUART3 on header pins, connected with a USB-serial adapter and named by the alias.
- Crux change: a build option that selects a separate console UART or one UART shared by the console and Crux Logging. State: Crux `main`. Priority 2.
- A Crux change for the logging UART on `native_sim` is in progress as a Crux Draft.
- Interim state: the serial console uses a second UART (LPUART3 on header pins, with a USB-serial adapter). Replacement criterion: none.

## Security profiles

### C7. SSH and TLS profiles

- Evidence: `CONFIG_CRUX_ACCESS` stops the build without `CONFIG_PSA_CRYPTO_PROVIDER_MBEDTLS` (`zephyr/CMakeLists.txt:198-200`; `zephyr/Kconfig:646-670`; Crux `docs/management-in-a-product.md:154-155`).
  So Crux Access, and every management service that depends on it (serial console, configuration service, status service, web sessions, web management, TLS certificate, reboot, File service and network settings), needs the Mbed profile of PSA Crypto, and an image on the Wolf profile, which SSH needs, has none of them through the module.
- Evidence: Crux SSH has a private provider interface only, with no public header and no `crux::` target, so a composition outside Crux needs a Crux composition interface.
- Evidence: `CONFIG_CRUX_SSH` needs the Wolf profile, and Crux refuses it together with the Mbed TLS module, because two TLS stacks are not a supported image (`zephyr/CMakeLists.txt:286-290`).
- Evidence: the Wolf profile needs a Zephyr patch for its TLS socket backend, whose application in a product is open in Crux (Crux `docs/management-in-a-product.md:58`); on Crux `main`, whose Zephyr is v4.5.0, the wolfSSL line stays on Zephyr v4.4.2 until a patch for Zephyr 4.5 exists (Crux `patches/zephyr/README.md`).
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

### C16. Security counter

- Evidence: Crux's image state contract has query, test request and confirm operations and no security counter (`components/image_state/include/crux/image_state.h`).
- Evidence (Crux `main` at `06813519`): MCUboot's downgrade prevention is optional with no default, and the Zephyr port has no non-volatile counter backend; a trusted counter on RT1060 would need fuses (`docs/evidence/boot-update/stage1-pinned-source-findings.md` B13; `docs/boot-update-investigation.md:135`).
- Crux change: a security counter in the image state contract and its storage, with the secure boot work. State: Crux change needed. Priority 2.
- Interim state: nothing enforces the image security counter. Replacement criterion: none; PR7 needs the change.

## Security events and at-rest protection

### C17. Security event persistence

- Evidence: Crux security events go to a RAM ring that a reset loses, and a low-priority thread hands the ring to Logging; the records are not tamper-proof (`components/security_event/include/crux/security_event.h:8-15`).
- Evidence: the only reader, `crux_security_event_read()`, needs an Access session with `events.read` (`security_event.h:252-276`), and the framework has no session of its own.
- Crux change: a composition-level reader or sink that the framework uses to persist events. State: Crux change needed. Priority 2.
- Interim state: security events reach the log only. Replacement criterion: none; criterion 44 needs the change.

### C18. Request rate limit

- Evidence: Crux Web bounds connections, backlog, request body and request time, and has no request rate limit; the login delay covers logins only ([Access controls at the pin](#access-controls-at-the-pin)).
- Effect: the framework cannot add a rate limit without wrapping the web server, which the repository rule against pass-through wrappers forbids.
- Crux change: a request rate limit per source in Crux Web. State: Crux change needed. Priority 3.
- Interim state: web management has no request rate limit. Replacement criterion: none; criterion 45 needs the change.

### C19. Credential store at rest

- Evidence: the PSA provider declares the basis `BASIS_DEVICE_ID_KEY` with no confidentiality against the medium and the chip ID; a card moved to another board reads unusable; rollback is not detected; a writer without the chip ID can overwrite both headers so that the store reads empty, which reopens provisioning (`docs/credential-store.md`, "Limits").
- Effect: S9 is a mandatory product record, and first-account setup on the serial command line (S1) is the barrier after a blanked store.
- Crux change: a hardware-bound key basis per SoC. State: Crux change needed when a product's record asks for it. Priority 3.

## Boards and operating systems

### C12. SoC gates

These refuse a board whose logging UART, watchdog or entropy source is not the NXP driver that Crux and this repository accept, or name RT1060 nodes:

| Where | What refuses | Services blocked |
|---|---|---|
| `components/logging/ports/zephyr/logging_binding.c:17-21` | "Crux Logging unsupported UART resource": only an `nxp,lpuart` node and the `native_sim` emulated UART | Logging, and every configuration on it |
| `components/system/ports/zephyr/system_binding.c:66` | "Crux System unsupported watchdog driver: crux-watchdog0 must be an nxp,imx-wdog node" | Health supervision, device management |
| `app/management/entropy.cmake:17-21` (this repository) | Needs `CONFIG_ENTROPY_MCUX_TRNG` | Device management |
| `app/boards/*.overlay`, `app/conf/management.conf` (this repository) | Name RT1060 nodes and RT1060 Ethernet driver options | Network, health supervision, device management |

- Evidence: Crux's FatFs providers on a real medium are chosen by generic disk and devicetree facts, not by a SoC or board name (`zephyr/Kconfig:307-310`), and the board-neutral Reliance Edge provider links source under GPLv2.
- Crux change: board-neutral driver gates. State: Crux change needed when a second board enters the scope (decision D9). Priority: deferred.

### C13. Linux providers

- Evidence: Crux has Linux providers for File, Logging, Netif, Serial, Sync, System, Thread, Time and Interrupt (`components/*/ports/linux`), and they are test providers until a Linux product is defined (Crux ADR-0003 R5).
- Evidence: Access, command line, Configuration, configuration service, management status, Web, Sockets, TLS certificate, credential store, Reboot, security events, SSH, File service and network settings have Zephyr providers only; the PSA ports of Access, credential store, TLS certificate and Web are crypto ports, not OS providers.
- Crux change: Linux providers for those components, which Crux designs when its first Linux product is defined (Crux ADR-0003 R5).

## Other Crux changes

- A web adapter for the File service, which HTTPS file transfer needs ([specification section 6.2](controller-framework-spec.md#62-security-items)). [crux-pilot#188](https://github.com/wonny-labs/crux-pilot/issues/188). State: Crux change needed. Priority 3.
