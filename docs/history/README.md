# History

This folder keeps text that left the main documents: the Pilot history of the steps (board runs,
approvals, tracking) and the procedures for a copy of the repository without the Git history. Nothing was dropped:
each moved paragraph is here, and the move log below says where it came from. The main documents state the facts
that a developer needs in short present-tense form and link here for the history.

The pages are kept as written and are not updated. In a moved page only the targets of relative links were
rewritten, so that they resolve from this folder. The changelog is not here: [CHANGELOG.md](../../CHANGELOG.md)
stays at the repository root, because `CONTRIBUTING.md` ("The pin and the manifest") names it as a place to update.

| Page | What it keeps |
|---|---|
| [board-runs-and-tracking.md](board-runs-and-tracking.md) | The board-run summary, the approval wording and the tracking notes of the roadmap and the glossary. |
| [copy-procedures.md](copy-procedures.md) | The zip and copy steps of the install guides, the troubleshooting rows for a copy and the glossary entry "Team copy". |
| [readme-before-entry-point.md](readme-before-entry-point.md) | The whole README before it was rewritten as an entry point. |
| [setup-checks.md](setup-checks.md) | The record of the local setup runs and the Dev Container job timing that Getting started carried. |
| [team-copy.md](team-copy.md) | The page for a team that keeps its own copy, moved from `docs/`. |

## Move log

Each row is one moved piece of text. "Whole" means the whole file or section. Where a main document keeps a short
statement instead, the last column says what it says now.

