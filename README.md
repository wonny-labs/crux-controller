# Crux Controller

Crux Controller is the official reference consumer firmware for ongoing integration,
evaluation and regression testing of Crux Platform capabilities through public and approved
composition interfaces. It may provide supporting evidence for relevant platform milestones, but it
is not a mandatory exit criterion for any of them.

Status: Stage 1, in progress. The repository builds in CI for the NXP RT1060-EVKB
Rev B with the Zephyr baseline gate required: a synthetic workload on Zephyr threads and a
message queue behind an adapter zone, with Crux Time and Logging (step S1), a TCP exchange over the Crux Sockets profile (step S2), a
configuration record kept in a file through Crux File (step S3, built and never run on a board),
the reset cause and a single-owner watchdog through Crux System (step S4, built and never run on a board),
and static resource use checked against declared limits. Step S2 ran twice on a board, on
9 and 12 November 2026: both times the Ethernet link came up without the MDIO correction that the
Crux sample applies, the board answered ping, and one TCP exchange with a host peer was echoed. The
second run reproduced the first on the same bench; that is two runs on one bench, not repeatability
in a statistical sense and not another board, and the TCP exchange was informational. Nothing else
has run on a board, and there is no release.

| Step | What it adds | `native_sim` scenario | RT1060-EVKB build | On a board |
|---|---|---|---|---|
| S0 | The clock of Crux Time | no | yes | not run |
| S1 | The workload on Zephyr threads and a message queue (adapter zone `app/os`), with Crux Time and Logging | yes | yes | not run |
| S2 | A TCP exchange over the Crux Sockets profile | yes, over loopback | yes | ran twice, reproduced on one bench (link up, ping answered, one exchange echoed) |
| S3 | A configuration record in a file through Crux File, mounted by the composition zone | yes, simulator provider on a RAM disk | yes, FatFs provider, microSD, no card used | not run |
| S4 | The reset cause logged at boot and a watchdog fed once per workload cycle, through Crux System | yes, the boot line and a watchdog that the simulator does not have; no feed cycle | yes, WDOG1 named by a devicetree alias | not run |

Every step is checked against its declared resource limits (`budgets/limits.json`,
placeholders). What S3 needed from the product is recorded in `docs/findings/s3-file-composition.md` and what S4 needed in `docs/findings/s4-system-composition.md`;
what the two board runs of S2 show and do not show is recorded in `docs/findings/s2-first-board-run.md`.
Why none of the Crux management features (HTTPS, serial and SSH command line, SFTP) is built here is
recorded in `docs/findings/management-has-no-public-composition.md`.

It is a product-shaped consumer of [Crux](https://github.com/wonny-labs/crux-pilot). It is meant to
exercise the Crux features together in one image on the NXP RT1060-EVKB Rev B, with declared
resource budgets, a release bundle and an SBOM, using only independently written code.

## What it is not

- It is not Crux, and it adds no Crux public interface. A gap found here is
  reported to `crux-pilot` as an issue.
- It is not evidence for any Crux security claim. That evidence lives in
  `crux-pilot`.
- It is not a mandatory exit criterion of any `crux-pilot` milestone. Where it supports a milestone,
  it is supporting evidence only.
- It contains no restricted or company-owned source and no product-specific
  control logic. Its workload will be synthetic and written for this
  repository.

## Boundary

The include rules of the source trees are checked by `scripts/check_boundary.py` in CI.
`app/src` includes ISO C, the Crux Sockets profile headers, public `<crux/NAME.h>` headers and its
own tree. `workload` includes ISO C and its own tree. The composition zone `app/compose` is the one
place that mounts a file system and binds it to Crux with the composition interface
`<crux/file_zephyr.h>` and a short allow-list of Zephyr headers; `app/src` reaches it only through
a product-owned header that it declares itself. See `docs/composition-zone.md`.

## How it is tracked

The platform questions and findings are tracked in a trial issue in the
`crux-pilot` M7 milestone. Implementation is tracked in this repository's own
milestones and issues.

## Licence, support and ownership

- Licence: Apache-2.0. See `LICENSE`.
- Support: no support period is promised. Only the latest release is supported.
- Contributing: see [CONTRIBUTING.md](CONTRIBUTING.md).
- Security reports: see `SECURITY.md`.
- Releases: see `RELEASE.md`. Dependencies and their licences: see `docs/dependencies.md`.
  Changes: see `CHANGELOG.md`.
