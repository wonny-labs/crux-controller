# crux-controller

Status: planning. Nothing builds yet, and there is no release.

`crux-controller` is a planned, product-shaped consumer of
[Crux](https://github.com/wonny-labs/crux-pilot). It is meant to exercise the
Crux features together in one image on the NXP RT1060-EVKB Rev B, with declared
resource budgets, a release bundle and an SBOM, using only independently
written code.

## What it is not

- It is not Crux, and it adds no Crux public interface. A gap found here is
  reported to `crux-pilot` as an issue.
- It is not evidence for any Crux security claim. That evidence lives in
  `crux-pilot`.
- It is not an exit criterion of any `crux-pilot` milestone.
- It contains no restricted or company-owned source and no product-specific
  control logic. Its workload will be synthetic and written for this
  repository.

## How it is tracked

The platform questions and findings are tracked in a trial issue in the
`crux-pilot` M7 milestone. Implementation is tracked in this repository's own
milestones and issues.

## Licence, support and ownership

- Licence: Apache-2.0. See `LICENSE`.
- Support: no support period is promised. The period is fixed when the product
  makes its release. Until then, only the latest release is supported.
