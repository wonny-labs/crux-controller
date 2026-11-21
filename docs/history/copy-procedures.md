# Copy procedures, as they were

This page keeps the text that described a copy of this repository without the Git history (for example a zip)
until it left the install guides. It is history: the steps are not maintained and may not match the current
scripts. The install guides now describe a clone only. The page that described a team's copy as a whole is
[team-copy.md](team-copy.md), kept as it was.

Each section below names the page and the section that the text came from. The text is unchanged; only the
targets of relative links were rewritten so that they resolve from this folder. The example workspace folder
reads `crux-controller-workspace`, the name that the guides used when the text was moved.

## From `docs/try-on-native-sim.md`: Quick start, the zip part of step 3 and step 4

   From a zip copy, unpack it so that `west.yml` and the hidden files (`.devcontainer`, `.clang-format`,
   `.github`) are directly in that folder (install `unzip` with `sudo apt-get install unzip` if it is missing).
   `unzip -l /path/to/the-copy.zip | head` shows whether the zip has one top-level folder. If it has, unzip into the
   parent folder and rename that folder to `crux-controller`:

   ```bash
   mkdir -p ~/work/crux-controller-workspace && cd ~/work/crux-controller-workspace
   unzip /path/to/the-copy.zip
   mv <the extracted folder> crux-controller
   cd crux-controller
   ls -a
   ```

   If the zip has no top-level folder, unzip into `crux-controller` itself:

   ```bash
   mkdir -p ~/work/crux-controller-workspace/crux-controller && cd ~/work/crux-controller-workspace/crux-controller
   unzip /path/to/the-copy.zip
   ls -a
   ```

   If you unpacked it into `crux-controller` and the files are in one more folder inside it, move them with the
   hidden files (a plain `mv sub/* .` leaves `.devcontainer`, `.github`, `.clang-format` and `.gitattributes`
   behind), then check:

   ```bash
   shopt -s dotglob
   mv sub/* .
   rmdir sub
   ls -a
   ```

   `ls -a` must list `.devcontainer`, `.clang-format`, `.github` and `west.yml`.

