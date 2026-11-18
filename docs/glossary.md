# Glossary

Each entry says how this repository uses the word, with the file where the use can be checked. Where
the repository is not consistent, the entry says so. Start with the [README](../README.md) and the
[architecture](architecture.md) if the terms are new. The sections are: product, platform and
composition; steps and stages; boundary and zones; build, pin and evidence; time; people and board
procedures; terms from outside this repository; and wording that differs between files.

## Product, platform and composition

**Product.** In this repository, the firmware that this repository holds: the code in `app/` and
`workload/`, as opposed to the Crux platform code that `west.yml` imports. "Product code", a "product-owned"
header (one that the application declares), the "product's" Kconfig symbols and the "product's" policy all use the
word this way. It is not a product in the commercial sense: the [README](../README.md) says that the firmware
has no real control logic, there is no release and no support period is promised. Crux's own documents use
"product" for any firmware repository built on Crux, for example the product composition guide
(`docs/product-composition.md` of `crux-pilot` at the pinned revision). Both uses mean "firmware built on Crux".

**Platform.** Crux, the embedded software platform that lives in the repository `crux-pilot`. "Crux Platform"
(the [README](../README.md) role sentence), "the platform" and "a platform milestone" all mean Crux and the
work in its repository. They do not mean Zephyr, which is the RTOS that Crux integrates, and they do not mean
this firmware.

**Composition.** The word has four meanings here. The context says which one is meant:

1. Crux's word, for the board- or project-specific configuration and initialisation that choose OS
   implementations and bind hardware resources (Kconfig, providers, device bindings). The concepts glossary of
   `crux-pilot` defines it (`docs/README.md` at the pinned revision). The finding titles that say "composing File"
   or "composing Crux System" use the verb in this sense.
