# Glossary

Each entry says how this repository uses the word, with the file where the use can be checked. Where
the repository is not consistent, the entry says so. Start with the [README](../README.md) and the
[architecture](architecture.md) if the terms are new. The sections are: product, platform and
composition; capabilities and build configurations; boundary and zones; build, pin and evidence; time; people and board
procedures; terms from outside this repository; and wording that differs between files.

## Product, platform and composition

**Product.** Crux's sense: a firmware repository outside this repository that is built on Crux, imports the
[controller framework](#capabilities-and-build-configurations) and adds its application, as the product
composition guide describes (`docs/product-composition.md` of Crux at the pinned revision). This
repository is not a product. In source comments and build files, "product code", a "product-owned" header (one
that this repository's code declares), the "product's" Kconfig symbols (`CRUX_CONTROLLER_`) and the "product's"
policy mean this repository's own code, as opposed to the Crux platform code that `west.yml` imports.

**Platform.** Crux, the embedded software platform that lives in the repository `crux`. "Crux Platform"
(the [README](../README.md) role sentence), "the platform" and "a platform milestone" all mean Crux and the
work in its repository. They do not mean Zephyr, which is the RTOS that Crux integrates, and they do not mean
this firmware.

**Composition.** The word has four meanings here. The context says which one is meant:

1. Crux's word, for the board- or project-specific configuration and initialisation that choose OS
   implementations and bind hardware resources (Kconfig, providers, device bindings). The concepts glossary of
   Crux defines it (`docs/README.md` at the pinned revision). The finding titles that say "composing File"
   or "composing Crux System" use the verb in this sense.
2. The [composition zone](#boundary-and-zones), the directory `framework/compose`, where this repository holds the
   product code that does that for File and for HTTPS management.
3. A [composition interface](#boundary-and-zones), a Crux header such as `<crux/file_zephyr.h>` that only
   composition code may include.
4. `app/src/composition.c`, with `composition_start()`. It starts the capabilities that a build selected. It is not
   the composition zone and it includes no composition interface.

## Capabilities and build configurations

**Capability.** One thing that the firmware shows a product how to do with Crux, such as a TCP exchange over the
Sockets profile or a watchdog through Crux System. Each capability has one *build configuration*.

**Controller framework.** The Zephyr module of this repository (`zephyr/module.yml`): the start function
`controller_framework_start()` of `<controller/framework.h>`, which composes the Crux services of a networked
controller in a defined order. One Kconfig symbol, `CRUX_CONTROLLER_FRAMEWORK`, turns it on. Its sources are
in `framework/` and its interface headers in `include/`.

**Base image.** The image of this repository that runs the controller framework with no application: the build
configuration `base`.

**Build configuration.** A named set of Kconfig fragments and devicetree overlays that builds one image, `minimal`
to `base`. Each configuration from `workload` to `management` has a Kconfig option (`CRUX_CONTROLLER_WORKLOAD` to
`CRUX_CONTROLLER_MANAGEMENT` in `app/Kconfig`), a fragment (`app/conf/<name>.conf`), a CI build job named after it
(for example `system build (RT1060-EVKB, System)`), its own row in the `Budget` matrix and in
`budgets/limits.json`, and a row in the README table. `base` has the fragment `app/conf/base.conf`, which turns
on the framework's symbol.

| Build configuration | What it adds |
|---|---|
| `minimal` | The clock of Crux Time answers. No option and no fragment: it is `app/prj.conf` alone. |
| `workload` | The synthetic workload on two Zephyr threads and a message queue (the adapter zone), with Crux Time and Logging. |
| `net` | Each workload message is also sent to a TCP peer over the Crux Sockets profile. |
| `file` | The workload's configuration record is kept in a file through Crux File, on a microSD volume mounted by the composition zone. |
| `system` | The reset cause is logged at boot and a watchdog is fed once for each pass of the workload that has cycles due, through Crux System. |
| `sntp` | The Crux Time realtime clock is set from an SNTP server on the `net` network, with a product policy for what an answer may do. |
| `management` | Management over HTTPS on the `net` network: Crux Access, the web server on the Mbed TLS profile, the status and configuration services and a packaged page, on a RAM disk, with no account until the first-account console exists. |
| `base` | The base image: the controller framework with web management and time synchronisation on the network of `net`, on a RAM disk, with no workload and no application. |

`net`, `file` and `system` each depend on `workload` in Kconfig and are built on top of `conf/workload.conf`. `sntp`
depends on `net` (and so on `workload`) and is built on `conf/workload.conf;conf/net.conf;conf/sntp.conf`.
`management` depends on `net` too, excludes `file` and `system` in Kconfig, and is built on
`conf/workload.conf;conf/net.conf;conf/management.conf`. "Built on" therefore means "depends on" another
configuration. CI builds each configuration as its own image and never combines `net`, `file` and `system`. What
each one has and has not run is in [roadmap.md](roadmap.md), and the procedure for adding one is in
[adding-a-capability.md](adding-a-capability.md).

**Step.** In a CI workflow, one entry of a job (`ci.yml`, `budget.yml`). In `RELEASE.md` the table "Step, Tool,
What fails the run" lists the actions of the release dry run. The notes in `docs/findings/` and `docs/history/`
also use step ids, S0 to S6, for the build configurations; the [findings index](findings/README.md) maps each id
to its name.

**Stage.** A planning label that the notes in `docs/findings/` and `docs/history/` use for phases of the repository's own work. It is not a property of the code, and no current
document defines it. `docs/findings/s2-first-board-run.md` says "an earlier platform stage", which means a phase
of Crux. How the stages were tracked is in [history](history/board-runs-and-tracking.md).

## Boundary and zones

**Boundary.** The include rules of the source trees, enforced by `scripts/check_boundary.py` in the CI
job `Boundary check`. There is no exception, waiver or per-file opt-out.

**Product include check.** The second include check of the `Boundary check` job: the script
`templates/product/check_domain_includes.py` of Crux, run in product mode. These documents call it "the
product include check". In product mode it fails on an include of one of the three frozen headers, or of the removed
`<crux/queue.h>`, in any C or C++ source under the repository, tests included. CI runs it twice: from a downloaded copy of the script, and through
the wrapper `check-includes.sh` of Crux, which calls the same script. The first check, `scripts/check_boundary.py`,
belongs to this repository. See [composition-zone.md](composition-zone.md#running-the-check).

**Adapter zone.** The directories `app/os` and `framework/os`, the places that create threads, queue messages and
sleep, using Zephyr kernel calls directly, and query an SNTP server. `app/os` implements the port header
`app/src/workload_os.h`, and `framework/os` the port header `framework/src/time_sync_port.h`. Each may
include exactly two Zephyr headers, `zephyr/kernel.h` and `zephyr/net/sntp.h` (`OS_ADAPTER_ZEPHYR_HEADERS`
in `scripts/check_boundary.py`), and no Sockets profile, POSIX or composition header.
`framework/os/time_sync_zephyr.c` includes the SNTP header. See [composition-zone.md](composition-zone.md).

**Composition zone.** The directory `framework/compose`. The one place that mounts a file system and binds it
to Crux File with the composition interface `<crux/file_zephyr.h>`, and the place that starts HTTPS management with
the Web composition interface `<crux/web_zephyr.h>` (`management`). It may include three Zephyr headers,
`zephyr/fs/fs.h`, `zephyr/devicetree.h` and `zephyr/net/tls_credentials.h`. It implements the port headers `framework/src/storage_port.h` and `framework/src/management_port.h` (`management`).
"Composition" has [four meanings](#product-platform-and-composition). Here the composition zone holds the
product code that does what Crux calls composition (meaning 1) for File and for HTTPS management. Do not confuse
`app/src/composition.c`, which starts the capabilities, with the zone.

**Composition interface.** A Crux header that names a provider and is meant for composition code only,
for example `<crux/file_zephyr.h>` with the CMake target `crux::file_zephyr`, or `<crux/web_zephyr.h>`
with `crux::web_zephyr`. Crux publishes these
under `components/*/ports/*/include/crux/`, apart from the public headers. `app/src` and `workload/` may
not include one.

**Port header.** A header that `app/src` or the framework core `framework/src` declares and a zone implements:
`app/src/workload_os.h` (implemented in `app/os`), `framework/src/time_sync_port.h` (implemented in
`framework/os`), and `framework/src/storage_port.h` and `framework/src/management_port.h` (both implemented in
`framework/compose`). It includes ISO C only, so it stays inside the rules of its tree. The declaring code calls
it; the linker joins the two sides.

**Frozen headers.** The three public Crux headers `<crux/thread.h>`, `<crux/sync.h>` and `<crux/serial.h>`
(`FROZEN_CRUX_HEADERS` in `scripts/check_boundary.py`). `app/src` and `app/os` fail on them although they
are public, because the product uses Zephyr directly for threads and queues. Crux marks these headers
"frozen for new product code": no new features, existing users keep working, and any deprecation waits for a
separate decision (concepts glossary, `docs/README.md` of Crux at the pinned revision). This
repository's rule goes further and refuses them in `app/src` and `app/os`. Crux publishes no `<crux/queue.h>` at
the pinned revision, so it is not on the list; the check refuses it with `--crux-root` as a name that Crux does not
publish.

**Sockets profile.** The set of standard POSIX socket headers that Crux's networking contract lists
(`SOCKET_PROFILE` in `scripts/check_boundary.py`: `sys/socket.h`, `netinet/in.h`, `arpa/inet.h`,
`poll.h`, `fcntl.h`, `unistd.h`, `errno.h`, `time.h`). `app/src` may include them, and `net`'s
`net_client.c` does. The Crux targets are `crux::sockets` and `crux::netif`. `app/os`, `framework/compose`
and `workload/` fail on the ones that are not ISO C headers. `errno.h` and `time.h` are also ISO C headers,
so they are allowed in every tree (`app/os/workload_os_zephyr.c` includes `<errno.h>`).

**Workload.** The synthetic program the firmware runs: a validated configuration record, a periodic
cycle that catches up after a stall, and an eight-byte message. The portable part is the directory
`workload/`. It is written for this repository and contains no product logic.

## Build, pin and evidence

**Baseline gate.** The CMake option `-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`, which every CI build of the
board image passes. It makes the Crux module refuse a Zephyr that is not the verified baseline
(`RELEASE.md`, the Build row). The gate is in Crux, not here. One quirk is recorded in
`docs/findings/s3-file-composition.md` (friction 5): CMake prints that the variable was "not used by the
project" even when the gate passes.

**Workspace.** The west workspace: the parent folder that holds the clone `crux-controller` next to `.west/` and
the projects that `west.yml` fetches (`zephyr/`, `modules/`, `crux/`). The Dev Container mounts it at
`/workspaces/ws`. Crux's Getting started (`docs/getting-started.md` of Crux at the pinned revision) also calls
the parent folder of the clone the workspace.

**Dev Container.** The Docker image in `.devcontainer/` with the tools of the CI jobs, an Ubuntu 24.04 userland and
Python 3.12, plus the script that fetches the workspace and the Zephyr SDK. It is opened through
`scripts/dev-shell.sh` or the VS Code Dev Containers extension ([Getting started](getting-started.md#dev-container)).

**Host tests.** The plain C tests of `tests/host`, built with CMake and run with CTest on the build machine, with no
Zephyr. Crux calls the matching environment the Linux Host; here the same tests also run on macOS.

**Pin.** The full commit of Crux that `west.yml` imports; the `revision` of the `crux` project
there is the current pin. It is a commit and never a branch or a tag; no Crux tag exists. `west crux-pins`
checks it in CI. A pin moves in its own pull request. See the pin section of
[CONTRIBUTING.md](../CONTRIBUTING.md).

**Hashes and numbers.** Short hashes, pull request numbers and issue numbers (for example "pull request 50",
"#44") name the history of the public repositories `wonny-labs/crux-controller` and `wonny-labs/crux` on
GitHub. The facts that matter are stated in the text next to them, and the documents do not depend on the content
of an issue.

**Finding.** A note under `docs/findings/` that records what building a capability or asking a question taught
about the product's use of Crux. Each statement in a finding carries a label, and the label set differs by note: Measured, Inferred and Open
(the `file` note, where "Measured" means that a CI job produced the result), Measured, Inferred, Recorded and Open
(the `system` and `sntp` notes, where "Measured" means that it was run locally while the note was written), Verified,
Inferred and Not verified (the `management` groundwork note), Verified, Inferred, Recorded and Open (the `management` composition note), and
Measured and Not shown (the `net` board-run note). "Recorded" is a CI result read from the job logs at a named revision. A finding is kept as written: when the pin or the facts
move, a later result is added as a dated update or a banner and the recorded reading is not rewritten, so each
note names the revision it was read at.

**Budget.** The static resource check. The `Budget` job in `.github/workflows/budget.yml` builds each
configuration, reads the memory region table and the ROM and RAM reports, and `budgets/check.py` compares them
with `budgets/limits.json`, which declares a minimum percentage of free space per region for each
configuration (placeholder values, 25 percent). It measures size only, not stack use, heap use or timing. A new
configuration needs a row in the limits file first, because the checker fails one that has none.

**`native_sim`.** Zephyr's simulated board, run on the build host as an ordinary program with emulated devices
instead of hardware: no Ethernet PHY, no microSD card, no watchdog peripheral and no RT1060 is involved. CI runs
the scenarios in `tests/native_sim` (one directory per configuration from `workload` to `sntp`) and `tests/native_sim_mbed` (`management`, which
needs the Mbed TLS modules of the Crux manifest and has its own CI job) with Twister for `native_sim/native/64`. Each scenario is a Zephyr ztest application
that compiles chosen sources of `app/` and `workload/`; none boots the board image. A `native_sim`
pass is not evidence about the board: for example `system`'s scenario does not enable the simulated watchdog of the pinned
Crux, so no feed cycle is shown there.

**EVKB.** Short for the board the repository targets, written "NXP RT1060-EVKB Rev B" in prose and
"RT1060-EVKB" in CI job names. CI passes it to `west build` as `mimxrt1060_evk@B//qspi`. In Zephyr's board naming that is the board
`mimxrt1060_evk`, its revision `B` (`@B`) and the variant `qspi`, with the default SoC left out between the two
slashes. An "EVKB build" in this repository means a cross-compile in CI. It never means a run.

**Scenario.** One Zephyr test application under `tests/native_sim/<name>` (`management`: `tests/native_sim_mbed/management`, which needs the Mbed TLS modules), with a `testcase.yaml` for
Twister. `file`, `system` and `sntp` select one case per image through a build variable (`FILE_CASE`, `SYSTEM_CASE`,
`SNTP_CASE`), because File can be bound and the watchdog started once per boot, and because the `sntp` test's
CMake file notes that Crux Time keeps its state for the whole run.

## Time

**Time Authority.** The part of a product that owns the realtime clock of Crux Time. Crux's Time contract
(`docs/time-contract.md` of Crux at the pinned revision) says that the designated product Time Authority
coordinates native clock changes with any external time manager and owns source selection and stale
synchronisation callbacks, and that the authority header is not a runtime permission mechanism. That is why
Crux provides no SNTP client: the product chooses the time source ([composition-zone.md](composition-zone.md)).
In code, `framework/src/time_sync.c` (`sntp`) is the one file that calls the Crux Time authority
(`<crux/time_authority.h>`, with `crux_realtime_set()`).

## People and board procedures

**Owner.** Whoever owns this repository on GitHub: the account in `CODEOWNERS`. The documents reserve to the
owner: merging a pull request, tags, GitHub Releases and forks (`CONTRIBUTING.md`), the release approval in
`RELEASE.md`, filing a request in Crux, and any run on a board (`docs/board-bring-up.md`). A review
`PASS` or a green CI result informs these decisions and does not make them. No rule reserves a change of the pinned
Crux revision to the owner; in practice the owner has approved each one (`west.yml` and
`tests/tooling/test_manifest.py` record the approval of the current pin). "The project owner" and "the
repository owner" (the wording of `RELEASE.md` and `SECURITY.md`) mean the same role.

**Maintainer.** Not a separate role. The `net` board-run note says "the repository maintainer" and means the owner.
No document gives rights to a "maintainer", and `CODEOWNERS` lists one account for every file.

**Reviewer.** Someone who did not write the change and who reads the actual files and the check results, as
`CONTRIBUTING.md`, section "Review", describes. The checklist is in [reviewing.md](reviewing.md).

**PASS, REVISE and ESCALATE.** The three results of an independent review, defined in `CONTRIBUTING.md`,
section "Review". A blocking finding is an unmet acceptance criterion, a broken rule of that guide or a factual
error.

- `PASS`: there is no blocking finding.
- `REVISE`: there are blocking findings that the author can fix. The author fixes them and gets one re-check.
- `ESCALATE`: the owner has to decide.

Other findings go in the pull request. A `PASS` does not grant merge, scope, hardware or release authority:
merging a pull request needs the owner's approval. A review finding is not the same thing as a *finding* under
`docs/findings/` (see Finding above).

**Files that need a reviewed change.** This repository's term for the files whose change a reviewer must look at
with care, because they hold the checks, the boundary lists, the pin, the limits or the rules. The list is in
[adding-a-capability.md](adding-a-capability.md#files-that-need-a-reviewed-change). `CONTRIBUTING.md` is the authority for
that list, and it states a rule for some of the files and none for the others. Other projects call such files
"protected"; this repository does not use that word.

**Operator.** The person who runs a board procedure on a bench, under the owner's approval for that task. The
`net` board-run note uses the word for the person who ran the reviewed driver.

**Bench.** The physical setup of a board run: the board, its probe and UART adapter, the Ethernet cable and the
host peer. "Two runs on one bench" means the same board and the same setup both times.

**Gated procedure.** The fixed sequence of the `net` board runs: identify the board, program it, run the host checks,
restore. Its approvals and guard checks are recorded in `docs/findings/s2-first-board-run.md`, "Method". The
procedure and its driver are
not in this repository: the driver is the Crux target test driver, and the run records are kept privately.

**Accepted normal image.** The firmware that was on the board before a run and that the procedure puts back and
verifies afterwards. It is not part of this repository. The `net` note records its SHA-256 and size.

## Terms from outside this repository

**west.** Zephyr's tool for workspaces, builds and tests. A west manifest (`west.yml`) lists the projects of a
workspace and their revisions; a manifest group filter switches optional groups of projects on or off. This
repository uses `west init -l`, `west update`, `west build` and `west twister`.

**Twister.** Zephyr's test runner (`west twister`). It builds and runs the scenarios that `testcase.yaml` files
describe.

**ztest.** Zephyr's test framework. Each `native_sim` scenario is a ztest application.

**Provider.** The implementation behind a Crux interface for one environment, for example a Zephyr provider
(Crux concepts glossary, `docs/README.md` of Crux).

**Profile.** A named choice of what an interface is built on. The Sockets profile is the set of POSIX socket
headers above. The Mbed TLS profile selects Mbed TLS for HTTPS; Crux's other TLS profile uses the wolf projects, which
this repository does not fetch.

**SNTP.** The Simple Network Time Protocol: a client asks a server for the time over UDP (port 123). A
kiss-o'-death answer is one in which the server tells the client to stop or slow down; `sntp` never sets the clock from one.

**WDOG1.** The watchdog peripheral of the RT1060 that the `system` capability uses. The overlay `app/boards/system.overlay` names it
with the alias `crux-watchdog0`.

**HWINFO.** Zephyr's hardware information API. Crux System reads the reset cause through it.

**RAM disk.** A Zephyr disk that keeps its data in RAM, so nothing survives a reset. The `file` scenario and the `management`
image use it as their medium.

**FatFs.** The FAT file system library (ChaN) that the board build of `file` uses on a microSD card.

**SBOM and SPDX.** A software bill of materials lists the components of a build; SPDX is a file format for it. The
release dry run produces SPDX files from `west spdx` and parses them (`RELEASE.md`).

**PHY and MDIO.** The PHY is the Ethernet physical-layer chip on the board. MDIO is the management interface
through which the Ethernet controller configures it. The Crux reference composition applies an "MDIO completion
correction" that the `net` image does not (`app/conf/net.conf`); the `net` board runs show the link coming up without it.

**Friction.** A heading used in findings for a point where using the public Crux interface took extra work, was
unclear or was blocked.

**Mutation run.** A check of a test: change the code on purpose and see whether the test fails. The `sntp` note records
five such runs of the time policy.

## Wording that differs between files

These are differences that a reader may trip over. Each is explained here and the files are kept as they are.

- The comments at the top of `app/conf/file.conf` and `app/conf/system.conf` say that `file` and `system` are built on `workload` without the
  other configurations. That agrees with `app/Kconfig`, which says that `net`, `file` and `system` build on `workload` and `sntp` on `net`.
- The CI job named `workload (native_sim and RT1060-EVKB)` in `ci.yml` also runs the `native_sim`
  scenarios of `net`, `file`, `system` and `sntp`, because it runs every scenario under `tests/native_sim`.
