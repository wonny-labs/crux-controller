# Finding: time synchronisation over SNTP (step S5)

Status: step S5 is written and its local checks pass. Its Zephyr builds, the `native_sim` scenarios and its
budget numbers run in CI and are recorded in the pull request, not here. Nothing ran on a board.

Every statement is labelled **Measured** (the author ran it, and the command is named), **Inferred** (read from
`crux-pilot` or Zephyr source, not run on its own here) or **Open**. The `crux-pilot` revision is the pinned commit
`37c92b18b44b7dfb95c2109f036f23d00f05cb4c`. The Zephyr source was read at `v4.4.0` (a local clone); the pin goes
through Crux to `v4.4.2`, and between the two tags the only change under `subsys/net/lib/sntp` and
`include/zephyr/net/sntp.h` is a fix in `sntp_close_async()`, which this step does not call (**Inferred**, from
`git log v4.4.0..v4.4.2` on those paths).

## Question and answer

Can a product set the realtime clock of Crux Time from an SNTP server with public means, inside the boundary of
`docs/composition-zone.md`, and decide for itself when an answer may move the clock?

**Yes, by reading the pinned source and by the checks below.** The product includes `<crux/time.h>`,
`<crux/time_authority.h>` (both public, neither frozen) and `<crux/logging.h>` in `app/src`; the Crux Time library
gives the authority header in the include directory that `crux::time` already provides. The Zephyr SNTP library is
called from the adapter zone `app/os` only, through `<zephyr/net/sntp.h>` and the one-shot string query
`sntp_simple()`, so no zone includes a socket header. The boundary check and its allow-lists are unchanged by this
step. The product adds no Crux interface and selects no Crux symbol.

## Results

| What | Result | Label | Source |
|---|---|---|---|
| Tooling tests (limits row, policy files, configuration, build files, glue, port, adapter, scenario files, CI jobs, this note) | all pass; the S5 tests were written first and were red before each change | Measured | `python -m unittest discover -s tests/tooling`, run by the author |
| Host test of the policy | 131416 checks, 0 failures, also built with the address and undefined-behaviour sanitizers; five boundary mutations of the policy (the two limit comparisons, the stale comparison, the end of the range, the fraction shift) each failed it (the mutation runs were made before the unreadable-snapshot case was added and were not repeated) | Measured | compiled with the host `cc` (clang, `-std=c17 -Wall -Wextra -Wpedantic -Werror`) and run by the author; the Host tests job runs the same file through CMake |
| Boundary check against the pinned Crux headers | passes with the S5 files in the tree | Measured | `scripts/check_boundary.py --crux-root <the pinned tree, exported with git archive>`, run by the author |
| The glue against the real pinned Crux headers | compiles with `-Wall -Wextra -Wpedantic -Werror -Wdouble-promotion -Werror=enum-compare`; run against a fake Crux Time and a fake port in a throwaway harness outside the repository it set, confirmed, corrected, refused, marked stale and re-synchronised as the policy table says, and reported a failed native write | Measured | host `cc` with the `components/*/include` directories of the pin; not a Zephyr build, and the fake is the author's reading of the header |
| The adapter | passes `-fsyntax-only -Werror` against stand-in declarations of the two Zephyr headers; this checks the C and not the Zephyr types | Measured | host `cc`; **Open** until the CI build |
| RT1060-EVKB build with the baseline gate required, resolved configuration, linked symbols | not yet known | Open | CI job "S5 build (RT1060-EVKB, SNTP time synchronisation)" |
| Static size of S5 against the declared limits | not yet known | Open | CI job "Budget S5" |
| `native_sim` scenarios: seven S5 cases | not yet known | Open | CI job "S1 (native_sim and RT1060-EVKB)", which runs every scenario under `tests/native_sim` |
| A query to a real server, a clock set on a board, a reset | not run | Open | no hardware, no real server |

## The policy

The decision is a pure function in `app/src/time_sync_policy.c` (plain C, no Crux and no Zephyr include, tested on
the host). The glue `app/src/time_sync.c` gives it one query result, one Crux Time snapshot, the age of the last
good answer and the limits, and carries out what it returns.

