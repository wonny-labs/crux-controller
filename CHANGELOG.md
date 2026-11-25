# Changelog

This file follows the idea of [Keep a Changelog](https://keepachangelog.com/). There is no release
yet and no tag, so everything below is unreleased: it is what the `main` branch contains. Only the `net`
image ran on a board, twice (see `docs/findings/s2-first-board-run.md`). Entries below the first section name the
build configurations by their earlier step ids, S0 to S6.

## Unreleased

### Capability names

- The step ids S0 to S6 are replaced by capability names: S0 `base`, S1 `workload`, S2 `net`, S3 `file`,
  S4 `system`, S5 `sntp` and S6 `management`. The fragments and overlays (`app/conf/<name>.conf`,
  `app/boards/<name>.overlay`), the product's Kconfig options (`CRUX_CONTROLLER_WORKLOAD` to
  `CRUX_CONTROLLER_MANAGEMENT`), the CI jobs (`net build` and so on), the `Budget` rows and jobs, the build
  directories, the `native_sim` scenario directories and Twister names (`controller.<name>.native_sim...`), the
  case variables (`FILE_CASE`, `SYSTEM_CASE`, `SNTP_CASE`), the tooling tests (`test_<name>.py`), the budget tool
  option (`--config`) and `docs/adding-a-capability.md` carry the new names. `docs/findings/README.md` maps each
  old id to its name, and the notes in `docs/findings/` and `docs/history/` keep the ids they were written with.
  No limit changes and no assertion is weakened. The `management` image reports the project version
  `crux-controller-management` instead of `crux-controller-s6`, and the firmware identity of each image changes
  with its Kconfig names.
- The documents are reworked by page type: the README is an entry page (capabilities, quick start, where to read
  next, one status line), and the board-run status, sizes and evidence links are on the roadmap and in the
  findings index.

### Dev Container and onboarding

- With `CRUX_JLINK=auto`, the image build downloads the J-Link version pinned in `.devcontainer/Dockerfile`
  (`CRUX_JLINK_SEGGER_VERSION`, `CRUX_JLINK_SEGGER_SHA256`) from SEGGER when no package is placed and no
  `CRUX_JLINK_URL` is set, as Crux's Dev Container does. A failed download or a SHA-256 mismatch installs nothing
  and builds without it, with a warning; `CRUX_JLINK=1` makes either an error. The `devcontainer` CI job sets
  `CRUX_JLINK=0`, so CI does not download the software or accept SEGGER's terms of use.
- One Dev Container instead of two: it mounts the USB bus of the host with a device cgroup rule, installs the
  SEGGER J-Link software from `.devcontainer/jlink/packages/` or from a hosted copy (`CRUX_JLINK_URL` with
  `CRUX_JLINK_DEB_SHA256`), and builds without it, with a warning, when neither is given. The optional board
  container (`.devcontainer/board/`) and `scripts/board-shell.sh` are removed; `scripts/dev-shell.sh` passes the USB
  bus itself.
- `scripts/bootstrap.sh` is the one entry that prepares a clone (`CRUX_BOOTSTRAP=host|zephyr|all`, `status`,
  `board-host`, `--keep-going`); the Dev Container runs it after it is created, as Crux's Dev Container does.
  `.devcontainer/setup.sh` and `.devcontainer/check-host.sh` keep their logic.
- `.vscode/` has the two Cortex-Debug profiles for the board, "Board: Flash and run to main" and "Board: Attach (no
  reset)", with the J-Link speed `auto`, and the tasks "Build firmware" and "Board: Build and flash". None has run
  on hardware.

### Build and manifest

- The west manifest imports `crux-pilot` at a pinned commit (`13c950bb`, which contains the File
  composition interface `<crux/file_zephyr.h>`) and adds `picolibc` as a test-only project. A CI job
  checks the pins with `west crux-pins` and has a negative control that must fail.
- The `crux-pilot` pin moved from `37c92b18` to `dfd3ad7d`, which adds the public management headers
  and the simulated `native_sim` System watchdog. That commit did not contain the move of the crypto
  modules to the Zephyr v4.4-branch revisions; the next entry covers it. The Zephyr revision (v4.4.2) and
  the verified baseline are unchanged. The new Crux manifest adds one optional group, `crux-boot` (MCUboot), which stays off. No
  controller code adopts the new headers yet. The S2 firmware hash and the budget tables are in the
  pull request, because they come from CI.
