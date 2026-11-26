# Adding a capability

This is a recipe for adding a *capability* to the firmware, with its build configuration. It is worked through
with `system` (Crux System: the reset cause and a watchdog), because it is the smallest capability that touches
every part. The [appendix](#appendix-how-sntp-and-management-differ) lists how `sntp` and `management` differ. Every file named here
exists on `main`. Read the [architecture](architecture.md) and the [glossary](glossary.md) first if the terms are
new, and [CONTRIBUTING.md](../CONTRIBUTING.md) for the rules that apply to every change.

Ground rules that shape the order of work:

- **Tests first.** Write the test, watch it fail, then write the code. CONTRIBUTING.md asks for this
  for new behaviour and for fixes, and says that an existing test or check is never weakened or deleted
  to make a change pass.
- **CI is the reference.** Zephyr builds, Twister runs and the budget numbers that a pull request cites come
  from CI. The [Tutorial](tutorial.md) and [Set up without the Dev Container](native-setup.md) give the CI commands for a
  local `native_sim` run, and
  a local result does not replace CI. You can also run the tooling tests, the boundary check and the host
  tests locally.
- **Public means only.** A capability uses public Crux headers and targets. If it seems to need a Zephyr header
  or a Crux private header in `app/src`, stop: that is either a new zone entry (a separate reviewed pull
  request) or a *finding*. `system` needed neither. Section 5 says what the rule is for drivers.
- **A build is not a release and not a board run.** A green CI build does not mean the image ran on a board,
  and the pull request must not say so. Merging needs the owner's approval (see [the owner](glossary.md#people-and-board-procedures)); a green CI and a
  review `PASS` do not give it.

## 1. Decide the shape

Answer these before writing any file. `system`'s answers are in brackets.

1. Which Crux component does the capability use, through which public header and target? (Crux System:
   `<crux/system.h>`, `crux::system`.)
2. Does the application need anything that `app/src` may not include? If the answer is a Zephyr header, a
   composition interface or a provider name, the capability needs a zone entry. (No: the driver, HWINFO and
   reboot calls are inside Crux's own binding. `file` did need the composition zone, `workload` the adapter zone.)
3. Which configuration does it build on? Every configuration after `base` depends on `workload`, directly or through `net`. (`workload`; not `net` or `file`,
   so the `system` image has no network and no file system.)
4. Which Crux pieces does the image have to provide, as Kconfig and devicetree? (Three native
   facilities, `WATCHDOG`, `HWINFO` and `REBOOT`, and the devicetree alias `crux-watchdog0`.)
5. Is there product logic that can be plain C? Put it in its own file so that a host test can run it. (The
   watchdog interval and the reset cause classes: `app/src/health_policy.[ch]`.)

## 2. The order of work

Work in the order of this table. Each row is a small commit with its test first.

| # | What | Files (`system`) | Test written first | What CI does with it |
|---|---|---|---|---|
| 1 | Declare the resource limits | `budgets/limits.json` (the `system` row) | `SystemLimits` in `tests/tooling/test_system.py` | `Budget` job: `budgets/check.py` fails a configuration that has no row |
| 2 | Plain-C policy, if any | `app/src/health_policy.c`, `app/src/health_policy.h`, `tests/host/CMakeLists.txt` | `tests/host/test_health_policy.c`; `SystemPolicy` in `test_system.py` | `Host tests` job, with the sanitizers off and on |
| 3 | Glue, option, fragment, overlay, build block, start | `app/src/health.[ch]`, `app/Kconfig`, `app/conf/system.conf`, `app/boards/system.overlay`, `app/CMakeLists.txt`, `app/src/composition.c` | `SystemConfiguration`, `SystemBuildFiles`, `SystemSources` in `test_system.py` | `Tooling tests`; `Boundary check`; the build job of row 5 |
| 4 | Scenario on `native_sim` | `tests/native_sim/system/` (`CMakeLists.txt`, `prj.conf`, `app.overlay`, `testcase.yaml`, `src/test_system.c`) | `SystemScenario` in `test_system.py`, then the scenario itself | The `workload` job runs `west twister -p native_sim/native/64 -T crux-controller/tests/native_sim`, which runs every scenario |
| 5 | CI build job and Budget row | `.github/workflows/ci.yml` (job `system`), `.github/workflows/budget.yml` (matrix row `system`) | `SystemWorkflows` in `test_system.py` | The new job and the new `Budget system` job |
| 6 | Documents | `docs/findings/s4-system-composition.md`, `docs/findings/README.md`, `README.md`, `docs/roadmap.md`, `CHANGELOG.md`, `CONTRIBUTING.md` | `SystemFindings` in `test_system.py`; `Contributing` in `tests/tooling/test_docs.py` | `Tooling tests` |

Update `CONTRIBUTING.md` in the same pull request as the rest (row 6).

The tooling tests are ordinary `unittest` files that read the repository's files as text (Kconfig, CMake,
`.conf`, the workflows, the documents). That is what lets a capability be written test-first without a Zephyr build.

### 2.1 The limits row, first

Add a row to `budgets/limits.json` that repeats the placeholder margin of the other configurations (25 percent
free in every region). Do it in its own commit before any job names the configuration: `budgets/check.py`
fails a configuration with no row, and the file's own comment says a change to it is a reviewed change. Do not
change another configuration's limit in the same pull request to make a build pass. Write `SystemLimits` first and watch it fail
before the row exists.

Known catch: the tooling tests of other capabilities pin the exact list of rows. `test_system.py`, `test_sntp.py`
and `test_management.py` each compare the rows of `budgets/limits.json` and of the `Budget` matrix with the
written-out list of all configurations, `["base", ..., "management"]`, in order. A new capability extends each
of those lists and says so in its pull request. A comment in `test_system.py` explains why the list there is
longer than `system`.

### 2.2 The policy as plain C

`app/src/health_policy.c` includes ISO C only and names no Crux or Zephyr symbol, so
`tests/host/CMakeLists.txt` builds it on the host with `-Wall -Wextra -Wpedantic -Werror`. Write the host test
`tests/host/test_health_policy.c` first. It fails to build without the policy. Run it with and
without the sanitizers, as CI does:

```bash
cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=ON
cmake --build build/host
ctest --test-dir build/host --output-on-failure
```

Use `-DWORKLOAD_SANITIZE=OFF` for the other half. Skip this part if the capability has no logic of its own. `net`'s
`net_client.c` is the other example of host-tested application code.

### 2.3 Glue, option, fragment, overlay, build, start

- **Kconfig.** A `config CRUX_CONTROLLER_SYSTEM` block in `app/Kconfig`. It depends on `CRUX_CONTROLLER_WORKLOAD`, on
  the Crux symbol and on the native facilities, and it selects nothing (a test checks that). The
  fragment, not the option, turns the Crux symbol on.
- **Fragment.** `app/conf/system.conf` turns on `CONFIG_CRUX_CONTROLLER_SYSTEM=y`, `CONFIG_CRUX_SYSTEM=y` and the
  three native facilities. Its comments say what Crux requires of the image and what it refuses (another
  owner of the watchdog), at "the pinned revision"; the hash itself is in `app/boards/system.overlay`.
- **Overlay.** `app/boards/system.overlay` sets the alias `crux-watchdog0` to `&wdog0` and enables the node. An
  overlay is configuration, not code, and CI passes it with `EXTRA_DTC_OVERLAY_FILE`.
- **Build block.** In `app/CMakeLists.txt`, inside `if(CONFIG_CRUX_CONTROLLER_WORKLOAD)`:

  ```cmake
  if(CONFIG_CRUX_CONTROLLER_SYSTEM)
      target_sources(app PRIVATE src/health.c src/health_policy.c)
      target_link_libraries(app PRIVATE crux::system)
  endif()
  ```

  No `target_include_directories` anywhere: the boundary check reads includes and cannot see CMake
  include paths, so `tests/tooling` checks that none is added.
- **Glue.** `app/src/health.[ch]` is the one place that calls Crux System. Application code includes
  public headers only (`<crux/system.h>`, `<crux/logging.h>`, `<crux/status.h>`).
- **Start.** `app/src/composition.c` gets an `#ifdef CONFIG_CRUX_CONTROLLER_SYSTEM` include and a start block.
  The position in `composition_start()` is a decision: `system` starts after the storage of `file` and before the
  workload threads, so that a slow mount cannot cost a reset.
- **Changes to shared code.** `system` needed a cycle hook in `app/src/workload_thread.[ch]`. Test shared code
  where it lives: `system` added a case to the `workload` scenario (`tests/native_sim/workload/src/test_workload.c`) for the hook.

Then run the checks that do not need Zephyr:

```bash
python -m unittest discover -s tests/tooling -v
python scripts/check_boundary.py
```

`scripts/check_boundary.py` with `--crux-root <a crux-pilot checkout at the pin>` is the stronger form
that CI runs: it also requires every `<crux/NAME.h>` to be a header Crux publishes. If the boundary
check fails, do not look for an exception. There is none; read
[composition-zone.md](composition-zone.md).

### 2.4 The scenario

`tests/native_sim/system/` is a Zephyr ztest application with a `testcase.yaml` for Twister. It compiles the
application's own `health.c` and `health_policy.c`, not copies, against the real Crux System provider. It
uses one image per case (`SYSTEM_CASE`, passed as `extra_args` in `testcase.yaml`) because Crux System allows
one watchdog start per boot. Write down what the scenario cannot show: it enables no watchdog, so `system`'s
scenario shows the boot line and an unavailable watchdog, and no feed cycle. That limit is stated in the
test source's header comment and in the findings note, and a test checks both.

A local Twister run (step 3 of the [Tutorial](tutorial.md#3-one-native_sim-run), or
[Set up without the Dev Container](native-setup.md#run-the-workload-to-sntp-scenarios)) is optional. The `workload` job's result is the one
the pull request cites; say in the pull request whether the scenario ran locally before CI.

### 2.5 The CI job and the Budget row

Add a job `system` to `.github/workflows/ci.yml` by copying the `file` job. The name must read `system build (...)`:
`tests/tooling/test_docs.py` finds the build jobs by the pattern `<name> build`, for each name of the `Budget`
matrix. The `system` job:

1. builds with `-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`, `-DEXTRA_CONF_FILE=conf/workload.conf;conf/system.conf` and
   `-DEXTRA_DTC_OVERLAY_FILE=boards/system.overlay`;
2. checks that `zephyr.bin` and `zephyr.meta` exist;
3. checks the resolved `.config` and `zephyr.dts`: the options that must be on, the options that must be
   off (another watchdog owner, Crux Thread and Sync), the alias, and the node status;
4. checks with `nm` that the glue and the Crux calls it makes are linked.

Item 3 exists because an unmet Kconfig dependency only prints a warning: the image would
build without the capability. CI therefore reads what the build resolved, not what the command line asked for.
Add the same guard to the Budget matrix through the row's `require` field in
`.github/workflows/budget.yml`:

```yaml
- config: system
  conf: "conf/workload.conf;conf/system.conf"
  overlay: "boards/system.overlay"
  require: "CONFIG_CRUX_CONTROLLER_SYSTEM=y CONFIG_CRUX_SYSTEM=y"
```

The `Budget system` job builds the configuration, runs the `rom_report` and `ram_report` targets, collects the memory
regions with `budgets/collect.py` and compares them with the limits row. It publishes the numbers as a
job summary and uploads nothing: the repository publishes hashes only, and a test fails if a workflow
uploads an artifact. No job flashes, resets or runs anything on a board.

### 2.6 The documents

- **Findings note**, `docs/findings/s4-system-composition.md`. Label each statement Measured (you ran it
  and name the command), Inferred (read from `crux-pilot` source at the pinned commit, not run) or Open.
  Results that only CI can produce are written as Open with the CI job named, and recorded in the pull
  request afterwards; once CI has run, update the note with the result, the revision it was read at and the label
  Recorded, as the `management` note does. The note lists what the product had to write, the friction, the decisions made
  (with the test that pins each) and what the capability does not show. It carries no line counts, because they
  go stale.
- **`README.md`**: a row in the capability table (capability, build configuration, code to read).
- **`docs/roadmap.md`**: a row in "What is built", with `not run` in the board column until a finding records a
  board run, and a row in the size table once a `Budget` job has printed the numbers.
- **`docs/findings/README.md`**: a row for the new note.
- **`CHANGELOG.md`**: an entry under Unreleased.
- **`CONTRIBUTING.md`**: three statements that `tests/tooling/test_docs.py` (class `Contributing`) checks
  against the workflows: the role section lists every build configuration of the `Budget` matrix in order, the
  `ci.yml` row names `<name> build`, and the `budget.yml` row says `` `Budget` for `base` to `<last>`: ``. Its static analysis section also
  states how many sources the host tests build and how many sources clang-tidy does not analyse, and
  `tests/tooling/test_contributing_standard.py` checks those counts against the repository. A capability that adds C
  sources changes them.

## 3. Checks before the pull request, and what to write in it

Run the tooling tests and the boundary check locally, and the host tests if you have CMake and a C
compiler. List each check in the pull request with the revision it ran on and who ran it (you, CI or a
reviewer), and name what was not run. For `system` that list ends with: Zephyr builds, Twister scenarios and
the Budget numbers come from CI (a local Twister run is optional); nothing ran on a board. Two cautions:

- A local compile with the host compiler is necessary and not sufficient. In `system`, GCC in CI rejected a
  comparison between constants of two different anonymous enums (`-Werror=enum-compare`) that the local Apple clang
  accepted.
- The Crux behaviour you rely on is read from the pinned source. Say so in the findings (Inferred),
  name the file, and do not assume a later Crux revision behaves the same.

If the capability needs a newer Crux than the pin, move the pin first, in its own pull request, as described
in [CONTRIBUTING.md](../CONTRIBUTING.md). A pin move is not folded into a capability.

## 4. Mechanical check list

Use this at the end. `<name>` is the name of the build configuration, short and lowercase.

- [ ] `budgets/limits.json` has the row `<name>`, added before any job names it.
- [ ] `app/Kconfig` has `CRUX_CONTROLLER_<NAME>`, depending on `CRUX_CONTROLLER_WORKLOAD` and selecting nothing.
- [ ] `app/conf/<name>.conf` and, if needed, `app/boards/<name>.overlay` exist, with comments naming the
      Crux revision they were read at (`system`'s `system.conf` says "the pinned revision" and its overlay names the hash).
- [ ] `app/CMakeLists.txt` has the block inside the `CONFIG_CRUX_CONTROLLER_WORKLOAD` condition and adds no
      include path.
- [ ] `app/src/composition.c` starts the capability, at a position that is argued in a comment.
- [ ] `tests/native_sim/<name>/` has a `testcase.yaml` with `platform_allow: native_sim/native/64`.
- [ ] `tests/tooling/test_<name>.py` exists, and the exact row lists of `test_system.py`, `test_sntp.py` and `test_management.py` are extended.
- [ ] `ci.yml` has the job `<name>`, named `<name> build (...)`; `budget.yml` has the row.
- [ ] Every new first-party C, CMake, Kconfig, Python and shell file starts with
      `SPDX-License-Identifier: Apache-2.0` in the form of section 4.1, and `python scripts/check_spdx.py` passes.
- [ ] `scripts/check-format.sh` passes, with clang-format 18.1.8.
- [ ] `CLANG_TIDY=clang-tidy-18 python3 scripts/analyze_host.py` passes. A new plain-C source that the host tests
      build is analysed. A new source that needs Zephyr or Crux headers shows up in the list of sources that are not
      analysed, without failing, and the counts in `CONTRIBUTING.md` change.
- [ ] `scripts/check-patch.sh` (the `Patch style` job: Zephyr's checkpatch, rule BRACES, on the changed C lines)
      passes. It needs a prepared Zephyr checkout in `ZEPHYR_BASE`, so CI is the practical place to run it.
- [ ] The findings note and its index row, the README row, the roadmap rows, the changelog entry and the three
      statements of `CONTRIBUTING.md` are updated.
- [ ] `python -m unittest discover -s tests/tooling` and `python scripts/check_boundary.py` pass.
- [ ] The pull request lists each check with its revision and who ran it, and says that CI builds are
      not board runs.

### 4.1 The licence line

`scripts/check_spdx.py` runs in the `Tooling tests` job (the workflow step `Check SPDX headers`). It requires an exact line
at the top of each covered file. Put it on the first line, or on the second line when the first is a shebang:

| Files | The line |
|---|---|
| `.c` and `.h` | `/* SPDX-License-Identifier: Apache-2.0 */` |
| `CMakeLists.txt`, `Kconfig`, `.cmake`, `.py` and `.sh` | `# SPDX-License-Identifier: Apache-2.0` |

`.conf` files, devicetree overlays, documents, JSON, YAML and the web assets of the management page are not covered.
The script keeps a list of two older scripts that lack the line, and an entry that no longer applies is an error, so the
list can only get shorter. Do not add to it.

### 4.2 Format, static analysis and patch style

These three checks run in CI and, for the first two, on your machine
([CONTRIBUTING.md](../CONTRIBUTING.md#static-analysis-and-coding-standard) has the scope of each):

- `scripts/check-format.sh` fails when a tracked C file differs from what clang-format 18.1.8 produces with
  `.clang-format`. It needs that exact version.
- `scripts/analyze_host.py` runs clang-tidy 18 over the sources that the host tests build and lists the tracked
  sources that it did not analyse. Any finding fails the job.
- `scripts/check-patch.sh` runs Zephyr's checkpatch with the rule BRACES on the C lines that the change adds.

## 5. Drivers and HAL: what the rule is and where the reasoning lives

A capability may seem to need a driver or a hardware abstraction layer (HAL). This section says what the repository
records and where to read more. It adds no policy.

**The rule.** `app/src` and `workload` include no Zephyr header. `app/os` and `app/compose` include only the
Zephyr headers on their exact allow-lists. Driver headers (`zephyr/drivers/*`), vendor headers (`fsl_*.h`) and every
other header that is not on a list fail the boundary check, and there is no exception, waiver or per-file opt-out
([CONTRIBUTING.md](../CONTRIBUTING.md#the-boundary)).

**The reason given in the repository.** A boundary that a change can step over says nothing about what a real
consumer can use, and it would hide the gap that this repository exists to find (CONTRIBUTING.md, "The boundary").
[composition-zone.md](composition-zone.md#the-allow-list-of-zephyr-headers) lists the Zephyr headers that are left
off on purpose, each with its reason. For drivers it says that a driver or network detail in the composition zone
"would be a second product layer, not a composition".

**How a capability reaches a device.** No source of the product includes a driver header, and the boundary check
would fail one. `system` names a devicetree alias and Kconfig options, and Crux System calls the watchdog and HWINFO drivers inside its own binding
([findings/s4-system-composition.md](findings/s4-system-composition.md)). The product's own Zephyr use is the
kernel in the adapter zone and the file system in the composition zone, behind port headers that the application
declares ([architecture.md](architecture.md#layers-and-zones)).

**No layer of its own.** CONTRIBUTING.md, "Changing behaviour", says to reuse what Zephyr and Crux provide rather
than adding a layer of your own. A port header covers one capability for one zone. It is not a general hardware
layer, and the repository does not have one.

**Out of scope.** The roadmap records GPIO, I2C and SPI as out of scope, with direct use of Crux Thread, Sync, Queue
and Serial (as the finding recorded them; the pinned Crux has no Queue), Reliance Edge and any firmware image in public form ([roadmap.md](roadmap.md#what-is-not-yet-possible-and-why)).
These are recorded positions, not commitments. A capability that needs one of them is a scope question: put the need and the
alternatives in the pull request. CONTRIBUTING.md does not rule on it. A new Zephyr header in a zone is a reviewed
change of `scripts/check_boundary.py`, `tests/tooling/test_boundary.py` and `docs/composition-zone.md` together.

**Where the reasoning lives.**

- In this repository: [composition-zone.md](composition-zone.md) ("Why a zone", "The adapter zone"),
  [architecture.md](architecture.md) ("Why zones exist") and the findings notes of `file`, `system` and `sntp`.
- In the platform repository, read at the pinned commit `13c950bb031fce0b14d4784f1586057d31434de3`:
  [`docs/choosing-an-api.md`](https://github.com/wonny-labs/crux-pilot/blob/13c950bb031fce0b14d4784f1586057d31434de3/docs/choosing-an-api.md)
  asks three questions in order (an OS or hardware facility, a platform service that Crux provides, the product's own
  behaviour) and sends each kind of code to a place, and
  [`docs/composition-interfaces.md`](https://github.com/wonny-labs/crux-pilot/blob/13c950bb031fce0b14d4784f1586057d31434de3/docs/composition-interfaces.md)
  describes the two routes to Zephyr for a product. That guidance is general. The Zephyr headers that this
  repository allows are the lists of its own boundary check.

## Files that need a reviewed change

This is a reading aid, collected from [CONTRIBUTING.md](../CONTRIBUTING.md) and from comments in the files.
CONTRIBUTING.md is the authority; where this list and it differ, follow it. CONTRIBUTING asks for an
independent review of a material change, and asks for a separate pull request only for a pin move and for the
three boundary files together.

- `scripts/check_boundary.py`, `tests/tooling/test_boundary.py` and `docs/composition-zone.md`: change together
  in one reviewed pull request (CONTRIBUTING, "The boundary").
- `app/CMakeLists.txt`, `app/management/management.cmake` and `app/management/entropy.cmake`: the boundary check
  reads them, and they may add no include path (CONTRIBUTING, "The boundary").
- `west.yml` and `tests/tooling/test_manifest.py`: a pin moves in its own small pull request (CONTRIBUTING, "The
  pin and the manifest"). `docs/dependencies.md`, `RELEASE.md` and `CHANGELOG.md` are covered only where they
  quote the pin.
- `budgets/limits.json`: its own `_comment` says that a change there is a reviewed change; CONTRIBUTING says a
  limit is not changed in a pin-bump pull request.
- `.github/workflows/*.yml`, `scripts/check_mbed_only.py` and `CODEOWNERS`: CONTRIBUTING does not state a
  rule for them. They are listed because they hold the checks, the licence gate of the Mbed TLS group and the
  ownership, and a reviewer should look at a change to them.
- `CONTRIBUTING.md` itself.

## Appendix: how `sntp` and `management` differ

`system` is the model above. `sntp` and `management` follow the same order, with the differences below. They are facts about the
current files, read from `app/Kconfig`, `app/CMakeLists.txt`, `app/os/CMakeLists.txt`, `app/management/`,
`app/compose/` and `.github/workflows/`.

**sntp (SNTP time synchronisation).**

- **It builds on `net`, not only `workload`.** `CRUX_CONTROLLER_SNTP` depends on `CRUX_CONTROLLER_NET`, `CRUX_TIME`,
  `SNTP`, `NET_UDP` and `NET_IPV4`. Its CI build uses `conf/workload.conf;conf/net.conf;conf/sntp.conf` and
  `boards/net.overlay`, and the Budget row says the same.
- **It uses a zone entry of its own.** `zephyr/net/sntp.h` is on the allow-list of `app/os`, a separate
  reviewed change as the ground rules above ask. The adapter zone has a second source,
  `app/os/time_sync_zephyr.c`, which `app/os/CMakeLists.txt` builds only when `sntp` is on.
- **Three files instead of two for the logic.** The plain-C policy is `app/src/time_sync_policy.[ch]`, the
  glue that calls the Crux Time authority is `app/src/time_sync.[ch]`, and the port that the glue calls is
  `app/src/time_sync_port.h`, implemented by the adapter. The policy has a host test
  (`tests/host/test_time_sync_policy.c`).
- **The scenario compiles the product's own glue, policy and adapter** against the real Crux Time provider
  and Zephyr's SNTP library, with a UDP responder on the loopback interface. It uses one image per case
  (`SNTP_CASE`, seven cases in `tests/native_sim/sntp/testcase.yaml`).
- **The CI build job checks more.** `.github/workflows/ci.yml` job `sntp` also checks that no RTC adapter
  (`CONFIG_CRUX_TIME_RTC`) and no SNTP uncertainty option are on, and that the glue, the policy and the
  adapter are linked.
- **The findings note** is `docs/findings/s5-time-synchronisation.md`. Its results table records what CI showed at
  a named revision.

**management (management over HTTPS).** `management` is the largest capability and the only one that needs a group of
the Crux manifest.

- **It needs the Mbed TLS modules.** They are in the optional group `crux-secure-management`, which stays off in
  `west.yml`. The `management` job and the `management` `Budget` row switch it on in their own runner, after
  `scripts/check_mbed_only.py` has checked the resolved project list. The scenario is in a sibling directory,
  `tests/native_sim_mbed`, so that the `workload` job never selects it, and a missing module fails the job and does not
  skip the scenario. Changing `ci.yml`, `budget.yml` and `CONTRIBUTING.md` is a reviewed change of the files listed under
  [Files that need a reviewed change](#files-that-need-a-reviewed-change).
- **It excludes two configurations.** `CRUX_CONTROLLER_MANAGEMENT` depends on `!CRUX_CONTROLLER_FILE` and `!CRUX_CONTROLLER_SYSTEM`, because
  `file` owns another file provider and `system` clears the reset cause that `management` reads once. `sntp` may be on, and that image is not
  built in CI.
- **The route table belongs to the target `app`.** Crux's route function sets properties on the sources of `app`,
  so `app/management/management.cmake` is included by `app/CMakeLists.txt` and is not a subdirectory. The tooling
  tests that forbid include paths and foreign sources read that file too: extend such a rule to a new build file, and
  never loosen it.
- **One file starts the services.** `app/compose/management_start.c` implements `app/src/management_port.h` in the
  order that the header documents. The policy, the address check and the version check are plain C in `app/src`
  and have a host test.
- **The scenario is one image with ordered cases**, because the start sequence runs once per program. Its Mbed
  profile is a copy of the fragment's, and a tooling test compares them.
- **The CI job reads more of what the build resolved**, including the devicetree alias, the RAM disk and the symbols
  that the image must not link.
- **A capability can make existing assertions false.** Replace such an assertion only for the changed behaviour
  and give the reason in the commit message; `management` replaced the `ManagementNotBuilt` checks of its
  groundwork, moved the synthetic Crux tree of three boundary tests to `tests/tooling/fake_crux.py` and extended
  the row lists of the other capability tests.
