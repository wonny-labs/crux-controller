# Board runs, approvals and tracking, as they were

This page keeps the board-run history, the approval narrative and the tracking bookkeeping that the roadmap and
the glossary carried before they were reduced to short present-tense statements. It is history: it is kept as
written and is not updated. The current facts are in [the roadmap](../roadmap.md#what-has-run-on-a-board), and the
record of the board runs is [docs/findings/s2-first-board-run.md](../findings/s2-first-board-run.md).

Each section names the page and the section that the text came from. The text is unchanged; only the targets of
relative links were rewritten so that they resolve from this folder. The tracking paragraph and the board-run
summary of the README are in [readme-before-entry-point.md](readme-before-entry-point.md).

## From `docs/roadmap.md`: Opening paragraph, one sentence (the words "the changelog" removed)

Status can go stale, so check the README, the changelog and the open pull requests, and read the

## From `docs/roadmap.md`: Short version, the S5 bullet

- S5 (the Crux Time realtime clock set from an SNTP server) arrived with
  [pull request 50](https://github.com/wonny-labs/crux-controller/pull/50) of the public repository. It was never run
  on a board.

## From `docs/roadmap.md`: Step S5 in more detail, the first sentence

S5 was added by [pull request 50](https://github.com/wonny-labs/crux-controller/pull/50) of the public
repository, which is merged; the pull request that put `zephyr/net/sntp.h` on the adapter zone's allow-list,
[pull request 49](https://github.com/wonny-labs/crux-controller/pull/49), is merged too. What ...

## From `docs/roadmap.md`: Step S5 in more detail, the last paragraph

The findings note labels its own results. When it was written, its seven `native_sim` cases, its Zephyr
build and its budget numbers were still open, to be recorded by CI; the note now records what CI showed at
the commit that merged S5. **S5 was never run on a board**, and the only board run of this repository is the S2 one
below.

## From `docs/roadmap.md`: What has run on a board (whole section body)

This is the whole of it, from [docs/findings/s2-first-board-run.md](../findings/s2-first-board-run.md). Its
status paragraph says:

> the S2 image ran twice on one RT1060-EVKB Rev B on the same bench, on 9 November 2026 (run 1,
> described first) and on 12 November 2026 (run 2, a reproducibility run, described under "Run 2" below).

Both runs used the same S2 image and the same gated procedure, and the board was restored to the accepted
normal image afterwards. Both runs observed the Ethernet link come up without the MDIO correction that the
Crux sample applies, ping answered 5 of 5 times, and one TCP exchange with a host peer echoed. The note says
the TCP exchange was informational and not a pass criterion. Its verdict on run 2 is: "Two boots on one
bench are evidence collection, not qualification." Its "Not shown" list, kept as written:

- "Run-time values of S2: stack use, CPU use and timing beyond what the log lines literally print."
- "Repeatability beyond two boots on one bench: another board, another cable or another bench, and any
  statistical statement about how often the link comes up."
- "Behaviour after the 180 s window."
- "Whether the link comes up the same way after a cold power cycle; the run restarted the image by
  programming and reset."
- "An exchange that is repeated, or an exchange when the peer is slow or restarts."
- "Anything about the S3 image, microSD, or the release bundle: they did not run."

Beyond that note, the README and the S4 note record that S3 and S4 are built and never run on a board,
and no S0, S1-only, S4 or S5 image has run. The S2 image contains the S1 workload, so the workload lines of S1
appeared in that capture; the "not run" in the S1 row of the README means S1 as an image of its own. No
release exists, so no released image has run anywhere. A green `native_sim` run is not a board run and a
CI build is not a board run.

## From `docs/roadmap.md`: What is not yet possible, and why, the last paragraph

A separate question is how the platform request itself is filed. The finding records that nothing has been
filed in `crux-pilot` and that filing needs the owner's approval. Stage 2 steps and their findings are
tracked in this repository's own issues on GitHub, with the epic
[issue 44](https://github.com/wonny-labs/crux-controller/issues/44) as the top. The open or closed state of those
issues can lag behind the code.

## From `docs/glossary.md`: Stage (whole entry, rewritten in short form)

**Stage.** A phase of the repository's own work, larger than a step. No document defines it; this entry
records how they use it. `docs/findings/management-has-no-public-composition.md` says it was
"recorded after Stage 1 step S3", so S3 is a Stage 1 step. The tracking paragraph of `README.md` says
that "Stage 2 steps and their findings" are tracked in the repository's own issues under an epic, and
lists S4 among the epic's children, so S4 is a Stage 2 step. Nothing places S5 in a stage: its README
text names no stage, and the pull request that added it is
[pull request 50](https://github.com/wonny-labs/crux-controller/pull/50) of the public repository. The header
comment of `west.yml` ("No optional group is enabled in Stage 1") uses the word in its earliest sense. One use differs from the rest:
`docs/findings/file-binding-has-no-public-header.md` says S3 "is not built in Stage 1",
a note from before S3 was built. Treat the stage number as a label of when something was planned, not
as a property of the code. One other use is unrelated: `docs/findings/s2-first-board-run.md` says "an
earlier platform stage", which means a phase of Crux, not of this repository.

## From `docs/glossary.md`: Gated procedure, the second sentence

Each run needed the owner's written approval, an explicit owner yes before the board was overwritten and
a guard check before each probe step (`docs/findings/s2-first-board-run.md`, "Method").
