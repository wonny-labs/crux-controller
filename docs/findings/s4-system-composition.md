# Finding: composing Crux System (step S4)

Status: step S4 is written and its local checks pass. Its Zephyr builds, the `native_sim` scenarios and its
budget numbers run in CI and are recorded in the pull request, not here. Nothing ran on a board.

Every statement is labelled **Measured** (the author ran it, and the command is named), **Inferred** (read from
`crux-pilot` source at the pinned commit `37c92b18b44b7dfb95c2109f036f23d00f05cb4c`, not run on its own here) or
**Open**.

## Question and answer

Can a product compose Crux System (reset cause, a single-owner watchdog, `<crux/system.h>`) with public headers,
public targets and configuration that the product owns, inside the boundary of `docs/composition-zone.md`?

**Yes, by reading the pinned source and by the checks below.** Application code includes `<crux/system.h>`,
`<crux/logging.h>` and `<crux/status.h>`; the build links the public target `crux::system`; the product's
Kconfig fragment turns on the three native facilities that System requires; and a devicetree overlay names the
RT1060's WDOG1 with the alias `crux-watchdog0`. No Zephyr header, no private Crux header and no new zone is
needed, and no allow-list of `scripts/check_boundary.py` changes. The native driver, HWINFO and reboot calls are
inside Crux's own binding, which includes `<zephyr/drivers/watchdog.h>`, `<zephyr/drivers/hwinfo.h>`,
`<zephyr/sys/reboot.h>` and the vendor header `<fsl_wdog.h>` (`components/system/ports/zephyr/system_zephyr.c`
and `system_binding.c`, Inferred). A product never includes them, and S4 does not.

## Results

| What | Result | Label | Source |
|---|---|---|---|
| Tooling tests (limits, policy files, configuration, build files, sources, boundary expectations, scenario files, CI jobs) | all pass; the S4 tests were written first and were red before each change | Measured | `python -m unittest discover -s tests/tooling`, run by the author |
| Boundary check against the pinned Crux headers | passes with `app/src/health.c` in the tree | Measured | `scripts/check_boundary.py --crux-root <the components directory of 37c92b18, exported with git archive>`, run by the author |
| Host test of the policy | 130528 checks, 0 failures, also built with the address and undefined-behaviour sanitizers | Measured | compiled with the host `cc` (clang, `-std=c17 -Wall -Wextra -Wpedantic -Werror`) and run by the author; the Host tests job runs the same file through CMake |
| The glue and the policy compile against the pinned public headers | `health.c`, `health_policy.c`, `workload_thread.c` pass `-fsyntax-only -Werror`; the `_Static_assert` lines that tie the policy's flag values to `CRUX_RESET_CAUSE_*` hold | Measured | host `cc` with the `components/*/include` directories of the pin; this is not a Zephyr build and links nothing |
| RT1060-EVKB build with the baseline gate required, resolved configuration, devicetree alias, linked symbols | not yet known | Open | CI job "S4 build (RT1060-EVKB, System)" |
| Static size of S4 against the declared limits | not yet known | Open | CI job "Budget S4" |
| `native_sim` scenarios: three S4 cases and one new S1 case | not yet known | Open | CI job "S1 (native_sim and RT1060-EVKB)", which runs every scenario under `tests/native_sim` |
| Watchdog start, feed, a missed feed and a reset on a board | not run | Open | no hardware |

## What a product had to write

| Item | File |
|---|---|
| The policy: cause classes and boot line level, the watchdog interval, the feed tracker | `app/src/health_policy.h`, `app/src/health_policy.c` |
| The glue that calls Crux System and Crux Logging | `app/src/health.h`, `app/src/health.c` |
| A cycle hook in the workload thread, and the S4 start in the composition | `app/src/workload_thread.[ch]`, `app/src/composition.c` |
| Kconfig option, build block, fragment and overlay | `app/Kconfig`, `app/CMakeLists.txt`, `app/conf/s4.conf`, `app/boards/s4.overlay` |
| Tests: host, scenario, tooling | `tests/host/test_health_policy.c`, `tests/native_sim/s4/`, `tests/tooling/test_s4.py` |

The composition proper is the fragment and the overlay. Line counts are left out on purpose:
`git diff --stat` of the pull request has them and they move with every edit.

## Friction

### 1. The simulator has no watchdog, so a feed cycle cannot be shown there

