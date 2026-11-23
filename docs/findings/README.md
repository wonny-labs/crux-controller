# Findings

The notes name each build configuration by the step id it had when the note was written. The current names:

| Step id in a note | Build configuration |
|---|---|
| S0 | `base` |
| S1 | `workload` |
| S2 | `net` |
| S3 | `file` |
| S4 | `system` |
| S5 | `sntp` |
| S6 | `management` |

A file, job or option that a note names with a step id has the new name in the same place: `app/conf/s4.conf` is
`app/conf/system.conf`, the CI job `S4 build` is `system build`, `CRUX_CONTROLLER_S4` is
`CRUX_CONTROLLER_SYSTEM`, and `tests/tooling/test_s4.py` is `tests/tooling/test_system.py`.

A finding records what building a step or asking a question taught about using Crux through its public
interfaces. Findings are kept as written. A later result is added as a dated update or a banner, and the
reading of the earlier revision is not rewritten, so each note names the revision of `crux-pilot` (the Crux
repository) that it was read at. The labels that a note uses (Measured, Inferred, Verified, Recorded, Open and
others) are listed in the [glossary](../glossary.md), under "Finding". Hashes and numbers in these notes name the
history of the public repositories on GitHub; see the [glossary](../glossary.md#build-pin-and-evidence).

A path in a finding that does not exist in this repository (for example under `components/`, `samples/`,
`tests/native/` or `cmake/`, or a `docs/` page that this repository does not have) is a path in
`crux-pilot` at the revision that the note names. A header such as `<zephyr/net/sntp.h>` belongs to Zephyr.

Each capability whose building taught something has a note: `net` the board runs, `file`, `system`, `sntp` and
`management` their composition notes below.

| Note | What it records | Crux revision read |
|---|---|---|
| [file-binding-has-no-public-header.md](file-binding-has-no-public-header.md) | A product could not bind the File provider with public means. Closed upstream since, by a published composition interface. | `56b5737`; the update names `37c92b18` |
| [management-has-no-public-composition.md](management-has-no-public-composition.md) | Which management features (HTTPS, command lines, SFTP, Access and its services) had no public product composition, and the licence limits that stood in the way. Partly overtaken by step S6. | `a72032b2`, with an update for the later pin |
| [s2-first-board-run.md](s2-first-board-run.md) | The two runs of the S2 image on one board and bench (9 and 12 November 2026): link up, ping answered, one TCP exchange echoed, and what the runs do not show. | pin `37c92b18` |
| [s3-file-composition.md](s3-file-composition.md) | Step S3: composing Crux File through the composition interface, with the friction found. | `37c92b18` |
| [s4-system-composition.md](s4-system-composition.md) | Step S4: reset cause and a single-owner watchdog through Crux System, and why the simulator cannot show a feed cycle. | `37c92b18` |
| [s5-time-synchronisation.md](s5-time-synchronisation.md) | Step S5: setting the Crux Time realtime clock from SNTP, the product policy, and its limits. | `37c92b18` |
| [s6-https-management-gaps.md](s6-https-management-gaps.md) | Groundwork for S6: the three gaps found by reading before HTTPS management was wired. Superseded by the next note and kept as recorded. | `8e3737d2` and `dfd3ad7d` |
| [s6-https-management.md](s6-https-management.md) | Step S6: what the product had to write for HTTPS management, the CI results at a named revision, and what is open. | `8e3737d2` |

The current pin is `c5439c51741bceb8f3327c11882dc3b58bbe2640` (see `west.yml`). A note read at an earlier
revision may no longer describe Crux at the pin.
