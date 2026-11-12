# Contributing to Crux Controller

This guide covers source, tests, documentation, build configuration and CI workflows in this
repository. It is short on purpose. For what the repository is, read the [README](README.md) first.

## What this repository is, and is not

Crux Controller is a consumer of [Crux](https://github.com/wonny-labs/crux-pilot) (the `crux-pilot`
repository). It exercises Crux through its public and approved composition interfaces, so that a gap in
those interfaces shows up here and is reported to `crux-pilot` as an issue.

- It is not a product, not Crux, and it adds no Crux public interface.
- It may provide supporting evidence for a Crux milestone. It is never a mandatory exit criterion of one.
- It is not evidence for any Crux security claim. That evidence lives in `crux-pilot`.
- Its workload is synthetic and written for this repository. Steps S0 to S3 are built in CI. Nothing
  has run on a board, and a change must not claim otherwise.

## The boundary

`scripts/check_boundary.py` checks what the source trees may include. It runs in CI as the
`Boundary check` job. Details and reasons are in [docs/composition-zone.md](docs/composition-zone.md).

| Tree | May include | Fails |
|---|---|---|
| `app/src` | ISO C, the headers of the Crux Sockets profile, public `<crux/NAME.h>` headers, its own tree, `workload/include` | any Zephyr header, `<crux/file_zephyr.h>`, a header of `app/compose` |
| `workload/` | ISO C and its own tree | Crux, Sockets profile and Zephyr headers |
| `app/compose/` (the composition zone) | ISO C, public `<crux/NAME.h>` headers, `<crux/file_zephyr.h>`, `zephyr/fs/fs.h`, `zephyr/devicetree.h`, its own tree, header files (`.h`) of `app/src` | the Sockets profile, a Crux private or port header, any other Zephyr header, vendor and third-party headers |

Any other include fails, and so does an include whose operand is a macro, because it cannot be checked.
The check reads includes only, so do not add include paths in CMake: `app/CMakeLists.txt` is checked
for that.

There is no exception, waiver or per-file opt-out. A boundary that a change can step over says nothing
about what a real consumer can use, and it would hide the gap that this repository exists to find.
To widen it (for example one more Zephyr header in the zone), change `scripts/check_boundary.py`,
`tests/tooling/test_boundary.py` and `docs/composition-zone.md` together in one pull request that is
reviewed as such, and say in it why the public interface is not enough.

## Build and test

Tooling tests run locally. They need Python with PyYAML (CI uses Python 3.12):

```bash
python3 -m venv .venv && . .venv/bin/activate && python -m pip install pyyaml
python -m unittest discover -s tests/tooling -v
python scripts/check_boundary.py
```

The Zephyr builds and the Twister runs happen in CI only. This repository describes no local Zephyr
build, so a change to `app/`, `conf`, overlays or `tests/native_sim` takes its evidence from CI, and
the pull request says so. CI is configured in `.github/workflows/`:

| Workflow | Jobs | When |
|---|---|---|
| `ci.yml` | `Tooling tests`, `West pins`, `Host tests` (sanitizer off and on), `S1` (Twister on `native_sim` for the scenarios in `tests/native_sim`, then the RT1060-EVKB build), `S2 build`, `S3 build`, `S0 build`, `Boundary check` (names shortened) | pull requests and pushes to `main` |
| `budget.yml` | `Budget` for S0 to S3: static resource use against `budgets/limits.json` | pull requests and pushes to `main` |
| `rebuild.yml` | builds S2 twice at different paths and compares `zephyr.bin` and `firmware_identity` | by hand, and pull requests that change the workflow or `release/` |
| `release.yml` | dry run of the release flow, publishes nothing | by hand, and pull requests that change the workflow, `release/` or `west.yml` |
| `scheduled-main.yml` | `S2 build against crux-pilot main` | daily, and by hand |

The scheduled build is information only: it shows ahead of time that a Crux pin moved or that Crux
broke the build, and the pinned build stays the gate for pull requests. Every RT1060-EVKB build requires
the verified Zephyr baseline (`-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON`). A green CI result does not replace
review, and a build in CI is not a run on a board.