| Situation | Action | Reason in the log |
|---|---|---|
| The query failed, timed out or the server sent a kiss-o'-death | none; never sets | `error`, `timeout`, `kiss-of-death` |
| The answer is outside 2000-01-01 to 2100-01-01, or its fraction is not below one second | refused; never sets | `out-of-range` |
| The Crux Time snapshot could not be read (the read returned an error) | none; never sets, even for an in-range answer, because the clock cannot be compared; counted as a failed round, logged as a warning | `clock-unreadable` |
| Any of the rows above, while the clock is valid and synchronised (or, for an unreadable snapshot, may be) and the last good answer is older than the stale age (strictly) | the clock is marked not synchronised; the call is `crux_realtime_set_synchronized(false)` | the reason of the failure; the action reads `mark-stale` |
| The clock is not valid (boot, or after a failed write) and an in-range answer arrives | set, source EXTERNAL, synchronised | `first-sync` |
| The clock is valid but not synchronised (stale, or lost after a refused step) and an in-range answer arrives | set, source EXTERNAL, synchronised, whatever the difference | `resync` |
| Synchronised, and the difference from the answer is below the correction threshold | none; the answer confirms the clock | `within-threshold` |
| Synchronised, and the difference is from the threshold up to and including the maximum step | set, source EXTERNAL, synchronised | `correction` |
| Synchronised, and the difference is above the maximum step | refused, the clock is left alone and marked not synchronised | `step-too-large` |

How the rules read:

- In short: a failed query at boot sets nothing, the clock stays not valid, and the same holds for every answer that
  is not an in-range answer, whatever the state.
- A snapshot that was read and reports no time is a clock that is not valid, and an in-range answer sets it (`first-sync`).
  A snapshot whose read failed is different: nothing is known about the clock, so the round fails like a failed query.
  Only the age decides the stale mark then; if the clock turns out not to be valid, Crux refuses the clear call and the
  glue logs its status.
- A failed or refused answer counts as a failure, and a clock that was synchronised and has had no confirming
  answer for longer than the stale age (strictly: an age equal to the limit is not stale) is marked not
  synchronised once. The next round finds Crux not synchronised, so it is not marked again. It stays valid and
  keeps its source.
- A clock that is not synchronised takes any in-range answer, the first after boot or after the stale mark or after
  a refused step. This is rule 2 of the policy header. When a step is refused, synchronisation is lost: that is how
  the next in-range answer is applied. The consequence is stated in the limitations below: the maximum step stops a
  single wrong answer from moving a synchronised clock, and then stops guarding.
- An answer that confirms the clock (within the threshold) or sets it (correction, resync, first sync) starts the
  age again. A refused step does not.
- The comparison reads both times as nanoseconds. A clock reading that is outside the supported range counts as not
  synchronised, because it cannot be compared.
- The decision about writes sits in one place: only `crux_realtime_set(..., CRUX_REALTIME_SOURCE_EXTERNAL, true)`
  writes a time, only on the set action, and only `crux_realtime_set_synchronized(false)` clears. The product never
  calls `crux_realtime_adopt()` or `crux_realtime_invalidate()`.

## Decisions made for this step

The owner has set no time policy. These are defaults chosen for the synthetic workload, each a Kconfig setting with a
range, documented in `app/Kconfig` and fixed by the resolved-configuration check of the CI job.

| Setting | Default | Range | Why |
|---|---|---|---|
| Server (`CRUX_CONTROLLER_TIME_SERVER`) | `192.168.77.1`, the peer of S2 | an IPv4 address, optionally `:port` | the image has no DNS resolver, so a host name does not resolve |
| Interval (`CRUX_CONTROLLER_TIME_INTERVAL_S`) | 600 s | 16 to 86400 | one query every ten minutes; RFC 4330 asks for no more than one in 15 seconds |
| Query timeout (`CRUX_CONTROLLER_TIME_TIMEOUT_MS`) | 3000 ms | 100 to 30000 | the library resends with a growing wait and checks the deadline only between rounds, so a query can run past it (see below); a build check keeps the value below the interval |
| Stale age (`CRUX_CONTROLLER_TIME_STALE_AGE_S`) | 1800 s | 60 to 604800 | three intervals without a confirming answer; a build check keeps it above the interval |
| Correction threshold (`CRUX_CONTROLLER_TIME_THRESHOLD_MS`) | 100 ms | 1 to 10000 | a difference below it is left alone, so that a good server does not cause a write every round |
| Maximum step (`CRUX_CONTROLLER_TIME_MAX_STEP_MS`) | 1000 ms | 1 to 3600000 | a build check keeps it at or above the threshold |
| Thread stack (`CRUX_CONTROLLER_TIME_STACK`) | 8192 bytes | 2048 to 65536 | a starting value, not measured: the 8192 bytes that the S2 consumer thread uses for the same reach into the network stack |

