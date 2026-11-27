# Contributing to Crux Controller

This guide covers source, tests, documentation, build configuration and CI workflows in this
repository. It is short on purpose. For what the repository is, read the [README](README.md) first.

## What this repository is, and is not

Crux Controller is built on [Crux](https://github.com/wonny-labs/crux) (the `crux`
repository) and uses Crux only through its public and approved composition interfaces, so that a gap in
those interfaces shows up here and is reported to Crux as an issue.

- Crux Controller is a controller framework for products built on Crux: a Zephyr module that composes
  the Crux services of a networked controller, with a base image that runs those services and no
  application. Products import the module and add their application.
- It is not a product and not Crux, and it adds no Crux public interface. A product is a firmware
  repository outside this one that imports Crux and the framework module.
- It is not evidence for any Crux security claim. That evidence lives in Crux.
- The configurations from `workload` to `management` build on a synthetic workload written for this
  repository. The build configurations `minimal`, `workload`, `net`, `file`, `system`, `sntp`, `management`
  and `base` are built in CI. Only the `net` image has run on a board (twice, on one bench; see
  `docs/findings/s2-first-board-run.md`), and a change must not claim otherwise.

## The boundary

`scripts/check_boundary.py` checks what the source trees may include. It runs in CI as the
`Boundary check` job. Details and reasons are in [docs/composition-zone.md](docs/composition-zone.md).

| Tree | May include | Fails |
|---|---|---|
| `app/src` | ISO C, the headers of the Crux Sockets profile, public `<crux/NAME.h>` headers except the frozen three, its own tree, `workload/include`, the headers of `framework/src`, `<controller/NAME.h>` | any Zephyr header, `<crux/thread.h>`, `<crux/sync.h>`, `<crux/serial.h>`, `<crux/file_zephyr.h>`, `<crux/web_zephyr.h>`, `<crux/cli_zephyr.h>`, a header of a composition or adapter zone |
| `workload/` | ISO C and its own tree | Crux, Sockets profile and Zephyr headers |
| `app/compose/` (the composition zone) | ISO C, public `<crux/NAME.h>` headers, `<crux/file_zephyr.h>`, `<crux/web_zephyr.h>`, `<crux/cli_zephyr.h>`, `zephyr/fs/fs.h`, `zephyr/devicetree.h`, `zephyr/net/tls_credentials.h`, its own tree, header files (`.h`) of `app/src` | the Sockets profile, a Crux private or port header, any other Zephyr header, vendor and third-party headers |
| `app/os/` (the adapter zone) | ISO C, public `<crux/NAME.h>` headers except the frozen three, `zephyr/kernel.h`, `zephyr/net/sntp.h`, its own tree, header files (`.h`) of `app/src` | the Sockets profile and other POSIX headers, `<crux/thread.h>`, `<crux/sync.h>`, `<crux/serial.h>`, `<crux/file_zephyr.h>`, `<crux/web_zephyr.h>`, `<crux/cli_zephyr.h>` or any composition interface, a Crux private or port header, any other Zephyr header, vendor and third-party headers |
| `include/` (the interface headers of the framework) | ISO C, public `<crux/NAME.h>` headers except the frozen three, its own tree | any Zephyr header, the Sockets profile, a composition interface, a header of `framework/` |
| `framework/src` (the portable core) | ISO C, public `<crux/NAME.h>` headers except the frozen three, its own tree, `<controller/NAME.h>` | any Zephyr header, the Sockets profile, a composition interface, the workload, a header of a zone |
| `framework/compose/` (the composition zone of the module) | the allow-list of `app/compose/`, header files (`.h`) of `framework/src` | as `app/compose/`, and `app/src` |
| `framework/os/` (the adapter zone of the module) | the allow-list of `app/os/`, `zephyr/task_wdt/task_wdt.h`, `zephyr/retention/retention.h`, `zephyr/fatal.h`, `zephyr/device.h`, `zephyr/devicetree.h`, header files (`.h`) of `framework/src` | as `app/os/` for every other header, and `app/src` |

A C or C++ source or header under `app/`, `framework/`, `include/` or `zephyr/` that is in none of these trees fails.

Any other include fails, and so does an include whose operand is a macro, because it cannot be checked.
The check reads includes only, so do not add include paths in CMake: `app/CMakeLists.txt`,
`framework/management/management.cmake` and `framework/management/entropy.cmake` are checked for that.
The module's build file `zephyr/CMakeLists.txt` adds one include path, `include/`, to the interface target that
an image links.

