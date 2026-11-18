# Your first change

This page takes you from a branch to a pull request with one small change that needs no Zephyr, no container
and no board: a new case in the host tests. You will write the test first, run the checks that run on your
machine, commit it, and read what CI and the reviewer do next. The example change is only there to carry the
steps. You do not need to keep it.

Read the [README](../README.md) and [CONTRIBUTING.md](../CONTRIBUTING.md) first if you have not. Words such as
`PASS`, "owner" and "pin" are in the [glossary](glossary.md).

## 1. What you need

- Git, and a C compiler.
- CMake 3.20 or newer and Ninja.
- Python 3 with PyYAML (CI uses Python 3.12) and clang-format 18.1.8, the version that the format check requires.

[try-on-native-sim.md](try-on-native-sim.md#what-you-need-first) lists the tools in more detail. The build and
check commands on this page were run on macOS. They use no Linux-only tool, except where a step says so. On Windows, use WSL2 and
work in the Linux file system, as the try-on page explains.

## 2. Get the repository and make a branch

```bash
git clone https://github.com/wonny-labs/crux-controller.git
cd crux-controller
git switch -c test/workload-zero-period
python3 -m venv .venv && . .venv/bin/activate && python -m pip install pyyaml clang-format==18.1.8
```

If your team keeps a copy of the repository, clone your copy instead ([team-copy.md](team-copy.md)).

CONTRIBUTING.md does not prescribe a branch name. The branches in this repository's history are called
`<type>/<short-description>`, with the same types as a commit subject (`fix/...`, `docs/...`). Use one branch for one
logical change.

## 3. Write the test first

The host tests are plain C programs in `tests/host/`. They need no Zephyr. Open `tests/host/test_workload.c`. Each
case is a `static void` function that calls `CHECK(...)`, and `main()` calls every case. The validator under test is
`workload_config_validate()` in `workload/`; `workload/include/workload.h` says that a period is valid from 10 ms to
60000 ms.

The example case checks that a period of 0 ms is rejected. Add it before `config_period_60001_rejected()`, and
call it from `main()` after `config_period_9_rejected();`:

```c
static void config_period_0_rejected(void)
{
    const workload_config_t config = config_with(0, 10);

    CHECK(workload_config_validate(&config) == WORKLOAD_ERR_RANGE);
}
```

Now watch the test fail, so that you know it can. The validator already rejects 0, so this test passes at once.
Make it fail on purpose: write `WORKLOAD_OK` where it says `WORKLOAD_ERR_RANGE`, and run the host tests:

```bash
cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=OFF
cmake --build build/host
ctest --test-dir build/host --output-on-failure
```

The `workload` test fails, and it prints the failing line and a count:

```text
FAIL <path>/tests/host/test_workload.c:<line>: workload_config_validate(&config) == WORKLOAD_OK
<n> checks, 1 failures
```

Change `WORKLOAD_OK` back to `WORKLOAD_ERR_RANGE` and run `cmake --build build/host` and `ctest` again. Every test
passes and `ctest` ends with `100% tests passed`.

For new behaviour or a fix you do not need the trick: you write the test for behaviour that the code does not have
yet, it fails, and then you write the code that makes it pass. CONTRIBUTING.md asks for that order and says never to
weaken or delete a test to make a change pass.

## 4. Run the host tests with the sanitizers

CI runs the host tests twice, with the address and undefined-behaviour sanitizers off and on. Use another build
directory for the second run:

```bash
cmake -S tests/host -B build/host-asan -G Ninja -DWORKLOAD_SANITIZE=ON
cmake --build build/host-asan
ctest --test-dir build/host-asan --output-on-failure
```

## 5. Run the other checks that run on your machine

Run these from the repository root, with the virtual environment active:

```bash
python -m unittest discover -s tests/tooling
python scripts/check_boundary.py
python scripts/check_spdx.py
scripts/check-format.sh
```

What each one tells you:

- The tooling tests read the repository's files: scripts, workflows, build files and documents. The run ends with
  `OK`. It also fails when a document drifts from the statement that a test pins, which matters as soon as you
  change a document.
- `check_boundary.py` prints `boundary check passed`. It checks the include rules of the source trees. A test file
  under `tests/host` is outside those trees, but a change to `app/` or `workload/` is not.
- `check_spdx.py` checks that each first-party C, CMake, Kconfig, Python and shell file starts with the licence
  identifier line. A new file without it fails.
- `check-format.sh` checks that every C file is formatted as `.clang-format` says, with clang-format 18.1.8. It
  prints the number of files it checked. To fix a file, run that clang-format on it.

Three more checks run in CI and need tools that this page did not run on macOS:

- clang-tidy 18 over the sources that the host tests build, which include the files in `tests/host`:
  `CLANG_TIDY=clang-tidy-18 python3 scripts/analyze_host.py`. Run it on Linux or in the dev container.
- Zephyr's checkpatch on the changed C lines, `scripts/check-patch.sh`. It needs a prepared Zephyr checkout in
  `ZEPHYR_BASE`.
- The Zephyr builds and the Twister scenarios. A change to a host test does not touch them, and CI runs them
  anyway.

## 6. Commit

Write the subject as `<type>: <summary>`: a lowercase imperative verb, no final full stop, under 72 characters.
The types in use are `feat`, `fix`, `docs`, `test`, `build`, `ci`, `refactor` and `chore`. Write in English. Say why in
the body when it is not obvious:

```bash
git add tests/host/test_workload.c
git commit -m "test: cover a zero period in the workload validator" -m "The validator rejects periods below 10 ms. Only 9 ms and values above the maximum were tested."
```

## 7. Push and open the pull request

```bash
git push -u origin test/workload-zero-period
```

Then open a pull request on GitHub from the branch. CONTRIBUTING.md does not say how a contributor gets permission
to push a branch to this repository. Ask the owner. This page does not cover that step, and the commands above
stop at the push.

The pull request says what changed, why and how it was checked: what was checked, at which revision, by whom (CI, a
reviewer or you), and what was not run. Do not report a check as passing if it did not run. For the example:

```text
test: cover a zero period in the workload validator

What changed: one case in tests/host/test_workload.c. A period of 0 ms is rejected with
WORKLOAD_ERR_RANGE. No source file changed.

Why: only 9 ms and values above the maximum were tested.

What was checked, at which revision, by whom:
- Host tests, sanitizers off and on, at <short SHA>: me.
- Tooling tests, boundary check, SPDX check and format check at <short SHA>: me.
- CI at <short SHA>: the checks of this pull request, read after they finished.

What was not run: clang-tidy and checkpatch on my machine (CI runs them), anything on a board.
```

## 8. What CI runs for the change

The [table of workflows in CONTRIBUTING.md](../CONTRIBUTING.md#build-and-test) lists the jobs and when they run.
For this change the jobs to read are `Tooling tests`, `Host tests` (sanitizer off and on), `Boundary check`,
`Patch style` and `Static analysis`. CONTRIBUTING.md says that `ci.yml` and `budget.yml` run for pull requests, so the
step build jobs and the `Budget` jobs run as well, although this change does not touch them. A change to
`app/`, a configuration fragment, an overlay or `tests/native_sim` takes its evidence from CI, and the pull request
says so. A build in CI is not a run on a board.

A red job is a result to read, not a check to relax. Do not weaken a check or a test to make a job pass. CONTRIBUTING.md
says to extend a check rather than loosen it.

## 9. Review and merge

A material change gets an independent review by someone who did not write it. CONTRIBUTING.md does not define
"material"; ask the owner when you are unsure. The reviewer reads the files and the check results, not your summary,
and gives `PASS`, `REVISE` or `ESCALATE`.

- `REVISE`: fix the blocking findings and ask for one re-check.
- `ESCALATE`: the owner decides.
- `PASS`: there is no blocking finding.

A `PASS` and a green CI do not merge anything. Merging needs the owner's approval, and the history of `main` uses merge
commits. The checklist that a reviewer follows is in [reviewing.md](reviewing.md).

## 10. Discard the example

If you did the example only to learn the steps, switch back and delete the branch:

```bash
git switch -
git branch -D test/workload-zero-period
```

## Next

- To change application code or a build file: [architecture.md](architecture.md) and the "Changing behaviour" section
  of CONTRIBUTING.md. If the check you meet is the boundary check, read [composition-zone.md](composition-zone.md)
  before you look for a way round it. There is none.
- To add a step: [adding-a-step.md](adding-a-step.md).
- To run the Zephyr scenarios on your machine: [try-on-native-sim.md](try-on-native-sim.md).