Other choices, each recorded in the code:

- The thread runs at priority 10, after the workload threads (5) and before the log thread (14): a starting value, not
  measured. It queries once after a fixed wait of five seconds (so that the static network configuration has had a
  moment) and then waits one interval after each query. A failed query at boot therefore waits one interval, ten
  minutes by default, for the next one. **Open:** whether a shorter retry while the clock is not valid is wanted; it
  would be a later change with its own test.
- `conf/s5.conf` raises the network contexts and connections from S2's four to six, a starting value, not measured,
  for one UDP socket next to the TCP exchange.
- The staleness age counts from the start of the service until the first good answer, so a clock cannot be marked stale
  before it was ever synchronised (it is not synchronised then, and the mark applies only to a synchronised clock).
- One log line per round, tag `time`: information for a clock that was set, confirmed or re-synchronised, a warning for
  every failure, refusal and stale mark, an error for a failed native write.

## Duties from the Crux Time contract and the platform consult

`<crux/time_authority.h>` says that applications own stale-callback and source policy. Crux Pilot was asked (2026-11-14,
read by that session on its main branch) whether a product thread may call `crux_realtime_set`. The answer, stated
here as a consult result and not as a Crux decision: no objection, and four duties for the product: staleness is the
product's, a write failure has to be handled, there is one writer of the native clock, and events carry a wall time
that moves. They are met as follows.

| Duty | How S5 meets it |
|---|---|
| Staleness is the product's | the stale age and the mark are the product's policy (table above); `time_authority.h` leaves staleness to the application and Crux Time keeps the flag until it is told otherwise |
| Handle a write failure | a native write failure clears validity and synchronisation in Crux Time and keeps the source (`time_authority.h`); the glue logs it as an error and treats the time as not valid, so the next round applies any in-range answer as a first sync; it does not retry in between and does not call adopt or invalidate |
| One writer of the native clock | the glue is the only caller of the authority in `app/` and `workload/`, and nothing in the image calls `sys_clock_settime` or `clock_settime`; tooling tests scan the sources for both. The linked Crux Time library and the SNTP library define those calls themselves, so the image's symbols cannot show the absence of another caller and the CI job does not claim it |
| Events carry a wall time that moves | see the next section |

## The events and the wall clock

**Inferred** from `components/security_event` at the pin (`security_event.h`, `security_event_drain.c`): a Crux security
event stores a monotonic time (`uptime_ms`) and a sequence number when it is recorded, and the drain computes the wall
time later, with a Time snapshot taken at read. So the wall time of an event that was emitted before the first set, or
across a step of the clock, is either missing (the clock is not set then, `CRUX_SECURITY_EVENT_CLOCK_NONE`) or
shifted by the step, while `seq` and `up` stay correct. No step of this product emits security events yet; the effect
applies from the step that does. A step of the realtime clock does not touch the monotonic clock: `sys_clock_settime`
only changes the realtime offset (`lib/os/clock.c`, **Inferred**), so kernel timeouts and sleeps are not disturbed.

## What a product had to write

| Item | File |
|---|---|
| The policy: the range, the fraction conversion, the decision, log level and names | `app/src/time_sync_policy.h`, `app/src/time_sync_policy.c` |
| The glue that reads the snapshot, calls the Crux Time authority and logs | `app/src/time_sync.h`, `app/src/time_sync.c` |
| The port that app/src declares, and the adapter that calls the SNTP library and runs the thread | `app/src/time_sync_port.h`, `app/os/time_sync_zephyr.c` |
| The start in the composition | `app/src/composition.c` |
| Kconfig options, build blocks and fragment | `app/Kconfig`, `app/CMakeLists.txt`, `app/os/CMakeLists.txt`, `app/conf/s5.conf` |
| Tests: host, scenario, tooling | `tests/host/test_time_sync_policy.c`, `tests/native_sim/s5/`, `tests/tooling/test_s5.py` |

The composition proper is the fragment, the glue and the adapter. Line counts are left out on purpose: `git diff
--stat` of the pull request has them and they move with every edit.

## Friction

### 1. The SNTP library reports the kiss-o'-death as `-EBUSY` and everything else as an errno