There is no exception, waiver or per-file opt-out. A boundary that a change can step over says nothing
about what a real consumer can use, and it would hide the gap that this repository exists to find.
To widen it (for example one more Zephyr header in a zone), change `scripts/check_boundary.py`,
`tests/tooling/test_boundary.py` and `docs/composition-zone.md` together in one pull request that is
reviewed as such, and say in it why the public interface is not enough.

## Build and test

Tooling tests run locally.
They need Python with PyYAML (CI uses Python 3.12); the tests that read the CI map file need Python 3.11 or later and skip on an older one:

```bash
python3 -m venv .venv && . .venv/bin/activate && python -m pip install pyyaml
python -m unittest discover -s tests/tooling -v
python scripts/check_boundary.py
```

The format check and the static analysis run locally with the pinned tools, from the repository root:

```bash
python3 -m pip install clang-format==18.1.8
scripts/check-format.sh
CLANG_TIDY=clang-tidy-18 python3 scripts/analyze_host.py
```

CI is the reference for the Zephyr builds and the Twister runs.
[docs/native-setup.md](docs/native-setup.md) gives the CI commands for a local `native_sim` run,
and a local result does not replace CI. A change to `app/`, `conf`, overlays or `tests/native_sim` takes
its evidence from CI, and the pull request says so.
The checks are in [`scripts/ci/checks.toml`](scripts/ci/checks.toml), in a job for each job below.
A workflow installs runner packages with [`scripts/ci/apt-install.sh`](scripts/ci/apt-install.sh), which reads only the Ubuntu archive, so a third-party source of the runner image cannot fail the job.
The workflows in `.github/workflows/` and the [`Jenkinsfile`](Jenkinsfile) only set up a runner and call `scripts/ci/run-tier.sh` ([CI tiers](#ci-tiers)):

| Workflow | Jobs | When |
|---|---|---|
| `ci.yml` | `Tooling tests` (with the checks `secret-scan`: `scripts/ci/secret-scan.sh`, and `spdx`: `scripts/check_spdx.py`), `West pins`, `Host tests` (sanitizer off and on; with sanitizer off also the coverage report `host-coverage`), `workload` (Twister on `native_sim` for the scenarios in `tests/native_sim`, then the RT1060-EVKB build), `net build`, `file build`, `system build`, `sntp build`, `management build` (Twister on `native_sim` for the scenario in `tests/native_sim_mbed`, then the RT1060-EVKB build; it fetches the Mbed TLS modules, with the group switched on in its own runner), `minimal build` (`app/prj.conf` alone), `base build` (the base image: Twister on `native_sim` for the scenarios in `tests/framework`, which build the framework from the Zephyr module, then the RT1060-EVKB build and its SBOM with `release/check_sbom.py`, and every night its known vulnerabilities with `scripts/ci/match-vulnerabilities.sh`; it fetches the Mbed TLS modules as `management build` does), `Boundary check` (with the include check script of the Crux style kit as a further check), `Patch style` (Zephyr's checkpatch, rule BRACES, on the changed C lines, with `scripts/check-patch.sh`), `Static analysis` (clang-format 18.1.8 over every tracked C file with `scripts/check-format.sh`, then clang-tidy 18 over the host-built sources with `scripts/analyze_host.py`, which prints the list of tracked sources not analysed; any difference or finding fails the job) (names shortened) | pull requests, pushes to `main`, nightly |
| `budget.yml` | `Budget` for `minimal` to `base`: static resource use against `budgets/limits.json` (the `management` and `base` rows fetch the Mbed TLS modules in their own runners) | pull requests, pushes to `main`, nightly |
| `devcontainer.yml` | `Dev container`: builds the image of `.devcontainer/` and runs in it, through `scripts/dev-shell.sh`, the tooling tests, the format check, the static analysis, the host tests (sanitizer off and on), both boundary checks, the `native_sim` scenarios and the RT1060-EVKB cross-build of `workload` with its output and configuration checks. Its pins are those of `ci.yml`, and `tests/tooling/test_devcontainer.py` compares them | pull requests and pushes to `main` that change `.devcontainer/`, `scripts/dev-shell.sh`, `scripts/bootstrap.sh`, `.vscode/`, `west.yml`, `scripts/ci/` or the workflow, nightly, and by hand |
| `rebuild.yml` | builds `net` twice at different paths and compares `zephyr.bin` and `firmware_identity` | by hand, nightly, and pull requests that change the workflow, `release/` or `scripts/ci/` |
| `release.yml` | dry run of the release flow, publishes nothing | by hand, nightly, and pull requests that change the workflow, `release/`, `west.yml` or `scripts/ci/` |
| `scheduled-main.yml` | `net build against Crux main` and `product integration (fixture product, native_sim)`, with the SBOM and the known vulnerabilities of the fixture image (checks of the `nightly` tier only) | daily, and by hand |
| `crux-pin-update.yml` | `Refresh the Crux pin pull request` (see "The pin and the manifest"), `Put the CI evidence into the pin pull request` | daily and by hand; the evidence job also after each `release` or `budget` run of the pin pull request |

The scheduled build is information only: it shows ahead of time that a Crux pin moved or that Crux
broke the build, and the pinned build stays the gate for pull requests. Every RT1060-EVKB build requires
the verified Zephyr baseline (`-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`). A green CI result does not replace
review, and a build in CI is not a run on a board.

### CI tiers

CI runs in the three tiers of Crux, with its entry point, tier names, map file format and Jenkins parameters, as the [Crux CI page](https://github.com/wonny-labs/crux/blob/1330195487c34c8df6046d41ae030d3cdf8a5138/docs/ci.md) describes.
`scripts/ci/tiers.py` is a copy of the Crux selector.

| Tier | When | What runs |
|---|---|---|
| `fast` | every push to a draft pull request, a Jenkins branch build | the tooling tests, and the checks of the parts of the repository that the change touches; a change to a CI, build or script file, `west.yml`, a CMake, Kconfig, `.conf` or overlay file, `budgets/`, a path outside the parts, or more than three parts runs `full` instead |
| `full` | a pull request that is ready for review and every push to it, a push to `main`, a Jenkins change request | every check of the table above, under the path filters of its workflow |
| `nightly` | daily on `main` | every check whatever the change, the build against Crux `main`, and the product integration check: a fixture product (`tests/product_integration`) imports this repository at the commit under test into a west workspace of its own and builds and runs on `native_sim` |

The parts and their checks are the `[components]` and `fast` entries of `scripts/ci/checks.toml`.
Mark a draft pull request ready for review to run the `full` tier.
To see what a tier selects for the current branch, or to run one check, from the clone in the workspace folder:

```bash
scripts/ci/run-tier.sh fast --plan
scripts/ci/run-tier.sh full --job net --check net-config
```

The entry point needs Python 3.11 or later, and a check that builds needs the workspace that `scripts/ci/prepare-job.sh` sets up.
A failing check prints the command that reruns it.
A new check goes into `scripts/ci/checks.toml`, and its id into `EXPECTED_FULL` in `tests/tooling/test_ci_tiers.py`.

## The pin and the manifest

`west.yml` imports `crux` at a pinned commit, a full SHA and never a branch or a tag. `west
crux-pins` must print a `CONTRACT crux` line and no `MISMATCH`; the `West pins` job checks this
and has a negative control that must fail. Another project is added to `west.yml` only with a comment
that says why it is there and where its revision comes from, and `docs/dependencies.md` is updated. The
optional groups of the Crux manifest stay off in `west.yml` and in every job except `management build`, `base build`
and the `Budget` rows of `management` and `base`. Those four switch `crux-secure-management` on in their own runner, only after
`scripts/check_mbed_only.py` has checked the resolved project list, so that only the Mbed TLS modules are
fetched. The other projects of that group are not under the Apache-2.0 terms of this repository, and the
narrowed import in `west.yml` keeps them out.

A pin moves in its own small pull request, with the reason in the commit message:

1. Change the revision and the comment above it in `west.yml`, and the approved commit in
   `tests/tooling/test_manifest.py`.
2. Update the places that quote the commit as the current pin: `docs/dependencies.md`, `RELEASE.md`
   (its link and the short hash that `tests/tooling/test_docs.py` looks for) and `CHANGELOG.md`.
   Notes under `docs/findings/` stay as they were recorded; only the current-pin line of its index moves.
3. Put in the pull request the SHA-256 of the `net` `zephyr.bin` and its `firmware_identity` (the release
   manifest that the `release.yml` dry run prints has both), and the budget tables of the `Budget`
   jobs. If numbers move, say so. A limit in `budgets/limits.json` is not changed in the same pull
   request to make a bump pass.

`crux-pin-update.yml` keeps one such pull request open, on the branch `bot/crux-pin`, and refreshes
it when Crux main moves. It runs `scripts/crux-pin-bot.py` of the Crux that `west.yml` pins, never a
script from Crux main. The bot rewrites the revision in `west.yml` and runs `scripts/crux-pin-hook`,
which moves the other quotes of steps 1 and 2 and the links to Crux pages at the pin (its `QUOTES`
table), and fails when a quote it expects is missing. The comment above the pin, the `CHANGELOG.md`
entry and the quotes in the hook's `KEPT` table, other than the revision in `west.yml`, stay manual. Step 3 comes from CI: after each refresh
and each `release` or `budget` run, `scripts/pin_evidence.py` copies the hash, the `firmware_identity`
and the budget tables from their logs into the pull request body. Nothing merges itself. A person
reads the Crux changes, adds a commit with the reason, the pin comment and the `CHANGELOG.md` entry
(the bot then stops refreshing the branch), compares the evidence with the previous pin and approves
the merge. `Jenkinsfile.example` runs the same bot for a copy built by Jenkins; that path has no
evidence step yet.

The workflow needs the repository secret `CRUX_PIN_TOKEN`: a fine-grained personal access token with
access to this repository only and the repository permissions Contents and Pull requests set to read
and write. A GitHub App installation token expires after one hour, so it would need a step that creates
it in the job, and this workflow has none. A pull request opened with the automatic `GITHUB_TOKEN`
would start no workflow, so its checks would not run. The bot's pull request is authored by the
token's owner, and the token expires on the date set when it was created, so it needs renewing. The bot's pull request is not a draft and changes `west.yml`,
so it runs the `full` tier. Without the secret the workflow changes nothing and ends with a warning.

## Changing behaviour

Write the test first for new behaviour and for a fix, and watch it fail. Never weaken or delete a test,
or relax a check, to make a change pass. Change an existing assertion only when the approved behaviour
changes, and say so in the pull request. Extend a check rather than loosen it.

Keep one logical change in a pull request. Reuse what Zephyr and Crux provide rather than adding a layer
of your own.

## Documentation

Every Markdown page follows [docs/documentation-guidelines.md](docs/documentation-guidelines.md): one type per
page, one home per fact, current state only. `tests/tooling/test_docs_page_types.py` guards it.

## Static analysis and coding standard

Measured on `main` at merge `e11e971`, on 18 November 2026; the counts of sources that are not analysed
follow the current tree. If the scripts and workflows named here have changed since, they are the source of truth.

- **Format.** clang-format 18.1.8 over every tracked C file is a gate: `scripts/check-format.sh`, in the
  `Static analysis` job of `ci.yml`.
- **clang-tidy.** clang-tidy 18 with `.clang-tidy` (checks from `bugprone`, `clang-analyzer`,
  `performance` and `portability`; warnings are errors) runs over the 22 sources that the host tests
  build: `scripts/analyze_host.py`, in the same job. `.clang-tidy` also lists
  `readability-identifier-naming` without options, so it checks no naming rule. The script prints the
  tracked sources that it did not analyse, 32 today: the sources that the host tests do not build,
  because they need Zephyr or Crux headers or Kconfig values. It does so without failing.
- **The 32 not analysed.** 19 of those 32 are product sources (`app/`, `framework/`), built with
  `-Wall -Wextra -Werror` as `app/CMakeLists.txt`, `app/os/CMakeLists.txt`, `framework/configurations.cmake`,
  `framework/compose/CMakeLists.txt` and `zephyr/CMakeLists.txt` set. The other 13 are the `native_sim` scenario
  sources (`tests/{native_sim*,framework}/*/src/*.c`, the helpers `tests/framework/common/*.c`, `tests/product_integration/src/test_*.c`): the CMake
  files of the scenarios set those flags on the product sources that they pull in, not on the scenario source.
- **Other gates.** The include rules (`scripts/check_boundary.py` and the Crux product include check,
  both in the `Boundary check` job) and the resource limits (`.github/workflows/budget.yml`).
- **Headers and patch style.** `scripts/check_spdx.py` (the check `spdx` of `Tooling tests`)
  requires the licence identifier line in first-party C, CMake, Kconfig, Python and shell files, and
  keeps a list of two older scripts that lack it. `scripts/check-patch.sh` (the `Patch style` job) runs
  Zephyr's checkpatch with the rule BRACES on the changed C lines of a change.
- **Coverage and secrets.** The check `host-coverage` of the `Host tests` job (sanitizer off) builds the host tests with GCC's `--coverage` and prints a gcovr summary; no threshold is set yet (an owner decision), so it reports and does not gate. The check `secret-scan` of `Tooling tests` runs Gitleaks over the checkout and fails on a finding.
- **Not done.** There is no coverage threshold, no coverage measurement of the `native_sim` scenarios and no linting of Python, shell, YAML and CMake. Parts of the Zephyr-side glue are not run by any test: the start order in `composition.c`, the `system` watchdog feed path and the `management` web page script.

These are the configured automated checks of this repository, not a claim of MISRA C, CERT C, security
or functional-safety compliance. The Crux platform states its own position in its
[coding guidelines](https://github.com/wonny-labs/crux/blob/751e04aead779ac08e438ec1e2640e57fc50e9fe/docs/coding-guidelines.md),
read at that commit.

Known gaps, not scheduled: the 32 sources above have no clang-tidy analysis, and nothing measures how much of the code the `native_sim` scenarios run.

The product's own Kconfig symbols use the prefix `CRUX_CONTROLLER_`; they are the product's names, not
Crux platform symbols.

Crux's former controller sample used the same prefix, and a Crux test image
(`tests/board_images/integration_probe/Kconfig`) still defines `CONFIG_CRUX_CONTROLLER_M3`. Crux System still refuses a configuration that enables
`CONFIG_CRUX_CONTROLLER_M3`, as a further owner of the native watchdog next to `WDT_SHELL`,
`HWINFO_SHELL` and `TASK_WDT_HW_FALLBACK`, not because of the prefix. The note
`docs/findings/s4-system-composition.md` records this as read at Crux `37c92b18`, and the same
check was in the Crux source at `8e3737d2`, `1c4cf284`, `c5439c51`, `ea16f99f`, `ce2eb313`, `13c950bb`, `bd9efbc7`, `62ed69f1` and `05a50475` and is at `13301954`
(`components/system/ports/zephyr/CMakeLists.txt`). This repository never defines that symbol.

## Commits and pull requests

Write in English. Use a short conventional subject, `<type>: <summary>`, with a lowercase imperative
verb and no final full stop, under 72 characters. The types in use are `feat`, `fix`, `docs`, `test`,
`build`, `ci`, `refactor` and `chore`. Explain why in the body when it is not obvious. Work on a branch
and open a pull request; the history of `main` uses merge commits.

A pull request says what changed, why, and how it was checked. List each check with the revision it ran
on and who ran it (CI, a reviewer, or you), and name what was not run. Do not report a check as passing
that did not run, and do not describe a CI build as a run on a board.

## Review

A material change gets an independent review by someone who did not write it. The reviewer reads the
actual files and checks, not the summary, and gives `PASS`, `REVISE` or `ESCALATE`. A blocking finding
is an unmet acceptance criterion, a broken rule of this guide or a factual error. `REVISE` means the
author can fix the blocking findings and get one re-check. `ESCALATE` means the owner has to decide.
Other findings go in the pull request.

A `PASS` means there is no blocking finding. It does not grant merge, scope, hardware or release
authority. Merging a pull request needs the owner's approval, and a `PASS` or green CI does not give it.
AI assistance is not approval and not evidence: claims about tests need the actual results.

## Content rules

Everything here is public. Do not add:

- a name of an employer or customer, a proprietary product or runtime, or a private repository, or a
  link to one;
- a reference to a private planning document (the test `tests/tooling/test_public_text.py` fails on
  the usual forms; it scans this file too);
- the memory sizes of a real product, secrets, keys or credentials, or an absolute path of a personal
  or build machine;
- code or text that you are not allowed to publish under Apache-2.0.

Hashes only: no firmware image, `.elf` or `.map` file goes into the repository, a release bundle or a
CI artefact. No workflow uploads an artefact, and a test fails if one starts to. See
[RELEASE.md](RELEASE.md).

## Versions, releases and tags

This section applies to people and to automated coding assistants alike. The release steps are in
[RELEASE.md](RELEASE.md).

- The version follows the rules in [RELEASE.md](RELEASE.md#versions). The number is kept only in
  `include/controller/version.h`.
- `main` carries the next planned release with `-dev`, now `0.1.0-dev`. No pull request outside a release
  task changes the version macros. Code must not test features by version number before 1.0.0.
- Each pull request records its change and its compatibility effect in [CHANGELOG.md](CHANGELOG.md) under
  Unreleased. Mark a breaking change to a public interface in that entry and in the pull request.
- Builds are told apart by commit SHA. The version string does not order two snapshots of `main`.
- `tests/tooling/test_version.py` fails when the version parts and the string disagree. CI runs it.
- Change the version files only in a release task. Create no tag and no GitHub Release, and do not treat a
  green check as approval. Tags, GitHub Releases and forks of this repository need the owner's approval.
  No workflow tags or publishes; they run with `contents: read`. No support period is promised, and only
  the latest release, if one exists, is supported.

## Security and licence

Report a suspected vulnerability privately as [SECURITY.md](SECURITY.md) describes, and not in a public
issue or pull request. A weakness in Crux itself belongs in Crux.

The licence is Apache-2.0 ([LICENSE](LICENSE)). Section 5 of the licence applies to a contribution
that you submit, unless you state otherwise.
