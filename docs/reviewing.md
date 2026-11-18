# Reviewing a change

This page is a checklist for the person who reviews a pull request in this repository. The rules come from
[CONTRIBUTING.md](../CONTRIBUTING.md), and each item names the section that states its rule. An item marked
"practice" is something the repository's own files show but CONTRIBUTING.md does not state as a rule. Where
CONTRIBUTING.md says nothing, the page says so and invents no rule.

The words `PASS`, `REVISE`, `ESCALATE`, "owner" and "reviewer" are in the [glossary](glossary.md#people-and-board-procedures).
If you are the author, [first-change.md](first-change.md) shows the other side of the same process.

## 1. Who reviews, and what they read

CONTRIBUTING.md, section "Review":

- A material change gets an independent review by someone who did not write it.
- The reviewer reads the actual files and the checks, not the summary.
- AI assistance is not approval and not evidence. A claim about a test needs the actual result.

CONTRIBUTING.md does not define "material", does not say how many reviewers a change needs, and does not say how to
record the revision that you reviewed. Name the commit you reviewed in your comment: the checks that the author lists
are tied to a revision, and a review that names none cannot be compared with them.

## 2. The three verdicts

| Verdict | Meaning, from CONTRIBUTING.md "Review" |
|---|---|
| `PASS` | There is no blocking finding. |
| `REVISE` | There are blocking findings that the author can fix. The author fixes them and gets one re-check. |
| `ESCALATE` | The owner has to decide. |

A blocking finding is an unmet acceptance criterion, a broken rule of CONTRIBUTING.md or a factual error. Other
findings go in the pull request. A `PASS` does not grant merge, scope, hardware or release authority.

CONTRIBUTING.md does not say what happens when the re-check still finds a blocking problem. The verdict that sends
a decision to the owner is `ESCALATE`. It also does not say how a finding is closed, or who may close it.

Write the verdict, the revision it applies to, the checks you ran yourself and what you did not check. A `PASS`
that does not say what it covered is hard to use later.

## 3. Every change

- [ ] **The pull request text is complete.** It says what changed, why and how it was checked. Each check carries the
  revision it ran on and who ran it (CI, a reviewer or the author), and the text names what was not run
  (CONTRIBUTING.md, "Commits and pull requests").
- [ ] **No check is reported as passing that did not run.** A CI build is not described as a run on a board
  (same section).
- [ ] **The commit subjects follow the format.** `<type>: <summary>` in English, a lowercase imperative verb, no
  final full stop, under 72 characters, with a type from the list in CONTRIBUTING.md (same section).
- [ ] **One logical change.** CONTRIBUTING.md, "Changing behaviour", asks for one logical change in a pull
  request.
- [ ] **Tests came first.** New behaviour and fixes have a test that the author watched fail. No test or check was
  weakened or deleted to make a change pass. An existing assertion changed only because the approved behaviour
  changed, and the pull request says so ("Changing behaviour").
- [ ] **CI results were read for the head commit.** A green CI result does not replace review. CI is the reference
  for the Zephyr builds and the Twister runs, and a local result does not replace it ("Build and test").
- [ ] **A claim about a board matches the record.** Only step S2 has run on a board, twice, on one bench
  (CONTRIBUTING.md, "What this repository is, and is not", and `docs/findings/s2-first-board-run.md`). A change must
  not claim otherwise.
- [ ] **The text is fit for a public repository.** No name of an employer or customer, no proprietary product, runtime
  or private repository, no reference to a private planning document, no memory sizes of a real product, no
  secrets or absolute paths of a personal or build machine, no text that cannot be published under Apache-2.0
  ("A public repository"). `tests/tooling/test_public_text.py` fails on the usual forms of the planning references
  and does not catch the rest. Read for those yourself.
- [ ] **Hashes only.** No firmware image, `.elf` or `.map` file goes into the repository, a release bundle or a CI
  artefact ("A public repository" and `RELEASE.md`).
- [ ] **The tooling tests pass.** Run `python -m unittest discover -s tests/tooling` on the head commit, or read the
  `Tooling tests` job (CONTRIBUTING.md, "Build and test"). Several documents are pinned by these tests.

## 4. Documentation changes

CONTRIBUTING.md states no separate rules for documents except the public-repository rules above and the review
rules. These items are practice, taken from how the tests and the findings are written.

- [ ] **Each fact matches a file.** Open every file, command, number and name that a changed sentence cites.
  Some of these are pinned by tests, many are not. A sentence that cites a path, a job name or an option must still
  name something that exists.
- [ ] **No claim about an environment that nobody ran.** [try-on-native-sim.md](try-on-native-sim.md), "What has
  been checked", lists what was run. A document that says "works on" a system either adds the run to that list or does
  not say it.
- [ ] **No claim that a CI build is a board run,** and no claim that a `native_sim` pass shows board behaviour
  (CONTRIBUTING.md, "Commits and pull requests", and the glossary entry for `native_sim`).
- [ ] **No private names.** The same rule as in section 3, applied to quoted approvals and to examples.
- [ ] **The pinned text and its pin changed together.** Several tests pin sentences, for example the role sentence in
  `README.md` (`tests/tooling/test_docs.py`). Change a pin only together with the text, and only when the approved
  behaviour changes ("Changing behaviour"). The tooling tests show which sentence is pinned.
- [ ] **The links resolve.** `tests/tooling/test_docs_navigation.py` checks the links of the index, of the pages that
  it names and of the edited pages. Check the others by opening them.
- [ ] **A finding is kept as written.** A later result is added as a dated update or a banner, and the earlier
  reading is not rewritten (`docs/findings/README.md`). Each statement in a finding carries a label that fits its
  evidence (see the glossary entry "Finding"): **Measured** (run, with the command or CI job named), **Inferred** (read
  from source at a named revision and not run), **Recorded** (a CI result read from the logs at a named revision) or
  **Open** (not known). The label set differs between notes, so check the note's own definitions.
- [ ] **Dates and "now" are tied to a record or absent.** A date belongs to a recorded result. A phrase such as
  "currently" or "at the time of writing" becomes false later. Practice only.

## 5. Step and driver changes

A change that adds a step, a Crux component, a zone entry or a build option. [adding-a-step.md](adding-a-step.md) has
the recipe and the mechanical checklist; the points below are what a reviewer verifies.

- [ ] **The limits row came first.** `budgets/limits.json` has the row for the step, added before any job names it,
  and no other step's limit changed to make a build pass. CONTRIBUTING.md says a limit is not changed in the
  same pull request as a pin move to make a bump pass, and the file's own comment says that a change there is a
  reviewed change.
- [ ] **The boundary lists changed together.** A new allowed include means a change of `scripts/check_boundary.py`,
  `tests/tooling/test_boundary.py` and `docs/composition-zone.md` in one pull request that is reviewed as such, with
  the reason why the public interface is not enough (CONTRIBUTING.md, "The boundary"). There is no exception,
  waiver or per-file opt-out.
- [ ] **No include path in CMake.** `app/CMakeLists.txt`, `app/management/management.cmake` and
  `app/management/entropy.cmake` add none, because the check reads includes only ("The boundary").
- [ ] **Kconfig dependencies hold in the resolved configuration.** An unmet dependency only prints a warning, and the
  image builds without the step. Look for the job's checks of the resolved `.config` and `zephyr.dts` (options that
  must be on, options that must be off, the devicetree alias) and for the `require` field of the `Budget` row. Practice:
  the CI job `s<n>` and `budget.yml` in [adding-a-step.md](adding-a-step.md), section 2.5.
