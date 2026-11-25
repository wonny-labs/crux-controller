# Dev Container reference

This page describes the Dev Container in detail: what it is and what CI runs in it, what it needs from the host,
the hosts it contacts, proxies and certificates, the folder layout, the VS Code and command-line routes, the
commands that run in it, and what to do after a pin or SDK change. To set it up, follow
[Getting started](getting-started.md#set-up-the-dev-container); what has been run on the board route is listed on
the [board page](board-bring-up.md#board-route-for-the-rt1060-evkb-rev-b).

## What the container is

CI runs it: the workflow `devcontainer.yml` builds the same image on an Ubuntu 24.04 x86_64 runner,
runs `scripts/dev-shell.sh` and, inside the container, the tooling tests, the format check, the static analysis, the host tests (sanitizers off and on), both boundary
checks, the `native_sim` scenarios of [the `workload` to `sntp` section](native-setup.md#run-the-workload-to-sntp-scenarios) and the RT1060-EVKB
cross-build of `workload` (with the baseline gate required) with its output and configuration checks, using the
Zephyr SDK that `setup.sh` installs. That is a run of the image and the scripts, not of VS Code or of WSL2 (see the
[setup checks record](history/setup-checks.md)). If a step fails for you, look the message up in
[troubleshooting.md](troubleshooting.md), and otherwise open an issue with the output.

The container is not the CI runner. It uses Ubuntu's Python 3.12 (not pinned to a patch release) where CI uses
`actions/setup-python`, a devcontainers base image where CI uses the runner image, pip's cmake and ninja where the
`Host tests` job uses the runner's, `clang-tidy-18` installed without its recommended packages, the extra packages
`python3-venv` (for the virtual environment), `curl` and `sudo` (for the setup script), and PyYAML pinned. The
Zephyr requirement files are not pinned, as in CI.

The files are `.devcontainer/devcontainer.json` (for VS Code), `.devcontainer/Dockerfile` (the image, with the base
image pinned by digest), `.devcontainer/requirements-tools.txt` (the pinned Python tools),
`scripts/bootstrap.sh` (the one entry that VS Code runs after the container is created; `CRUX_BOOTSTRAP=host`, `zephyr` or
`all`, the default), `.devcontainer/setup.sh` (the workspace and SDK setup it calls), `.devcontainer/check-host.sh`
(the check of the folder on the host) and `scripts/dev-shell.sh` (the same without VS Code). The versions follow `ci.yml`, and a tooling test
compares them. `.gitattributes` pins LF line ends, so that a clone checks the scripts out with LF on every platform.
For C code, VS Code uses the clangd extension with the image's `clangd-18`, which reads the `compile_commands.json`
of the last board build of the task **Board: Build** (set in `.clangd`), and `setup.sh` writes the bash Tab
completion of `west` on every run. The C/C++ extension (`ms-vscode.cpptools`) and `gdb` are installed for
debugging, for example of the host tests through CMake Tools; `C_Cpp.intelliSenseEngine` is `disabled` in
`devcontainer.json`, the setting that the clangd extension asks for when both are installed, so clangd stays the
language server.

**What has been run** for the editor tools: the tooling tests, which read these files.

Not run: an image with `gdb` and `ms-vscode.cpptools`, a debug session of the host tests, the VS Code tasks and
profiles ([board route](board-bring-up.md#vs-code-tasks-and-debug-profiles)).

`.devcontainer/check-host.sh` checks the folder layout on the host before the container is created. VS Code runs it
as the `initializeCommand` of `devcontainer.json`, on the host side, so it needs bash there: open the folder from
WSL, as [With VS Code](#with-vs-code) says. It refuses, with a line that starts `check-host:` and exit status 2, a
clone that is not in a folder named `crux-controller`, a parent folder that is your home directory or `/`, and a
parent folder that holds `.ssh`, `.gnupg`, `.bashrc`, `.profile` or `.gitconfig`. It only warns when the parent
folder holds other entries, because the container sees them (`.crux-extra-ca.crt` is not one of them).
`scripts/dev-shell.sh` does not run it. `setup.sh` has a smaller check of its own in the container: the folder name
and the markers of a home directory.

`.devcontainer/setup.sh` prints to the standard error stream, also what pip, west and git print, so that a command
which `scripts/dev-shell.sh` runs after it keeps a clean standard output.
It prints a `setup:` line for each piece of work that a step does, almost nothing for a step that is already done (the west workspace step reminds you to run `west update` after the pin in `west.yml` moves), and when a step fails it prints `setup: failed during <step>; rerun: bash .devcontainer/setup.sh`.
It does again what an
interrupt left half done: a virtual environment without pip, a `.west` folder from an interrupted `west init`, and
an SDK folder without its install marker.

## What you need

1. WSL2 with a Linux distribution, and your files in its Linux file system (not under `/mnt/c`: the builds are
   slow there and file modes can differ).
2. Docker Engine inside the distribution, installed as step 1 of [Set up the Dev Container](getting-started.md#set-up-the-dev-container) says, and a running
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
5. In VS Code on Windows, turn off **Dev › Containers: Mount Wayland Socket** in your user settings (it cannot be set in the repository).
   The container needs no display, and with the setting on it can fail to start with `bind source path does not exist: /run/user/1000/wayland-0`.
   After turning it off, run **Dev Containers: Rebuild Container** once.

Nothing in the files uses `host.docker.internal`, the Docker socket or a mount of your home directory.

## Network and prerequisites

The setup contacts these hosts. Only `mcr.microsoft.com` (the `FROM` line of `.devcontainer/Dockerfile`),
`www.segger.com` (`.devcontainer/jlink/install-jlink.sh`) and the `github.com` remotes of `west.yml` are read from
the files. The other names are the usual ones and were not looked
up, and Zephyr's own manifest, which the pinned `crux-pilot` imports, was not read for this page: it may name
more hosts. A firewall or proxy must allow them.

| Host | What for | When |
|---|---|---|
| `mcr.microsoft.com` | the base image named in the Dockerfile, pulled by the Docker daemon | the first image build, and when the digest changes |
| the Ubuntu package mirrors that the base image is set up with | `apt-get install` of the packages in the Dockerfile | the image build |
| PyPI (`pypi.org` and its file host) | `pip install` of `.devcontainer/requirements-tools.txt` and of the Zephyr requirement files | the first setup, and when a requirements file changes |
| `github.com` | `west update`: this repository's manifest projects from `github.com/wonny-labs` and `github.com/zephyrproject-rtos` | the first setup, and `west update` after a pin change |
| `api.github.com` and the GitHub release downloads | `west sdk install`, the Zephyr SDK | the first setup, and after an SDK version change |
| `www.segger.com` | the J-Link version pinned in the Dockerfile, downloaded by `.devcontainer/jlink/install-jlink.sh` unless a placed package or `CRUX_JLINK_URL` overrides it, or `CRUX_JLINK=0` skips it. The `devcontainer` CI job sets `CRUX_JLINK=0`, and any other automated image build should do the same, so that it never downloads from SEGGER ([board route](board-bring-up.md#3-open-the-dev-container-with-the-probe)) | the image build |
| Docker Hub | the `hello-world` check of [Set up the Dev Container](getting-started.md#set-up-the-dev-container) and the `curlimages/curl` test of the proxy section | once each |

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
about 7 and 15 minutes in total, and its first step (image, workspace and SDK) about 3.5 minutes, in the runs of
18 November 2026 that the [setup checks record](history/setup-checks.md) describes. That job also runs the tests. A slower network,
a proxy or a laptop will take longer. The memory and CPU guidance is in [What you need](#what-you-need).

Offline: the first run needs the network. Whether later runs work with no network at all is not tested, and a
fully offline setup is not supported.

## Behind a proxy or with a company certificate

Which route passes what, as the files are written (none of it was run behind a proxy):

- The VS Code route passes the proxy variables `http_proxy`, `https_proxy` and `no_proxy` (and the upper-case
  names) from the host environment, as build arguments of the image and as environment of the container, and it
  passes `GH_TOKEN` too. `devcontainer.json` reads them from the environment of the process that starts VS Code
  (general knowledge), so export them in a WSL shell and start `code .` from that shell. A VS Code server that
  already runs in WSL keeps its old environment: close all VS Code windows of that distribution, or run
  `wsl --shutdown`, first.
- `scripts/dev-shell.sh` passes `GH_TOKEN` and `CI` when they are set, your user and group ids and any `CRUX_JLINK*` variable that is set (as build arguments, by name), and no proxy variable.
  A proxy variable that you export in your shell does not reach its container.
  For this route use Docker's own client configuration: the `proxies` section of `~/.docker/config.json` makes the Docker command line add the variables to the build and to the container (general knowledge, not tested).
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

If the proxy decrypts HTTPS and re-signs it with a certificate of your organisation, downloads in the image build
or in the container fail with a certificate error, for example
`curl: (60) SSL certificate problem: unable to get local issuer certificate`, `certificate verify failed`, or the
same from pip, Git or west. The image build
and the setup then need the root certificate authority (CA) certificate of your organisation. There are two places
for it; each developer places their own file in one of them, and neither is in the repository.

**In the image (preferred).** Place the file in `.devcontainer/certs/` of your clone as a `.crt`, `.pem` or `.cer`
file, then run **Dev Containers: Rebuild Container**, or `bash scripts/dev-shell.sh` again, which builds the image
again. Git ignores every file there except `README.md` and `.gitkeep`, so the certificate stays on your machine.
The first RUN step of the Dockerfile, `.devcontainer/install-org-certs.sh`, runs before `apt-get`, the J-Link download
and every later download. It installs each such file as a `.crt` system certificate: a PEM file (one with a
`BEGIN CERTIFICATE` line) as it is, without Windows line ends, and a DER file converted to PEM with
`openssl x509 -inform der`. A PEM file with several certificates is installed as one file per certificate. A file
that holds a private key (whatever its ending), a file that is neither PEM nor DER, a PEM file with a block other
than a certificate and a certificate that does not parse stop the build with an `error:` line that names the file,
and then no certificate is installed; a file with another ending is skipped with a `certs: skipping` line. An empty
folder installs nothing. The step reads the folder through a BuildKit bind mount, so the image keeps the installed
certificates and no other file of the folder; VS Code and Docker Engine 23 and later build with BuildKit by
default, and a builder without BuildKit stops at that step. The image also sets `REQUESTS_CA_BUNDLE`,
`CURL_CA_BUNDLE`, `SSL_CERT_FILE`, `GIT_SSL_CAINFO`, `PIP_CERT` and `NODE_EXTRA_CA_CERTS` to the system bundle,
`/etc/ssl/certs/ca-certificates.crt`, for the build and for every terminal of the container, so pip, Python's
requests, curl, git and Node.js use it. With an empty folder that bundle holds only the CAs of the distribution.
The pull of the base image happens on the host, before any of this, and needs the certificate there (see
below).

**In the workspace folder (no rebuild).** The setup script also takes the CA certificate as a PEM file, named
`.crux-extra-ca.crt`, in the workspace folder, which is the parent folder of the clone and outside the repository:

```bash
cp /path/to/company-ca.pem ~/work/crux-controller-workspace/.crux-extra-ca.crt
```

In the container the file is `/workspaces/ws/.crux-extra-ca.crt`. That folder is mounted in both routes, so this
works for both. Before any pip, git, west or curl step, `setup.sh` installs the file as a system certificate (with
`sudo update-ca-certificates`) and points pip, Python's requests and git at the system bundle. It prints which file it
uses and never the content. If `CRUX_EXTRA_CA_FILE` is set inside the container, `setup.sh` uses the file that it
names instead; neither route sets it for you. This route comes after the image build, so the J-Link download of the
build does not see the file; use the folder above for that.

- A `CRUX_EXTRA_CA_FILE` that names a file which does not exist, or a `.crux-extra-ca.crt` that is a dangling
  symbolic link, stops the setup with a message that ends in `which is not a readable file`.
- A file without a `BEGIN CERTIFICATE` line is not PEM, and the setup says so. A DER file (often `.cer`) converts
  with the command that the message prints; use the result as `.crux-extra-ca.crt`:

  ```bash
  openssl x509 -inform der -in company.cer -out company.crt
  ```

The image sets the bundle variables for every terminal (see the folder route above), so the certificate that the
setup installs reaches pip, requests and git there too.

Some of it nobody can do for you, because it is on the host and not in the container (all of this is general
knowledge, not checked against these files):

- The Docker daemon needs its own proxy setting for its own pulls, such as the base image: the `proxies` key of
  `/etc/docker/daemon.json`, or a systemd drop-in for the `docker` service. That setting covers the daemon's pulls,
  not the `apt-get` steps of the image build: those run in a container and get the proxy from build arguments (the
  VS Code route passes them) or from the client configuration in the next item. A user of `scripts/dev-shell.sh`
  needs both, so do not stop after `daemon.json`. If the proxy re-signs HTTPS, the daemon also needs the CA in the distribution's trust store
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

### Get the root certificate

Ask IT for the root CA certificate as a PEM or DER file. To check a file before you rebuild, in the folder that
holds it (a DER file needs `-inform der`):

```bash
openssl x509 -noout -issuer -subject -in company.crt
```

## Layout

The Dev Container mounts the parent folder of the clone as the west workspace, so that `.west/`, `zephyr/`,
`modules/`, `crux-pilot/` and the other projects of the manifest (several GiB together; no size was measured)
are on your Linux file system and survive a rebuild of the image. Use a folder of its own, empty apart from the clone, and name the clone `crux-controller`,
because `west.yml` requires that name. The setup script stops with a message if the clone has another name or if
the parent folder is a home directory, and the VS Code route checks the layout earlier still, with `check-host.sh`. The reason for an empty folder: `west init -l` puts `.west/` there and
`west update` fetches the projects of the manifest next to the clone (`west list` shows each path after the
setup), and the whole folder is bind-mounted, readable and writable, into the container. Anything else in it is
exposed to the container and can clash with those folders.

```bash
mkdir -p ~/work/crux-controller-workspace && cd ~/work/crux-controller-workspace
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
printf '%s' "$HOME/work/crux-controller-workspace" | cksum | cut -d' ' -f1
```

## With VS Code

Open the clone from a WSL terminal, so that VS Code runs in WSL and finds Docker there:

```bash
cd ~/work/crux-controller-workspace/crux-controller
code .
```

Run "Dev Containers: Reopen in Container". Before it creates the container, VS Code runs
`.devcontainer/check-host.sh` on the host side (it needs bash there, which is why the folder is opened from WSL) and
the creation stops if the layout is refused. Start `code .` from a shell where `GH_TOKEN` and the proxy variables
are exported if you need them: this route passes them on. The first start builds the image and runs
`.devcontainer/setup.sh`,
which does `west init -l crux-controller` and `west update` only when the workspace does not exist yet, installs the
Python requirements of Zephyr and runs `west sdk install` for the SDK version of the CI jobs. That takes a long time
and downloads several GiB; watch the creation log.
The setup runs `west update --narrow -o=--progress`, which fetches only the pinned revisions and prints git's fetch progress, so a long fetch does not look stuck (with `CI` set, it leaves out `-o=--progress`, which would only fill the job log).
Later starts and rebuilds find all of it already there.
If the creation fails or is interrupted, run `bash .devcontainer/setup.sh` in a terminal of the container: it carries on,
and it runs `west update` again if the first one did not finish. After a change of the pin in `west.yml`, run
`west update` by hand: the setup script does not run it again (see
[After a pin or SDK change](#after-a-pin-or-sdk-change)).

## Without VS Code

```bash
cd ~/work/crux-controller-workspace/crux-controller
bash scripts/dev-shell.sh            # a shell in the container, in the repository
bash scripts/dev-shell.sh <command>  # one command, with the repository as working directory
```

The script builds the image, runs `scripts/bootstrap.sh zephyr` (which runs `.devcontainer/setup.sh`) and then your
command, as the same numeric user as
yours, so that the files it writes into the workspace belong to you. It passes `GH_TOKEN` (set it to avoid GitHub's
rate limit for the SDK download) and the `CRUX_JLINK*` build arguments that are set (a hosted J-Link package, see
[the board route](board-bring-up.md#3-open-the-dev-container-with-the-probe)), mounts the USB bus of the host
when `/dev/bus/usb` exists (`CRUX_BOARD_USB_DIR` names another folder), and nothing else of your environment; for a proxy or a company certificate see
[Behind a proxy or with a company certificate](#behind-a-proxy-or-with-a-company-certificate). It does not run
`.devcontainer/check-host.sh`. It stops with a message if Docker is missing, if you run it as root, or if the clone
is not in a folder named `crux-controller`; with the daemon down, you get Docker's own error.

## Commands inside the container

Run them in the container's terminal, or one at a time through `bash scripts/dev-shell.sh <command>` (for a command
that starts in the workspace folder, `bash scripts/dev-shell.sh bash -c 'cd /workspaces/ws && <command>'`, as in
the [Tutorial](tutorial.md)). The scenarios run from the workspace directory, as in [Set up without the Dev Container](native-setup.md).

```bash
cd /workspaces/ws
# workload to sntp, all scenarios of tests/native_sim, as the workload job does
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim \
  --inline-logs --clobber-output -O twister-out
# workload only
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim/workload \
  --inline-logs --clobber-output -O twister-out-workload
# net only
west twister -p native_sim/native/64 -T crux-controller/tests/native_sim/net \
  --inline-logs --clobber-output -O twister-out-net
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

The board build of `workload`, as the `workload` job runs it (the SDK is already installed):

```bash
cd /workspaces/ws
west build -p always -b 'mimxrt1060_evk@B//qspi' -d crux-controller/build/workload \
  crux-controller/app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON -DEXTRA_CONF_FILE=conf/workload.conf
```

`CLANG_TIDY` is set in the image, as the static analysis job needs it. The optional `management` job steps, the stronger boundary
check and the product include check of [Set up without the Dev Container](native-setup.md) work unchanged from `/workspaces/ws` (the pinned
`crux-pilot` contains the product include check); the container does not switch the Mbed TLS group on by itself. The container mounts the USB bus of the host and can have the J-Link software
(`.devcontainer/jlink/`), so a probe can be reached from it after the host steps of
[board-bring-up.md](board-bring-up.md), whose run list says what has been run; a `native_sim` run is not a board run.

The J-Link software that the build installs, downloaded or placed in `.devcontainer/jlink/packages/`, goes into the
image you build on your own machine, and so the licensed SEGGER software stays in that local image layer: do not
push or share the image. Git ignores a placed package file.

## After a pin or SDK change

A pin change is a new revision of `crux-pilot` in `west.yml`; it arrives with a `git pull`. The
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

## If the Dev Container fails

Look the message up in [troubleshooting.md](troubleshooting.md#setup-and-the-dev-container). It has every message of
`scripts/dev-shell.sh`, `.devcontainer/setup.sh` and `.devcontainer/check-host.sh`, with the cause and the fix. After a
fix, run the same command again: the setup skips what is done. To start from nothing, remove the cache volume (see
[Layout](#layout)). CI is still the reference for a pull request, and the [route without the Dev Container](native-setup.md) stays valid on
Ubuntu 24.04.
