# Adding a step

This is a recipe for adding a *step* to the firmware, worked through with step S4 (Crux System: the
reset cause and a watchdog) because it is the most recent step on `main` and the smallest one that
touches every part. Every file named here exists on `main`. The commits are the ones that added S4
(`git log --oneline` shows them; the hashes are given so that you can run `git show` on each). Read the
[architecture](architecture.md) and the [glossary](glossary.md) first if the terms are new, and
[CONTRIBUTING.md](../CONTRIBUTING.md) for the rules that apply to every change.

Ground rules that shape the order of work:

- **Tests first.** Write the test, watch it fail, then write the code. CONTRIBUTING.md asks for this
  for new behaviour and for fixes, and says that an existing test or check is never weakened or deleted
  to make a change pass.
- **CI is the build.** This repository describes no local Zephyr build. Zephyr builds, Twister runs and the
  budget numbers come from CI. What you can run locally is the tooling tests, the boundary check and the
  host tests.
- **Public means only.** A step uses public Crux headers and targets. If it seems to need a Zephyr header
  or a Crux private header in `app/src`, stop: that is either a new zone entry (a separate reviewed pull
  request) or a *finding*. S4 needed neither.
- **A step is not a release and not a board run.** A green CI build does not mean the step ran on a board,
  and the pull request must not say so. Merging needs the owner's approval; a green CI and a review `PASS`
  do not give it.

## 1. Decide the shape

Answer these before writing any file. S4's answers are in brackets.

1. Which Crux component does the step use, through which public header and target? (Crux System:
   `<crux/system.h>`, `crux::system`.)
2. Does the application need anything that `app/src` may not include? If the answer is a Zephyr header, a
   composition interface or a provider name, the step needs a zone entry. (No: the driver, HWINFO and
   reboot calls are inside Crux's own binding. S3 did need the composition zone, S1 the adapter zone.)
3. Which step does it build on? Every step so far depends on S1. (S1; not S2 or S3, so the S4 image has no
   network and no file system.)
4. Which Crux pieces does the image have to provide, as Kconfig and devicetree? (Three native
   facilities, `WATCHDOG`, `HWINFO` and `REBOOT`, and the devicetree alias `crux-watchdog0`.)
5. Is there product logic that can be plain C? Put it in its own file so that a host test can run it. (The
   watchdog interval and the reset cause classes: `app/src/health_policy.[ch]`.)

## 2. The order of work

| # | What | Files (S4) | Test written first | What CI does with it |
|---|---|---|---|---|
| 1 | Declare the resource limits | `budgets/limits.json` (the `S4` row) | `S4Limits` in `tests/tooling/test_s4.py` | `Budget` job: `budgets/check.py` fails a step that has no row |
| 2 | Plain-C policy, if any | `app/src/health_policy.c`, `app/src/health_policy.h`, `tests/host/CMakeLists.txt` | `tests/host/test_health_policy.c`; `S4Policy` in `test_s4.py` | `Host tests` job, with the sanitizers off and on |
| 3 | Glue, option, fragment, overlay, build block, start | `app/src/health.[ch]`, `app/Kconfig`, `app/conf/s4.conf`, `app/boards/s4.overlay`, `app/CMakeLists.txt`, `app/src/composition.c` | `S4Configuration`, `S4BuildFiles`, `S4Sources` in `test_s4.py` | `Tooling tests`; `Boundary check`; the build job of step 5 |
| 4 | Scenario on `native_sim` | `tests/native_sim/s4/` (`CMakeLists.txt`, `prj.conf`, `app.overlay`, `testcase.yaml`, `src/test_s4.c`) | `S4Scenario` in `test_s4.py`, then the scenario itself | The `S1` job runs `west twister -p native_sim/native/64 -T crux-controller/tests/native_sim`, which runs every scenario |
| 5 | CI build job and Budget row | `.github/workflows/ci.yml` (job `s4`), `.github/workflows/budget.yml` (matrix row `S4`) | `S4Workflows` in `test_s4.py` | The new job and the new `Budget S4` job |
| 6 | Documents | `docs/findings/s4-system-composition.md`, `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md` | `S4Findings` in `test_s4.py`; `Contributing` in `tests/tooling/test_docs.py` | `Tooling tests` |

S4's history follows that order: the limits row `cbef076`, the policy `edd0bb3`, the glue with its
option, fragment, overlay and scenario `521d8db`, the CI job and Budget row `3551eab`, the findings note
with the README and changelog `8556444`. `CONTRIBUTING.md` was updated later, in `f4c66e9`, because it was
missed; do it in the same pull request as the rest.

Each step in the table is a small commit with its test first. The tooling tests are ordinary
`unittest` files that read the repository's files as text (Kconfig, CMake, `.conf`, the workflows,
the documents). That is what lets a step be written test-first without a Zephyr build.