- [ ] **The CI job checks what the build resolved.** The job named `S<n> build (...)` builds with the baseline gate
  required (CONTRIBUTING.md, "Build and test") and reads the resolved configuration, not only the command line.
- [ ] **The three statements in CONTRIBUTING.md are updated:** the role section ("Steps S0 to S<n> are built in CI"),
  the `ci.yml` row (`S<n> build`) and the `budget.yml` row (`Budget` for S0 to S<n>). `tests/tooling/test_docs.py`
  checks them against the workflows.
- [ ] **The exact row lists of the earlier step tests are extended, not loosened.** Say so in the pull request.
- [ ] **The findings note labels are honest.** A result that only CI can produce is **Open** with the job named,
  until it is recorded with its revision as **Recorded**. A step is described as built and never run on a board
  until a board run is recorded in a finding (README and `docs/adding-a-step.md`).
- [ ] **A pin move is its own pull request.** It follows the three steps of CONTRIBUTING.md, "The pin and the
  manifest": the revision and the approved commit in the test change together, the places that quote the
  commit are updated, and the pull request carries the SHA-256 of the S2 `zephyr.bin`, its `firmware_identity` and
  the budget tables. A limit does not change in the same pull request.
- [ ] **A driver or HAL question is raised, not settled in passing.** A change that adds GPIO, I2C or SPI use, or a
  Zephyr driver header in `app/src`, meets the rules in [adding-a-step.md](adding-a-step.md), section 5. The
  roadmap records GPIO, I2C and SPI as out of scope. CONTRIBUTING.md does not rule on them.

## 6. Evidence in the pull request

- [ ] Each check names the **revision**, the **command or configuration** and **who ran it**. A check that only the
  author says passed, with no revision, is not evidence yet (CONTRIBUTING.md, "Commits and pull requests").
- [ ] The kinds of result are kept apart: tooling tests, host tests, `native_sim` scenarios (CI), the cross-build for
  the board (CI) and a run on a board. None of them implies another.
- [ ] Failures and skipped checks are listed. A check that did not run is described as not run.
- [ ] For a pin move: the hashes are in the pull request, and nothing in the pull request publishes an image.

## 7. Files that need a reviewed change

When the change touches one of the files in the list
[Files that need a reviewed change](adding-a-step.md#files-that-need-a-reviewed-change), say so in the review and
check the rule that stands next to it in that list. List the files of the change with:

```bash
git diff --name-only --no-renames origin/main...HEAD
```

CONTRIBUTING.md asks for a separate pull request only for a pin move, and for the three boundary files to change
together. It states no rule for `.github/workflows/*.yml`, `scripts/check_mbed_only.py` and `CODEOWNERS`. Those are in
the list because they hold the checks, the licence gate of the Mbed TLS group and the ownership, so read a change to
them with care.

Nothing in this repository enforces the list. `CODEOWNERS` names one account for every file, and whether
GitHub branch protection or required reviews are set for `main` is not recorded in this repository.

## 8. What the owner's approval must cover

CONTRIBUTING.md, "Review" and "Releases, tags and forks", reserve to the owner: merging a pull request, tags,
GitHub Releases and forks. A `PASS` or a green CI result does not give any of them. `docs/board-bring-up.md` reserves
any run on a board, and `RELEASE.md` reserves a tag.

CONTRIBUTING.md does not say how an approval is recorded or how wide it is. The files of the repository show this
practice:

- The approval names what it covers: this pull request, this tag, this run. `RELEASE.md` says that a tag needs the
  approval "given for that tag", and `docs/board-bring-up.md` says that an earlier approval does not carry over to a
  new task.
- A pin move records the approved commit in `west.yml` and in `tests/tooling/test_manifest.py`, together with the
  date of the approval.
- A review `PASS` informs the owner's decision and does not replace it.

When you review a change that needs an approval that is not in the pull request, give `ESCALATE` or say in the
review that the approval is missing. Do not treat your own `PASS` as that approval.
