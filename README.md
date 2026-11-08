# crux-controller

Status: Stage 1, in progress. The repository builds in CI for the NXP RT1060-EVKB
Rev B with the Zephyr baseline gate required: a synthetic workload on Crux threads, a
queue and logging (step S1), a TCP exchange over the Crux Sockets profile (step S2, built
and never run), and static resource use checked against declared limits. Nothing has run
on a board, and there is no release.

crux-controller is the official reference consumer firmware for ongoing integration,
evaluation and regression testing of Crux Platform capabilities through public and approved
composition interfaces. It may provide supporting evidence for relevant platform milestones, but it
is not a mandatory exit criterion for any of them.

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
- Security reports: see `SECURITY.md`.
- Releases: see `RELEASE.md`. Dependencies and their licences: see `docs/dependencies.md`.
  Changes: see `CHANGELOG.md`.