**Inferred** from `components/system/ports/zephyr/system_binding.c` lines 5 to 11: on `native_sim` the binding
returns no device ("No physical watchdog is claimed by the normal simulator composition. Tests substitute an actual
native driver object at this private binding seam."). Crux's own tests substitute it by wrapping private symbols
at link time (`tests/system/zephyr/CMakeLists.txt`), which a product cannot do with public means. So on
`native_sim` the real provider reports the watchdog as not supported, and the S4 scenario shows that: the boot
line with the reset cause the simulator reports, the clear after it, one "watchdog not started" line, a cycle
hook that does nothing, and the status `CRUX_WATCHDOG_UNAVAILABLE`. A feed cycle and a missed feed are covered
only by the Host test of the policy (feed results are injected there) and by the EVKB build. **Open:** whether
Crux should offer a public simulated watchdog binding; this note does not file that request.

### 2. A feed that the native side refuses is final, and the header does not say so

**Inferred** from `components/system/src/system.c` (feed from line 225): after a successful start, a failure
reported by the native side (the probe before the feed, or the feed itself) moves the lifecycle to faulted
(`fault()`, line 45), and every later feed returns `CRUX_ERR_IO`. Not every error does that: a call from an
interrupt or before the kernel runs (`CRUX_ERR_NOT_SUPPORTED`), a zero or foreign token
(`CRUX_ERR_INVALID_ARGUMENT`) and a lock failure (`CRUX_ERR_IO`) return without moving the lifecycle to
faulted. `<crux/system.h>` says `CRUX_OK` means native acceptance and does not say which errors are final. The
product does not try to tell them apart: it reports the first non-OK result once and stops feeding, whatever
its cause, instead of retrying.

### 3. The interval rules are in the port source, not in the header

**Inferred** from `components/system/ports/zephyr/system_zephyr.c` lines 32 to 37: 500 ms to 64000 ms in
steps of 500 ms; `crux_watchdog_start` documents only "provider-specific". The product's policy copies the
numbers and names the file. A change on the Crux side shows up as a refused start at run time, not as a build
error.

### 4. The facilities and the alias are the product's to declare

**Inferred** from `components/system/ports/zephyr/CMakeLists.txt`: the provider stops the CMake run when
`WATCHDOG`, `HWINFO` or `REBOOT` is off, or when another owner is on (`CRUX_CONTROLLER_M3`, `WDT_SHELL`,
`HWINFO_SHELL`, `TASK_WDT_HW_FALLBACK`); `system_binding.c` stops the compile with `#error` when the alias
`crux-watchdog0` is missing or its node is disabled, and a `BUILD_ASSERT` requires that node to be `wdog0`. At the pin the overlay lines that name the alias for this board are set by `tests/system_consumer` and `tests/m5_integrated` (read with `git show` at `37c92b18`). `tests/zephyr/management_rt1060_compile` may be a third place that sets it; that was not checked at the pin. The sample `samples/controller/zephyr/m3_main.c` reads the alias `watchdog0` instead and is the native owner that System refuses. A later Crux revision was not read.
These are good, early failures. The wording of the Kconfig help of `CRUX_SYSTEM` ("explicit native
WATCHDOG/HWINFO/REBOOT composition required") is what tells a product to write them.

### 5. A reset cause is cleared only after a read, and each clear attempt is spent

`<crux/system.h>` (read at the pin) allows a clear only after a successful public read, and each admitted attempt
consumes the permission even when it fails. The product reads, writes its line, then clears once. **Inferred**
that on the RT1060 the flags would otherwise stay latched and pile up across resets, so a watchdog reset after a
power-on would read as both; the simulator's HWINFO clears the flag, so the scenario can check the clear, and
the board behaviour is **Open**.

### 6. An unmet Kconfig dependency leaves the step off with only a warning

As for S3. The S4 option depends on `CRUX_CONTROLLER_S1`, `CRUX_SYSTEM`, `WATCHDOG`, `HWINFO` and `REBOOT`. The S4
CI job and the S4 budget row check the resolved `.config` for the step and the provider. No failure of this kind
occurred, so the check has not been seen to fire.

### 7. A possible reset loop

The watchdog is armed before workload_thread_start. If the workload start fails, or the producer thread exits
on a clock error, nothing feeds the watchdog, the board resets, and because the policy never stops the start (no
reset cause keeps the watchdog from being armed) it would arm again and keep resetting. The same holds after
a start that fails in the unknown state that the decisions table describes. **Open:** no board has run this. Any future board
run must be supervised and time-limited.

## Decisions made for this step

The owner has set no health or reset policy. These are conservative defaults chosen for the synthetic workload,
each pinned by a test in `tests/host/test_health_policy.c` and recorded in the pull request.

| Decision | Choice | Why |
|---|---|---|
| Watchdog interval | ten workload cycles, rounded up to 500 ms, at least 2000 ms and at most 64000 ms: 2000 ms for the default 100 ms cycle | generously longer than a cycle; stays inside what the provider accepts |
| A cycle that does not fit | the product does not arm when even the clamped interval is shorter than three cycles (a cycle above 21333 ms) | a late cycle would otherwise reset the controller |
| Who feeds | the workload's producer thread, once for each pass that finds cycles due, and nothing else | a workload that stops cycling stops feeding; the consumer thread is not covered |
| Reset cause line | one line at boot under the tag `system`: info for power, pin, software, debugger, user or hardware resets; warning for a watchdog reset or an unknown cause; error for a CPU lockup, a security reset or a temperature reset | the product reports and does not change its behaviour |
| Clear | the flags are cleared once, after the line was written | stops the flags from piling up |
| Cause never stops the start | no cause keeps the product from arming the watchdog, and none puts it in a safe mode | no escalation beyond what Crux does |
| A refused feed | reported once at error level, feeding stops, no retry and no call to `crux_system_reset()` | Crux makes the refusal final; the watchdog ends the run |
| A start that fails | no watchdog runs only when the policy refuses the cycle (`CRUX_ERR_OUT_OF_RANGE`), Crux refuses the interval before any attempt (`CRUX_ERR_OUT_OF_RANGE`) or there is no device (`CRUX_ERR_NOT_SUPPORTED`); the product reports it once and the workload starts. On any other error the native start may have been attempted: the state is unknown, the product does not feed it, says so at error level, and the watchdog may still reset the board | Crux does not retry an uncertain start (`<crux/system.h>`; `system.c` lines 196 to 218 at the pin: after the attempt an error moves the lifecycle to faulted); a platform without a watchdog, such as the simulator, must still run |
| Start order | after the storage step, before the workload threads | a slow mount cannot cost a reset |

## What this step does not show

- Nothing ran on a board: no watchdog start, no feed, no reset, no reset cause from the RT1060's SRC.
- The feed cycle and the missed feed are not shown by any scenario (friction 1).
- The consumer thread's progress is not part of the feed.
- Stack use of the glue and the timing of a feed against the cycle are not measured; the main stack stays at the
  4096 bytes of S1.
- The static size of S4 is whatever the Budget job reports against placeholder limits.
