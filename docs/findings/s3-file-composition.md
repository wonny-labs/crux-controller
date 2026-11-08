# Finding: composing File through the approved interface (step S3)

Status: step S3 is built and its CI checks pass. Nothing ran on a board.

Every statement is labelled **Measured** (a CI job of this repository produced it; the job and
run are named), **Inferred** (read from `crux-pilot` source or documents at the pinned commit
`37c92b18`, or derived from a Measured result, and not run on its own here) or **Open**.

## Question and answer

Can a product compose Crux File through the interface that `crux-pilot` PR 346 published
(`<crux/file_zephyr.h>`, target `crux::file_zephyr`), with its application code on `<crux/file.h>`
only, inside the boundary of `docs/composition-zone.md`?

**Yes, for the simulator provider and for a build of the FatFs provider on the RT1060-EVKB.**
Application code includes `<crux/file.h>` only; the composition zone includes `<crux/file_zephyr.h>`,
`<crux/file.h>`, `zephyr/fs/fs.h`, `zephyr/devicetree.h` and ISO C headers. The boundary check
passes on this tree (CI job "Boundary check", run 42516424890). No exception, private include path
or copy of Crux code was needed. The product did have to learn four things the Crux text does not
say (friction 1 to 4) and to work around one misleading build message (friction 5).

## Results

| What | Result | Label | Source |
|---|---|---|---|
| `native_sim` Twister scenarios: S1, S2 and five S3 scenarios | 7 of 7 configurations pass, 20 of 20 test cases pass (S1 1, S2 4, S3 15 by the source count) | Measured | CI job "S1 (native_sim and RT1060-EVKB)", run 42516424890; the split of the 20 cases is Inferred from counting `ZTEST` in the sources |
| S3 scenarios | `not_ready` (3 cases), `mounted_not_bound` (3), `mount_failure` (2), `roundtrip` (6), `bind_failure` (1) | Measured (pass), case counts Inferred | same |
| RT1060-EVKB build, FatFs provider, microSD volume from a devicetree fstab entry, baseline gate required | builds; resolved configuration and devicetree checked (S3 selected, provider selected, no auto-format, no format service, no Reliance Edge, entry present) | Measured | CI job "S3 build (RT1060-EVKB, File)", run 42516424890 |
| Image symbols of that build | `storage_port_mount`, `storage_port_bind`, `crux_file_zephyr_bind`, `config_store_save`, `config_store_load`, `fs_mount` are linked; `f_mkfs` and `fs_mkfs` are not | Measured | same job, step "Check what the image links" |
| Static size of S3 (built on S1) | FLASH 70352 B, RAM 39520 B; S1 is FLASH 43392 B, RAM 35456 B, so the S3 additions (File, the file system and the SD drivers, the zone and the store) are 26960 B of flash and 4064 B of RAM in this image; ITCM, DTCM, OCRAM, OCRAM2 and IDT_LIST 0 B; limit check passes (placeholder limits) | Measured | CI job "Budget S3", run 42516424900, and the S3 build job |
| A mount of a real card, a read or write on a board, run-time stack use, timing | not run | Open | no hardware |

The static sizes are linker views of one build. They say nothing about stack use during a File
call; the `crux-pilot` microSD notes put the `fs_stat` chain at about 780 B of stack before the
SD driver (Inferred from that document), and the S3 image keeps the 4096 B main stack of S1 without
a measurement.

## What a product had to write

| Item | File | Lines |
|---|---|---|
| The port the application declares and the zone implements | `app/src/storage_port.h` | 51 |
| The zone: mount, optional format, layout directory, bind | `app/compose/storage_mount.c`, `app/compose/CMakeLists.txt` | 100 + 11 |
| The application's use of File: record saved and loaded | `app/src/config_store.c`, `app/src/config_store.h` | 93 + 29 |
| Record codec, portable and host-tested | `workload/src/config_record.c` (the codec is the added part) | about 55 added |
| Kconfig fragment and devicetree overlay for the board | `app/conf/s3.conf`, `app/boards/s3.overlay`, plus 51 added lines in `app/CMakeLists.txt`, `app/Kconfig` and `app/src/composition.c` | 22 + 20 + 51 |
| The scenario: sources, overlay, configuration | `tests/native_sim/s3/` | 241 + 23 + 19 + 16 + 17 |

All counts are `wc -l` and `git diff` of this branch (Measured by the author on this branch when the note was last edited; later edits can move them by a few lines). The composition proper, the zone and its port, is about 160 lines (162 at the time of writing).

## Friction

### 1. The reference compositions need a file system library header

**Inferred** from every consumer of `crux::file_zephyr` in `crux-pilot`
(`samples/storage_sd/sd_storage.c`, `tests/native/file_fatfs/main.c` and others): each includes
`<ff.h>` to declare a `FATFS` object and fills `struct fs_mount_t` by hand. `ff.h` is neither a Zephyr
nor a Crux header. The composition interface document says a product needs a zone "allowed to
include `<crux/file_zephyr.h>` and Zephyr headers"; it does not say that its own references also
include `ff.h` and `zephyr/storage/disk_access.h`. A product that copies a reference hits its
boundary on the first include.

