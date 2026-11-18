# How to try it without a board

This page is for a teammate who wants to see the firmware's tests run and has no RT1060-EVKB at hand.
Terms are in the [glossary](glossary.md), the layout is in the [architecture](architecture.md), and what has
and has not run on a board is in the [roadmap](roadmap.md).

Six terms, defined once. **west** is Zephyr's tool for workspaces, builds and tests. A **workspace** is the
folder that holds this repository next to the `.west/` folder and the projects that `west.yml` fetches
(`zephyr/`, `modules/`, `crux-pilot/`). **Twister** is Zephyr's test runner (`west twister`). **`native_sim`**
is a simulated Zephyr board that runs as an ordinary program on the build host. The **pin** is the one commit
of `crux-pilot` that `west.yml` imports. A **dev container** is a Docker image with the tools of the CI jobs;
the workspace folder is mounted into it.

There are two routes, and the first is the one to start with:

1. **The dev container.** For Windows 11 with WSL2 (an Ubuntu 22.04 distribution is fine), for any Linux older
   than Ubuntu 24.04, and for anyone who would rather not install the tools on the host. It needs Docker
   Engine only, not Docker Desktop. Start at the [quick start](#quick-start).
2. **The native setup on Ubuntu 24.04**, the CI image, on x86_64, with no Docker. Start at
   [What you need first](#what-you-need-first). A distribution older than Ubuntu 24.04 cannot do it: Zephyr 4.4
   needs Python 3.12, and Ubuntu 22.04 has 3.10.

On macOS only part of this runs natively. In the author's runs (Apple clang 17, CMake 4.4, Ninja and Python
3.9 with PyYAML) the Python tooling tests, the boundary check, the SPDX check, the format check (with
clang-format 18.1.8 from pip) and the host tests (sanitizers off and on) passed; the host tests also build on
macOS. The tooling tests, the SPDX check and the format check need a Git repository. The Zephyr builds and the
Twister runs need Linux or the dev container (Zephyr's `native_sim` is documented for Linux hosts: general
knowledge). Docker on macOS was not tried.

The commands come from the CI workflow (`.github/workflows/ci.yml`, job `S1`, on `ubuntu-24.04`) and from
[CONTRIBUTING.md](../CONTRIBUTING.md), with the CI-only variables replaced by local values. What was run
locally, and what was not, is in [What has been checked](#what-has-been-checked). CI stays the reference:
a local result is a convenience and does not replace the CI result that a pull request cites. If something
fails, look it up by its message in [troubleshooting.md](troubleshooting.md).

## Dev container

A dev container is a Docker image with the host packages and tools of the CI jobs, an Ubuntu 24.04 userland and
Python 3.12, plus a script that fetches the west workspace and the Zephyr SDK. It is for a teammate whose Linux is
older than 24.04, for example an Ubuntu 22.04 distribution under WSL2, and it needs **Docker Engine only: no Docker
Desktop**.

**Nobody has run it on WSL2 yet.** Not tested by anyone: this container on WSL2, Docker Engine in a WSL2
distribution, the VS Code route, systemd in `/etc/wsl.conf`, a proxy or a company certificate, and a run without a
network. Only an x86_64 host was exercised, and only in CI. [What the container is](#what-the-container-is)
says what CI does run.

### Quick start

For a teammate on Windows 11 with WSL2 and an Ubuntu 22.04 distribution; the same steps apply to a Linux machine
with Docker Engine. Run the commands in a WSL terminal, not in PowerShell, unless a step says PowerShell.

1. Install Docker Engine in the distribution, as Docker describes for Ubuntu
   (<https://docs.docker.com/engine/install/ubuntu/>). Do not install Docker Desktop. Add yourself to the
   `docker` group, then close the terminal, run `wsl --shutdown` in PowerShell and open the distribution again,
   so that `docker` works without `sudo`:

   ```bash
   sudo usermod -aG docker "$USER"
   ```

2. Start the Docker daemon and check it. If systemd is enabled in the distribution, the daemon starts by itself.
   If not, start it after every `wsl --shutdown` and every reboot. Enabling systemd (`systemd=true` under
   `[boot]` in `/etc/wsl.conf`, then `wsl --shutdown`) is an option that nobody has tested here.

   ```bash
   sudo service docker start
   docker run --rm hello-world
   ```

3. Choose a parent folder of its own in the Linux home directory (not under `/mnt/c`), empty apart from the
   clone, and put the sources in a folder named exactly `crux-controller` in it, for example
   `~/work/controller-ws/crux-controller`. From a clone:

   ```bash
   mkdir -p ~/work/controller-ws && cd ~/work/controller-ws
   git clone -c core.autocrlf=false https://github.com/wonny-labs/crux-controller.git crux-controller
   cd crux-controller
   ```

   From a zip copy, unpack it so that `west.yml` and `README.md` are directly in that folder (install `unzip`
   with `sudo apt-get install unzip` if it is missing). If `ls west.yml` fails, the zip holds one more folder:
   move its content up one level.

   ```bash
   mkdir -p ~/work/controller-ws/crux-controller && cd ~/work/controller-ws/crux-controller
   unzip /path/to/the-copy.zip
   ls west.yml
   ```

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

5. First run. This builds the image, then runs `.devcontainer/setup.sh` in the container: it creates the virtual
   environment, fetches Zephyr and the modules with `west init -l` and `west update`, installs the Python
   requirements of Zephyr and installs the Zephyr SDK. It downloads several GiB and takes a long time (see
   [Network and prerequisites](#network-and-prerequisites)). Later runs find all of it already there.

   ```bash
   bash scripts/dev-shell.sh west --version
   ```

   It is done when the command returns with status 0 after these lines (the SDK and west versions are those of
   `.devcontainer/Dockerfile` and `.devcontainer/requirements-tools.txt`):

   ```text
   setup: workspace /workspaces/ws, Zephyr SDK 1.0.1, West version: v1.4.0
   West version: v1.4.0
   ```

   If it stops, the last line names the step:

   ```text
   setup: failed during <step>; rerun: bash .devcontainer/setup.sh
   ```

   Read the lines above it, fix the cause and run the same command again: the setup carries on where it stopped.

6. Run all the `native_sim` scenarios of steps S1 to S5. `scripts/dev-shell.sh` runs a command with the
   repository as the working directory, so the command changes into the workspace folder first
   (`/workspaces/ws` in the container is your `~/work/controller-ws`):

   ```bash
   bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && west twister -p native_sim/native/64 -T crux-controller/tests/native_sim --inline-logs --clobber-output -O twister-out'
   ```

   It ends like this (quoted from a CI log, with the end of each line cut):

   ```text
   INFO    - 17 of 17 executed test configurations passed (100.00%), 0 built (not run), 0 ...
   INFO    - 31 of 31 executed test cases passed (100.00%) on 1 out of total ... platforms ...
   ```

   All 17 Twister ids of [the table below](#run-the-s1-to-s5-scenarios) must be there and passed. A lower
   count means that a scenario did not run.

7. Run the tooling tests, the Python tests of the scripts, workflows and documents:

   ```bash
   bash scripts/dev-shell.sh python -m unittest discover -s tests/tooling
   ```

   It ends with `Ran <n> tests in <t>s` and `OK`; when some tests are skipped the last line reads
   `OK (skipped=<m>)`.

8. Run one scenario, here step S1, by pointing `-T` at its directory (this form is ordinary Twister usage and
   was not run for this page):

   ```bash
   bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && west twister -p native_sim/native/64 -T crux-controller/tests/native_sim/s1 --inline-logs --clobber-output -O twister-out-s1'
   ```

9. Find the outputs. The Twister folders (`twister-out`, `twister-out-s1`) are in the workspace folder, next to
   the clone (`~/work/controller-ws`), because the commands ran there; each scenario has its own build folder
   in them, and `--inline-logs` prints the output of a failed scenario. Builds of the repository itself
   (for example `build/host` of the host tests) are under `build/` in the clone, which `.gitignore` excludes.

To check a change before you push it, the other CI checks run through the same script, for example
`bash scripts/dev-shell.sh bash scripts/check-format.sh`. [Commands inside the container](#commands-inside-the-container)
lists them.

### What the container is

What does run is CI: the workflow `devcontainer.yml` builds the same image on an Ubuntu 24.04 x86_64 runner,
runs `scripts/dev-shell.sh` and, inside the container, the tooling tests, the format check, the static analysis, the host tests (sanitizers off and on), both boundary
checks, the `native_sim` scenarios of [the S1 to S5 section](#run-the-s1-to-s5-scenarios) and the RT1060-EVKB
cross-build of step S1 (with the baseline gate required) with its output and configuration checks, using the
Zephyr SDK that `setup.sh` installs. That is a run of the image and the scripts, not of VS Code or of WSL2 (see
[What has been checked](#what-has-been-checked)). If a step fails for you, look the message up in
[troubleshooting.md](troubleshooting.md), and otherwise open an issue with the output.

The container is not the CI runner. It uses Ubuntu's Python 3.12 (not pinned to a patch release) where CI uses
`actions/setup-python`, a devcontainers base image where CI uses the runner image, pip's cmake and ninja where the
`Host tests` job uses the runner's, `clang-tidy-18` installed without its recommended packages, the extra packages
`python3-venv` (for the virtual environment), `curl` and `sudo` (for the setup script), and PyYAML pinned. The
Zephyr requirement files are not pinned, as in CI.

The files are `.devcontainer/devcontainer.json` (for VS Code), `.devcontainer/Dockerfile` (the image, with the base
image pinned by digest), `.devcontainer/requirements-tools.txt` (the pinned Python tools),
`.devcontainer/setup.sh` (the workspace and SDK setup), `.devcontainer/check-host.sh` (the check of the folder on
the host) and `scripts/dev-shell.sh` (the same without VS Code). The versions follow `ci.yml`, and a tooling test
compares them. `.gitattributes` pins LF line ends, so that a clone checks the scripts out with LF on every platform.

`.devcontainer/check-host.sh` checks the folder layout on the host before the container is created. VS Code runs it
as the `initializeCommand` of `devcontainer.json`, on the host side, so it needs bash there: open the folder from
WSL, as [With VS Code](#with-vs-code) says. It refuses, with a line that starts `check-host:` and exit status 2, a
clone that is not in a folder named `crux-controller`, a parent folder that is your home directory or `/`, and a
parent folder that holds `.ssh`, `.gnupg`, `.bashrc`, `.profile` or `.gitconfig`. It only warns when the parent
folder holds other entries, because the container sees them (`.crux-extra-ca.crt` is not one of them).
`scripts/dev-shell.sh` does not run it. `setup.sh` has a smaller check of its own in the container: the folder name
and the markers of a home directory.

`.devcontainer/setup.sh` prints to the standard error stream, also what pip, west and git print, so that a command
which `scripts/dev-shell.sh` runs after it keeps a clean standard output. It names each step as it starts it, and
when one fails it prints `setup: failed during <step>; rerun: bash .devcontainer/setup.sh`. It does again what an
interrupt left half done: a virtual environment without pip, a `.west` folder from an interrupted `west init`, and
an SDK folder without its install marker.

### What you need

1. WSL2 with a Linux distribution, and your files in its Linux file system (not under `/mnt/c`: the builds are
   slow there and file modes can differ).
2. Docker Engine inside the distribution, installed as the first step of the quick start says, and a running
   daemon. The image is `linux/amd64`, the architecture of a Windows PC, and only an x86_64 host was exercised,
   and only in CI. On an arm64 host Docker Engine needs amd64 emulation (binfmt handlers for QEMU) registered
   first, or the build fails with "exec format error"; that was not tested.
3. Memory and CPUs for WSL2. Zephyr builds and parallel Twister runs need more than a small default. WSL2 gets a
   share of the machine's memory and all its logical processors unless `%UserProfile%\.wslconfig` on Windows says
   otherwise, for example (the numbers are an example, not a measured requirement):

   ```ini
   [wsl2]
   memory=12GB
   processors=6
   ```

   Run `wsl --shutdown` in PowerShell for a change to apply.
4. For VS Code: Visual Studio Code on Windows with the WSL extension and the Dev Containers extension.

Nothing in the files uses `host.docker.internal`, the Docker socket or a mount of your home directory.

### Network and prerequisites

The setup contacts these hosts. Only `mcr.microsoft.com` (the `FROM` line of `.devcontainer/Dockerfile`) and the
`github.com` remotes of `west.yml` are read from the files. The other names are the usual ones and were not looked
up, and Zephyr's own manifest, which the pinned `crux-pilot` imports, was not read for this page: it may name
more hosts. A firewall or proxy must allow them.

| Host | What for | When |
|---|---|---|
| `mcr.microsoft.com` | the base image named in the Dockerfile, pulled by the Docker daemon | the first image build, and when the digest changes |
| the Ubuntu package mirrors that the base image is set up with | `apt-get install` of the packages in the Dockerfile | the image build |
| PyPI (`pypi.org` and its file host) | `pip install` of `.devcontainer/requirements-tools.txt` and of the Zephyr requirement files | the first setup, and when a requirements file changes |
| `github.com` | `west update`: this repository's manifest projects from `github.com/wonny-labs` and `github.com/zephyrproject-rtos` | the first setup, and `west update` after a pin change |
| `api.github.com` and the GitHub release downloads | `west sdk install`, the Zephyr SDK | the first setup, and after an SDK version change |
| Docker Hub | the `hello-world` check of the quick start only | once |

The SDK install uses GitHub release downloads, and an anonymous request limit of the GitHub API can apply (not
verified for this setup). If the install fails with a rate-limit error, set a GitHub token before the run; both
`scripts/dev-shell.sh` and the VS Code route pass `GH_TOKEN` on to the container when it is set. Read it without
echoing it, and keep it out of files:

```bash
read -rs GH_TOKEN && export GH_TOKEN
```

First run, honestly: it needs several GiB (the image, the workspace folder with Zephyr and the modules, and the
cache volume with the SDK and the virtual environment) and a long time; neither was measured on a developer
machine. For scale only: the CI job that builds this image on a GitHub runner with a fast network took between
about 7 and 15 minutes in total in its recent successful runs on 18 November 2026, and its first step (image,
workspace and SDK) about 3.5 minutes in the run read for this page. That job also runs the tests. A slower network,
a proxy or a laptop will take longer. The memory and CPU guidance is in [What you need](#what-you-need).

Offline: the first run needs the network. Whether later runs work with no network at all is not tested, and a
fully offline setup is not supported.

### Behind a proxy or with a company certificate

Which route passes what, as the files are written (none of it was run behind a proxy):

- The VS Code route passes the proxy variables `http_proxy`, `https_proxy` and `no_proxy` (and the upper-case
  names) from the host environment, as build arguments of the image and as environment of the container, and it
  passes `GH_TOKEN` too. `devcontainer.json` reads them from the environment of the process that starts VS Code,
  so export them in a WSL shell and start `code .` from that shell.
- `scripts/dev-shell.sh` passes only `GH_TOKEN` and your user and group ids. A proxy variable that you export in
  your shell does not reach its container. For this route use Docker's own client configuration: the `proxies`
  section of `~/.docker/config.json` makes the Docker command line add the variables to the build and to the
  container (general knowledge, not tested).
- Inside the container, `.devcontainer/setup.sh` exports both cases of every proxy variable that is set, for pip,
  west, git and curl, and prints their names and never the values.

`proxy.example.com:3128` is a placeholder for your proxy, in a shell from which you start VS Code:

```bash
export http_proxy=http://proxy.example.com:3128
export https_proxy=http://proxy.example.com:3128
export no_proxy=localhost,127.0.0.1
code .
```

Two limits. A proxy on `127.0.0.1` or `localhost` of the host is not reachable from the container. The proxy
values that `containerEnv` passes are visible with `docker inspect`, so a proxy URL with a password is visible to
whoever can run Docker as you.

If the proxy decrypts HTTPS and re-signs it with a company certificate, tools fail with certificate errors (for
example `certificate verify failed` from pip or git: general knowledge). Give the setup script the certificate
authority (CA) certificate as a PEM file, named `.crux-extra-ca.crt`, in the workspace folder, which is the parent
folder of the clone and outside the repository:

```bash
cp /path/to/company-ca.pem ~/work/controller-ws/.crux-extra-ca.crt
```

In the container the file is `/workspaces/ws/.crux-extra-ca.crt`. That folder is mounted in both routes, so this
works for both. Before any pip, git, west or curl step, `setup.sh` installs the file as a system certificate (with
`sudo update-ca-certificates`) and points pip, Python's requests and git at the system bundle. It prints which file it
uses and never the content. If `CRUX_EXTRA_CA_FILE` is set inside the container, `setup.sh` uses the file that it
names instead; neither route sets it for you.

- A `CRUX_EXTRA_CA_FILE` that names a file which does not exist, or a `.crux-extra-ca.crt` that is a dangling
  symbolic link, stops the setup with a message that ends in `which is not a readable file`.
- A file without a `BEGIN CERTIFICATE` line is not PEM, and the setup says so. A DER file (often `.cer`) converts
  with the command that the message prints; use the result as `.crux-extra-ca.crt`:

  ```bash
  openssl x509 -inform der -in company.cer -out company.crt
  ```

The variables that point pip, requests and git at the bundle exist only inside the setup script. A terminal that
you open later in the container does not have them, so pip there needs them again (`PIP_CERT` set to
`/etc/ssl/certs/ca-certificates.crt`) or a `cert` entry in a `pip.conf`; curl, git and apt use the system bundle,
which now holds the certificate. The image build and the pull of the base image happen before the setup and do
not see the file.

Some of it nobody can do for you, because it is on the host and not in the container (all of this is general
knowledge, not checked against these files):

- The Docker daemon pulls the base image and gives the image build its network access, so it needs its own
  proxy setting: the `proxies` key of `/etc/docker/daemon.json`, or a systemd drop-in for the `docker` service. If the
  proxy re-signs HTTPS, the daemon also needs the CA in the distribution's trust store
  (`/usr/local/share/ca-certificates/`, then `sudo update-ca-certificates` and a restart of Docker).
- The Docker command line can add the proxy variables to builds and containers itself, from the `proxies`
  section of `~/.docker/config.json`.

A one-line test that Docker can reach GitHub from a container (general knowledge; it needs the image from Docker
Hub, which the proxy must allow too). A status line such as `HTTP/2 200` is a pass, and a certificate or
time-out error is the problem to fix first:

```bash
docker run --rm curlimages/curl -I https://github.com
```

What to ask IT: whether the proxy inspects TLS (decrypts and re-signs HTTPS), and if it does, how to get the CA
certificate as a PEM file; the proxy address and the `no_proxy` list; and whether the hosts in the table above are
allowed.

### Layout

The dev container mounts the parent folder of the clone as the west workspace, so that `.west/`, `zephyr/`,
`modules/`, `crux-pilot/` and the other projects of the manifest (several GiB together; no size was measured)
are on your Linux file system and survive a rebuild of the image. Use a folder of its own, empty apart from the clone, and name the clone `crux-controller`,
because `west.yml` requires that name. The setup script stops with a message if the clone has another name or if
the parent folder is a home directory, and the VS Code route checks the layout earlier still, with `check-host.sh`. The reason for an empty folder: `west init -l` puts `.west/` there and
`west update` fetches the projects of the manifest next to the clone (`west list` shows each path after the
setup), and the whole folder is bind-mounted, readable and writable, into the container. Anything else in it is
exposed to the container and can clash with those folders.

```bash
mkdir -p ~/work/controller-ws && cd ~/work/controller-ws
git clone -c core.autocrlf=false https://github.com/wonny-labs/crux-controller.git crux-controller
```

Inside the container the workspace is `/workspaces/ws` and the repository is `/workspaces/ws/crux-controller`. The
Zephyr SDK and the virtual environment (cmake, ninja, west, clang-format, PyYAML and the Python requirements of
Zephyr) are in a Docker volume of this workspace folder, mounted at `/opt/crux-cache`. The variables
`ZEPHYR_BASE` and `ZEPHYR_SDK_INSTALL_DIR` are set, as the CI steps set them.

The two entry routes keep separate cache volumes for the same folder. `scripts/dev-shell.sh` names its volume
`crux-controller-dev-cache-<number>`, where the number is a checksum of the workspace folder's path;
`devcontainer.json` names its volume `crux-controller-dev-cache-<id>`, with an id that the Dev Containers extension
chooses. Using both routes on one folder downloads the SDK twice, and moving or renaming the folder starts a new
volume under the script. List the volumes, and remove one that no container uses:

```bash
docker volume ls --filter name=crux-controller-dev-cache
docker volume rm crux-controller-dev-cache-<number>
```

To see which volume the script uses for a folder, compute the number:

```bash
printf '%s' "$HOME/work/controller-ws" | cksum | cut -d' ' -f1
```

### From a copy without Git history

A copy is a zip or any folder without a `.git` folder. It runs the same, with these differences.

- **The folder name and place.** The files go directly in a folder named `crux-controller`, in a parent folder of
  its own, as in the quick start. The copy keeps nothing of the Git history, so a short hash, a pull request number
  or an issue number in the text cannot be opened from it.
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
  [After a pin or SDK change](#after-a-pin-or-sdk-change) if `west.yml` changed.

### With VS Code

Open the clone from a WSL terminal, so that VS Code runs in WSL and finds Docker there:

```bash
cd ~/work/controller-ws/crux-controller
code .
```

Run "Dev Containers: Reopen in Container". Before it creates the container, VS Code runs
`.devcontainer/check-host.sh` on the host side (it needs bash there, which is why the folder is opened from WSL) and
the creation stops if the layout is refused. Start `code .` from a shell where `GH_TOKEN` and the proxy variables
are exported if you need them: this route passes them on. The first start builds the image and runs
`.devcontainer/setup.sh`,
which does `west init -l crux-controller` and `west update` only when the workspace does not exist yet, installs the
Python requirements of Zephyr and runs `west sdk install` for the SDK version of the CI jobs. That takes a long time
and downloads several GiB; watch the creation log. Later starts and rebuilds find all of it already there. If the
creation fails or is interrupted, run `bash .devcontainer/setup.sh` in a terminal of the container: it carries on,
and it runs `west update` again if the first one did not finish. After a change of the pin in `west.yml`, run
`west update` by hand: the setup script does not run it again (see
[After a pin or SDK change](#after-a-pin-or-sdk-change)).

### Without VS Code

```bash
cd ~/work/controller-ws/crux-controller
bash scripts/dev-shell.sh            # a shell in the container, in the repository
bash scripts/dev-shell.sh <command>  # one command, with the repository as working directory
```

The script builds the image, runs `.devcontainer/setup.sh` and then your command, as the same numeric user as
yours, so that the files it writes into the workspace belong to you. It passes `GH_TOKEN` (set it to avoid GitHub's
rate limit for the SDK download) and nothing else of your environment; for a proxy or a company certificate see
[Behind a proxy or with a company certificate](#behind-a-proxy-or-with-a-company-certificate). It does not run
`.devcontainer/check-host.sh`. It stops with a message if Docker is missing, if you run it as root, or if the clone
is not in a folder named `crux-controller`; with the daemon down, you get Docker's own error.

### Commands inside the container

Run them in the container's terminal, or one at a time through `bash scripts/dev-shell.sh <command>` (for a command
that starts in the workspace folder, `bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && <command>'`, as in
the quick start). The scenarios run from the workspace directory, as in the sections below.

```bash
cd /workspaces/ws
# S1 to S5, all scenarios of tests/native_sim, as the S1 job does
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim \
  --inline-logs --clobber-output -O twister-out
# S1 only
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim/s1 \
  --inline-logs --clobber-output -O twister-out-s1
# S2 only
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim/s2 \
  --inline-logs --clobber-output -O twister-out-s2
```

From the repository (`/workspaces/ws/crux-controller`):

```bash
cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=OFF
cmake --build build/host && ctest --test-dir build/host --output-on-failure
python -m unittest discover -s tests/tooling -v
bash scripts/check-format.sh
python scripts/analyze_host.py
cd .. && python crux-controller/scripts/check_boundary.py --repo crux-controller --crux-root crux-pilot
```

The board build of step S1, as the `S1` job runs it (the SDK is already installed):

```bash
cd /workspaces/ws
west build -p always -b 'mimxrt1060_evk@B//qspi' -d crux-controller/build/s1 \
  crux-controller/app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON -DEXTRA_CONF_FILE=conf/s1.conf
```

`CLANG_TIDY` is set in the image, as the static analysis job needs it. The optional S6 steps, the stronger boundary
check and the product include check of the sections below work unchanged from `/workspaces/ws` (the pinned
`crux-pilot` contains the product include check); the container does not switch the Mbed TLS group on by itself. The container does not reach a board: there is no USB or probe
passthrough, and a `native_sim` run is not a board run.

### After a pin or SDK change

A pin change is a new revision of `crux-pilot` in `west.yml`; it arrives with a `git pull` or a newer copy. The
setup script runs `west update` only for a workspace that does not exist yet, so run it yourself, then run the
setup script again: it installs Zephyr's Python requirements again when their files changed (the next call of
`scripts/dev-shell.sh` would run it too).

```bash
bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && west update && cd crux-controller && bash .devcontainer/setup.sh'
```

In the VS Code terminal the same is `cd /workspaces/ws && west update`, then
`bash crux-controller/.devcontainer/setup.sh`. If `west update` stops half-way, run it again.

A change of the Zephyr SDK version (`ZEPHYR_SDK_VERSION` in `.devcontainer/Dockerfile`) needs the image rebuilt:
`scripts/dev-shell.sh` rebuilds it on its next run (Docker's layer cache keeps the unchanged layers), and in VS Code
you run "Dev Containers: Rebuild Container". The setup then installs the new SDK next to the old one in the cache
volume. The old one is not used any more; delete it to free the space, inside the container:

```bash
ls /opt/crux-cache/sdk
rm -rf /opt/crux-cache/sdk/zephyr-sdk-<old version>
```

The setup marks a finished SDK install with the file `.crux-installed` in the SDK folder. An SDK folder without
it, from an interrupted install or from a volume that was made before the marker existed, is removed and installed
again once: several GiB and a long time. That is expected, not an error.

To start from nothing, remove the cache volume (see [Layout](#layout)); delete `.west/`, `zephyr/` and `modules/`
next to the clone only if you also want a new `west init`.

### If the dev container fails

Look the message up in [troubleshooting.md](troubleshooting.md). The cases of this section:

- "Cannot connect to the Docker daemon" (Docker's own message, which `scripts/dev-shell.sh` does not replace): the
  daemon is not running. Start it (`sudo service docker start`) and check it with `docker info`.
- `permission denied` on `/var/run/docker.sock`: you are not in the `docker` group yet, or the session predates the
  change. Restart WSL as in the quick start.
- `env: bash\r: No such file or directory` or an error at `pipefail`: CRLF line ends. See
  [From a copy without Git history](#from-a-copy-without-git-history).
- `Permission denied` on a script: the exec bit is lost. Run `chmod +x scripts/*.sh .devcontainer/*.sh`, or start
  the script as `bash scripts/...`.
- `fatal: not a git repository`, or tooling tests that fail with a Git error: the copy has no `.git`. Run
  `git init`, `git config core.autocrlf false` and `git add -A`.
- "the clone is in a folder named ...": rename the clone folder to `crux-controller`.
- "looks like a home directory" or "is your home directory", from `setup.sh` or from a line that starts
  `check-host:`: the parent of the clone is your home directory (or holds files such as `.bashrc`). Put the clone in
  a parent folder of its own, as in the quick start.
- `setup: failed during <step>; rerun: bash .devcontainer/setup.sh`: a step of the setup failed. The lines above
  name the cause; fix it and run the command again.
- "which is not a readable file" or "is not a PEM certificate": the company CA file. See
  [Behind a proxy or with a company certificate](#behind-a-proxy-or-with-a-company-certificate).
- "is incomplete (it has no install marker); removing it and installing the SDK again": an interrupted install, or an
  old volume. Let it finish; it is once.
- If the creation of the container failed, open a terminal in it (or run `bash scripts/dev-shell.sh`) and run
  `bash .devcontainer/setup.sh` again. It skips what is done and repeats an interrupted `west update`.
- To start from nothing, remove the cache volume of the workspace (`docker volume ls`, then
  `docker volume rm crux-controller-dev-cache-<number>`, with no container using it). The workspace folder next to
  the clone is yours: delete `.west/`, `zephyr/` and `modules/` there only if you want a new `west init`.
- CI is still the reference for a pull request. The native route in the sections below stays valid on Ubuntu 24.04.

## What `native_sim` is

`native_sim` is a simulated Zephyr board. Zephyr builds the application into an ordinary program that runs
on the build host, with emulated devices instead of hardware. It is not a board: no Ethernet PHY, no
microSD card, no watchdog peripheral and no RT1060 is involved. A passing `native_sim` run is not a board
run, and the roadmap says so for every step.

In this repository the `native_sim` scenarios are Zephyr ztest applications under `tests/native_sim`, one
directory per step from S1 to S5, and the S6 scenario in `tests/native_sim_mbed`, which needs the Mbed TLS modules of the Crux manifest and is run by its own CI job. Each one compiles chosen sources of `app/` and `workload/`; none boots the
board image (see the glossary entry for `native_sim`). The scenarios are run through Twister, Zephyr's test
runner, for the platform `native_sim/native/64`.

## What you need first

This is the native route: Ubuntu 24.04 on x86_64, Python 3.12 and no Docker. On Windows use WSL2 with an Ubuntu
24.04 distribution and work in the Linux file system (your home directory), not under `/mnt/c`: the builds are slow
there and file modes can differ. Clone with `git clone -c core.autocrlf=false` if your Git for Windows settings
could reach the clone, because CRLF line ends break the shell scripts (see
[troubleshooting.md](troubleshooting.md)). CI runs on x86_64 only.

- A west workspace. The repository is the west manifest repository: it imports `crux-pilot` at a pinned
  commit, which brings Zephyr and the Zephyr modules, and adds the test-only project `picolibc` for the S2
  scenario (the S5 scenario's `prj.conf` also selects it). `docs/dependencies.md` explains the manifest and
  the pin, and the pin section of [CONTRIBUTING.md](../CONTRIBUTING.md) explains how it moves.
- The Python packages of Zephyr's base, build-test and run-test requirements, `west` 1.4.0, CMake 3.28.4 and
  Ninja 1.11.1 (the versions that the `S1` job installs), in one virtual environment for the workspace.
- A host toolchain and the host packages that the `S1` job installs, plus `python3-venv`, which the job does
  not need because `actions/setup-python` provides Python. Ubuntu 24.04 refuses `pip install` into the system
  Python (PEP 668), so do not skip the virtual environment.
- The Zephyr SDK 1.0.1 with the `arm-zephyr-eabi` toolchain, which the `S1` job installs before it runs
  Twister. It is needed for the board build. Whether a `native_sim` run alone needs it was not tested;
  install it anyway, as CI does.
- Free disk space for Zephyr, its modules and the SDK. Nothing in the repository states a size.

The workspace directory holds the clone, the `.west` directory, `zephyr/`, `modules/` and the virtual
environment. The clone must be named `crux-controller`, because `west.yml` sets `self: path: crux-controller`
and a test pins it. Do not clone into your home directory itself: `west init -l` would put `.west`, `zephyr/`
and `modules/` there.

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  build-essential gcc-multilib ca-certificates device-tree-compiler file gperf git \
  libmagic1 libsdl2-dev pkg-config python3-dev python3-venv wget xz-utils
```

`gcc-multilib` is in the CI list, and CI runs on x86_64 only. The package does not exist on arm64 hosts, and
whether `native_sim/native/64` builds and runs on an arm64 host was not checked.

```bash
mkdir -p ~/crux-ws && cd ~/crux-ws
git clone https://github.com/wonny-labs/crux-controller.git crux-controller
python3 -m venv .venv && . .venv/bin/activate
python -m pip install cmake==3.28.4 ninja==1.11.1 west==1.4.0
west init -l crux-controller
west update
python -m pip install -r zephyr/scripts/requirements-base.txt \
  -r zephyr/scripts/requirements-build-test.txt \
  -r zephyr/scripts/requirements-run-test.txt
```

`west update` fetches Zephyr and the modules from GitHub. It takes a while and uses a lot of disk.

The SDK step. CI runs it from the `zephyr` directory, with the version and the install base taken from the
workflow's variables, and passes the workflow's token. Locally the values are concrete, and the token is not
needed (it only avoids GitHub's rate limit for anonymous requests; add `--personal-access-token` with your own
token if you hit it):

```bash
cd zephyr
west sdk install --version 1.0.1 --install-base "$HOME" --gnu-toolchains arm-zephyr-eabi
cd ..
export ZEPHYR_SDK_INSTALL_DIR="$HOME/zephyr-sdk-1.0.1"
export ZEPHYR_BASE="$PWD/zephyr"
```

The two `export` lines mirror the `env` of the CI steps. Every later command on this page runs from
`~/crux-ws` with the virtual environment active (`. .venv/bin/activate`) and, for Twister, with these two
variables set, unless a section says to use the repository root. Paths such as
`crux-controller/tests/native_sim` are relative to `~/crux-ws`.

## Run the S1 to S5 scenarios

One command runs every scenario, because it points Twister at the whole `tests/native_sim` directory. The
job sets `ZEPHYR_BASE` to `<workspace>/zephyr` for it, as the `export` above does:

```bash
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim \
  --inline-logs --clobber-output -O twister-out
```

To run one scenario, point `-T` at its directory. This is ordinary Twister usage and was not run for this
page (each directory holds one `testcase.yaml`; S3, S4 and S5 build one image per case):

```bash
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim/s1 \
  --inline-logs --clobber-output -O twister-out-s1
```

A pass ends with lines like these. They are quoted from the CI log of the `ci` run for `main` at revision `fa11293` of the public
repository (17 November 2026), where Twister ran the whole directory:

```text
INFO    - 17 of 17 executed test configurations passed (100.00%), 0 built (not run), 0 ...
INFO    - 31 of 31 executed test cases passed (100.00%) on 1 out of total ... platforms ...
```

Counts change when a scenario is added, so read them as an example. The tail of the Twister output is what to
compare, together with the Twister ids in the table below: all 17 must be present and passed, and a count
lower than the table lists means that a scenario did not run.

The S6 scenario is in a sibling directory, `tests/native_sim_mbed`, so that this command never selects it in a
workspace that has no Mbed TLS modules. The default workspace above does not have them: the group
`crux-secure-management` is off in `west.yml`, and the S6 build fails without the modules. The `S6 build` job
switches the group on in its own runner, after `scripts/check_mbed_only.py` has checked that only the Mbed TLS
modules would be fetched. To run S6 locally, repeat those steps (from `ci.yml`) in your workspace, with the
virtual environment active:

```bash
west list --all -f '{name} {active}' > list-default.txt
python crux-controller/scripts/check_mbed_only.py --mode default < list-default.txt
west config --local manifest.group-filter -- +crux-secure-management
west list --all -f '{name} {active}' > list-mbed.txt
python crux-controller/scripts/check_mbed_only.py --mode mbed --baseline list-default.txt < list-mbed.txt
west update
for name in wolfssl wolfssh wolfpsa; do test ! -e "modules/crypto/$name" || echo "unexpected $name"; done
for name in mbedtls tf-psa-crypto; do test -d "modules/crypto/$name" || echo "missing $name"; done
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim_mbed \
  --inline-logs --clobber-output -O twister-out-s6
west config --local -d manifest.group-filter
```

The two `for` loops are CI's check after the fetch (CI exits on a finding; here they print a line): no wolf
project may be on disk and both Mbed modules must be. The checks before `west update` stop the run if the group would fetch anything beyond the Mbed TLS modules. The
fetch adds Mbed TLS and TF-PSA-Crypto, which are distributed as Apache-2.0 OR GPL-2.0-or-later. The last line
puts the workspace back to the default filter; the fetched modules stay on disk. CI also installs the same
Python requirement files after this `west update`, which the first setup already did. A passing run prints
`1 of 1 executed test configurations passed` and `10 of 10 executed test cases passed`, as in the CI log of
the same run.

It is one image with ten ordered cases: the start sequence, the certificate, a TLS 1.3 handshake that the client
verifies, a TLS 1.2-only client that is refused, plain HTTP that is not answered, the page bytes and four requests of
the login path. It shows none of a successful login, handshake time, stack use, key strength (the simulator's
entropy is a fake source) or a browser.

Case 4 connects a control client with a TLS 1.3 suite first, and then a client with only a TLS 1.2 suite, which must fail
with an errno that is neither a refused connection nor a timeout. A refusal on the client side cannot be fully excluded in one
process, because the client and the server share the TLS library, the credentials and the clock. Crux's own check of the
version refusal uses `openssl s_client` against its listener (`docs/https-composition.md` in `crux-pilot`, "Checked on the
wire"), and this case does not replace it.

The scenarios that this command finds, by their ids in the `testcase.yaml` files:

| Step | Twister ids |
|---|---|
| S1 | `controller.s1.native_sim` |
| S2 | `controller.s2.native_sim` |
| S3 | `controller.s3.native_sim.not_ready`, `.mounted_not_bound`, `.mount_failure`, `.roundtrip`, `.bind_failure` |
| S4 | `controller.s4.native_sim.reset_cause`, `.watchdog_unsupported`, `.period_out_of_range` |
| S5 | `controller.s5.native_sim.first_sync`, `.kiss_of_death`, `.late_answer`, `.out_of_range`, `.step_refused_then_resync`, `.correction_and_threshold`, `.stale_after_silence` |

S3, S4 and S5 build one image per case (a build variable such as `S5_CASE`), so one `west twister` run builds
one image per Twister id in the table. What a scenario can and cannot show is stated in its findings note and in the
header of its test source; for example, S4's scenario does not enable the simulated watchdog of the pinned Crux, so it shows no feed
cycle.

The `S1` job runs the command above as one step and its next steps build for the board. Read the checks of
a commit on GitHub for the real outcome.

## Run the host tests

These are plain C tests of the portable core, the S2 exchange and the policy code, built with CMake on the build host.
They need no Zephyr. The `Host tests` job runs them twice, once with the sanitizers off and once on. The
commands, copied from `ci.yml` with the matrix value filled in (`OFF`, then `ON`):

```bash
cmake -S tests/host -B build/host -G Ninja -DWORKLOAD_SANITIZE=OFF
cmake --build build/host
ctest --test-dir build/host --output-on-failure
```

```bash
cmake -S tests/host -B build/host-asan -G Ninja -DWORKLOAD_SANITIZE=ON
cmake --build build/host-asan
ctest --test-dir build/host-asan --output-on-failure
```

Use a different build directory for the second run (for example `build/host-asan`) so that it does not reuse the
first one; CI starts each matrix leg on a fresh runner. These commands run from the repository root
(`~/crux-ws/crux-controller`; the `Host tests` job checks the repository out without a separate path). They need
CMake 3.20 or newer, Ninja and a C compiler; the virtual environment above provides the first two. One host
test, `test_net_client`, asks the system for a free port on `127.0.0.1` for each exchange, so two runs at the
same time do not disturb each other (CTest runs two copies together as `net_client_concurrent`).

The host tests are `tests/host/test_workload.c`, `test_net_client.c`, `test_health_policy.c`,
`test_time_sync_policy.c` and `test_management_policy.c`. Each of the five ends by printing
`<n> checks, <m> failures` and returns a non-zero exit status when `m` is not zero; that is what their
source says. A passing run of the five prints `0 failures` for each. CTest lists six tests, the five and
`net_client_concurrent`, and ends with `100% tests passed, 0 tests failed out of 6`. (The CI log of the run named
above shows `out of 5`: it is from before `net_client_concurrent` was added.)

## Run the tooling tests and the boundary check

These are Python tests of the scripts, workflows, documents and build files, plus the include check.
[CONTRIBUTING.md](../CONTRIBUTING.md) describes them as the checks that run locally. They need only PyYAML. From
the repository root, with the workspace virtual environment active (or a new one, as CONTRIBUTING shows):

```bash
cd ~/crux-ws/crux-controller
python -m pip install pyyaml
python -m unittest discover -s tests/tooling -v
python scripts/check_boundary.py
```

A pass ends the test run with `Ran <n> tests` and `OK`, and the check prints `boundary check passed`.

CI runs a stronger form of the boundary check, against the headers of the pinned `crux-pilot`, and a second
check from `crux-pilot`. From the workspace directory:

```bash
cd ~/crux-ws
python crux-controller/scripts/check_boundary.py --repo crux-controller --crux-root crux-pilot
python crux-pilot/templates/product/check_domain_includes.py --product crux-controller
```

Run from the wrong directory, `check_boundary.py` finds none of its trees and fails with status 2 and a message;
it does not print a pass. [composition-zone.md](composition-zone.md#running-the-check) explains both commands.

## If something fails

CI is the reference. The checks of a commit on GitHub show the same jobs that these commands come from. A
failure that appears only on your machine may be a difference in the host, the toolchain or the workspace.
[troubleshooting.md](troubleshooting.md) lists the failures that have a known cause, by their message, and says
how to read the CI logs; it does not cover every difference. Any change to the boundary lists, the
workflows or the other files that CONTRIBUTING.md treats as reviewed (a reading aid is in
[adding-a-step.md](adding-a-step.md#files-that-need-a-reviewed-change)) is a reviewed change under
[CONTRIBUTING.md](../CONTRIBUTING.md), not a fix for a local failure.

## Why the evidence comes from CI

[CONTRIBUTING.md](../CONTRIBUTING.md) says that CI is the reference for the Zephyr builds and the Twister runs, that
this page gives the CI commands for a local `native_sim` run, that a local result does not replace CI, and that a
change to `app/`, `conf`, overlays or `tests/native_sim` takes its evidence from CI, with the pull request saying so.
It states the rule and gives no reason. What the repository's own files show:

- CI is one environment with pinned versions: `ubuntu-24.04` on x86_64, Python 3.12, CMake 3.28.4, Ninja 1.11.1,
  west 1.4.0, the Zephyr SDK 1.0.1 and a fixed package list (`.github/workflows/ci.yml`). A reviewer can open the
  same job logs for every change, and a number in them (a size, a Twister count, an image hash) was produced under
  the same conditions as the one before it.
- A local environment differs in ways that matter. For example, GCC in CI rejected a comparison between constants of two
  anonymous enums (`-Werror=enum-compare`) that the Apple clang on a developer's machine had accepted
  ([adding-a-step.md](adding-a-step.md)). CI covers only x86_64 Ubuntu, and so does the job that runs the
  [dev container](#dev-container). Apart from the setup steps listed under
  [What has been checked](#what-has-been-checked), arm64 and WSL2 are untested, and nobody has run the dev container
  on WSL2.
- A Zephyr workspace is large. `west update` and the SDK install take a long time and a lot of disk (see
  [What you need first](#what-you-need-first)), so a local build is optional.

GitHub Actions logs expire (the default retention is 90 days), so the run numbers in the Recorded rows of the
findings will stop resolving, and so will the logs behind the roadmap table; that is why the results themselves are
copied into those notes.

So the commands below are a convenience for finding a failure before you push. A local pass does not replace the
CI result in a pull request, and a local failure that CI does not show is a difference in your host to look at, not
a reason to change a check.

## What has been checked

- The venv block (`python3 -m venv`, `pip install` of the pinned tools, `west init -l`)
  was run in a fresh `ubuntu:24.04` container on 18 November 2026 (arm64, Python 3.12.3), after
  `apt-get install python3-venv python3-dev git ca-certificates`. The clone was copied in from a local checkout,
  so the `git clone` command and the full `apt-get` package list were not run. It confirmed that there is no
  `python` command before the virtual environment exists, that `west 1.4.0` installs in it and that
  `west init -l crux-controller` creates `.west` in the workspace directory.
- WSL2 was not tested. Only that arm64 `ubuntu:24.04` container ran those steps.
- Not run for this page: `west update`, the SDK install, Twister, the S6 group steps and the host tests on
  a fresh Linux machine. Their commands are those of the CI jobs with the variables replaced.
- On macOS on 18 November 2026 (Apple clang 17.0.0, CMake 4.4.5, Ninja, Python 3.9 with PyYAML, clang-format 18.1.8
  from pip) these ran and passed in a Git repository: the host tests with the sanitizers off and on (six CTest tests
  each), the tooling tests (983 tests at that revision, 3 skipped), the boundary check, the SPDX check and `scripts/check-format.sh`.
- Also on macOS, one-off runs of the failures that [troubleshooting.md](troubleshooting.md) lists, with the counts
  of that day at that revision (they drift as tests are added). In a copy without `.git`, one tooling test failed and seven stopped
  with a Git error, and `scripts/check_spdx.py` exited with status 2; `scripts/check_boundary.py` passed. After
  `git init` and `git add -A` all of them passed. With CRLF line ends in every text file, 21 tooling tests
  failed (the ones that run the shell scripts), a script started directly failed with
  `env: bash\r: No such file or directory`, and clang-format 18.1.8 itself accepted a CRLF C file. With the exec bits
  removed, five tooling tests failed. Without `.clang-format`, clang-format 18.1.8 reported errors for a file that
  it accepts with it.
- `.devcontainer/check-host.sh` ran on macOS on 18 November 2026 in a scratch folder: it passed a layout of its own,
  refused a wrong folder name, a parent that holds `.bashrc` and a parent that is the home directory (exit status 2),
  and only warned about another entry, not about `.crux-extra-ca.crt`. What `setup.sh` does with a proxy, a
  certificate, a failed step or an old SDK folder, and what `devcontainer.json` passes, is read from the files and was
  not run.
- The dev container (`.devcontainer/`, `scripts/dev-shell.sh`) was not started on a developer machine at all, and
  nobody has used it with WSL2, Docker Engine in WSL2 or the Dev Containers extension. Its files were checked by
  tooling tests (versions against `ci.yml`, the base image digest, no Docker Desktop feature, no write permission or
  upload in the workflow), and the workflow `devcontainer.yml` runs the image and `scripts/dev-shell.sh` on an
  Ubuntu 24.04 x86_64 GitHub runner (the checks listed in the dev container section, including the S1 cross-build).
  The result of that job for the revision that you are reading is in the checks of the commit on GitHub.
- Not tested by anyone, and so written as general knowledge or as the interface of the container files: the proxy
  and company-certificate settings, a run with no network, systemd in `/etc/wsl.conf`, the GitHub rate-limit
  message, and how much disk and time a first run takes on a developer machine.
