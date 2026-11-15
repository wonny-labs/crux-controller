# Glossary

Each entry says how this repository uses the word, with the file where the use can be checked. Where
the repository is not consistent, the entry says so. Start with the [architecture](architecture.md) if
the terms are new to you.

## Steps and stages

**Step.** A numbered increment of what the firmware does, written S0 to S5 on `main`. Each step after S0
has a Kconfig option (`CRUX_CONTROLLER_S1` to `CRUX_CONTROLLER_S5` in `app/Kconfig`), a configuration
fragment (`app/conf/s1.conf` to `s5.conf`), a CI build job (the S1 job is named `S1 (native_sim and RT1060-EVKB)`), its own row in the `Budget` matrix and
in `budgets/limits.json`, and a row in the README table.

| Step | What it adds |
|---|---|
| S0 | The clock of Crux Time answers. No option and no fragment: it is the base build. |
| S1 | The synthetic workload on two Zephyr threads and a message queue (the adapter zone), with Crux Time and Logging. |
| S2 | Each workload message is also sent to a TCP peer over the Crux Sockets profile. |
| S3 | The workload's configuration record is kept in a file through Crux File, on a microSD volume mounted by the composition zone. |
| S4 | The reset cause is logged at boot and a watchdog is fed once for each pass of the workload that has cycles due, through Crux System. |
| S5 | The Crux Time realtime clock is set from an SNTP server on the S2 network, with a product policy for what an answer may do. |

S2, S3 and S4 each depend on S1 in Kconfig and are built on top of `conf/s1.conf`. S5 depends on S2
(and so on S1) and is built on `conf/s1.conf;conf/s2.conf;conf/s5.conf`. "Build on" in the
repository therefore means "depends on" a lower step. CI builds each step as its own image and never
combines S2, S3 and S4; the S5 image is built on S2 (and so on S1). What each step has and has not run is in [roadmap.md](roadmap.md), and the procedure for
adding one is in [adding-a-step.md](adding-a-step.md).

"Step" has two other meanings that share the word. In a GitHub Actions workflow a step is one entry of
a job (`ci.yml`, `budget.yml`). In `RELEASE.md` the table "Step, Tool, What fails the run" lists the
actions of the release dry run. The context says which one is meant.

**Stage.** A phase of the repository's own work, larger than a step. The documents never define it;
this entry records how they use it. `docs/findings/management-has-no-public-composition.md` says it was
"recorded after Stage 1 step S3", so S3 is a Stage 1 step. The tracking paragraph of `README.md` says
that "Stage 2 steps and their findings" are tracked in the repository's own issues under an epic, and
lists S4 among the epic's children, so S4 is a Stage 2 step. Nothing places S5 in a stage: its README
text names no stage, and it arrived with
[wonny-labs/crux-controller#50](https://github.com/wonny-labs/crux-controller/pull/50). The comment at
`west.yml` line 18 ("chosen for Stage 1") is historical. One use differs from the rest:
`docs/findings/file-binding-has-no-public-header.md` (lines 3 and 21) says S3 "is not built in Stage 1",
a note from before S3 was built. Treat the stage number as a label of when something was planned, not
as a property of the code. One other use is unrelated: `docs/findings/s2-first-board-run.md` says "an
earlier platform stage", which means a phase of Crux, not of this repository.

## Boundary and zones

**Boundary.** The include rules of the source trees, enforced by `scripts/check_boundary.py` in the CI
job `Boundary check`. There is no exception, waiver or per-file opt-out.

**Adapter zone.** The directory `app/os`. The one place that creates threads, queues messages and
sleeps, using Zephyr kernel calls directly, and queries an SNTP server for S5. It implements the port headers
`app/src/workload_os.h` and `app/src/time_sync_port.h`. It may
include exactly two Zephyr headers, `zephyr/kernel.h` and `zephyr/net/sntp.h` (`OS_ADAPTER_ZEPHYR_HEADERS`
in `scripts/check_boundary.py`), and no Sockets profile, POSIX or composition header. Of its two sources,
`app/os/time_sync_zephyr.c` (S5) includes the SNTP header. See [composition-zone.md](composition-zone.md).

**Composition zone.** The directory `app/compose`. The one place that mounts a file system and binds it
to Crux File with the composition interface `<crux/file_zephyr.h>`. It may include two Zephyr headers,
`zephyr/fs/fs.h` and `zephyr/devicetree.h`. It implements the port header `app/src/storage_port.h`.
"Composition" in this repository's documents means product code that joins Crux components to the
board and the OS; the Crux definition itself was not read for this page. Do not confuse
`app/src/composition.c`, which starts the steps, with the zone.

**Composition interface.** A Crux header that names a provider and is meant for composition code only,
for example `<crux/file_zephyr.h>` with the CMake target `crux::file_zephyr`. Crux publishes these
under `components/*/ports/*/include/crux/`, apart from the public headers. `app/src` and `workload/` may
not include one.

**Port header.** A header in `app/src` that the application declares and a zone implements:
`workload_os.h` and `time_sync_port.h` (both implemented in `app/os`) and `storage_port.h` (implemented in `app/compose`). It includes
ISO C only, so it stays inside the rules of `app/src`. The application calls it; the linker joins the
two sides.

**Frozen headers.** The four public Crux headers `<crux/thread.h>`, `<crux/sync.h>`, `<crux/queue.h>`
and `<crux/serial.h>` (`FROZEN_CRUX_HEADERS` in `scripts/check_boundary.py`). `app/src` and `app/os` fail
on them although they are public, because the product uses Zephyr directly for threads and queues. The
word "frozen" belongs to this repository's rule. It does not describe a state of the Crux headers.

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

**Pin.** The full commit of `crux-pilot` that `west.yml` imports, currently
`37c92b18b44b7dfb95c2109f036f23d00f05cb4c`. It is a commit and never a branch or a tag; no Crux tag
exists. `west crux-pins` checks it in CI. A pin moves in its own pull request. See the pin section of
[CONTRIBUTING.md](../CONTRIBUTING.md).

**Finding.** A note under `docs/findings/` that records what building a step or asking a question taught
about the product's use of Crux. Statements in a finding are labelled Measured, Inferred or Open (the
S2 board-run note uses Measured and Not shown). A finding is kept as written; when the pin or the facts
move, the note is not rewritten, so each one names the revision it was read at.