| Source file | Source section | Destination | Destination section | What the source says now |
|---|---|---|---|---|
| `docs/team-copy.md` | whole file | [team-copy.md](team-copy.md) | whole file | Moved with `git mv`; relative link targets rebased. |
| `README.md` | whole file | [readme-before-entry-point.md](readme-before-entry-point.md) | whole page | The README is rewritten as an entry point (below). |
| `README.md` | opening paragraphs and "Who this is for, and where to start" | [readme-before-entry-point.md](readme-before-entry-point.md) | "Crux Controller", "Who this is for, and where to start" | A short opening, the role sentence (unchanged) and "Reading path". |
| `README.md` | Terms used below | [readme-before-entry-point.md](readme-before-entry-point.md) | "Terms used below" | Dropped; every term is in the [glossary](../glossary.md). |
| `README.md` | Roles and references | [readme-before-entry-point.md](readme-before-entry-point.md) | "Roles and references" | Dropped; owner, reviewer and operator are in the [glossary](../glossary.md#people-and-board-procedures), which also gained the entry "Hashes and numbers" from this section. |
| `README.md` | How to try it | [readme-before-entry-point.md](readme-before-entry-point.md) | "How to try it" | Shortened: step 1 drops "in the distribution", step 2 drops the copy instruction, and step 5 becomes a paragraph without the sentence that pointed at CONTRIBUTING.md for the contribution rules and the Python tooling tests. |
| `README.md` | Status | [readme-before-entry-point.md](readme-before-entry-point.md) | "Status" | "State": the step table is unchanged; the dated S2 board-run summary and the findings list are replaced by one sentence and links. |
| `README.md` | What it is not | [readme-before-entry-point.md](readme-before-entry-point.md) | "What it is not" | Dropped; `CONTRIBUTING.md`, "What this repository is, and is not", states it. |
| `README.md` | Boundary | [readme-before-entry-point.md](readme-before-entry-point.md) | "Boundary" | Dropped; [composition-zone.md](../composition-zone.md) and [architecture.md](../architecture.md) state it. |
| `README.md` | The Crux pin | [readme-before-entry-point.md](readme-before-entry-point.md) | "The Crux pin" | Dropped; the glossary entry "Pin", [dependencies.md](../dependencies.md) and `CONTRIBUTING.md` state it. |
| `README.md` | How it is tracked | [readme-before-entry-point.md](readme-before-entry-point.md) | "How it is tracked" | Dropped; history only. |
| `README.md` | Licence, support and ownership: the "Contributing" bullet, the team-copy bullet, the "Dependencies and their licences" clause and the changelog clause of the "Releases" bullet | [readme-before-entry-point.md](readme-before-entry-point.md) | "Licence, support and ownership" | CONTRIBUTING.md, dependencies.md and CHANGELOG.md are linked under "Where the rules are"; the other bullets stay; an ownership bullet points at the glossary. |
| `docs/roadmap.md` | Short version, the S5 bullet | [board-runs-and-tracking.md](board-runs-and-tracking.md) | "Short version, the S5 bullet" | Dropped; the next bullet says what has run on a board. |
| `docs/roadmap.md` | Step S5 in more detail, first sentence | [board-runs-and-tracking.md](board-runs-and-tracking.md) | "Step S5 in more detail, the first sentence" | The section starts with what the code does. |
| `docs/roadmap.md` | Step S5 in more detail, last paragraph | [board-runs-and-tracking.md](board-runs-and-tracking.md) | "Step S5 in more detail, the last paragraph" | "S5 has never run on a board." |
| `docs/roadmap.md` | What has run on a board | [board-runs-and-tracking.md](board-runs-and-tracking.md) | "What has run on a board (whole section body)" | Two short paragraphs without dates or quotations; the record stays in the S2 finding. |
| `docs/roadmap.md` | What is not yet possible, and why, last paragraph | [board-runs-and-tracking.md](board-runs-and-tracking.md) | "What is not yet possible, and why, the last paragraph" | Nothing is filed in `crux-pilot`; filing needs the owner's approval. |
| `docs/glossary.md` | Stage | [board-runs-and-tracking.md](board-runs-and-tracking.md) | "Stage (whole entry, rewritten in short form)" | A short entry without the tracking paragraph and pull request numbers. |
| `docs/glossary.md` | Gated procedure, second sentence | [board-runs-and-tracking.md](board-runs-and-tracking.md) | "Gated procedure, the second sentence" | Points at the "Method" section of the S2 finding. |
| `docs/architecture.md` | Layers and zones, the `zephyr/net/sntp.h` bullet, last sentence | [board-runs-and-tracking.md](board-runs-and-tracking.md) | "Layers and zones, the `zephyr/net/sntp.h` bullet, the last sentence" | The bullet ends with what the source includes. |
| `docs/glossary.md` | Owner, last sentence | [copy-procedures.md](copy-procedures.md) | "Owner, the last sentence" | Dropped. |
| `docs/glossary.md` | Team copy | [copy-procedures.md](copy-procedures.md) | "Team copy (whole entry)" | Dropped. |
| `docs/try-on-native-sim.md` | Quick start, the zip part of step 3 and step 4 | [copy-procedures.md](copy-procedures.md) | "Quick start, the zip part of step 3 and step 4" | Step 3 clones; the later steps are numbered 4 to 8. |
| `docs/try-on-native-sim.md` | From a copy without Git history | [copy-procedures.md](copy-procedures.md) | "From a copy without Git history (whole section)" | Dropped. |
| `docs/try-on-native-sim.md` | After a pin or SDK change, first sentence | [copy-procedures.md](copy-procedures.md) | "After a pin or SDK change, first sentence" | "it arrives with a `git pull`." |
| `docs/try-on-native-sim.md` | If the dev container fails, two bullets | [copy-procedures.md](copy-procedures.md) | "If the dev container fails, two bullets" | The CRLF bullet gives the fix itself; the bullet for a copy without `.git` is dropped. |
| `docs/troubleshooting.md` | Setup and the dev container, five rows; Checks that fail locally, one row | [copy-procedures.md](copy-procedures.md) | "Six rows as they were" | Two rows dropped; four reworded without the copy (CRLF, exec bit, a new copy, `.clang-format`). |
| `docs/first-change.md` | 1. Get the code, the copy sentence | [copy-procedures.md](copy-procedures.md) | "1. Get the code, the sentence after the clone commands" | Dropped. |
| `docs/README.md` | Paths by task, "I keep a copy of the repository" | [copy-procedures.md](copy-procedures.md) | "Paths by task" | Dropped. |
| `docs/README.md` | All documents, the row of `team-copy.md` | [copy-procedures.md](copy-procedures.md) | "All documents, the row of team-copy.md" | The page is listed under "In `docs/history/`". |

### Removed duplicates

These pieces were removed because another page states the same thing; they were not copied here. The text
before the removal is in the Git history of the file.

| Source file | Removed | Where the content is now |
|---|---|---|
| `README.md` | "New here?" line, "How to try it" steps 1 to 4, "Reading path" with the reading times, the EVKB build column of the step table | [README](../../README.md#quick-start) "Quick start" points at [first-hour.md](../tutorial.md); the task table "Where to read next"; the times are in the [index](../README.md); every step is built for the EVKB, as "Status" says |
| `docs/README.md` | the reading-time preface, the reading-path total and the bullet lists under "Paths by task" | one short paragraph per task; the "All documents" tables keep each page and its time |
| `docs/try-on-native-sim.md` | "If the dev container fails", the list of messages | [troubleshooting.md](../troubleshooting.md#setup-and-the-dev-container), which has every message with its cause and fix |
| `docs/try-on-native-sim.md`, `docs/roadmap.md`, `docs/architecture.md` | link lists in the opening paragraphs | the [index](../README.md) and the README task table |
| `docs/first-hour.md` | whole file | `docs/tutorial.md` | whole file | Renamed with `git mv` to follow the Crux page names; the run steps 5 to 8 of the Getting started "Quick start" joined it. |
| `docs/try-on-native-sim.md` | What has been checked | [setup-checks.md](setup-checks.md) | "What was checked" | Getting started states the current facts and links the record. |
| `docs/try-on-native-sim.md` | Network and prerequisites, the dated CI timing sentence | [setup-checks.md](setup-checks.md) | "Timing of the Dev Container job" | The same figures without the date, with a link to the record. |
| `docs/try-on-native-sim.md` | opening, the six-term paragraph and the macOS run details | [setup-checks.md](setup-checks.md) and the [glossary](../glossary.md) | "What was checked"; glossary entries | One sentence links the glossary; the macOS sentence states what runs, and the record holds the run. |
| `docs/dependencies.md` | the paragraph on the pin move of 16 November 2026 | [CHANGELOG.md](../../CHANGELOG.md) | the entry for the move from `dfd3ad7d` to `8e3737d2` | Dropped from the page; the changelog entry holds the same facts, and the page keeps the rule to read the groups of a new Crux manifest. |

The example workspace folder of the guides and of `.devcontainer` is `crux-controller-workspace` (it was `controller-ws`); the moved
copies use the new name.
