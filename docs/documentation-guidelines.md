# Documentation guidelines

This page is the standard for every Markdown page of this repository. It is for authors and reviewers of a
documentation change. It adapts the guidelines of Crux; the rationale and the sources are on the Crux page,
linked at the end.

## Checklist

Apply the tests in order to each page, section and sentence that a change adds or keeps. Act on the first
test that fails.

| # | Test | If it fails |
| --- | --- | --- |
| 1 | The page type fits the reader's task. | Move the text to a page of the type that fits. |
| 2 | The text serves the heading it sits under. | Move it under the heading it serves. |
| 3 | The fact has no other home. | Keep it in its home and link there. |
| 4 | The reader of this page would fail or be confused without it. | Move it to a page whose reader needs it, or cut it. |
| 5 | It holds no history, status, date, verification trail or measurement, and no steps for a route that nobody ran. | Move it to its home, or cut it. |

Never delete a fact that a reader needs and that has no other home: move it to a page whose type fits.
Write the current rule, not the change: "The handle is invalid after close", not a sentence about what a
release dropped.

## Page types and homes

| Type | Pages |
| --- | --- |
| Entry | [README](../README.md), [documentation map](README.md), [Getting started](getting-started.md) |
| Tutorial | [Tutorial](tutorial.md), [First change](first-change.md) |
| How-to guide | [Set up without the Dev Container](native-setup.md), [Adding a capability](adding-a-capability.md), [Board bring-up](board-bring-up.md) |
| Reference | [Troubleshooting](troubleshooting.md), [Dev Container](dev-container.md), [Dependencies](dependencies.md), [Composition zone](composition-zone.md), [Glossary](glossary.md), [CONTRIBUTING](../CONTRIBUTING.md), [RELEASE](../RELEASE.md), [SECURITY](../SECURITY.md) |
| Explanation | [Architecture](architecture.md), [Reviewing](reviewing.md) |
| Dated | [Findings](findings/README.md), [history](history/README.md), [CHANGELOG](../CHANGELOG.md): one activity with its date, revision and limits, never the only home of a current fact |

Each fact has one home; other pages link to it.

| Fact | Home |
| --- | --- |
| What changed | [CHANGELOG](../CHANGELOG.md) |
| What ran on a board, and the evidence | [Roadmap](roadmap.md) and the [findings](findings/README.md) |
| Rules for a change, review verdicts, approvals | [CONTRIBUTING](../CONTRIBUTING.md) |
| Include rules of each source tree | [Composition zone](composition-zone.md) |
| The pinned Crux revision | `west.yml` |
| Crux facts and board steps (probe, flash, debug) | the Crux pages at the pinned revision |

## Product repository

This repository is a product built on Crux. It links the Crux board pages and keeps only its own board
steps: its image, its build command and the log it expects.

## Check

[`test_docs_page_types.py`](../tests/tooling/test_docs_page_types.py) fails when a page holds more change,
provenance, status or verification markers than its entry in
[`docs_page_types.json`](../tests/tooling/fixtures/docs_page_types.json). Lower an entry when you fix a page;
never raise one. The test matches text only; review applies the checklist to everything else.

Rationale and sources: the
[Crux documentation guidelines](https://github.com/wonny-labs/crux-pilot/blob/c5439c51741bceb8f3327c11882dc3b58bbe2640/docs/documentation-guidelines.md)
at the pinned revision.