### 1. The limits row, first

Add a row to `budgets/limits.json` that repeats the placeholder margin of the earlier steps (25 percent
free in every region). Do it in its own commit before any job names the step: `budgets/check.py` fails a
step with no row, and the file's own comment says a change to it is a reviewed change. Do not change
another step's limit in the same pull request to make a build pass. Write `S4Limits` first; it was red
(3 failures and 1 error) before the row existed.

Known catch: `test_s4.py` pins the exact list of rows (`["S0", "S1", "S2", "S3", "S4"]` in
`test_the_s4_row_equals_the_s3_row_and_no_other_row_changed` and again in
`test_the_budget_rows_of_the_other_steps_are_unchanged`). The next step has to extend those two lists, and
should say so in its pull request.

### 2. The policy as plain C

`app/src/health_policy.c` includes ISO C only and names no Crux or Zephyr symbol, so
`tests/host/CMakeLists.txt` builds it on the host with `-Wall -Wextra -Wpedantic -Werror`. The host test
`tests/host/test_health_policy.c` was written first and failed to build without the policy. Run it with and
without the sanitizers, as CI does:

```bash
cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=ON
cmake --build build/host
ctest --test-dir build/host --output-on-failure
```

Use `-DWORKLOAD_SANITIZE=OFF` for the other half. Skip this step if the step has no logic of its own. S2's
`net_client.c` is the other example of host-tested application code.

### 3. Glue, option, fragment, overlay, build, start

- **Kconfig.** A `config CRUX_CONTROLLER_S4` block in `app/Kconfig`. It depends on `CRUX_CONTROLLER_S1`, on
  the Crux symbol and on the native facilities, and it selects nothing (a test checks that). The
  fragment, not the option, turns the Crux symbol on.
- **Fragment.** `app/conf/s4.conf` turns on `CONFIG_CRUX_CONTROLLER_S4=y`, `CONFIG_CRUX_SYSTEM=y` and the
  three native facilities. Its comments say what Crux requires of the image and what it refuses (another
  owner of the watchdog), with the revision they were read at.
- **Overlay.** `app/boards/s4.overlay` sets the alias `crux-watchdog0` to `&wdog0` and enables the node. An
  overlay is configuration, not code, and CI passes it with `EXTRA_DTC_OVERLAY_FILE`.
- **Build block.** In `app/CMakeLists.txt`, inside `if(CONFIG_CRUX_CONTROLLER_S1)`:

  ```cmake
  if(CONFIG_CRUX_CONTROLLER_S4)
      target_sources(app PRIVATE src/health.c src/health_policy.c)
      target_link_libraries(app PRIVATE crux::system)
  endif()
  ```

  No `target_include_directories` anywhere: the boundary check reads includes and cannot see CMake
  include paths, so `tests/tooling` checks that none is added.
- **Glue.** `app/src/health.[ch]` is the one place that calls Crux System. Application code includes
  public headers only (`<crux/system.h>`, `<crux/logging.h>`, `<crux/status.h>`).
- **Start.** `app/src/composition.c` gets an `#ifdef CONFIG_CRUX_CONTROLLER_S4` include and a start block.
  The position in `composition_start()` is a decision: S4 starts after the storage step and before the
  workload threads, so that a slow mount cannot cost a reset.
- **Changes to shared code.** S4 needed a cycle hook in `app/src/workload_thread.[ch]`. Test shared code
  where it lives: S4 added a case to the S1 scenario (`tests/native_sim/s1/src/test_s1.c`) for the hook.

Then run the checks that do not need Zephyr:

```bash
python -m unittest discover -s tests/tooling -v
python scripts/check_boundary.py
```

`scripts/check_boundary.py` with `--crux-root <a crux-pilot checkout at the pin>` is the stronger form
that CI runs: it also requires every `<crux/NAME.h>` to be a header Crux publishes. If the boundary
check fails, do not look for an exception. There is none; read
[composition-zone.md](composition-zone.md).

### 4. The scenario

`tests/native_sim/s4/` is a Zephyr ztest application with a `testcase.yaml` for Twister. It compiles the
application's own `health.c` and `health_policy.c`, not copies, against the real Crux System provider. It
uses one image per case (`S4_CASE`, passed as `extra_args` in `testcase.yaml`) because Crux System allows
one watchdog start per boot. Write down what the simulator cannot show: it has no watchdog, so S4's
scenario shows the boot line and an unavailable watchdog, and no feed cycle. That limit is stated in the
test source's header comment and in the findings note, and a test checks both.

You cannot run Twister locally. Open the pull request and let the `S1` job run it; say in the pull request
that the scenario had not run before CI.

### 5. The CI job and the Budget row

