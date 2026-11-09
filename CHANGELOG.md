# Changelog

This file follows the idea of [Keep a Changelog](https://keepachangelog.com/). There is no release
yet and no tag, so everything below is unreleased: it is what the `main` branch contains. Step S2 ran
once on a board (see `docs/findings/s2-first-board-run.md`); nothing else has run on a board.

## Unreleased

### Build and manifest

- The west manifest imports `crux-pilot` at a pinned commit (`37c92b18`, which publishes the File
  composition interface `<crux/file_zephyr.h>`) and adds `picolibc` as a test-only project. A CI job
  checks the pins with `west crux-pins` and has a negative control that must fail.
- A daily build against `crux-pilot` main (`.github/workflows/scheduled-main.yml`) reports pin
  mismatches and build failures in its job summary. It is information only: the pinned build stays
  the gate for pull requests, and the workflow publishes nothing.
- CI builds step S0 (the skeleton), S1 (Crux threads, a queue and logging on a synthetic workload),
  S2 (a TCP exchange over the Crux Sockets profile) and S3 (a configuration record in a file through
  Crux File, mounted by the composition zone, on a FatFs provider for microSD) for the NXP RT1060-EVKB Rev B with the Zephyr
  baseline gate required. S3 is built and never run on a board; S2 ran once on a board.
- A `native_sim` scenario runs S1, one for S2 uses the test-only `picolibc`, and one for S3 runs the
  file through the simulator provider on a RAM disk. Host tests with and
  without sanitizers cover the portable workload core.

### Boundary and budgets

- A boundary check (`scripts/check_boundary.py`) limits what `app/src` and `workload` include, and a
  composition zone, `app/compose`, is the one place that may include `<crux/file_zephyr.h>`. See
  `docs/composition-zone.md`.
- Static resource use is collected and checked against declared limits (`budgets/`), with a
  step summary per step.

### Release tooling

- A release bundle of hashes and identities, its schema and a bundle check, a release dry run that
  publishes nothing and a rebuild comparison at another path (`release/`).
- The release dry run parses the SPDX files that `west spdx` writes (`release/parse_spdx.py`) and
  prints the package count of each document.

### Documents

- The File binding finding and the S3 findings note (`docs/findings/`), the composition zone note, the README with the
  repository's role, and this changelog together with `SECURITY.md`, `RELEASE.md` and
  `docs/dependencies.md`.
