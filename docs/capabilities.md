# Capabilities

This page is the reference for how the `sntp`, `system` and `management` build configurations behave: what each
does, its policy and settings, and its limits. The findings notes record how each was built and what CI showed, at
a named revision: [sntp](findings/s5-time-synchronisation.md), [system](findings/s4-system-composition.md) and
[management](findings/s6-https-management.md). The [README](../README.md#capabilities) lists all configurations.

## `sntp`

The product sets the Crux Time realtime clock from an SNTP server and decides itself when an answer may move the
clock. The decision is a pure function in `framework/src/time_sync_policy.c`; the glue `framework/src/time_sync.c` gives it one
query result, one Crux Time snapshot, the age of the last good answer and the limits, and carries out what it returns.
The adapter `framework/os/time_sync_zephyr.c` calls the Zephyr SNTP library (`sntp_simple()`) from one thread, so no zone
includes a socket header.

| Situation | Action | Reason in the log |
|---|---|---|
| The query failed, timed out or the server sent a kiss-o'-death | none; never sets | `error`, `timeout`, `kiss-of-death` |
| The answer is outside 2000-01-01 to 2100-01-01, or its fraction is not below one second | refused; never sets | `out-of-range` |
| The Crux Time snapshot could not be read | none; never sets, counted as a failed round | `clock-unreadable` |
| Any row above, while the clock is synchronised (or the snapshot could not be read) and the last good answer is older than the stale age | the clock is marked not synchronised (`crux_realtime_set_synchronized(false)`) | the failure reason, action `mark-stale` |
| The clock is not valid and an in-range answer arrives | set, source EXTERNAL, synchronised | `first-sync` |
| The clock is valid but not synchronised (stale, lost after a refused step, or a reading outside the supported range) and an in-range answer arrives | set, whatever the difference | `resync` |
| Synchronised, difference below the correction threshold | none; the answer confirms the clock | `within-threshold` |
| Synchronised, difference from the threshold up to the maximum step | set | `correction` |
| Synchronised, difference above the maximum step | refused; the clock is marked not synchronised | `step-too-large` |

Only `crux_realtime_set(..., CRUX_REALTIME_SOURCE_EXTERNAL, true)` writes a time and only
`crux_realtime_set_synchronized(false)` clears. The product never calls `crux_realtime_adopt()` or
`crux_realtime_invalidate()`. An answer that confirms or sets the clock restarts the age; a refused step does not.

| Setting | Default | Range |
|---|---|---|
| Server (`CRUX_CONTROLLER_TIME_SERVER`), an IPv4 address with an optional `:port` | `192.168.77.1` | |
| Interval (`CRUX_CONTROLLER_TIME_INTERVAL_S`) | 600 s | 16 to 86400 |
| Query timeout (`CRUX_CONTROLLER_TIME_TIMEOUT_MS`), below the interval | 3000 ms | 100 to 30000 |
| Stale age (`CRUX_CONTROLLER_TIME_STALE_AGE_S`), above the interval | 1800 s | 60 to 604800 |
| Correction threshold (`CRUX_CONTROLLER_TIME_THRESHOLD_MS`) | 100 ms | 1 to 10000 |
| Maximum step (`CRUX_CONTROLLER_TIME_MAX_STEP_MS`), at or above the threshold | 1000 ms | 1 to 3600000 |
| Thread stack (`CRUX_CONTROLLER_TIME_STACK`) | 8192 bytes | 2048 to 65536 |

The thread runs at priority 10. It queries once after a fixed wait of five seconds and then waits one interval after
each query, so a failed query at boot waits one interval for the next. The image has no DNS resolver, so the server
is an address.

Limits:

- The protocol is plain, unauthenticated SNTP. A server, or anything on the path, that answers with a time in range
  can move the clock: the first answer after boot is applied, a synchronised clock follows a difference up to the
  maximum step, and after one refused larger answer the next in-range answer is applied.
- The clock is set with a step, not a slew; time as read can go backwards by up to the maximum step.
- The path delay is not compensated.
- Time is not persisted: there is no RTC, so the time is not valid after a reset until the first answer.
- A query can run past the timeout by up to one round of the library (1600 ms), or longer while it skips answers to earlier requests.
- `sntp` allows one thread to call `sntp_simple()`, which keeps one static structure.

## `system`

The product reads the reset cause at boot, logs it once and clears it, then starts a hardware watchdog that the
workload's producer thread feeds. The code is `app/src/health.c` and `app/src/health_policy.c`.

| Decision | Choice |
|---|---|
| Watchdog interval | ten workload cycles, rounded up to 500 ms, at least 2000 ms and at most 64000 ms: 2000 ms for the default 100 ms cycle |
| A cycle that does not fit | no watchdog is armed when even the clamped interval is shorter than three cycles (a cycle above 21333 ms) |
| Who feeds | the producer thread, once for each pass that finds cycles due; the consumer thread is not covered |
| Reset cause line | one line at boot under the tag `system`: info for power, pin, software, debugger, user or hardware resets; warning for a watchdog reset or an unknown cause; error for a CPU lockup, a security reset or a temperature reset |
| Clear | the flags are cleared once, after the line is written |
| Cause and start | no cause keeps the watchdog from being armed or puts the product in a safe mode |
| A refused feed | reported once at error level, feeding stops, no retry and no call to `crux_system_reset()` |
| A start that fails | when the policy refuses the cycle, Crux refuses the interval or there is no device, the product reports it once and the workload starts; on any other error the state is unknown, the product does not feed and says so at error level |
| Start order | after the storage step, before the workload threads |

Requirements: the provider needs `WATCHDOG`, `HWINFO` and `REBOOT`, the alias `crux-watchdog0` on an enabled `wdog0`
node, and no other owner of the native watchdog (`WDT_SHELL`, `HWINFO_SHELL`, `TASK_WDT_HW_FALLBACK`). The interval
is 500 ms to 64000 ms in steps of 500 ms (Crux behaviour, from `system_zephyr.c`; see [the `system` record](findings/s4-system-composition.md)). The configuration excludes `management` in Kconfig.

Limits:

- On `native_sim` the provider reports the watchdog as not supported, so no scenario shows a feed cycle or a missed
  feed.
- A feed that the native side refuses is final: every later feed returns `CRUX_ERR_IO` (Crux behaviour; see [the `system` record](findings/s4-system-composition.md)).
- The watchdog is armed before the workload starts. If the start fails or the producer thread ends, nothing feeds it
  and the board resets in a loop, so a run on a board needs a person present and a time limit.

## `management`

HTTPS management on the `net` network with the Mbed TLS profile of Crux: login and sessions of Crux Access, the status
service, the configuration service and one packaged page, on `192.168.77.2` port 443. The certificate is self-signed
and made on the device at its first start. The medium is a RAM disk, so nothing persists across a reset.

- The start sequence is one file in the composition zone, `framework/compose/management_start.c`, which implements
  `framework/src/management_port.h`. It refuses to start when the product's copy of a permission name differs from the Crux
  macro, and it checks both `tls_credential_add()` results before the listener starts. The key material is neither
  copied nor logged.
- The route sources, the packaged page and the entropy rules are in `framework/management/`. The page is three files with
  no framework, no external URL and no inline script or style.
- The image has no account, because the first account needs the serial console and the boundary does not allow
  `<crux/cli_zephyr.h>`. The save route of the configuration service ends as not supported. There is no reboot,
  network or file route, no SSH and no command line.
- The configuration depends on `net` and excludes `file` and `system`: the status service takes the reset cause once
  and never clears it, and `system` clears it. `sntp` may share the image; CI does not build that combination.
- The fragment names no Thread, Sync or Queue symbol; the Crux services select them.
- The group `crux-secure-management` is switched on in the `management` build job and its `Budget` row only, never in
  `west.yml` ([dependencies](dependencies.md)).