**Budget.** The static resource check. The `Budget` job in `.github/workflows/budget.yml` builds each
step, reads the memory region table and the ROM and RAM reports, and `budgets/check.py` compares them
with `budgets/limits.json`, which declares a minimum percentage of free space per region for each
step (placeholder values, 25 percent). It measures size only, not stack use, heap use or timing. A new
step needs a row in the limits file first, because the checker fails a step that has none.

**`native_sim`.** Zephyr's simulated board, run on the build host. CI runs the scenarios in
`tests/native_sim` with Twister for `native_sim/native/64`. Each scenario is a Zephyr ztest application
that compiles chosen sources of `app/` and `workload/`; none boots the board image. A `native_sim`
pass is not evidence about the board: for example the simulator has no watchdog, so S4's feed cycle
cannot be shown there.

**EVKB.** Short for the board the repository targets, written "NXP RT1060-EVKB Rev B" in prose and
"RT1060-EVKB" in CI job names. CI passes it to `west build` as `mimxrt1060_evk@B//qspi`. The repository does not explain
that board string; reading `@B` as revision B is the reader's inference and is not verified here. An
"EVKB build" in this repository means a cross-compile in CI. It never means a run.

**Scenario.** One Zephyr test application under `tests/native_sim/sN`, with a `testcase.yaml` for
Twister. S3, S4 and S5 select one case per image through a build variable (`S3_CASE`, `S4_CASE`,
`S5_CASE`), because File can be bound and the watchdog started once per boot, and because the S5 test's
CMake file notes that Crux Time keeps its state for the whole run.

## Time

**Time Authority.** Used once, in [composition-zone.md](composition-zone.md), where it is the reason
Crux provides no SNTP client: Crux's Time contract "designates the product as the owner of the Time
Authority", so the product chooses the time source. This repository does not define the term beyond
that sentence. In code, `app/src/time_sync.c` (S5) is the one file that calls the Crux Time authority
(`<crux/time_authority.h>`, with `crux_realtime_set()`). What the Crux Time contract says exactly
was not read for this page.

## Inconsistencies in the repository's wording

These are recorded, not fixed here, because the files involved belong to other changes or are kept as
written.

- Step and stage, as above: no document defines the stages, S5 is in none, and
  `docs/findings/file-binding-has-no-public-header.md` line 21 says S3 "is not built in Stage 1", a note
  kept as written from before S3 was built, while the management finding calls S3 a
  Stage 1 step. The comment at `west.yml` line 18 says the pin was chosen "for Stage 1"; it is historical,
  and the pin serves all six steps.
- `app/conf/s3.conf` line 3 and `app/conf/s4.conf` line 3 say that S3 and S4 are built on S1 without the
  other steps. That agrees with `app/Kconfig`, which says that S2, S3 and S4 build on S1 and S5 on S2.
- The CI job named `S1 (native_sim and RT1060-EVKB)` (`ci.yml` line 147) also runs the `native_sim`
  scenarios of S2, S3, S4 and S5, because it runs every scenario under `tests/native_sim`.
