# Roadmap and status

This page is the status page: what is built, what has run on a board, and what cannot be done yet and why. It
promises no dates and no features. "Not yet possible" does not mean "planned": the finding that covers most of
these says "Not decided and not scheduled: whether and when any of this is built here." The checks of a commit
and the [changelog](../CHANGELOG.md) are the reference when this page and a commit disagree. Terms such as
"owner" and "operator" are in the [glossary](glossary.md).

## Short version

- Seven build configurations, `base` to `management`, are on `main`. CI builds them for the NXP RT1060-EVKB Rev B
  and runs `native_sim` scenarios for `workload` to `management`. CI results change with every commit, so this
  page claims none; look at the checks of the commit you care about.
- **Only the `net` image has run on a physical board**, twice, on one bench
  ([what has run on a board](#what-has-run-on-a-board)).
- One management feature is wired: HTTPS management on the Mbed TLS profile (`management`, with Crux Access, the
  status and configuration services and a packaged page). It is built in CI and has never run on a board, and
  the image has no account, so nobody can log in until the first-account console exists. The serial and SSH
  command lines, SFTP, network settings, file and reboot routes are not built, and each has a recorded reason.
- There is no release and no tag.

## What is built

| Build configuration | What it adds | What the repository has for it | On a board |
|---|---|---|---|
| `base` | The clock of Crux Time answers | A CI build for the board. No scenario. | not run |
| `workload` | The synthetic workload on two Zephyr threads and a message queue in the adapter zone `app/os`, with Crux Time and Logging | A `native_sim` scenario that reads the logged messages from an emulated UART, host tests of the portable workload core, and a CI build for the board. | not run as an image of its own (the `net` image contains it) |
| `net` | Each message is also sent to a TCP peer over the Crux Sockets profile | A `native_sim` scenario over loopback (it needs the test-only `picolibc` project), host tests of the exchange against a loopback peer, a CI build for the board. | ran twice, on one bench |
| `file` | The configuration record is kept in a file through Crux File, mounted by the composition zone | A `native_sim` scenario with the simulator provider on a RAM disk, and a CI build for the board with the FatFs provider on microSD. No card was used. | not run |
| `system` | The reset cause is logged at boot, and a watchdog is fed once for each pass of the workload that has cycles due, through Crux System | A `native_sim` scenario that shows the boot line and an unavailable watchdog (no feed cycle), host tests of the policy, and a CI build for the board with WDOG1 named by a devicetree alias. | not run |
| `sntp` | The Crux Time realtime clock is set from an SNTP server on the `net` network, by a low-priority thread, and a product policy decides what an answer may do | `native_sim` scenarios with a UDP responder on loopback, in seven cases (each case is its own image), host tests of the policy, and a CI build for the board on the `net` base. | not run |
| `management` | HTTPS management on the `net` network: Crux Access, the web server on the Mbed TLS profile, the status and configuration services and a packaged page, on a RAM disk | One `native_sim` image with ten ordered cases (a TLS 1.3 handshake that an in-process client verifies, the page bytes and the login path up to a rejected attempt), host tests of the address parser, and a CI build for the board with the Mbed TLS group switched on in its own runner. No account and no successful login. | not run |

The pinned Crux has a simulated `native_sim` watchdog (`CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG`). The `system`
scenario does not enable it, so it shows no feed cycle. Using it is not decided or scheduled.

Around the configurations:

- The boundary check (`scripts/check_boundary.py`) and two zones, `app/os` and `app/compose`.
- Declared resource limits for `base` to `management` (`budgets/limits.json`), which are placeholders, checked in
  CI against static size only. Stack use, heap use and timing are not measured.
- Release tooling and a dry run that publishes nothing, a rebuild comparison at another path, and a daily
  build against the current `crux-pilot` main that is information only.
- The findings, one per capability where building it taught something, are listed in the
  [findings index](findings/README.md).

## Static size per configuration

The `Budget` job builds each configuration for the RT1060-EVKB and reads the Zephyr memory region table. The
numbers below are the `FLASH` and `RAM` rows of that table, in bytes used, as the `Budget` jobs print them. They
were read from the job logs of the `budget` workflow at `26c78a3` and at `8d47942d` (revisions of the public
repository), which printed the same values. The region sizes are the ones that the table prints: `FLASH` 8 MB
and `RAM` 32 MB. Both revisions are older than the current pin; the `Budget` jobs of a commit give its current
sizes.

| Build configuration | FLASH used (bytes) | FLASH of region | RAM used (bytes) | RAM of region |
|---|---|---|---|---|
| `base` | 32440 | 0.39 % | 4288 | 0.01 % |
| `workload` | 40720 | 0.49 % | 22656 | 0.07 % |
| `net` | 100748 | 1.20 % | 70508 | 0.21 % |
| `file` | 68296 | 0.81 % | 26656 | 0.08 % |
| `system` | 45236 | 0.54 % | 22720 | 0.07 % |
| `sntp` | 105984 | 1.26 % | 80876 | 0.24 % |
| `management` | 288984 | 3.44 % | 1265012 | 3.77 % |

**The declared limits are placeholders, and the run-time values are not measured.** `budgets/limits.json` asks
for at least 25 percent free in every region, which is a placeholder and not a derived figure; every
configuration uses far less than the 75 percent that the limit allows, so a pass says that the image fits the
placeholder and says nothing about margins in a product. These are static sizes of the linked image. Stack use,
heap peaks and timing are not measured by any job. The sizes change with the pinned Crux revision, with Kconfig
and with the code.

The `net` image that CI built at `8d47942d` has the `zephyr.bin` SHA-256
`0551c82576b5b2edbe6e68eef6058882b8899a10119409cbe7c17d7c360d754b` and the `firmware_identity`
`8c66f4b5c269d56d8dad6f06032802283c99e66619cf976b76de35486024adf4`, as the release dry run job printed them at
that revision. This is not the image that ran on the board: the board runs used the `net` image with the
SHA-256 recorded in [docs/findings/s2-first-board-run.md](findings/s2-first-board-run.md), built at an earlier
Crux pin.

## What `sntp` does

What the code on `main` does, read from `app/Kconfig`, `app/src/time_sync*.c` and `app/os/time_sync_zephyr.c`:

- A low-priority thread (Zephyr priority 10) waits five seconds after start, then queries one IPv4 SNTP
  server and repeats after each interval. The defaults are the server `192.168.77.1` (the `net` peer), 600
  seconds between queries and a 3000 ms timeout for one query.
- The application's policy decides what an answer may do. It never sets the clock for a failed,
  kiss-o'-death or out-of-range answer. It sets any in-range answer while the clock is not synchronised, and
  corrects a synchronised clock for a difference from 100 ms up to 1000 ms. A larger difference is refused
  once and marks synchronisation lost. When a round fails or is out of range and the clock is synchronised, it is
  marked not synchronised if more than 1800 seconds have passed since the last good answer.
- The one caller of the Crux Time authority is `app/src/time_sync.c`. The Zephyr SNTP library is called only
  in the adapter zone, through `sntp_simple()`.
- Limits, as `docs/findings/s5-time-synchronisation.md` and the `app/Kconfig` help text state them: SNTP
  here is unauthenticated, so a server or anything on the path that answers with an in-range time can move
  the clock; the clock is stepped, not slewed; nothing persists time, so it is not valid after a reset
  until the first answer; the server must be an IPv4 address because the image has no DNS resolver; stack
  use of the thread and query timing are not measured.

**sntp has never run on a board.**

## What has run on a board

Only the `net` image has run on a board: twice, on one RT1060-EVKB Rev B on one bench, with the same image and the
same gated procedure, and the board was restored to the accepted normal image afterwards. Both runs saw the
Ethernet link come up without the MDIO correction that the Crux sample applies, ping answered 5 of 5 times, and one
TCP exchange with a host peer was echoed; the exchange was informational, not a pass criterion. Two boots on one
bench are evidence collection, not qualification: they show nothing about another board or bench, a cold power
cycle, run-time values or a repeated exchange. The record, with its full "Not shown" list, is
[docs/findings/s2-first-board-run.md](findings/s2-first-board-run.md). The dates of the runs are in
[history](history/board-runs-and-tracking.md).

No `base`, `workload`-only, `file`, `system`, `sntp` or `management` image has run on a board. No release exists, so no
released image has run anywhere. A green `native_sim` run is not a board run and a CI build is not a board run.

## What is not yet possible, and why

Everything below is a Crux management feature or something around one. The reasons are from
[docs/findings/management-has-no-public-composition.md](findings/management-has-no-public-composition.md)
unless another note is named. That note was read against a Crux revision other than the pin
(its own "State at the pin" section says so), so the reasons are not re-verified at the current pin.
This repository's boundary check keeps no exception, so a feature that needs a Crux private header is
blocked until Crux offers a public way, and nothing here will widen the check to get around it.

`management` composes HTTPS, the web page, Access, the credential store and the configuration service with
public Crux headers and targets, built in CI and never run on a board, with no account and no login shown. The
rows below keep what the earlier finding recorded at its own revision; the current state of those features, and
what is still open, is in [docs/findings/s6-https-management.md](findings/s6-https-management.md).

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
| Reboot on request | Not recorded as a finding; this is a reading of two notes. Crux System has a reset call (`crux_system_reset()`, named in the `system` note), and the `system` capability deliberately never calls it: a missed watchdog feed ends in the watchdog's own reset. A reboot that a user or a remote party can ask for needs an interface to ask through and access control over it, and neither exists here. | An interface, access control, and a policy decision. |

What the finding says could be considered once a public composition exists and the owner approves it:
HTTPS on the Mbed profile, the serial command line, Access and its services, each as its own capability with
its own resource row and tests first on `native_sim`. What it says is out of scope: GPIO, I2C and SPI, direct use
of Crux Thread, Sync, Queue and Serial, Reliance Edge, and any firmware image in public form. These are
the recorded positions, not commitments.

Nothing has been filed in `crux-pilot`, and filing a request there needs the owner's approval. How the work
was tracked is in [history](history/board-runs-and-tracking.md).

## Also not done

- A release, a tag or a published image. The release flow runs only as a dry run, and images are never
  published, only hashes.
- A board run of `base`, of `workload` alone, of `file`, of `system`, of `sntp` or of `management`, and any run
  after a cold power cycle.
- Run-time measurement: the budget job measures static size only.
- A firmware image, `.elf` or `.map` in the repository, a bundle or a CI artifact: this is a rule, not a
  gap.
