# Roadmap and status

This page says honestly what exists, what has run on a board and what cannot be done yet and why. It
promises no dates and no features. "Not yet possible" does not mean "planned": the finding that
covers most of these says "Not decided and not scheduled: whether and when any of this is built here."
Status can go stale, so check the README, the changelog and the open pull requests, and read the
[architecture](architecture.md) and the [glossary](glossary.md) for the terms.
To see the tests run without a board, read [try-on-native-sim.md](try-on-native-sim.md). An outline of how a
board bring-up would go, not yet run for this controller, is in [board-bring-up.md](board-bring-up.md).

## Short version

- Six steps, S0 to S5, are on `main`. CI builds them for the NXP RT1060-EVKB Rev B and runs
  `native_sim` scenarios for S1 to S5. This page does not claim a current CI result; look at the checks of
  the commit you care about.
- S5 (the Crux Time realtime clock set from an SNTP server) arrived with
  [wonny-labs/crux-controller#50](https://github.com/wonny-labs/crux-controller/pull/50). It was never run
  on a board.
- **Nothing here has run on a physical board except what
  [docs/findings/s2-first-board-run.md](findings/s2-first-board-run.md) records**: the S2 image, twice, on
  one bench. See [What has run on a board](#what-has-run-on-a-board) for the exact scope.
- None of the management features (HTTPS, command lines, SFTP, access control and the rest) is built here,
  and for each there is a recorded reason why not.
- There is no release and no tag.

## What exists on `main`

| Step | What it adds | What the repository has for it |
|---|---|---|
| S0 | The clock of Crux Time answers | A CI build for the board. No scenario. |
| S1 | The synthetic workload on two Zephyr threads and a message queue in the adapter zone `app/os`, with Crux Time and Logging | A `native_sim` scenario that reads the logged messages from an emulated UART, host tests of the portable workload core, and a CI build for the board. |
| S2 | Each message is also sent to a TCP peer over the Crux Sockets profile | A `native_sim` scenario over loopback (it needs the test-only `picolibc` project), host tests of the exchange against a loopback peer, a CI build for the board. It is the only image that has run on a board. |
| S3 | The configuration record is kept in a file through Crux File, mounted by the composition zone | A `native_sim` scenario with the simulator provider on a RAM disk, and a CI build for the board with the FatFs provider on microSD. No card was used. |
| S4 | The reset cause is logged at boot, and a watchdog is fed once for each pass of the workload that has cycles due, through Crux System | A `native_sim` scenario that shows the boot line and an unavailable watchdog (the simulator has none, so no feed cycle), host tests of the policy, and a CI build for the board with WDOG1 named by a devicetree alias. |
| S5 | The Crux Time realtime clock is set from an SNTP server on the S2 network, by a low-priority thread, and a product policy decides what an answer may do | `native_sim` scenarios with a UDP responder on loopback, in seven cases (each case is its own image), host tests of the policy, and a CI build for the board on the S2 base. No board run. |

On the S4 row: A simulated watchdog exists in Crux at revision 35431b1e, after this repository's pin, so
the feed-cycle scenario becomes possible once the pin is moved; nothing is decided or scheduled.

Around the steps:

- The boundary check (`scripts/check_boundary.py`) and two zones, `app/os` and `app/compose`.
  `zephyr/net/sntp.h` is on the adapter zone's allow-list, and one source includes it:
  `app/os/time_sync_zephyr.c` (step S5).
- Declared resource limits for S0 to S5 (`budgets/limits.json`), which are placeholders, checked in CI
  against static size only. Stack use, heap use and timing are not measured.
- Release tooling and a dry run that publishes nothing, a rebuild comparison at another path, and a daily
  build against the current `crux-pilot` main that is information only.
- Findings in `docs/findings/`: the File binding (closed upstream since), step S3, step S4, step S5, the S2 board
  runs and the management features.

The README table is the maintained summary of the steps and says, per step, whether it ran on a board.

## Step S5 in more detail

S5 was added by [wonny-labs/crux-controller#50](https://github.com/wonny-labs/crux-controller/pull/50),
which is merged; the pull request that put `zephyr/net/sntp.h` on the adapter zone's allow-list,
[wonny-labs/crux-controller#49](https://github.com/wonny-labs/crux-controller/pull/49), is merged too. What
the code on `main` does, read from `app/Kconfig`, `app/src/time_sync*.c` and `app/os/time_sync_zephyr.c`:

- A low-priority thread (Zephyr priority 10) waits five seconds after start, then queries one IPv4 SNTP
  server and repeats after each interval. The defaults are the server `192.168.77.1` (the S2 peer), 600
  seconds between queries and a 3000 ms timeout for one query.
- The application's policy decides what an answer may do. It never sets the clock for a failed,
  kiss-o'-death or out-of-range answer. It sets any in-range answer while the clock is not synchronised, and
  corrects a synchronised clock for a difference from 100 ms up to 1000 ms. A larger difference is refused
  once and marks synchronisation lost. A clock that no answer has confirmed for 1800 seconds is marked not
  synchronised.
- The one caller of the Crux Time authority is `app/src/time_sync.c`. The Zephyr SNTP library is called only
  in the adapter zone, through `sntp_simple()`.
- Limits, as `docs/findings/s5-time-synchronisation.md` and the `app/Kconfig` help text state them: SNTP
  here is unauthenticated, so a server or anything on the path that answers with an in-range time can move
  the clock; the clock is stepped, not slewed; nothing persists time, so it is not valid after a reset
  until the first answer; the server must be an IPv4 address because the image has no DNS resolver; stack
  use of the thread and query timing are not measured.

The findings note labels its own results. When it was written, its seven `native_sim` cases, its Zephyr
build and its budget numbers were still open, to be recorded by CI. This page does not state a result for
them: look at the checks of the commit you care about. **S5 was never run on a board**, and the only board
run of this repository is the S2 one below.

## What has run on a board

This is the whole of it, from [docs/findings/s2-first-board-run.md](findings/s2-first-board-run.md). Its
status paragraph says:

> the S2 image ran twice on one RT1060-EVKB Rev B on the same bench, on 9 November 2026 (run 1,
> described first) and on 12 November 2026 (run 2, a reproducibility run, described under "Run 2" below).

Both runs used the same S2 image and the same gated procedure, and the board was restored to the accepted
normal image afterwards. Both runs observed the Ethernet link come up without the MDIO correction that the
Crux sample applies, ping answered 5 of 5 times, and one TCP exchange with a host peer echoed. The note says
the TCP exchange was informational and not a pass criterion. Its verdict on run 2 is: "Two boots on one
bench are evidence collection, not qualification." Its "Not shown" list, kept as written:

- "Run-time values of S2: stack use, CPU use and timing beyond what the log lines literally print."
- "Repeatability beyond two boots on one bench: another board, another cable or another bench, and any
  statistical statement about how often the link comes up."
- "Behaviour after the 180 s window."
- "Whether the link comes up the same way after a cold power cycle; the run restarted the image by
  programming and reset."
- "An exchange that is repeated, or an exchange when the peer is slow or restarts."
- "Anything about the S3 image, microSD, or the release bundle: they did not run."

Beyond that note, the README and the S4 note record that S3 and S4 are built and never run on a board,
and no S0, S1-only, S4 or S5 image has run. The S2 image contains the S1 workload, so the workload lines of S1
appeared in that capture; the S1 row of the README, "not run", most likely refers to S1 as an image of its own (that is this page's reading of the README, not something the README says). No
release exists, so no released image has run anywhere. A green `native_sim` run is not a board run and a
CI build is not a board run.

## What is not yet possible, and why

Everything below is a Crux management feature or something around one. The reasons are from
[docs/findings/management-has-no-public-composition.md](findings/management-has-no-public-composition.md)
unless another note is named. That note was read against a Crux revision other than the pin
(its own "State at the pin" section says so), so the reasons are not re-verified at the current pin.
This repository's boundary check keeps no exception, so a feature that needs a Crux private header is
blocked until Crux offers a public way, and nothing here will widen the check to get around it.

| Feature | What blocks it, as recorded | Open before it could be built |
|---|---|---|
| HTTPS | Mostly as the finding records (the name blocklist is from `west.yml`, and the finding says that narrowing "has not been tried"). No public composition: the web start function and the certificate start function are in private headers, and the web adapter's include directory is offered only through an interface target that is marked "only for a composition". Licensing: Mbed TLS and TF-PSA-Crypto are stated as Apache-2.0 OR GPL-2.0-or-later, which fits this Apache-2.0 repository under the Apache option, but Crux puts them in one optional group with the wolf projects (GPL or commercial), and this repository's import blocks those three by name. The Wolf profile also needs a Zephyr patch whose terms are unconfirmed, so it cannot be used here. | Certificate handling, the interface a listener binds, and what management load does to the control cycle. |
| Web page | The same as HTTPS. The finding speaks of "HTTPS web management" as one feature, and records no separate blocker for a page. | The same. |
| Serial command line | No public composition. Crux builds a command-line directory under a Kconfig option, but the finding reports that Crux's readiness document calls that directory compile evidence that links none of its code into an image. Licence is clear (Crux code under Apache-2.0). | A public composition, then an owner decision. |
| SSH command line | SSH is private to Crux, with no public header and no `crux::` target. It needs wolfSSH, wolfSSL and wolfPSA, which are GPL-3.0-or-later or commercial, and they stay off in default CI and in releases. | The licence question, which is not decided. |
| SFTP | The same as the SSH command line. | The same. |
| Access control | Crux's Access component has ports that a composition must list, and at the revision read "No product composition exists". It has no Kconfig symbol and no composition under Crux's Zephyr module directory. | A public composition and the first-account and key-registration decisions. |
| Credential store | In the group of Crux code with no public composition. Its licence is Apache-2.0. | A public composition. |
| Configuration service, network settings service | The finding groups "the management services" with the rest and records no public composition for them. It lists a persistence provider and a network apply port among the product's own work or open decisions in Crux's guide to management in a product. Whether those two items correspond one to one to these two services is not stated in this repository and was not verified. | A public composition and the product's providers. |
| Reboot on request | Not recorded as a finding; this is a reading of two notes. Crux System has a reset call (`crux_system_reset()`, named in the S4 note), and the S4 product deliberately never calls it: a missed watchdog feed ends in the watchdog's own reset. A reboot that a user or a remote party can ask for needs an interface to ask through and access control over it, and neither exists here. | An interface, access control, and a policy decision. |

What the finding says could be considered once a public composition exists and the owner approves it:
HTTPS on the Mbed profile, the serial command line, Access and its services, each as its own step with its
own resource row and tests first on `native_sim`. What it says is out of scope: GPIO, I2C and SPI, direct use
of Crux Thread, Sync, Queue and Serial, Reliance Edge, and any firmware image in public form. These are
the recorded positions, not commitments.

A separate question is how the platform request itself is filed. The finding records that nothing has been
filed in `crux-pilot` and that filing needs the owner's approval. Stage 2 steps and their findings are
tracked in this repository's own issues, with the epic
[wonny-labs/crux-controller#44](https://github.com/wonny-labs/crux-controller/issues/44) as the top.

## Also not done

- A release, a tag or a published image. The release flow runs only as a dry run, and images are never
  published, only hashes.
- A board run of S0, of S1 alone, of S3, of S4 or of S5, and any run after a cold power cycle.
- Run-time measurement: the budget job measures static size only.
- A firmware image, `.elf` or `.map` in the repository, a bundle or a CI artifact: this is a rule, not a
  gap.
