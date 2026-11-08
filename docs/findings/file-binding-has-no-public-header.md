# Finding: the File binding has no public header for products

Status: recorded for Stage 1. Tracked in issue #6. Filing it in `crux-pilot` needs the owner's approval and has not happened.

**Update, 8 November 2026: the gap is closed upstream.** `crux-pilot` PR 346 (merge commit `37c92b18`) publishes the root binding as a composition interface: the header `<crux/file_zephyr.h>` and the CMake target `crux::file_zephyr` (design note `docs/file-composition-interface.md` in that repository). It is for composition code only, not for application code. This repository answers with a narrow composition zone in the boundary check (`docs/composition-zone.md`) and builds step S3 on it. The text below is the finding as recorded at the time and is kept as written: it describes the pin `db5adca`, which does not have the header. The pin moves in a separate pull request.

## Finding

A product that uses public targets only cannot compose the File capability on RT1060-EVKB Rev B.

## Evidence

All read in `wonny-labs/crux-pilot` at `56b5737`. The pinned commit of this repository, `db5adca`, is later and was not re-read for this finding.

- The documented microSD composition mounts the volume, checks its layout and then binds the File provider with `crux_file_zephyr_bind` (`docs/microsd-composition.md`, Composition, step 4). The eMMC composition makes the same call (`docs/emmc-reliance-composition.md`, step 4).
- That function is declared in `components/file/ports/zephyr/file_native.h`. No `<crux/...>` header provides it, and the File service proposal records root binding as composition only (`docs/plans/file-service-contract-proposal.md`, line 43).
- `crux-pilot`'s own sample reaches the header through a private include directory (`samples/storage_sd/CMakeLists.txt`, `target_include_directories`).

## Consequence for this repository

Step S3 (file storage) is not built in Stage 1 and has no budget step. The boundary check (`scripts/check_boundary.py`) keeps no exception. A rule that allows the port header would hide this finding. The check fails a quoted include that does not resolve inside the checked tree, and `test_crux_port_header_fails` covers `file_native.h`.

## What would reopen it

A public binding in `crux-pilot`. The owner decides whether and how that is filed there. This repository will not file it without approval.

## Not run

No build of S3 was attempted. Nothing here claims that the provider cannot work, only that a product cannot reach its binding through public targets.