Add a job `s4` to `.github/workflows/ci.yml` by copying the S3 job. The name must read `S4 build (...)`:
`tests/tooling/test_docs.py` finds the step build jobs by the pattern `S<digit> build`. The S4 job:

1. builds with `-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`, `-DEXTRA_CONF_FILE=conf/s1.conf;conf/s4.conf` and
   `-DEXTRA_DTC_OVERLAY_FILE=boards/s4.overlay`;
2. checks that `zephyr.bin` and `zephyr.meta` exist;
3. checks the resolved `.config` and `zephyr.dts`: the options that must be on, the options that must be
   off (another watchdog owner, Crux Thread, Sync, Queue), the alias, and the node status;
4. checks with `nm` that the glue and the Crux calls it makes are linked.

Step 3 of the job exists because an unmet Kconfig dependency only prints a warning: the image would
build without the step. CI therefore reads what the build resolved, not what the command line asked for.
Add the same guard to the Budget matrix through the row's `require` field in
`.github/workflows/budget.yml`:

```yaml
- step: S4
  conf: "conf/s1.conf;conf/s4.conf"
  overlay: "boards/s4.overlay"
  require: "CONFIG_CRUX_CONTROLLER_S4=y CONFIG_CRUX_SYSTEM=y"
```

The `Budget S4` job builds the step, runs the `rom_report` and `ram_report` targets, collects the memory
regions with `budgets/collect.py` and compares them with the limits row. It publishes the numbers as a
job summary and uploads nothing: the repository publishes hashes only, and a test fails if a workflow
uploads an artifact. No job flashes, resets or runs anything on a board.

### 6. The documents

- **Findings note**, `docs/findings/s4-system-composition.md`. Label each statement Measured (you ran it
  and name the command), Inferred (read from `crux-pilot` source at the pinned commit, not run) or Open.
  Results that only CI can produce are written as Open with the CI job named, and recorded in the pull
  request afterwards. The note lists what the product had to write, the friction, the decisions made
  (with the test that pins each) and what the step does not show. It carries no line counts, because they
  go stale.
- **`README.md`**: a row in the step table and a clause in the status paragraph. The status must say
  "built and never run on a board" until a board run is recorded in a finding.
- **`CHANGELOG.md`**: an entry under Unreleased.
- **`CONTRIBUTING.md`**: three statements that `tests/tooling/test_docs.py` (class `Contributing`) checks
  against the workflows: the role section says "Steps S0 to S<n> are built in CI", the `ci.yml` row
  names `S<n> build`, and the `budget.yml` row says `` `Budget` for S0 to S<n>: ``.

## 3. Checks before the pull request, and what to write in it

Run the tooling tests and the boundary check locally, and the host tests if you have CMake and a C
compiler. List each check in the pull request with the revision it ran on and who ran it (you, CI or a
reviewer), and name what was not run. For S4 that list ends with: Zephyr builds, Twister scenarios and
the Budget numbers run in CI only; nothing ran on a board. Two cautions from S4's history:

- A local compile with the host compiler is necessary and not sufficient. GCC in CI rejected a comparison
  between constants of two different anonymous enums (`-Werror=enum-compare`) that the local Apple clang
  accepted (`1cbf399`).
- The Crux behaviour you rely on is read from the pinned source. Say so in the findings (Inferred), name
  the file, and do not assume a later Crux revision behaves the same.

If the step needs a newer Crux than the pin, move the pin first, in its own pull request, as described
in [CONTRIBUTING.md](../CONTRIBUTING.md). A pin move is not folded into a step.

## 4. Mechanical check list

Use this at the end. `<n>` is the step number.

- [ ] `budgets/limits.json` has the row `S<n>`, added before any job names it.
- [ ] `app/Kconfig` has `CRUX_CONTROLLER_S<n>`, depending on the base step and selecting nothing.
- [ ] `app/conf/s<n>.conf` and, if needed, `app/boards/s<n>.overlay` exist, with comments naming the
      Crux revision they were read at.
- [ ] `app/CMakeLists.txt` has the block inside the `CONFIG_CRUX_CONTROLLER_S1` condition and adds no
      include path.
- [ ] `app/src/composition.c` starts the step, at a position that is argued in a comment.
- [ ] `tests/native_sim/s<n>/` has a `testcase.yaml` with `platform_allow: native_sim/native/64`.
- [ ] `tests/tooling/test_s<n>.py` exists, and the exact row lists of `test_s4.py` are extended.
- [ ] `ci.yml` has the job `s<n>`, named `S<n> build (...)`; `budget.yml` has the row.
- [ ] The findings note, the README row, the changelog entry and the three statements of
      `CONTRIBUTING.md` are updated.
- [ ] `python -m unittest discover -s tests/tooling` and `python scripts/check_boundary.py` pass.
- [ ] The pull request lists each check with its revision and who ran it, and says that CI builds are
      not board runs.
