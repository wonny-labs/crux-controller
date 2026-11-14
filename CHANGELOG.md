# Changelog

This file follows the idea of [Keep a Changelog](https://keepachangelog.com/). There is no release
yet and no tag, so everything below is unreleased: it is what the `main` branch contains. Step S2 ran
twice on a board (see `docs/findings/s2-first-board-run.md`); nothing else has run on a board.

## Unreleased

### Build and manifest

- The west manifest imports `crux-pilot` at a pinned commit (`37c92b18`, which publishes the File
  composition interface `<crux/file_zephyr.h>`) and adds `picolibc` as a test-only project. A CI job
  checks the pins with `west crux-pins` and has a negative control that must fail.
- A daily build against `crux-pilot` main (`.github/workflows/scheduled-main.yml`) reports pin
  mismatches and build failures in its job summary. It is information only: the pinned build stays
  the gate for pull requests, and the workflow publishes nothing.
- CI builds step S0 (the skeleton), S1 (Zephyr threads and a message queue in the `app/os` adapter zone, with Crux Time and Logging, on a
  synthetic workload),
  S2 (a TCP exchange over the Crux Sockets profile) and S3 (a configuration record in a file through
  Crux File, mounted by the composition zone, on a FatFs provider for microSD) for the NXP RT1060-EVKB Rev B with the Zephyr
  baseline gate required. S3 is built and never run on a board; S2 ran twice on a board.
- CI also builds step S4 (the reset cause and a single-owner watchdog through Crux System, with the
  workload's producer thread feeding it once per cycle) on the S1 base, and the Budget job has an S4 row
  against limits declared first. The product composes System with public means only: `<crux/system.h>`,
  the target `crux::system`, a Kconfig fragment and a devicetree alias, with no new zone and no change to
  the boundary lists. Its conservative defaults are in `docs/findings/s4-system-composition.md`. S4 is built
  and never run on a board.
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
- The workload's build switch is the product's own Kconfig option `CRUX_CONTROLLER_S1`, not the Crux
  Thread provider. `app/Kconfig`, `app/CMakeLists.txt` and `app/src/composition.c` key on it, and no
  conf of the product or of the S1 scenario selects Crux Thread or Crux Queue any more. The worker
  stack size of each step is unchanged: 4096 bytes in S1 and S3, 8192 in S2. The S2 conf no longer sets
  `CONFIG_CRUX_THREAD_STACK_BYTES`, which no step defines now. Tooling tests pin the new wiring; the
  Zephyr builds and the budget jobs run in CI.
- Static resource use is collected and checked against declared limits (`budgets/`), with a
  step summary per step.

### Release tooling

- A release bundle of hashes and identities, its schema and a bundle check, a release dry run that
  publishes nothing and a rebuild comparison at another path (`release/`).
- The release dry run parses the SPDX files that `west spdx` writes (`release/parse_spdx.py`) and
  prints the package count of each document.

### Documents

- The finding on the S2 board runs (`docs/findings/s2-first-board-run.md`) records a second run on
  12 November 2026 with the same S2 image on the same bench: the link, ping, S2 log and restore
  checks reproduced those of the first run. That is two runs on one bench; it shows no S2 timing,
  stack or resource use, and it is not qualification.
- The File binding finding and the S3 findings note (`docs/findings/`), the composition zone note, the README with the
  repository's role, and this changelog together with `SECURITY.md`, `RELEASE.md` and
  `docs/dependencies.md`.
