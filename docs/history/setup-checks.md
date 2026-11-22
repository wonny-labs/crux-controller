# Setup checks record

Record of the local runs behind the statements of [Getting started](../try-on-native-sim.md) about the setup
routes, the Dev Container and macOS, made on 18 November 2026; each item names its revision where one was recorded. It
is kept as written, apart from rebased link targets. The current guidance is on Getting started; CI results are in the Actions tab of each pull request.

## What was checked


- The venv block (`python3 -m venv`, `pip install` of the pinned tools, `west init -l`)
  was run in a fresh `ubuntu:24.04` container on 18 November 2026 (arm64, Python 3.12.3; the revision of the
  clone is not recorded), after
  `apt-get install python3-venv python3-dev git ca-certificates`. The clone was copied in from a local checkout,
  so the `git clone` command and the full `apt-get` package list were not run. It confirmed that there is no
  `python` command before the virtual environment exists, that `west 1.4.0` installs in it and that
  `west init -l crux-controller` creates `.west` in the workspace directory.
- WSL2 was not tested. Only that arm64 `ubuntu:24.04` container ran those steps.
- Not run for this page: `west update`, the SDK install, Twister, the S6 group steps and the host tests on
  a fresh Linux machine. Their commands are those of the CI jobs with the variables replaced.
- On macOS on 18 November 2026 (Apple clang 17.0.0, CMake 4.4.5, Ninja, Python 3.9 with PyYAML, clang-format 18.1.8
  from pip), at `f7d3fab`, these ran and passed in a Git repository. `f7d3fab` is a local revision of that day (main
  plus the pull requests that were open then), not a published commit. The host tests with the sanitizers off and on
  (six CTest tests each), the tooling tests (983 tests, 3 skipped), the boundary check, the SPDX check and `scripts/check-format.sh`.
- Also on macOS, at the same local revision `f7d3fab`, one-off runs of the failures that
  [troubleshooting.md](../troubleshooting.md) listed then, with the counts of that day (they drift as tests are added). In a copy without `.git`, one tooling test failed and seven stopped
  with a Git error, and `scripts/check_spdx.py` exited with status 2; `scripts/check_boundary.py` passed. After
  `git init` and `git add -A` all of them passed. With CRLF line ends in every text file, 21 tooling tests
  failed (the ones that run the shell scripts), a script started directly failed with
  `env: bash\r: No such file or directory`, and clang-format 18.1.8 itself accepted a CRLF C file. With the exec bits
  removed, five tooling tests failed. Without `.clang-format`, clang-format 18.1.8 reported errors for a file that
  it accepts with it.
- `.devcontainer/check-host.sh`, as at `f9342b3` of `main`, ran on macOS on 18 November 2026 in a scratch folder: it passed a layout of its own,
  refused a wrong folder name, a parent that holds `.bashrc` and a parent that is the home directory (exit status 2),
  and only warned about another entry, not about `.crux-extra-ca.crt`. What `setup.sh` does with a proxy, a
  certificate, a failed step or an old SDK folder, and what `devcontainer.json` passes, is read from the files and was
  not run.
- The dev container (`.devcontainer/`, `scripts/dev-shell.sh`) was not started on a developer machine at all, and
  nobody has used it with WSL2, Docker Engine in WSL2 or the dev containers extension. Its files were checked by
  tooling tests (versions against `ci.yml`, the base image digest, no Docker Desktop feature, no write permission or
  upload in the workflow), and the workflow `devcontainer.yml` runs the image and `scripts/dev-shell.sh` on an
  Ubuntu 24.04 x86_64 GitHub runner (the checks listed in the dev container section, including the S1 cross-build).
  That job runs when a pull request or a push changes `.devcontainer/`, `scripts/dev-shell.sh`, `west.yml` or the
  workflow file, and when it is started by hand. Its latest result is in the Actions tab, under the `devcontainer`
  workflow, for the pull request that last changed those paths; a docs-only revision has no result of its own.
- Not tested by anyone, and so written as general knowledge or as the interface of the container files: the proxy
  and company-certificate settings, a run with no network, systemd in `/etc/wsl.conf`, the GitHub rate-limit
  message, and how much disk and time a first run takes on a developer machine.

## Timing of the Dev Container job

The CI job that builds the Dev Container image on a GitHub runner with a fast network took between about 7 and
15 minutes in total in its recent successful runs on 18 November 2026, and its first step (image, workspace and
SDK) about 3.5 minutes in the run read for Getting started.
