# Keeping a copy of this repository

This page is for a team that keeps its own copy of this repository, for example as a zip without the Git history in
an internal repository that has no GitHub Actions. It says which words in the documents need a new meaning in your
copy, what to change, how to take over later changes, and what must stay.

It is a reading aid. [CONTRIBUTING.md](../CONTRIBUTING.md) stays the authority for the rules of the public
repository. Licence questions are for your own legal department: this page is not legal advice.

## 1. What the repository does not provide

- **No support.** The repository promises no support period, and only the latest release, if one exists, is
  supported ([README](../README.md#licence-support-and-ownership), `SECURITY.md`). There is no release yet.
- **No service level for security reports.** `SECURITY.md` says so.
- **No product.** The firmware has no real control logic, and its workload is synthetic. Only step S2 has run on a
  board, twice, on one bench ([roadmap](roadmap.md#what-has-run-on-a-board)).
- **No evidence for Crux security claims.** That evidence lives in `crux-pilot`, the Crux repository.

Your team owns everything that your copy adds to this.

## 2. Who "the owner" is in your copy

The documents give some decisions to "the owner": merging a pull request, tags, GitHub Releases and forks, the
release approval, filing a request in `crux-pilot`, and any run on a board. The word means the account in
`CODEOWNERS` in the public repository. In your copy, the owner is whoever approves merges and releases in your
copy. Decide who that is before the first change, and write it down where your team will see it.

The files that name the roles are:

| File | What it says about roles |
|---|---|
| `CONTRIBUTING.md` | The reviewer, the three verdicts, and what needs the owner's approval ("Review", "Releases, tags and forks"). |
| `RELEASE.md` | A tag needs the repository owner's approval, given for that tag. |
| `CODEOWNERS` | One account for every file. |

The reviewer is someone who did not write the change, as before. A review `PASS` and a green CI result do not
replace the owner's approval in your copy either. See the [glossary](glossary.md#people-and-board-procedures) and
[reviewing.md](reviewing.md).

## 3. Make the copy a Git repository

Several scripts and tests call Git. In an export without `.git`, `scripts/check_spdx.py`, `scripts/check-format.sh`
and `scripts/analyze_host.py` fail, and so do some of the tooling tests. In the unpacked copy, run:

```bash
git init && git add -A
```

If the copy already contains `.git`, keep it. Then make the first commit and record which upstream commit the copy
was taken from. Ask whoever made the zip for the commit, because the zip has no history to read it from:

```bash
git commit -m "chore: import crux-controller at <upstream commit>"
```

Check the copy before you change anything. This is the baseline for every later change:

```bash
python3 -m venv .venv && . .venv/bin/activate && python -m pip install pyyaml
python -m unittest discover -s tests/tooling
python scripts/check_boundary.py
python scripts/check_spdx.py
```

## 4. What to change in the copy

- **`CODEOWNERS`.** It holds one line that names an account of the public repository. Replace it with your owners,
  in the format of your Git host. No tooling test reads this file.
- **The issue tracker.** The documents name issues and pull requests of the public repository: "#44", "pull request
  50", and short hashes. In your copy they open nothing, or something unrelated. The facts that matter are stated
  next to them. Do not renumber them. When you refer to your own tracker, say which tracker: "our tracker, item 12".
  Tests pin some of these sentences (`tests/tooling/test_docs.py`), so change the text and the test together.
- **Where to report.** `SECURITY.md` names GitHub private vulnerability reporting. If your copy has no such
  channel, change that text to yours, and change its test (`tests/tooling/test_docs.py`) with it. Keep the rule
  that a vulnerability is not reported in a public issue.
- **Links that point at the public repository.** The README and the findings link to `crux-pilot` and to this
  repository on GitHub. They stay correct as references to upstream.
- **Private names.** If your copy needs internal names in its own documents, keep them out of anything that you send
  back to the public repository (section 8).

## 5. Licence and notices

- Keep `LICENSE` (Apache-2.0).
- Keep the line `SPDX-License-Identifier: Apache-2.0` at the top of first-party files. `scripts/check_spdx.py` checks
  C, CMake, Kconfig, Python and shell files, and your files should carry the line too.
- Add a `NOTICE` file in your copy if your company requires one. The repository has none.
- `docs/dependencies.md` says what `west update` fetches and under which licence each project states it is
  distributed. Those projects are not part of the copy. A product built from the copy has its own obligations,
  which this page does not assess.

## 6. Take over later upstream changes

The zip has no common history with upstream, so a merge has nothing to start from. Compare two exports instead:

```bash
git clone https://github.com/wonny-labs/crux-controller.git ../crux-controller-upstream
git -C ../crux-controller-upstream switch --detach <upstream commit>
diff -ru --exclude=.git --exclude=.venv --exclude=build ../crux-controller-upstream .
```

Read the differences, take the ones you want on a branch of your copy, and run the checks of section 3 again, with
the tooling tests. Name the upstream commit in the commit message. A difference in a sentence that a test pins fails
the tooling tests until the text and the test agree. If you changed such text in your copy, you resolve that
yourself.

If your copy kept the history of this repository, you can add a remote and fetch instead:

```bash
git remote add upstream https://github.com/wonny-labs/crux-controller.git
git fetch upstream
```

A change of the pin, of `.github/workflows/`, of `scripts/` or of the boundary lists is one of the
[files that need a reviewed change](adding-a-step.md#files-that-need-a-reviewed-change). Review it as such in your
copy.

## 7. The Crux pin

`west.yml` imports `crux-pilot` at one pinned commit, a full SHA and never a branch or a tag. `west crux-pins` must
print a `CONTRACT crux-pilot` line and no `MISMATCH`. Do not move the pin as part of another change.

A pin moves in its own small pull request, as CONTRIBUTING.md, "The pin and the manifest", describes:

1. Change the revision and its comment in `west.yml`, and the approved commit in `tests/tooling/test_manifest.py`.
2. Update the places that quote the commit: `docs/dependencies.md`, `RELEASE.md` and `CHANGELOG.md`.
3. Put the SHA-256 of the S2 `zephyr.bin`, its `firmware_identity` and the budget tables in the pull request.

No rule of the public repository reserves a pin move to the owner, and in practice the owner has approved each one.
In your copy, decide who approves it. If an upstream change moves the pin, treat taking it over as a pin move.

`west.yml` names GitHub as the source of `crux-pilot` and, through the Crux manifest, of Zephyr and its modules. How
your build machines reach those repositories is your team's task. This page does not cover it.

## 8. CI in your copy

Everything under `.github/workflows/` is GitHub Actions and runs on GitHub-hosted `ubuntu-24.04` runners:
`ci.yml` (tooling tests, west pins, host tests, the step builds S0 to S6, boundary check, patch style, static analysis),
`budget.yml`, `devcontainer.yml`, `rebuild.yml`, `release.yml` and `scheduled-main.yml`.

- **Keep the workflow files in the copy, even where nothing runs them.** The tooling tests read them, and over a
  hundred tests fail when the directory is missing.
- **Rebuild the checks in your own CI from those files.** Each job lists its commands. The checks that need no Zephyr
  are the tooling tests, the host tests, the boundary check, the SPDX check, the format check and the static analysis
  ([first-change.md](first-change.md) shows them). The step builds, the Twister scenarios and the `Budget` jobs need the
  west workspace and the Zephyr SDK ([try-on-native-sim.md](try-on-native-sim.md)).
- **The `Boundary check` job downloads two scripts from GitHub** and checks their SHA-256. The pinned `crux-pilot`
  contains the same script, so in a west workspace you can run it from there, as
  [composition-zone.md](composition-zone.md#running-the-check) shows.
- **Your CI results are your copy's results.** Do not describe a build in your CI as a run on a board, and do not
  quote it as a result of the public repository.

## 9. What not to do

- Do not weaken or delete a test or a check to make your CI pass, and do not add an exception, waiver or per-file
  opt-out to the boundary check. CONTRIBUTING.md says to extend a check, not to loosen it.
- Do not publish private names. A change that you send to the public repository follows "A public repository" in
  CONTRIBUTING.md: no employer, customer or proprietary product names, no private repository or link, no memory sizes of
  a real product, no secrets and no absolute paths of a personal or build machine.
- Do not merge a change in your copy on a review `PASS` or a green CI alone.
- Do not claim support, certification or a board result that the repository does not record.

## 10. Where to report problems

- A problem with your copy or your CI: your own tracker.
- A problem with this repository, in the documents, the tests or the firmware:
  <https://github.com/wonny-labs/crux-controller/issues>. The page is public: leave out private names, internal
  addresses and secrets.
- A suspected vulnerability: report it privately as `SECURITY.md` describes. Do not open a public issue or pull
  request for it. A weakness in Crux itself belongs in `crux-pilot`.
