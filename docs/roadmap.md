# Roadmap and status

This page is the status page: what is built, what has run on a board, and what cannot be done yet and why. It
promises no dates and no features. "Not yet possible" does not mean "planned": the finding that covers most of
these says "Not decided and not scheduled: whether and when any of this is built here." The checks of a commit
and the [changelog](../CHANGELOG.md) are the reference when this page and a commit disagree. Terms such as
"owner" and "operator" are in the [glossary](glossary.md).

## Short version

- Eight build configurations, `minimal` to `base`, are on `main`. CI builds them for the NXP RT1060-EVKB Rev B
  and runs `native_sim` scenarios for `workload` to `base`. CI results change with every commit, so this
  page claims none; look at the checks of the commit you care about.
- **Only the `net` image has run on a physical board**, twice, on one bench
  ([what has run on a board](#what-has-run-on-a-board)).
- The `management` image is HTTPS management on the Mbed TLS profile (Crux Access, the status and configuration
  services and a packaged page). It has no account, so nobody can log in to it: the first-account setup runs only
  in `base`. The base image composes web management, the serial command line, Access, the credential store, the
  status and configuration services, and the serial commands for reboot, recovery and factory reset behind a login.
  Both images are built in CI and run on `native_sim`; neither has run on a board. The SSH command line, SFTP, the
  network settings service and web routes for files and reboot are not built, and each has a recorded reason.
- The controller framework is a Zephyr module of this repository, and the base image (`base`) runs it with web
  management, the serial command line with its first-account setup, time synchronisation and health supervision
  (watchdog, boot counter, safe mode, retained last-fault record), and no application. The application interface
  (descriptor, channels, status items, parameters, data root, operator stop and start) is in the module at the lowest
  stability tier; a fixture application exercises it in `native_sim` scenarios only, and no product uses it yet.
- The application template (`template/`) is a folder that a product team copies once. A copy builds and runs on
  `native_sim` and builds for the board in the nightly checks; it has not run on a board.
- No readiness level of the [specification](design/controller-framework-spec.md#83-readiness-levels) is declared.
- There is no release and no tag.

## What is built

| Build configuration | What it adds | What the repository has for it | On a board |
|---|---|---|---|
| `minimal` | The clock of Crux Time answers | A CI build for the board. No scenario. | not run |
| `workload` | The synthetic workload on two Zephyr threads and a message queue in the adapter zone `app/os`, with Crux Time and Logging | A `native_sim` scenario that reads the logged messages from an emulated UART, host tests of the portable workload core, and a CI build for the board. | not run as an image of its own (the `net` image contains it) |
| `net` | Each message is also sent to a TCP peer over the Crux Sockets profile | A `native_sim` scenario over loopback (it needs the test-only `picolibc` project), host tests of the exchange against a loopback peer, a CI build for the board. | ran twice, on one bench |
| `file` | The configuration record is kept in a file through Crux File, mounted by the composition zone | A `native_sim` scenario with the simulator provider on a RAM disk, and a CI build for the board with the FatFs provider on microSD. No card was used. | not run |
| `system` | The reset cause is logged at boot, and a watchdog is fed once for each pass of the workload that has cycles due, through Crux System | A `native_sim` scenario that shows the boot line and an unavailable watchdog (no feed cycle), host tests of the policy, and a CI build for the board with WDOG1 named by a devicetree alias. | not run |
| `sntp` | The Crux Time realtime clock is set from an SNTP server on the `net` network, by a low-priority thread, and a product policy decides what an answer may do | `native_sim` scenarios with a UDP responder on loopback, in seven cases (each case is its own image), host tests of the policy, and a CI build for the board on the `net` base. | not run |
| `management` | HTTPS management on the `net` network: Crux Access, the web server on the Mbed TLS profile, the status and configuration services and a packaged page, on a RAM disk | One `native_sim` image with ten ordered cases (a TLS 1.3 handshake that an in-process client verifies, the page bytes and the login path up to a rejected attempt), host tests of the address parser, and a CI build for the board with the Mbed TLS group switched on in its own runner. No account and no successful login. | not run |
| `base` | The base image: the controller framework from the Zephyr module, with web management (as `management`), the serial command line on LPUART3 (alias `crux-serial0`), time synchronisation (as `sntp`) and health supervision with WDOG1 and a retained region in OCRAM2, on the network of `net`, on a RAM disk, and no workload | One `native_sim` image with eleven ordered cases that builds the framework from the module and runs its start function (each step reported, a second start refused, the listener accepting a connection, on an emulated UART the console's prompt, a refused login without accounts, the first-account setup, a refused second setup and a login that runs a command, and the start order and degraded state of supervision with no watchdog); two `native_sim` scenarios over several restarts of the simulated process (a stalled step, a fatal error, stalled framework threads, safe mode and its exit; a software reset with no watchdog); host tests of the startup sequence, the reset rules, the supervision decisions and the states; and a CI build for the board with the Mbed TLS group switched on in its own runner. | not run |

The pinned Crux has a simulated `native_sim` watchdog (`CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG`). The `system`
scenario does not enable it, so it shows no feed cycle; the framework scenario `tests/framework/recovery` uses it.

Around the configurations:

- The boundary check (`scripts/check_boundary.py`) with the zones `app/os`, `framework/compose` and
  `framework/os`, the portable core `framework/src` and the interface header in `include/`.
- Declared resource limits for `minimal` to `base` (`budgets/limits.json`), which are placeholders, checked in
  CI against static size only. Stack use, heap use and timing are not measured.
- Release tooling and a dry run that publishes nothing, a rebuild comparison at another path, and a daily
  build against the current Crux `main` that is information only.
- The findings notes are listed in the [findings index](findings/README.md).

## Static size per configuration

The `Budget` job builds each configuration for the RT1060-EVKB and reads the Zephyr memory region table. The
numbers below are the `FLASH` and `RAM` rows of that table, in bytes used, as the `Budget` jobs print them. They
were read from the job logs of the `budget` workflow at `b407d2c4` (a revision of the public repository, at the
current Crux pin). The region sizes are the ones that the table prints: `FLASH` 8 MB and `RAM` 32 MB. The `Budget`
jobs of a commit give its current sizes.

| Build configuration | FLASH used (bytes) | FLASH of region | RAM used (bytes) | RAM of region |
|---|---|---|---|---|
| `minimal` | 34556 | 0.41 % | 4416 | 0.01 % |
| `workload` | 42268 | 0.50 % | 22784 | 0.07 % |
| `net` | 105412 | 1.26 % | 72044 | 0.21 % |
| `file` | 71760 | 0.86 % | 27168 | 0.08 % |
| `system` | 47016 | 0.56 % | 22848 | 0.07 % |
| `sntp` | 110656 | 1.32 % | 82428 | 0.25 % |
| `management` | 299488 | 3.57 % | 1268788 | 3.78 % |
| `base` | 342556 | 4.08 % | 1275832 | 3.80 % |

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

## What has run on a board

Only the `net` image has run on a board: twice, on one RT1060-EVKB Rev B on one bench, with the same image and the
same gated procedure, and the board was restored to the accepted normal image afterwards. Both runs saw the
Ethernet link come up without the MDIO correction that the Crux sample applies, ping answered 5 of 5 times, and one
TCP exchange with a host peer was echoed; the exchange was informational, not a pass criterion. Two boots on one
bench are evidence collection, not qualification: they show nothing about another board or bench, a cold power
cycle, run-time values or a repeated exchange. The record, with its full "Not shown" list, is
[docs/findings/s2-first-board-run.md](findings/s2-first-board-run.md). The dates of the runs are in
[history](history/board-runs-and-tracking.md).

No `minimal`, `workload`-only, `file`, `system`, `sntp`, `management` or `base` image has run on a board. No release exists, so no
released image has run anywhere. A green `native_sim` run is not a board run and a CI build is not a board run.

## What is not yet possible, and why

Everything below is a Crux management feature or something around one. The licence facts and the SSH and SFTP
reasons are from [docs/findings/management-has-no-public-composition.md](findings/management-has-no-public-composition.md),
which was read against a Crux revision other than the pin (its own "State at the pin" section says so). The
composition state is from the code at the current pin; [docs/findings/s6-https-management.md](findings/s6-https-management.md)
records how `management` was built.

The boundary check (`scripts/check_boundary.py`) lets the composition zones include five named Crux composition
interfaces: `<crux/file_zephyr.h>`, `<crux/web_zephyr.h>`, `<crux/cli_zephyr.h>`,
`<crux/service_priority_zephyr.h>` and `<crux/credential_store_zephyr.h>`. Every other Crux private, port or
composition header stays blocked, and each new entry is a separate reviewed change
([composition zone](composition-zone.md)). A feature that needs any other private header waits until Crux offers a
public way.

| Feature | State on `main` | Still open |
|---|---|---|
| HTTPS | Composed in `management` and `base` by `framework/compose/management_start.c`, through `<crux/web_zephyr.h>` and the public TLS certificate start. Built in CI and run on `native_sim`; a login over HTTPS succeeds only in the `native_sim` scenario with the fixture application. Licensing: Mbed TLS and TF-PSA-Crypto are stated as Apache-2.0 OR GPL-2.0-or-later, which fits this Apache-2.0 repository under the Apache option, but Crux puts them in one optional group with the wolf projects (GPL or commercial), and this repository's import blocks those three by name. The Wolf profile also needs a Zephyr patch whose terms are unconfirmed, so it cannot be used here. | A board run; device preparation of the key and certificate (specification section 5.5); what management load does to the control cycle. |
| Web page | The packaged page of `framework/management/`, served with HTTPS. | The same as HTTPS. |
| Serial command line | Composed in `base` by `framework/compose/cli_start.c`, through `<crux/cli_zephyr.h>`, on the UART of the alias `crux-serial0`, with an Access login on every command except the login and first-account setup. Licence is clear (Crux code under Apache-2.0). | A board run; its use in production is a product decision (D16). |
| SSH command line | SSH is private to Crux, with no public header and no `crux::` target. It needs wolfSSH, wolfSSL and wolfPSA, which are GPL-3.0-or-later or commercial, and they stay off in default CI and in releases. | The licence question, which is not decided, and the Crux changes of gap C7. |
| SFTP | The same as the SSH command line. | The same. |
| Access control | Composed in `management` and `base` through `<crux/access.h>`. In `base`, the first account is set up over the serial command line; a second setup is refused. | A board run; no route or command creates a further account (gap C21). |
| Credential store | Composed in `management` and `base` through `<crux/credential_store.h>`; the factory reset erases the accounts through `<crux/credential_store_zephyr.h>`. Its licence is Apache-2.0. | Storage on the product medium; on the board images it is on FatFs (gap C4). |
| Configuration service | Composed in `management` and `base` through `<crux/config_service.h>`; parameters are shown and changed through web management. | Saving: the framework does not yet initialise Crux's Settings File provider, so nothing is persistent (gaps C4 and C22). |
| Network settings service | Not composed: the framework starts neither the service nor its worker. | Applying changed settings needs an apply port of the framework and the save provider (specification section 8.2, later items). |
| Reboot on request | The `base` image has the serial commands `reboot`, `recovery clear`, `recovery exit` and `factory reset`, each behind an Access login and a permission, through Crux Reboot (`framework/compose/supervision_start.c`). The `system` capability still never calls `crux_system_reset()`: a missed watchdog feed ends in the watchdog's own reset. | A web route for reboot is not built. |

What the finding says is out of scope: GPIO, I2C and SPI, direct use
of Crux Thread, Sync, Queue and Serial, Reliance Edge, and any firmware image in public form. These are
the recorded positions, not commitments.

Nothing has been filed in Crux, and filing a request there needs the owner's approval. How the work
was tracked is in [history](history/board-runs-and-tracking.md).

## Also not done

- A release, a tag or a published image. The release flow runs only as a dry run, and images are never
  published, only hashes.
- A board run of `minimal`, of `workload` alone, of `file`, of `system`, of `sntp`, of `management` or of `base`, and any run
  after a cold power cycle.
- Run-time measurement: the budget job measures static size only.
- A firmware image, `.elf` or `.map` in the repository, a bundle or a CI artifact: this is a rule, not a
  gap.