**Inferred** from `subsys/net/lib/sntp/sntp.c`: a stratum of zero returns `-EBUSY`, an answer to another request
returns `-ERANGE`, a wrong mode or a zero transmit time `-EINVAL`, a short packet `-EMSGSIZE`, no answer in time
`-ETIMEDOUT`. `sntp_simple()` keeps asking with a growing wait (100, 200, 400, 800, then 1000 ms) until its timeout is
over, skips an answer to an earlier request and returns the last result. It checks the deadline between rounds,
not inside one, so a query can run past the configured timeout by up to the wait of one round (1000 ms at most) and
longer while it is skipping answers to earlier requests. The timeout is therefore a lower bound on how long a
failing query takes. The stale mark is judged when a failed round ends, so the 1800 s boundary depends on how long
each query ran as well as on the interval: it is not a fixed time after the last good answer. Read in
`sntp_simple.c` at `v4.4.0` in the local clone (**Inferred**, not run on its own here); the file is not among the
paths that differ at the pinned `v4.4.2`. The adapter maps `-ETIMEDOUT` to a timeout,
`-EBUSY` to a kiss-o'-death and everything else to an error. The meaning of `-EBUSY` is the library's, not a promise
of its header. **Open:** the cases `-ERANGE`, `-EINVAL` and `-EMSGSIZE` are not shown by a scenario.

### 2. `sntp_simple()` keeps one static structure, so one thread may call it

**Inferred** from `sntp_simple.c` (a static `hints`). The adapter has one thread and the scenario calls the glue from one
test thread. The port says so.

### 3. The library reports a fraction in units of 2^-32 s

**Inferred**, and checked by the host test: without the uncertainty option, `fraction` counts 2^-32 s and `seconds`
counts from 1970. The policy converts it to nanoseconds, rounding down, so that it never reaches a whole second. The
uncertainty option, which would change both fields, is not selected, and the CI job checks that it is off.

### 4. An unmet Kconfig dependency leaves the step off with only a warning

As for S3 and S4. The S5 option depends on the S2 step, `CRUX_TIME`, `SNTP`, `NET_UDP` and `NET_IPV4`. The S5 CI job and
the S5 budget row check the resolved `.config` for the step, its dependencies and the defaults. No failure of this
kind occurred, so the check has not been seen to fire.

### 5. The adapter zone needed no change of its rules

The rule change of the zone (`zephyr/net/sntp.h` in `app/os`) was a separate reviewed change. S5 uses it with the string
query only, includes no socket header, and `app/os` gets a second source that is built only for this step.

## What this step does not show

- Nothing ran on a board: no query to a real server over the real link, no clock set on the RT1060, no reset. The
  S2 network that this step builds on ran on a board twice (`docs/findings/s2-first-board-run.md`); S5 did not.
- The `native_sim` scenario shows seven cases over the loopback interface, each in its own image: `first_sync`,
  `kiss_of_death`, `late_answer`, `out_of_range`, `step_refused_then_resync`, `correction_and_threshold` and
  `stale_after_silence`. They run on one simulated clock with test limits (a 600 ms timeout, a stale age of two
  seconds), not the defaults.
- A failed native write is not shown by any scenario: the simulator's clock accepts every value in range. It is covered
  by the throwaway harness above and by reading `time_authority.h`.
- The protocol here is plain SNTP and unauthenticated: the answer is not checked against anything but the request.
  So a rogue server, or anything on the path, that answers with a time inside the supported range can move the clock: the
  first answer after boot is applied whatever it says, a synchronised clock follows a difference of up to the maximum
  step, and after one refused larger answer the next in-range answer is applied whatever the difference. This is an
  accepted limitation, recorded here and in the pull request, and not a security claim of any kind.
- The clock is set with a step, not a slew: a correction is a jump of up to the maximum step, and time as read can go
  backwards by up to that.
- The path delay is not compensated: the answer is applied as the server's transmit time, so the clock is late by about
  the one-way delay and the time between the answer and the write. The library's own estimate of the response delay is not
  used.
- Time is not persisted: nothing persists time. There is no RTC (`CRUX_TIME_RTC` is off and the CI job checks it), so the
  time is not valid after a reset, and stays not valid until the first answer.
- No authentication, no HTTPS, command line or SSH, and no change of the Crux pin.
- Stack use of the thread and the timing of a query against the interval are not measured. The static size of S5 is
  whatever the Budget job reports against placeholder limits.