2. The [composition zone](#boundary-and-zones), the directory `app/compose`, where this repository holds the
   product code that does that for File and for HTTPS management.
3. A [composition interface](#boundary-and-zones), a Crux header such as `<crux/file_zephyr.h>` that only
   composition code may include.
4. `app/src/composition.c`, with `composition_start()`. It starts the steps that a build selected. It is not
   the composition zone and it includes no composition interface.

## Steps and stages

**Step.** A numbered increment of what the firmware does, written S0 to S6 on `main`. Each step after S0
has a Kconfig option (`CRUX_CONTROLLER_S1` to `CRUX_CONTROLLER_S6` in `app/Kconfig`), a configuration
fragment (`app/conf/s1.conf` to `s6.conf`), a CI build job (the S1 job is named `S1 (native_sim and RT1060-EVKB)`), its own row in the `Budget` matrix and
in `budgets/limits.json`, and a row in the README table.

| Step | What it adds |
|---|---|
| S0 | The clock of Crux Time answers. No option and no fragment: it is the base build. |
| S1 | The synthetic workload on two Zephyr threads and a message queue (the adapter zone), with Crux Time and Logging. |
| S2 | Each workload message is also sent to a TCP peer over the Crux Sockets profile. |
| S3 | The workload's configuration record is kept in a file through Crux File, on a microSD volume mounted by the composition zone. |
| S4 | The reset cause is logged at boot and a watchdog is fed once for each pass of the workload that has cycles due, through Crux System. |
| S5 | The Crux Time realtime clock is set from an SNTP server on the S2 network, with a product policy for what an answer may do. |
| S6 | Management over HTTPS on the S2 network: Crux Access, the web server on the Mbed TLS profile, the status and configuration services and a packaged page, on a RAM disk, with no account until the first-account console exists. |

S2, S3 and S4 each depend on S1 in Kconfig and are built on top of `conf/s1.conf`. S5 depends on S2
(and so on S1) and is built on `conf/s1.conf;conf/s2.conf;conf/s5.conf`. S6 depends on S2 too, excludes S3 and S4 in Kconfig, and is
built on `conf/s1.conf;conf/s2.conf;conf/s6.conf`. "Build on" in the
repository therefore means "depends on" a lower step. CI builds each step as its own image and never
combines S2, S3 and S4; the S5 and S6 images are built on S2 (and so on S1). What each step has and has not run is in [roadmap.md](roadmap.md), and the procedure for
adding one is in [adding-a-step.md](adding-a-step.md).

"Step" has two other meanings that share the word. In a GitHub Actions workflow a step is one entry of
a job (`ci.yml`, `budget.yml`). In `RELEASE.md` the table "Step, Tool, What fails the run" lists the
actions of the release dry run. The context says which one is meant.

**Stage.** A phase of the repository's own work, larger than a step. No document defines it; this entry
records how they use it. `docs/findings/management-has-no-public-composition.md` says it was
"recorded after Stage 1 step S3", so S3 is a Stage 1 step. The tracking paragraph of `README.md` says
that "Stage 2 steps and their findings" are tracked in the repository's own issues under an epic, and
lists S4 among the epic's children, so S4 is a Stage 2 step. Nothing places S5 in a stage: its README
text names no stage, and it arrived with
[pull request 50](https://github.com/wonny-labs/crux-controller/pull/50) of the public repository. The header
comment of `west.yml` ("No optional group is enabled in Stage 1") is historical. One use differs from the rest:
`docs/findings/file-binding-has-no-public-header.md` says S3 "is not built in Stage 1",
a note from before S3 was built. Treat the stage number as a label of when something was planned, not
as a property of the code. One other use is unrelated: `docs/findings/s2-first-board-run.md` says "an
earlier platform stage", which means a phase of Crux, not of this repository.

## Boundary and zones

**Boundary.** The include rules of the source trees, enforced by `scripts/check_boundary.py` in the CI
job `Boundary check`. There is no exception, waiver or per-file opt-out.

**Product include check.** The second include check of the `Boundary check` job: the script
`templates/product/check_domain_includes.py` of `crux-pilot`, run in product mode. These documents call it "the
product include check". In product mode it fails on an include of one of the four frozen headers in any C or C++
source under the repository, tests included. CI runs it twice: from a downloaded copy of the script, and through
the wrapper `check-includes.sh` of `crux-pilot`, which calls the same script. The first check, `scripts/check_boundary.py`,
belongs to this repository. See [composition-zone.md](composition-zone.md#running-the-check).

**Adapter zone.** The directory `app/os`. The one place that creates threads, queues messages and
sleeps, using Zephyr kernel calls directly, and queries an SNTP server for S5. It implements the port headers
`app/src/workload_os.h` and `app/src/time_sync_port.h`. It may
include exactly two Zephyr headers, `zephyr/kernel.h` and `zephyr/net/sntp.h` (`OS_ADAPTER_ZEPHYR_HEADERS`
in `scripts/check_boundary.py`), and no Sockets profile, POSIX or composition header. Of its two sources,
`app/os/time_sync_zephyr.c` (S5) includes the SNTP header. See [composition-zone.md](composition-zone.md).

**Composition zone.** The directory `app/compose`. The one place that mounts a file system and binds it
to Crux File with the composition interface `<crux/file_zephyr.h>`, and the place that starts HTTPS management with
the Web composition interface `<crux/web_zephyr.h>` (S6). It may include three Zephyr headers,
`zephyr/fs/fs.h`, `zephyr/devicetree.h` and `zephyr/net/tls_credentials.h`. It implements the port headers `app/src/storage_port.h` and `app/src/management_port.h` (S6).
"Composition" has [four meanings](#product-platform-and-composition). Here the composition zone holds the
product code that does what Crux calls composition (meaning 1) for File and for HTTPS management. Do not confuse
`app/src/composition.c`, which starts the steps, with the zone.

**Composition interface.** A Crux header that names a provider and is meant for composition code only,
for example `<crux/file_zephyr.h>` with the CMake target `crux::file_zephyr`, or `<crux/web_zephyr.h>`
with `crux::web_zephyr`. Crux publishes these
under `components/*/ports/*/include/crux/`, apart from the public headers. `app/src` and `workload/` may
not include one.

**Port header.** A header in `app/src` that the application declares and a zone implements:
`workload_os.h` and `time_sync_port.h` (both implemented in `app/os`), and `storage_port.h` and `management_port.h` (S6) (both implemented in `app/compose`). It includes
ISO C only, so it stays inside the rules of `app/src`. The application calls it; the linker joins the
two sides.

**Frozen headers.** The four public Crux headers `<crux/thread.h>`, `<crux/sync.h>`, `<crux/queue.h>`
and `<crux/serial.h>` (`FROZEN_CRUX_HEADERS` in `scripts/check_boundary.py`). `app/src` and `app/os` fail
on them although they are public, because the product uses Zephyr directly for threads and queues. Crux
marks these four headers "frozen for new product code": no new features, existing users keep working, and any
deprecation waits for a separate decision (concepts glossary, `docs/README.md` of `crux-pilot` at the pinned
revision). This repository's rule goes further and refuses them in `app/src` and `app/os`.

**Sockets profile.** The set of standard POSIX socket headers that Crux's networking contract lists
(`SOCKET_PROFILE` in `scripts/check_boundary.py`: `sys/socket.h`, `netinet/in.h`, `arpa/inet.h`,
`poll.h`, `fcntl.h`, `unistd.h`, `errno.h`, `time.h`). `app/src` may include them, and S2's
`net_client.c` does. The Crux targets are `crux::sockets` and `crux::netif`. `app/os`, `app/compose`
and `workload/` fail on the ones that are not ISO C headers. `errno.h` and `time.h` are also ISO C headers,
so they are allowed in every tree (`app/os/workload_os_zephyr.c` includes `<errno.h>`).

**Workload.** The synthetic program the firmware runs: a validated configuration record, a periodic
cycle that catches up after a stall, and an eight-byte message. The portable part is the directory
`workload/`. It is written for this repository and contains no product logic.

## Build, pin and evidence

**Baseline gate.** The CMake option `-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`, which every CI build of the
board image passes. It makes the Crux module refuse a Zephyr that is not the verified baseline
(`RELEASE.md`, the Build row). The gate is in `crux-pilot`, not here. One quirk is recorded in
`docs/findings/s3-file-composition.md` (friction 5): CMake prints that the variable was "not used by the
project" even when the gate passes.

**Pin.** The full commit of `crux-pilot` that `west.yml` imports; the `revision` of the `crux-pilot` project
there is the current pin. It is a commit and never a branch or a tag; no Crux tag exists. `west crux-pins`
checks it in CI. A pin moves in its own pull request. See the pin section of
[CONTRIBUTING.md](../CONTRIBUTING.md).

**Finding.** A note under `docs/findings/` that records what building a step or asking a question taught
about the product's use of Crux. Each statement in a finding carries a label, and the label set differs by note: Measured, Inferred and Open
(the S3 note, where "Measured" means that a CI job produced the result), Measured, Inferred, Recorded and Open
(the S4 and S5 notes, where "Measured" means that it was run locally while the step was written), Verified,
Inferred and Not verified (the S6 groundwork note), Verified, Inferred, Recorded and Open (the S6 step note), and
Measured and Not shown (the S2 board-run note). "Recorded" is a CI result read from the job logs at a named revision. A finding is kept as written: when the pin or the facts
move, a later result is added as a dated update or a banner and the recorded reading is not rewritten, so each
note names the revision it was read at.

**Budget.** The static resource check. The `Budget` job in `.github/workflows/budget.yml` builds each
step, reads the memory region table and the ROM and RAM reports, and `budgets/check.py` compares them
with `budgets/limits.json`, which declares a minimum percentage of free space per region for each
step (placeholder values, 25 percent). It measures size only, not stack use, heap use or timing. A new
step needs a row in the limits file first, because the checker fails a step that has none.

**`native_sim`.** Zephyr's simulated board, run on the build host. CI runs the scenarios in
`tests/native_sim` and `tests/native_sim_mbed` (S6) with Twister for `native_sim/native/64`. Each scenario is a Zephyr ztest application
that compiles chosen sources of `app/` and `workload/`; none boots the board image. A `native_sim`
pass is not evidence about the board: for example S4's scenario does not enable the simulated watchdog of the pinned
Crux, so no feed cycle is shown there.

**EVKB.** Short for the board the repository targets, written "NXP RT1060-EVKB Rev B" in prose and
"RT1060-EVKB" in CI job names. CI passes it to `west build` as `mimxrt1060_evk@B//qspi`. In Zephyr's board naming that is the board
`mimxrt1060_evk`, its revision `B` (`@B`) and the variant `qspi`, with the default SoC left out between the two
slashes. An "EVKB build" in this repository means a cross-compile in CI. It never means a run.

**Scenario.** One Zephyr test application under `tests/native_sim/sN` (S6: `tests/native_sim_mbed/s6`, which needs the Mbed TLS modules), with a `testcase.yaml` for
Twister. S3, S4 and S5 select one case per image through a build variable (`S3_CASE`, `S4_CASE`,
`S5_CASE`), because File can be bound and the watchdog started once per boot, and because the S5 test's
CMake file notes that Crux Time keeps its state for the whole run.

## Time

**Time Authority.** The part of a product that owns the realtime clock of Crux Time. Crux's Time contract
(`docs/time-contract.md` of `crux-pilot` at the pinned revision) says that the designated product Time Authority
coordinates native clock changes with any external time manager and owns source selection and stale
synchronisation callbacks, and that the authority header is not a runtime permission mechanism. That is why
Crux provides no SNTP client: the product chooses the time source ([composition-zone.md](composition-zone.md)).
In code, `app/src/time_sync.c` (S5) is the one file that calls the Crux Time authority
(`<crux/time_authority.h>`, with `crux_realtime_set()`).

## People and board procedures

**Owner.** Whoever owns this repository on GitHub: the account in `CODEOWNERS`. The documents reserve to the
owner: merging a pull request, tags, GitHub Releases and forks (`CONTRIBUTING.md`), the release approval in
`RELEASE.md`, filing a request in `crux-pilot`, and any run on a board (`docs/board-bring-up.md`). A review
`PASS` or a green CI result informs these decisions and does not make them. No rule reserves a change of the pinned
Crux revision to the owner; in practice the owner has approved each one (`west.yml` and
`tests/tooling/test_manifest.py` record the approval of the current pin). "The project owner" and "the
repository owner" (the wording of `RELEASE.md` and `SECURITY.md`) mean the same role. In a
[team copy](team-copy.md) of this repository the owner is whoever approves merges and releases
in that copy.

**Maintainer.** Not a separate role. The S2 board-run note says "the repository maintainer" and means the owner.
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
[adding-a-step.md](adding-a-step.md#files-that-need-a-reviewed-change). `CONTRIBUTING.md` is the authority for
that list, and it states a rule for some of the files and none for the others. Other projects call such files
"protected"; this repository does not use that word.

**Team copy.** A copy of this repository that a team keeps in its own repository, for example as a zip without
the Git history. [team-copy.md](team-copy.md) says what to change in it.

**Operator.** The person who runs a board procedure on a bench, under the owner's approval for that task. The
S2 board-run note uses the word for the person who ran the reviewed driver.

**Bench.** The physical setup of a board run: the board, its probe and UART adapter, the Ethernet cable and the
host peer. "Two runs on one bench" means the same board and the same setup both times.

**Gated procedure.** The fixed sequence of the S2 board runs: identify the board, program it, run the host checks,
restore. Each run needed the owner's written approval, an explicit owner yes before the board was overwritten and
a guard check before each probe step (`docs/findings/s2-first-board-run.md`, "Method"). The procedure and its driver are
not in this repository: the driver is the `crux-pilot` target test driver, and the run records are kept privately.

**Accepted normal image.** The firmware that was on the board before a run and that the procedure puts back and
verifies afterwards. It is not part of this repository. The S2 note records its SHA-256 and size.

## Terms from outside this repository

**west.** Zephyr's tool for workspaces, builds and tests. A west manifest (`west.yml`) lists the projects of a
workspace and their revisions; a manifest group filter switches optional groups of projects on or off. This
repository uses `west init -l`, `west update`, `west build` and `west twister`.

**Twister.** Zephyr's test runner (`west twister`). It builds and runs the scenarios that `testcase.yaml` files
describe.

**ztest.** Zephyr's test framework. Each `native_sim` scenario is a ztest application.

**Provider.** The implementation behind a Crux interface for one environment, for example a Zephyr provider
(Crux concepts glossary, `docs/README.md` of `crux-pilot`).

**Profile.** A named choice of what an interface is built on. The Sockets profile is the set of POSIX socket
headers above. The Mbed TLS profile selects Mbed TLS for HTTPS; Crux's other TLS profile uses the wolf projects, which
this repository does not fetch.

**SNTP.** The Simple Network Time Protocol: a client asks a server for the time over UDP (port 123). A
kiss-o'-death answer is one in which the server tells the client to stop or slow down; S5 never sets the clock from one.

**WDOG1.** The watchdog peripheral of the RT1060 that step S4 uses. The overlay `app/boards/s4.overlay` names it
with the alias `crux-watchdog0`.

**HWINFO.** Zephyr's hardware information API. Crux System reads the reset cause through it.

**RAM disk.** A Zephyr disk that keeps its data in RAM, so nothing survives a reset. The S3 scenario and the S6
image use it as their medium.

**FatFs.** The FAT file system library (ChaN) that the board build of S3 uses on a microSD card.

**SBOM and SPDX.** A software bill of materials lists the components of a build; SPDX is a file format for it. The
release dry run produces SPDX files from `west spdx` and parses them (`RELEASE.md`).

**PHY and MDIO.** The PHY is the Ethernet physical-layer chip on the board. MDIO is the management interface
through which the Ethernet controller configures it. The Crux reference composition applies an "MDIO completion
correction" that the S2 image does not (`app/conf/s2.conf`); the S2 board runs show the link coming up without it.

**Friction.** A heading used in findings for a point where using the public Crux interface took extra work, was
unclear or was blocked.

**Mutation run.** A check of a test: change the code on purpose and see whether the test fails. The S5 note records
five such runs of the time policy.

## Wording that differs between files

These are differences that a reader may trip over. Each is explained here and the files are kept as they are.

- Step and stage, as above: no document defines the stages, S5 is in none, and
  `docs/findings/file-binding-has-no-public-header.md` says S3 "is not built in Stage 1", a note
  kept as written from before S3 was built, while the management finding calls S3 a
  Stage 1 step. The header comment of `west.yml` says that no group is enabled "in Stage 1"; it is historical,
  and the pin serves all seven steps.
- The comments at the top of `app/conf/s3.conf` and `app/conf/s4.conf` say that S3 and S4 are built on S1 without the
  other steps. That agrees with `app/Kconfig`, which says that S2, S3 and S4 build on S1 and S5 on S2.
- The CI job named `S1 (native_sim and RT1060-EVKB)` in `ci.yml` also runs the `native_sim`
  scenarios of S2, S3, S4 and S5, because it runs every scenario under `tests/native_sim`.
