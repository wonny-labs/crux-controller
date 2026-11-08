# Finding: composing File through the approved interface (step S3)

Status: in progress. This note is written while step S3 is built. Every statement is labelled
**Measured** (a command or a CI job produced it in this repository, and the result is quoted),
**Inferred** (read from `crux-pilot` source or documents at the pinned commit, not run here) or
**Open**. Results of CI runs are filled in after the first run.

The question: can a product compose Crux File using the composition interface that `crux-pilot`
PR 346 published (`<crux/file_zephyr.h>`, target `crux::file_zephyr`), with application code on
`<crux/file.h>` only, inside the boundary of `docs/composition-zone.md`?

## What a product had to write

| Item | Where | Lines |
|---|---|---|
| The port the application declares and the zone implements | `app/src/storage_port.h` | to be counted |
| The zone: mount, optional format, bind | `app/compose/storage_mount.c`, `app/compose/CMakeLists.txt` | to be counted |
| The application's use of File: a configuration record saved and loaded | `app/src/config_store.c`, `app/src/config_store.h` | to be counted |
| A record codec, portable and host-tested | `workload/src/config_record.c` | to be counted |
| Kconfig fragment, devicetree overlay (board and simulator) | `app/conf/s3.conf`, `app/boards/s3.overlay`, `tests/native_sim/s3/` | to be counted |

## Friction

### 1. The mount object needs a library header unless the devicetree declares the mount

**Inferred.** Every consumer of `crux::file_zephyr` in `crux-pilot` at the pinned commit
(`samples/storage_sd`, `tests/native/file_fatfs` and the others) includes `<ff.h>` to declare a
`FATFS` object and fills a `struct fs_mount_t` by hand. `ff.h` is the FatFs library header, not a
Zephyr header and not a Crux header, and the boundary of this repository does not allow it in the
composition zone. The documentation of the composition interface says a product needs "a
composition zone ... allowed to include `<crux/file_zephyr.h>` and Zephyr headers"; it does not say
that the reference compositions also need a file system library header.

**Way out used here, Open until CI runs.** A `zephyr,fstab,fatfs` devicetree node. Zephyr's own FatFs
support declares the file system object and the mount description for it, so the zone includes
`zephyr/fs/fs.h` and `zephyr/devicetree.h` only.

### 2. The composition interface header does not say how a failed bind recovers

**Inferred.** `<crux/file_zephyr.h>` says a binding "lasts for the life of the program" and that there
is no rebind. It does not say whether a bind that failed leaves the root free for a later bind.
`docs/microsd-composition.md` in `crux-pilot` says it does ("leaves the File component unbound, so a
later `sd_storage_start()` can succeed"). The `bind_failure` scenario tests it (Open until CI runs).

### 3. A mount is not readiness

**Inferred**, tested by the `mounted_not_bound` scenario (Open until CI runs). The header says File
calls return `CRUX_FILE_ERR_NOT_READY` while the root is absent, and `file_zephyr.h` says "bound root
is absent"; a reader can take "absent" to mean "not mounted". The contract is that nothing works
before the bind, whatever is mounted.

## Results of the evaluation

To be filled in after CI: the scenarios, the RT1060-EVKB cross-build, the symbols, the budget
numbers.

## Not done and not claimed

- Nothing ran on a board. No card was used. The build does not show that the FatFs provider mounts
  a real card.
- Reliance Edge, eMMC and the secure management group are off and untouched.