**Way out used here.** A `zephyr,fstab,fatfs` devicetree entry (`app/boards/s3.overlay`). Zephyr's FatFs
support then declares the file system object and the mount description. **Measured:** the zone
compiles and links with `zephyr/fs/fs.h` and `zephyr/devicetree.h` only, for the RT1060-EVKB build
(S3 build job), and the same entry mounts a RAM disk on `native_sim` (the `roundtrip` scenario). It
leaves two things open: **Open** whether the same entry mounts a real card (no card was used), and
that an fstab FatFs entry does not accept `no-format` (**Inferred** from `BUILD_ASSERT` in Zephyr's
`subsys/fs/fat_fs.c`), so whether a volume is formatted is decided only by
`CONFIG_FS_FATFS_MOUNT_MKFS`, which the Crux provider requires off.

### 2. `zephyr/fs/fs.h` does not bring in the devicetree macros

**Inferred** from the pinned Zephyr (`fs.h` includes `sys/types.h`, `zephyr/sys/dlist.h`,
`zephyr/fs/fs_interface.h`). Its fstab macros expand `DT_*` macros, so a composition that uses
`FS_FSTAB_ENTRY(DT_NODELABEL(...))` must include `zephyr/devicetree.h` itself. The allow-list of the
composition zone has to name it. The Crux text is silent because its references never use the
devicetree route.

### 3. A failed bind leaves the root free; the header does not say so

`<crux/file_zephyr.h>` says a binding lasts for the life of the program and that there is no
rebind. It does not say what a failed bind does. `docs/microsd-composition.md` in `crux-pilot` says a
later start can succeed. **Measured:** the `bind_failure` scenario removes the directory, sees the
bind fail, sees File still answer `CRUX_FILE_ERR_NOT_READY`, restores the directory, and the next
bind succeeds; a bind after that returns `CRUX_FILE_ERR_INVALID_STATE`.

### 4. A mount is not readiness, and the wording invites the opposite reading

The header says File calls return `CRUX_FILE_ERR_NOT_READY` while "the bound root is absent". A reader
can take "absent" to mean "not mounted". **Measured:** after a successful mount and before the
bind, File calls return `CRUX_FILE_ERR_NOT_READY` (`mounted_not_bound`), and a bind before any mount
fails and leaves File not ready (`not_ready`).

### 5. A build message that reads as "the gate is not wired"

**Measured:** every build in this repository prints, from CMake, "Manually-specified variables were
not used by the project: CRUX_REQUIRE_VERIFIED_ZEPHYR" (for example in the S3 build job log), while
the build passes with the gate required. **Inferred** from `cmake/CruxZephyrBaseline.cmake`: the
variable is read only after a version mismatch, so a matching Zephyr never touches it and CMake
reports it unused. The gate is wired; nothing in the output says the gate passed. A product that
reads the warning cannot tell the two cases apart without reading that file.

### 6. An unmet Kconfig dependency leaves the step off with only a warning

**Inferred** from `crux-pilot` (`docs/microsd-composition.md`: "Kconfig only warns"). The step option
depends on `CRUX_FILE_FATFS_RT1060`, which depends on a chain of board and driver options. If one is
unmet, the option is off, Kconfig prints a warning, and the build still succeeds. **Mitigation here, Measured as
working, not as catching:** the S3 CI job and the S3 budget row check the resolved `.config` for the
step and provider options. No failure of this kind occurred, so the check has not been seen to fire.

### 7. File is bound once per program, so every scenario is an image

**Measured** as a design cost: the five S3 scenarios build five images (`S3_CASE`), because there
is no unbind and tests would otherwise depend on order. This is the documented contract; it makes a
File test suite heavier than one for a service that can be reset.

### 8. Two mistakes of this repository, found by CI

Recorded because they are friction a product meets: the first CI run failed three scenarios to build
with `-Werror` on unused helper functions of the test (**Measured**, run 42509335965, S1 job).
Cause and fix are in the repository history and are not a Crux matter.

## Not done and not claimed

- The board image creates no directory. The card needs `files` already, as in the `crux-pilot`
  microSD composition; on a card without it the bind fails and the default configuration stays.
  The `FORMAT_ON_FAILED_MOUNT` policy exists for RAM disks and tests, and no scenario runs it on a
  volume that already mounts, or the image without the formatting service (**Open**).

- Nothing ran on a board. No card was used. The build does not show that the FatFs provider mounts
  a real card, or that the S3 image starts, or how long a File call takes.
- Reliance Edge, eMMC and the secure management group are off and untouched.
- Whether the design generalises to a second provider (Reliance Edge, Linux) is not tested.
- The limits in `budgets/limits.json` for S3 are placeholders, as for S0 to S2.