## The pin and the manifest

`west.yml` imports `crux-pilot` at a pinned commit, a full SHA and never a branch or a tag. `west
crux-pins` must print a `CONTRACT crux-pilot` line and no `MISMATCH`; the `West pins` job checks this
and has a negative control that must fail. Another project is added to `west.yml` only with a comment
that says why it is there and where its revision comes from, and `docs/dependencies.md` is updated. The
optional groups of the Crux manifest stay off, `crux-secure-management` among them: their terms are not
the Apache-2.0 terms of this repository.

A pin moves in its own small pull request, with the reason in the commit message:

1. Change the revision and the comment above it in `west.yml`, and the approved commit in
   `tests/tooling/test_manifest.py`.
2. Update the places that quote the commit as the current pin: `docs/dependencies.md`, `RELEASE.md`
   (its link and the short hash that `tests/tooling/test_docs.py` looks for) and `CHANGELOG.md`.
   Notes under `docs/findings/` stay as they were recorded.
3. Put in the pull request the SHA-256 of the S2 `zephyr.bin` and its `firmware_identity` (the release
   manifest that the `release.yml` dry run prints has both), and the budget tables of the `Budget`
   jobs. If numbers move, say so. A limit in `budgets/limits.json` is not changed in the same pull
   request to make a bump pass.

## Changing behaviour

Write the test first for new behaviour and for a fix, and watch it fail. Never weaken or delete a test,
or relax a check, to make a change pass. Change an existing assertion only when the approved behaviour
changes, and say so in the pull request. Extend a check rather than loosen it.

Keep one logical change in a pull request. Reuse what Zephyr and Crux provide rather than adding a layer
of your own.

## Commits and pull requests

Write in English. Use a short conventional subject, `<type>: <summary>`, with a lowercase imperative
verb and no final full stop, under 72 characters. The types in use are `feat`, `fix`, `docs`, `test`,
`build`, `ci`, `refactor` and `chore`. Explain why in the body when it is not obvious. Work on a branch
and open a pull request; the history of `main` uses merge commits.

A pull request says what changed, why, and how it was checked. List each check with the revision it ran
on and who ran it (CI, a reviewer, or you), and name what was not run. Do not report a check as passing
that did not run, and do not describe a CI build as a run on a board.

## Review

A material change gets an independent review by someone who did not write it. The reviewer reads the
actual files and checks, not the summary, and gives `PASS`, `REVISE` or `ESCALATE`. A blocking finding
is an unmet acceptance criterion, a broken rule of this guide or a factual error. `REVISE` means the
author can fix the blocking findings and get one re-check. `ESCALATE` means the owner has to decide.
Other findings go in the pull request.

A `PASS` means there is no blocking finding. It does not grant merge, scope, hardware or release
authority. Merging a pull request needs the owner's approval, and a `PASS` or green CI does not give it.
AI assistance is not approval and not evidence: claims about tests need the actual results.

## A public repository

Everything here is public. Do not add:

- a name of an employer or customer, a proprietary product or runtime, or a private repository, or a
  link to one;
- a reference to a private planning document (the test `tests/tooling/test_public_text.py` fails on
  the usual forms; it scans this file too);
- the memory sizes of a real product, secrets, keys or credentials, or an absolute path of a personal
  or build machine;
- code or text that you are not allowed to publish under Apache-2.0.

Hashes only: no firmware image, `.elf` or `.map` file goes into the repository, a release bundle or a
CI artefact. No workflow uploads an artefact, and a test fails if one starts to. See
[RELEASE.md](RELEASE.md).

## Releases, tags and forks

Tags, GitHub Releases and forks of this repository need the owner's approval. No workflow tags or
publishes; they run with `contents: read`. No support period is promised, and only the latest release,
if one exists, is supported.

## Security and licence

Report a suspected vulnerability privately as [SECURITY.md](SECURITY.md) describes, and not in a public
issue or pull request. A weakness in Crux itself belongs in `crux-pilot`.

The licence is Apache-2.0 ([LICENSE](LICENSE)). Section 5 of the licence applies to a contribution
that you submit, unless you state otherwise.