- The `crux-pilot` pin moved from `dfd3ad7d` to `8e3737d2`, the squash commit of wonny-labs/crux-pilot#485,
  approved by the project owner on 16 November 2026. The range contains the move of the crypto modules
  (wonny-labs/crux-pilot#416): `mbedtls` is now Mbed TLS 4.1.1 plus 8 commits and `tf-psa-crypto` is
  TF-PSA-Crypto 1.1.1 plus 24 commits (as the dependency review of `crux-pilot` counts them), the revisions
  of Zephyr's v4.4-branch after v4.4.2. Both are in the optional group
  `crux-secure-management`, which stays off, so this repository does not fetch them; the Crux manifest
  differs from the previous pin only in those two revisions and the comment above them. The Zephyr revision (v4.4.2) and the verified
  baseline are unchanged. The pin now also holds `CONFIG_CRUX_PSA_THREADING` (Experimental, off by
  default), `<crux/cli_zephyr.h>` and an RT1060 management sample on the Mbed TLS profile. No controller
  code uses them yet. The S2 firmware hash and the budget tables are in the pull request, because they
  come from CI.
- The `crux-pilot` pin moved from `8e3737d2` to `cd66b9e5`, the squash commit of wonny-labs/crux-pilot#530.
  The Crux manifest is unchanged in this range, so the Zephyr revision (v4.4.2), the module revisions and
  the optional groups stay as they were. The range adds `CONFIG_CRUX_WEB_HEADER_DEADLINE_MS` (default
  10000, which step S6 keeps), makes `crux_web_start()` refuse a second start and a bind text that is no
  address, and adds `CONFIG_CRUX_FILE_POOL_SIZE` (default 4) and `CONFIG_CRUX_FILE_DIR_POOL_SIZE`
  (default 2). `app/conf/s6.conf` and the S3 and S6 `native_sim` fragments set
  `CONFIG_FS_FATFS_NUM_FILES=6`; the S3 board image keeps Zephyr's default of 4, which equals the pool of
  4. Zephyr's default `CONFIG_FS_FATFS_NUM_DIRS` of 4 covers the listing pool of 2, which the Crux build
  checks. For the header deadline the Crux web adapter compiles a copy of Zephyr's
  `http_server_core.c` patched at configure time in place of the original, so the S6 image links a
  patched server core and the configure step fails if the Zephyr source differs from the one the patch
  expects. wonny-labs/crux-pilot#530 removes Crux Queue (`<crux/queue.h>`, `CONFIG_CRUX_QUEUE`); this
  repository never used it, and the boundary check and the CI option checks still refuse both. No
  controller code changes. The S2 firmware hash and the budget tables are in the pull
  request, because they come from CI.
- The `crux-pilot` pin moved from `cd66b9e5` to `5fa99839`, the squash commit of wonny-labs/crux-pilot#532.
  The Crux manifest is unchanged in this range. #532 renames the Kconfig switch of the Crux module from
  `CONFIG_CRUX_PILOT_MODULE` to `CONFIG_CRUX_MODULE`, still on by default and without an alias, so the old
  name is an unknown symbol now. No file of this repository sets either name; the comment in
  `app/conf/s3.conf` and the tests that guard the switch name the new one. `ZEPHYR_CRUX_PILOT_MODULE_DIR`,
  which `app/management/*.cmake` read, is made by Zephyr from the module folder name and is not part of
  the rename. The range also holds a documentation change (#531). No controller code changes. The S2
  firmware hash and the budget tables are in the pull request, because they come from CI.
- The `crux-pilot` pin moved from `5fa99839` to `2c017f68`, the squash commit of wonny-labs/crux-pilot#536.
  The Crux manifest is unchanged in this range, and so are the public headers, the Kconfig files and the
  CMake helpers that this repository uses. wonny-labs/crux-pilot#534 sets `name: crux` in Crux's
  `zephyr/module.yml`, so Zephyr now makes `ZEPHYR_CRUX_MODULE_DIR` and `CONFIG_ZEPHYR_CRUX_MODULE`
  whatever the checkout folder is called, and no longer sets `ZEPHYR_CRUX_PILOT_MODULE_DIR`.
  `app/management/management.cmake` (the variable and its error text) and `app/management/entropy.cmake`
  read the new name, with no fallback to the old one. The west project and its folder keep the name
  `crux-pilot`. The range also renames the Crux CMake project (#533) and adds Zephyr-style samples, host
  samples in CTest and a first-hour guide (#536). The S2 firmware hash and the budget tables are in the
  pull request, because they come from CI.
- The `crux-pilot` pin moved from `2c017f68` to `1c4cf284`, the head of Crux `main` after its onboarding
  change (one board-ready Dev Container with `scripts/bootstrap.sh`, samples sorted by purpose, the controller
  sample removed from Crux, the Settings File selection that does not depend on Reliance Edge, the pin bot). The
  Crux manifest, the public headers and the module name are as before. No controller code changes; four comments in
  `app/conf/` and `app/boards/` name the moved Crux files and sample folders. The S2 firmware hash and the budget tables
  are in the pull request, because they come from CI.
- The `crux-pilot` pin moved from `1c4cf284` to `c5439c51`, the head of Crux `main` after two changes: the
  samples `time/clock_shell` and `file/write_read` are renamed `time/shell` and `file/basic`, and the Dev Container
  image build downloads the pinned J-Link package when none is given (CI and automated image builds pass
  `CRUX_JLINK=0`). The Crux manifest, the public headers and the module name are as before. No controller file named
  the renamed samples, and the J-Link installer and its pinned version already match Crux. The S2 firmware hash and
  the budget tables are in the pull request, because they come from CI.
- The `crux-pilot` pin moved from `c5439c51` to `ea16f99f`, the head of Crux `main` after changes to its documentation,
  Dev Container, VS Code files, `scripts/bootstrap.sh` and time shell sample, and the removal of the CMake status line
  `Crux Time realtime provider` from Crux's host Time build. The Crux manifest, the public headers and the module name
  are as before. No controller code changes.
- The `crux-pilot` pin moved from `ea16f99f` to `ce2eb313`, the head of Crux `main` after wonny-labs/crux-pilot#590,
  which changes Crux's `.clangd`, VS Code files, `CMakePresets.json` display names, two documentation pages,
  `scripts/bootstrap.sh`, `scripts/bootstrap-zephyr.sh` and their tests. The Crux manifest, the public headers, the
  component code and the module name are as before. No controller code changes.
- The `crux-pilot` pin moved from `ce2eb313` to `13c950bb`, the head of Crux `main` after its sample layout and version
  batch: the release version header `<crux/version.h>`, `zephyr/`, `linux/` and `common/` folders for each Crux
  sample, renamed sections of Crux's coding guidelines, shorter bootstrap and Dev Container guidance, and
  documentation, CI and test changes. The Crux manifest, the existing public headers, the Zephyr module, the board
  samples and the product template are as before. No controller code changes.
- The `crux-pilot` import blocks wolfSSL, wolfSSH and wolfPSA by name, so enabling the Mbed TLS group
  would activate Mbed TLS and TF-PSA-Crypto and no GPL stack (checked on the project list; no job
  enables the group or fetches with it on, and it stays off in every job).
  `scripts/check_mbed_only.py` checks the resolved project list, and the `West pins` job runs it with a
  negative control that must fail.
- A daily build against `crux-pilot` main (`.github/workflows/scheduled-main.yml`) reports pin
  mismatches and build failures in its job summary. It is information only: the pinned build stays
  the gate for pull requests, and the workflow publishes nothing.
- CI builds step S0 (the skeleton), S1 (Zephyr threads and a message queue in the `app/os` adapter zone, with Crux Time and Logging, on a
  synthetic workload),
  S2 (a TCP exchange over the Crux Sockets profile) and S3 (a configuration record in a file through
  Crux File, mounted by the composition zone, on a FatFs provider for microSD) for the NXP RT1060-EVKB Rev B with the Zephyr
  baseline gate required. S3 is built and never run on a board; S2 ran twice on a board.
- CI also builds step S4 (the reset cause and a single-owner watchdog through Crux System, with the
  workload's producer thread feeding it once for each pass that has cycles due) on the S1 base, and the Budget job has an S4 row
  against limits declared first. The product composes System with public means only: `<crux/system.h>`,
  the target `crux::system`, a Kconfig fragment and a devicetree alias, with no new zone and no change to
  the boundary lists. Its conservative defaults are in `docs/findings/s4-system-composition.md`. S4 is built
  and never run on a board.
- CI also builds step S5 (the Crux Time realtime clock set from an SNTP server, on the S2 network) and the Budget
  job has an S5 row against limits declared first. A low-priority thread queries one IPv4 server through the
  Zephyr SNTP library (called only in the adapter zone `app/os`, with `sntp_simple()`), and the product's
  policy (`app/src/time_sync_policy.c`, plain C) decides what an answer may do: it never sets for a failed,
  kiss-o'-death or out-of-range answer or when the clock snapshot cannot be read, sets any in-range answer while
  the clock is not synchronised, corrects a synchronised clock from the threshold up to the maximum step, and
  refuses a larger step once and marks synchronisation lost. A synchronised clock is marked not synchronised when
  its last confirming answer is older than the stale age (strictly), judged on a failed round. The glue
  `app/src/time_sync.c` is the only caller of the Crux Time authority. SNTP here is unauthenticated, the clock
  is stepped and not slewed, nothing persists time, and S5 is built and never run on a board. Defaults and
  limits are in `docs/findings/s5-time-synchronisation.md`.
- CI also builds step S6 (management over HTTPS on the S2 network) and the Budget job has an S6 row against limits
  declared first. The composition zone starts Crux Access, the credential store, the security events, the status and
  configuration services, the TLS certificate (made on the device at its first start and registered with Zephyr's
  TLS credentials) and the web server on Zephyr's HTTP server with Mbed TLS, in the order of
  `app/src/management_port.h`. The route sources of the session and management services are Crux's own, named by
  `app/management/management.cmake` and handed their private include directories by Crux's route function, so no
  build file here adds an include path. The packaged page, the reviewed route list, a RAM disk, the entropy rules of
  the board image and a `native_sim` scenario of ten cases in `tests/native_sim_mbed` come with it. The image has no
  account, so nobody can log in until a first-account console exists, and nothing persists across a reset. The Mbed
  TLS group `crux-secure-management` is switched on in the runners of the S6 job and the S6 Budget row only, after
  `scripts/check_mbed_only.py` has checked the project list, and stays off in `west.yml`. S6 is built and never run on
  a board, and the first CI run is the first build of this chain from outside `crux-pilot`: see
  `docs/findings/s6-https-management.md` for what is open. No firmware image of S0 to S5 changes.
- A `native_sim` scenario runs S1, one for S2 uses the test-only `picolibc`, and one for S3 runs the
  file through the simulator provider on a RAM disk. Host tests with and
  without sanitizers cover the portable workload core.

### Boundary and budgets

- A boundary check (`scripts/check_boundary.py`) limits what `app/src` and `workload` include, and a
  composition zone, `app/compose`, is the one place that may include `<crux/file_zephyr.h>`. See
  `docs/composition-zone.md`.
- The workload runs its two threads and its queue through Zephyr calls in a second zone, `app/os`,
  behind a product-owned port header of `app/src`. The boundary check fails `app/src` and `app/os`
  on `<crux/thread.h>`, `<crux/sync.h>`, `<crux/queue.h>` and `<crux/serial.h>`. Not run on a board:
  the S2 comparison with the earlier runs is still to do.
- The adapter zone `app/os` may now include `<zephyr/net/sntp.h>`, the Zephyr SNTP library header,
  besides `<zephyr/kernel.h>`. Sockets stay off for the zone, and every other Zephyr header, the Zephyr
  and Crux Sockets profile socket headers included, still fails there. This allows the include only:
  the first SNTP code is step S5 below. See `docs/composition-zone.md`.
- The workload's build switch is the product's own Kconfig option `CRUX_CONTROLLER_S1`, not the Crux
  Thread provider. `app/Kconfig`, `app/CMakeLists.txt` and `app/src/composition.c` key on it, and no
  conf of the product or of the S1 scenario selects Crux Thread or Crux Queue any more. The worker
  stack size of each step is unchanged: 4096 bytes in S1 and S3, 8192 in S2. The S2 conf no longer sets
  `CONFIG_CRUX_THREAD_STACK_BYTES`, which no step defines now. Tooling tests pin the new wiring; the
  Zephyr builds and the budget jobs run in CI.
- Static resource use is collected and checked against declared limits (`budgets/`), with a
  step summary per step.
- Groundwork for a later step S6 (HTTPS management), which is not a step yet: the limits file declares a
  row `S6` equal to the `S5` row (the placeholder of 25 percent free in every region), before anything is
  measured and before any workflow uses it. `app/src/management_policy.[ch]` hold a strict IPv4 text check,
  the administrator and read-only role data, the session limits and a version text check, and
  `app/src/management_port.h` declares the product-owned port. They are built and tested on the host only:
  no firmware image changes, because no build file, option or configuration names them. The finding
  `docs/findings/s6-https-management-gaps.md` records the gaps found by reading, with what is not verified.
- The boundary check fails, with status 2 and a message, when none of its four trees exists under `--repo`
  (for example when it runs from the workspace directory). One absent tree is still skipped.
- Crux Queue left the boundary check and the CI option checks. The pinned Crux no longer publishes
  `<crux/queue.h>` or `CONFIG_CRUX_QUEUE`, so `FROZEN_CRUX_HEADERS` now holds `<crux/thread.h>`,
  `<crux/sync.h>` and `<crux/serial.h>`, and the S1, S4, S5, S6 and Dev container jobs no longer look for the
  symbol. An include of `<crux/queue.h>` still fails: with `--crux-root`, which CI passes, the boundary check
  refuses a name that Crux does not publish, and the product include check refuses it in every source. The
  pin entry under "Build and manifest" that says both checks "still refuse both" was true when written. No
  firmware image changes.

### Release tooling

- A release bundle of hashes and identities, its schema and a bundle check, a release dry run that
  publishes nothing and a rebuild comparison at another path (`release/`).
- The release dry run parses the SPDX files that `west spdx` writes (`release/parse_spdx.py`) and
  prints the package count of each document.

### Documents

- The documents follow the documentation guidelines of Crux: one type per page, current state only, one home
  for each fact, and the Crux page names and terms. `docs/first-hour.md` is renamed `docs/tutorial.md` and takes
  over the run steps of the Getting started quick start, so there is one path from a clone to the first build and
  run. `docs/try-on-native-sim.md` becomes the Getting started page: its "Quick start" is "Set up the Dev
  Container" with the host steps only, its term paragraph points at the glossary, and its dated "What has been
  checked" record moves to `docs/history/setup-checks.md`; "Why the evidence comes from CI" moves to
  `docs/architecture.md` and "What `native_sim` is" into the glossary entry for `native_sim`. Getting started then
  holds only the environment and the first command: the Dev Container details move to `docs/dev-container.md`
  (reference) and the route without the Dev Container to `docs/native-setup.md` (how-to), with a short section
  and the same check left on Getting started. The tutorial runs from a working Dev Container in three parts: host
  tests, the `native_sim` scenarios, and the board image with a board table. The README has the shape of the Crux README (what it
  is and for whom, what it provides, quick start, where to read next, status and limits, contributing, licence),
  `docs/README.md` is the documentation map with the type of each page, and the glossary defines workspace, Dev
  Container and host tests. "Dev Container" is written as Crux writes it. `docs/try-on-native-sim.md` is renamed
  `docs/getting-started.md`, with the paths in `CONTRIBUTING.md`, `scripts/` and `.devcontainer/`. No
  firmware image changes.
- The README is an entry point: the quick start points at `docs/first-hour.md`, a step table shows which code
  and which finding teach each Crux capability, the Crux guides at the pin are linked as the canonical place
  for building a product, and a task table replaces the timed reading path. `docs/README.md`,
  `docs/try-on-native-sim.md`, `docs/roadmap.md` and `docs/architecture.md` lose duplicated text; the failure list
  of the dev container lives only in `docs/troubleshooting.md`. Stale statements are corrected in
  `docs/adding-a-step.md` (the S4 job checks Crux Thread and Sync, not Queue), `docs/dependencies.md` and
  `docs/roadmap.md`. `docs/history/README.md` lists what was removed. No firmware image changes.
- `docs/first-hour.md`, linked at the top of the README and of `docs/README.md`: the short path for a new team
  member on Linux or WSL2, from a clone to one build, one `native_sim` run and the local checks in the dev
  container, with the times of the CI job. `docs/board-bring-up.md` is now a board route: the probe on WSL2 with
  usbipd, an optional board container (`.devcontainer/board/`, `scripts/board-shell.sh`) with the J-Link package
  from a file that you download yourself, a read-only compare of the flash, `west flash` and `west debug` with
  the J-Link runner, and a run record template. The route and the board container are untested on hardware,
  and the default dev container does not change.
- The section "A public repository" of `CONTRIBUTING.md` is now "Content rules", with the same rules, and
  `docs/reviewing.md` points at it. The maintained documents and the comments of `west.yml` state their facts
  without the pull request or issue number that brought them, `docs/first-change.md` clones from
  `<repository-url>`, and prose that is not about the hosting service says "the CI". The stale comment in
  `ci.yml` that said the pinned `crux-pilot` predates the product include check now says that the pin contains
  the same script with the same hash.
- Navigation and role pages: an index of every document with a path for each task and a reading time
  (`docs/README.md`), a tutorial from branch to pull request with a small host-test change
  (`docs/first-change.md`), a reviewer checklist (`docs/reviewing.md`) and a note for teams that keep a copy of the
  repository (`docs/team-copy.md`). The README says about 80 minutes for its five-page reading path and defines
  EVKB, SNTP, MDIO, SBOM, ztest, Twister and the review results where it first uses them. The glossary defines
  product, platform, composition, the product include check, `PASS`, `REVISE` and `ESCALATE`, and the files that
  need a reviewed change. `docs/adding-a-step.md` has one numbering scheme, moves the S5 and S6 retellings to an
  appendix, lists the licence line, format, clang-tidy and patch-style checks, and has a section on drivers and
  HAL. The index states the known limits of the checks and tests, which are not scheduled. No firmware image changes.
- Corrections of earlier entries, which were true when written and are not rewritten: the entries under
  "Build and manifest" about the `crux-pilot` pin and the Mbed TLS group ("no job enables the group", "stays off
  in every job", "no controller code uses them yet") describe the repository before step S6. Since S6, the `S6 build` job
  and the S6 `Budget` row switch the group on in their own runner, and `app/compose/management_start.c` uses
  the management headers. The "groundwork for a later step S6" entry under "Boundary and budgets" also predates S6: `management_policy` and
  `management_port.h` are now built into the S6 image. The documents `docs/dependencies.md`,
  `docs/try-on-native-sim.md`, `docs/roadmap.md`, `docs/glossary.md` and `docs/architecture.md` were corrected
  to match, and the try-on page now gives commands for Ubuntu 24.04 and WSL2.
- Clarification of the same kind: "the S2 comparison with the earlier runs is still to do", in the entry about the
  second zone `app/os` under "Boundary and budgets", means that the S2 image built with that zone has not run on
  a board. The two S2 board runs used an image built before the zone existed, so they are not a comparison with it.
- The documents now open with an audience statement and a reading order (`README.md`), define the roles
  "owner", "reviewer" and "operator" and the terms of the board runs (`docs/glossary.md`), index the findings
  (`docs/findings/README.md`), record the static size of each step (`docs/roadmap.md`), explain why Zephyr build
  evidence comes from CI (`docs/try-on-native-sim.md`) and document the second check of the `Boundary check` job
  (`docs/composition-zone.md`). The S4 and S5 findings record their CI results, the S5 and S6 notes no longer
  describe how the work was organised, and `docs/adding-a-step.md` no longer relies on Git history.
- The finding on the S2 board runs (`docs/findings/s2-first-board-run.md`) records a second run on
  12 November 2026 with the same S2 image on the same bench: the link, ping, S2 log and restore
  checks reproduced those of the first run. That is two runs on one bench; it shows no S2 timing,
  stack or resource use, and it is not qualification.
- The File binding finding and the S3 findings note (`docs/findings/`), the composition zone note, the README with the
  repository's role, and this changelog together with `SECURITY.md`, `RELEASE.md` and
  `docs/dependencies.md`.