4. Only for a copy without a `.git` folder: make it a Git repository, because the format check, the static
   analysis, the SPDX check and several tooling tests ask Git for the file list. Set `core.autocrlf` before
   `git add`, check that the scripts have LF line ends, and restore the exec bits that a zip can lose. No commit
   and no Git identity are needed. [From a copy without Git history](#from-a-copy-without-git-history) says
   what to do if `file` reports CRLF.

   ```bash
   git init
   git config core.autocrlf false
   git add -A
   file scripts/dev-shell.sh
   chmod +x scripts/*.sh .devcontainer/*.sh
   ```

## From `docs/try-on-native-sim.md`: From a copy without Git history (whole section)

### From a copy without Git history

A copy is a zip or any folder without a `.git` folder. It runs the same, with these differences.

- **The folder name and place.** The files go directly in a folder named `crux-controller`, in a parent folder of
  its own, as in the quick start. The copy keeps nothing of the Git history, so a short hash, a pull request number
  or an issue number in the text cannot be opened from it.
- **Unpacking.** A zip with one top-level folder is unzipped into the parent folder, and the extracted folder is
  renamed `crux-controller`. If you moved the files up by hand, include the hidden ones:
  `shopt -s dotglob; mv sub/* .; rmdir sub`, and check with `ls -a` that `.devcontainer`, `.clang-format` and
  `.github` are there. A plain `mv sub/* .` leaves them behind.
- **A Git repository.** These need one: `scripts/check-format.sh`, `scripts/analyze_host.py` and
  `scripts/check_spdx.py`, which ask Git for the file list, and several tooling tests that do the same (eight of
  them failed in a copy without `.git` in the author's run). `scripts/check_boundary.py` and the host tests did
  not need one in the author's runs. Whether `west` itself needs one was not tested. Run
  `git init`, `git config core.autocrlf false` and `git add -A` in the folder, in that order; the configuration
  comes first, so that a global Git setting does not change what `git add` records. No commit is needed.
- **Line ends.** A clone checks out LF on every platform, because `.gitattributes` pins it. A copy that Git did not
  make can still have CRLF, and a file with CRLF line ends breaks the shell scripts: started directly they fail with
  `env: bash\r: No such file or directory`, and run as `bash scripts/...` they fail at the line that sets
  `pipefail`. A copy made on Windows, or from a Git for Windows checkout with `core.autocrlf` on, can have them.
  `file scripts/dev-shell.sh` must not say `with CRLF line terminators`. No file of this repository needs a CR, so
  the fix is to strip them and add the files again:

  ```bash
  git ls-files -z | xargs -0 sed -i 's/\r$//'
  git add -A
  ```

- **Exec bits.** A zip can lose the executable bit of the scripts, and `./scripts/check-format.sh` then says
  `Permission denied`. Either restore the bits (below), or start the scripts as `bash scripts/check-format.sh`:

  ```bash
  chmod +x scripts/*.sh .devcontainer/*.sh
  ```

- **Hidden files.** `ls -a` must list `.clang-format`, `.clang-tidy`, `.devcontainer`, `.github` and `.gitignore`.
  A copy made by a tool that skips hidden files lacks them. Without `.clang-format`, clang-format uses its default
  style and the format check reports every C file (the author saw this with clang-format 18.1.8).
- **A newer copy.** Replace the whole `crux-controller` folder and leave the parent folder alone, then follow
  [After a pin or SDK change](../try-on-native-sim.md#after-a-pin-or-sdk-change) if `west.yml` changed.

## From `docs/try-on-native-sim.md`: After a pin or SDK change, first sentence (the words "or a newer copy" removed)

A pin change is a new revision of `crux-pilot` in `west.yml`; it arrives with a `git pull` or a newer copy.

## From `docs/try-on-native-sim.md`: If the dev container fails, two bullets (the CRLF bullet's link and the bullet for a copy without `.git`)

- `env: bash\r: No such file or directory` or an error at `pipefail`: CRLF line ends. See
  [From a copy without Git history](#from-a-copy-without-git-history).
- `fatal: not a git repository`, or tooling tests that fail with a Git error: the copy has no `.git`. Run
  `git init`, `git config core.autocrlf false` and `git add -A`.

## From `docs/troubleshooting.md`: Six rows as they were (two removed: `.devcontainer` missing after unzip, `fatal: not a git repository`; four reworded: CRLF, exec bit, a new copy, `.clang-format` missing from the copy)

| Symptom | Where it appears | Cause | Fix | More |
|---|---|---|---|---|
| `env: bash\r: No such file or directory`, or `set: pipefail: invalid option name` | starting a script directly, or `bash scripts/check-format.sh` | CRLF line ends, from a zip made on Windows or a Git for Windows checkout with `core.autocrlf` on | `git ls-files -z \| xargs -0 sed -i 's/\r$//'`, then `git add -A`; `file scripts/dev-shell.sh` must not say CRLF | [From a copy without Git history](#from-a-copy-without-git-history) |
| `bash scripts/dev-shell.sh`: docker build fails (for example that the path `.devcontainer` is not found), .devcontainer missing after unzip | `bash scripts/dev-shell.sh`; `ls -a` shows no `.devcontainer`, `.clang-format` or `.github` | the hidden files stayed behind: a zip was moved up with `mv sub/* .`, which does not move dot files (general knowledge for the Docker wording) | `shopt -s dotglob; mv sub/* .; rmdir sub`, or unzip into the parent folder and rename the folder to `crux-controller`; `ls -a` must list `.devcontainer`, `.clang-format`, `.github` | [Quick start](../try-on-native-sim.md#quick-start) |
| `Permission denied` when you start a script | `./scripts/check-format.sh`, `scripts/dev-shell.sh` | the exec bit is lost, as a zip can lose it | `chmod +x scripts/*.sh .devcontainer/*.sh`, or start it as `bash scripts/check-format.sh` | [From a copy without Git history](#from-a-copy-without-git-history) |
| `fatal: not a git repository`, `check_spdx: cannot list the files of ...`, or tooling tests that stop with a `CalledProcessError` of `git ls-files` | `scripts/check-format.sh`, `scripts/analyze_host.py`, `scripts/check_spdx.py`, `tests/tooling` | the copy has no `.git` folder | `git init`, `git config core.autocrlf false`, `git add -A` | [From a copy without Git history](#from-a-copy-without-git-history) |
| import errors or a failing Twister run after a `git pull` or a new copy that moved the pin | any command in the container | the workspace still has the old projects, or Zephyr's requirement files changed | `west update`, then `bash .devcontainer/setup.sh` | [After a pin or SDK change](../try-on-native-sim.md#after-a-pin-or-sdk-change) |
| `error: code should be clang-formatted [-Wclang-format-violations]` for many files, or for every file | `scripts/check-format.sh` with 18.1.8 | real differences, or `.clang-format` is missing from the copy, so clang-format uses its default style (CRLF alone did not cause it in the author's run) | `ls -a` must list `.clang-format`; otherwise run `clang-format -i` with 18.1.8 on the files that the message names | [From a copy without Git history](#from-a-copy-without-git-history) |

## From `docs/first-change.md`: 1. Get the code, the sentence after the clone commands

If your team keeps a copy of the repository, clone your copy instead ([team-copy.md](team-copy.md)).

## From `docs/glossary.md`: Owner, the last sentence

In a
[team copy](team-copy.md) of this repository the owner is whoever approves merges and releases
in that copy.

## From `docs/glossary.md`: Team copy (whole entry)

**Team copy.** A copy of this repository that a team keeps in its own repository, for example as a zip without
the Git history. [team-copy.md](team-copy.md) says what to change in it.

## From `docs/README.md`: Paths by task, "I keep a copy of the repository"

### I keep a copy of the repository

- [team-copy.md](team-copy.md): what to change and what to keep in a copy without the Git history or GitHub CI.

## From `docs/README.md`: All documents, the row of team-copy.md

| [team-copy.md](team-copy.md) | What to change and what to keep when a team holds a copy of the repository without GitHub CI. | 6 min |
