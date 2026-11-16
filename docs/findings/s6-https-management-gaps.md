# Finding: what stands between this repository and HTTPS management (groundwork for step S6)

Status: recorded as groundwork. S6 is not a step yet: there is no Kconfig option, no configuration fragment, no
build, no budget job and no CI job for it, and the README step table has no row for it. This note records the
gaps that were found by reading, and the groundwork files that this change adds. Those files are not compiled into
any firmware image.

No Zephyr build, Twister run, CI run or board run stands behind any statement in this note.

Every statement carries one of three labels:

- **Verified**: read in a named file at a named revision. The file and the revision are in the same row.
- **Inferred**: a reading of the sources, or a plan, that no file states and nothing has run.
- **Not verified**: a question that this note cannot answer.

The revisions are `crux-pilot` at `8e3737d25d048b14a00c01da00494f58a62958c6`, the commit that `west.yml` pins, and
at `dfd3ad7d4380b06a47d8c8b5b9f0ce46fbba0576`, the pin before it (a statement that names the earlier one says so).
Files of this repository are read at its `main` revision `8b9c702`. In the rows below "8e3737d2", "dfd3ad7d" and
"8b9c702" are the short forms of these.

## The question

Can this repository compose Crux's HTTPS management (the Access accounts and sessions, the web server on the Mbed TLS
profile, the status service and the configuration save) with public headers and public targets only, first as a
`native_sim` scenario? The three gaps below are the ones that the reading found. The names are used only inside this
note.

| Gap | In words | State at 8e3737d2 |
|---|---|---|
| Locks gap | Access refuses an Mbed image that has no TF-PSA-Crypto locks, and a product had no public way to get them | open at the previous pin, addressed at 8e3737d2 by a Kconfig symbol (below) |
| First-account gap | the first account can only be created through Crux's serial console, and a product could not compose that console | a public header exists at 8e3737d2, and the boundary check of this repository does not yet allow it |
| Route-sources gap | the web route sources of the Crux services have to be named by the product's own CMake | unproven from outside the Crux repository |

## Gap 1: the locks

| Statement | Label | Source |
|---|---|---|
| `CONFIG_CRUX_PSA_THREADING` is defined. It depends on `CRUX_PILOT_MODULE && MULTITHREADING && PSA_CRYPTO_PROVIDER_MBEDTLS`, it has no `default` line, and its help says "Experimental tier", "Off by default" and that it builds the core's locks on `k_mutex` and `k_condvar` | **Verified** | `zephyr/Kconfig` at 8e3737d2, `config CRUX_PSA_THREADING` |
| The help says `CONFIG_CRUX_ACCESS` refuses an Mbed profile image without these locks, or without a lock provider of the product's own | **Verified** | `zephyr/Kconfig` at 8e3737d2 |
| The configuration step stops with an error that names `CONFIG_CRUX_PSA_THREADING` when `CONFIG_CRUX_ACCESS` has no locks | **Verified** | `zephyr/CMakeLists.txt` at 8e3737d2 |
| At the previous pin the same step stopped with a message that pointed only at a test configuration file, and the symbol is absent from its Kconfig | **Verified** | `zephyr/CMakeLists.txt` and `zephyr/Kconfig` at dfd3ad7d |
| So the locks gap was open at the previous pin and is addressed at 8e3737d2: a product sets `CONFIG_CRUX_PSA_THREADING=y`. That a product image can use it is not shown | **Inferred** | the rows above |
| The help says no case exercises a concurrent use of the core, so the locks show no absence of a race | **Verified** | `zephyr/Kconfig` at 8e3737d2 |
| The symbol is Experimental and off by default, so a later Crux revision may change it, and a change is listed in the Crux release notes | **Verified** | `zephyr/Kconfig` at 8e3737d2 |

What follows for this repository: an S6 configuration has to set the symbol, and a resolved-configuration check has
to assert it. Neither exists yet.

## Gap 2: the first account over serial

| Statement | Label | Source |
|---|---|---|
| `crux_access_provision_first_account` is declared in the Access adapter header, whose comment says projects must not include it | **Verified** | `components/access/adapter/crux_access_adapter.h` at 8e3737d2 |
| `<crux/cli_zephyr.h>` is present. It declares `crux_cli_serial_start()`, which takes a `setup_role` that must exist in the Access policy and hold `access.manage`, and the console creates the first account when a person types `!setup` at the login prompt | **Verified** | `components/cli/ports/zephyr/include/crux/cli_zephyr.h` at 8e3737d2 |
| The header is absent at the previous pin | **Verified** | no `components/cli/ports/zephyr/include/crux/cli_zephyr.h` in the tree of `crux-pilot` at dfd3ad7d, searched by name |
| `CONFIG_CRUX_CLI_CONSOLE` (Experimental, off by default) depends on `CRUX_CLI && CRUX_ACCESS`, and the console owns the UART that the devicetree alias `crux-serial0` names, so no Zephyr console, log backend or shell may use that UART | **Verified** | `zephyr/Kconfig` at 8e3737d2 and the header above |
| The composition zone of this repository may include only `<crux/file_zephyr.h>` and `<crux/web_zephyr.h>` among the composition interfaces, so an include of `<crux/cli_zephyr.h>` fails the boundary check today | **Verified** | `scripts/check_boundary.py` at 8b9c702, `COMPOSITION_CRUX_HEADERS` |
| Allowing it is a reviewed change of `scripts/check_boundary.py`, `tests/tooling/test_boundary.py` and `docs/composition-zone.md` together, and it must say why the public interface is not enough | **Verified** | `CONTRIBUTING.md` at 8b9c702, "The boundary" |
| A read-only account can only be made by a signed-in administrator, because creating an account needs `access.manage` | **Verified** | `components/access/include/crux/access.h` at 8e3737d2 |
| A product command that creates the read-only account would be the product's own code, after the console exists | **Inferred** | `components/cli/include/crux/cli.h` at 8e3737d2 offers the command tables; no product command was read or written |

What follows: the first account needs the console, and the console needs an allow-list change that is not part of
this change. This change adds no `crux/cli_zephyr.h` include and does not touch `scripts/check_boundary.py`.

## Gap 3: the route sources from outside the Crux repository

| Statement | Label | Source |
|---|---|---|
| `crux_web_routes()` gives Crux's own route sources their private include directories as per-source properties, so a product's own sources do not see them | **Verified** | `cmake/CruxWebRoutes.cmake` at 8e3737d2 |
| The guide for a product says that none of its snippets was compiled or run as written, and that a product's own paths and a product build were not tried | **Verified** | `docs/management-in-a-product.md` at 8e3737d2, "Which snippets were compiled or run" |
| Crux's own consumer fixture still adds private directories of the web component to its target by include path, and says a product outside the repository cannot do that and keep to the include rule | **Verified** | `tests/native/management_module/CMakeLists.txt` at 8e3737d2, header comment and `target_include_directories` |
| So whether the route sources of the session and management services compile from this repository, under its own warning flags, is unproven | **Inferred** | the three rows above |

The route-sources gap is unproven. The first native_sim build of the composition will prove or disprove it, and that
build is a later change. If it fails, there is no private include workaround: this repository will not add a Crux
private directory to an include path or copy Crux code. The failure is recorded here as a platform gap, and the owner
decides what happens next. A request to `crux-pilot` is filed only with the owner's approval.

## Choices for the scenario

| Statement | Label | Source |
|---|---|---|
| The web adapter has a build assertion against `CONFIG_EXTERNAL_LIBC`, because the server's wildcard matching needs Zephyr's own `fnmatch`; `native_sim` selects the external libc by default | **Verified** | `components/web/ports/zephyr/web_http_server.c` at 8e3737d2, and `docs/web-contract.md` at 8e3737d2 |
| The earlier scenarios of this repository pick `CONFIG_PICOLIBC=y`, for a different reason (the native libc would bypass Zephyr's socket providers), and the picolibc module is in the manifest | **Verified** | `tests/native_sim/s2/prj.conf` and `west.yml` at 8b9c702 |
| The S6 scenario should try picolibc first, because the target uses picolibc, and fall back to the minimal libc (the choice that Crux's own web tests make) only if the server's start refuses picolibc's `fnmatch`; which one passes, if either, is not known | **Inferred** | the rows above |
| In Crux's manifest `mbedtls`, `tf-psa-crypto`, `wolfssl`, `wolfssh` and `wolfpsa` are all in the optional group `crux-secure-management`, which is off by default | **Verified** | `west.yml` at 8e3737d2 |
| This repository's manifest blocks the three wolf projects by name and enables no optional group, `scripts/check_mbed_only.py` checks the resolved project list in both modes, and the existing `West pins` job already switches the group on in its runner with `west config --local` and off again | **Verified** | `west.yml`, `scripts/check_mbed_only.py` and `.github/workflows/ci.yml` (the step "Mbed-only check, group on") at 8b9c702 |
| The Mbed group is therefore to be switched on in the runner of the S6 and budget jobs only, with `check_mbed_only.py` run before the fetch, and never in `west.yml`, because the contribution guide says the optional groups stay off | **Inferred** (a plan), from the rows above and `CONTRIBUTING.md` at 8b9c702 | changing `.github/workflows/ci.yml`, `.github/workflows/budget.yml` and `CONTRIBUTING.md` is a later, separately reviewed change |

## Thread and Sync

| Statement | Label | Source |
|---|---|---|
| `CONFIG_CRUX_ACCESS` selects `CRUX_THREAD` and `CRUX_SYNC`, and so do `CRUX_WEB_SESSION` and `CRUX_WEB_MANAGEMENT` | **Verified** | `zephyr/Kconfig` at 8e3737d2 |
| `app/Kconfig` says the product uses no Crux Thread, Sync or Queue provider, so none is selected for it, and `docs/architecture.md` says Thread, Sync, Queue and Serial are not used. Both are true for steps S1 to S5 only | **Verified** | `app/Kconfig` and `docs/architecture.md` at 8b9c702 |
| The boundary check denies `<crux/thread.h>`, `<crux/sync.h>`, `<crux/queue.h>` and `<crux/serial.h>` in `app/src` and `app/os` | **Verified** | `scripts/check_boundary.py` at 8b9c702, `FROZEN_CRUX_HEADERS` |
| Once S6 exists, the resolved configuration will have `CONFIG_CRUX_THREAD=y` and `CONFIG_CRUX_SYNC=y`. The right wording then is that the Crux services select them for themselves and product code includes none | **Inferred** | the rows above |

The two documents must change in the change that adds the step, not before. The existing S1 to S5 jobs assert the
absence of those symbols in their own configurations, and they stay as they are.

## The limit of one silent client

| Statement | Label | Source |
|---|---|---|
| With `CONFIG_CRUX_WEB` on, Crux declares `NET_SOCKETS_TLS_CONNECT_TIMEOUT` as 2,000 ms for the whole image, and says the value is a proposal from `native_sim` until RT1060 evidence | **Verified** | `docs/https-composition.md` at 8e3737d2, "Stalled handshake" |
| The handshake runs on the one server thread, so one silent client stops every other client for up to that time, and a client can repeat it. Crux calls this a bound and not a defence | **Verified** | `docs/https-composition.md` at 8e3737d2 |
| The same option also bounds every outbound TLS connect in the image | **Verified** | `docs/https-composition.md` at 8e3737d2 |
| Whether 2,000 ms suits the target, and what a loaded control task sees while a client stalls the server, is not known here | **Not verified** | no run |

## What is not verified

Nothing in this note or in the groundwork files shows any of the following, and no statement above should be read as
if it did:

- login, sessions and request forgery protection working, and roles at run time (the policy is data that a host test
  reads; Crux Access has not run with it);
- the first account, the serial console and the read-only account;
- the page in a browser, and whether a browser accepts the generated self-signed certificate;
- any board, Ethernet, the clock source and the true random source;
- timing: handshake time, password hashing time and the effect of management on the control workload;
- stack use of the web and session workers, and heap use of the TLS stack;
- entropy: the native_sim entropy source is a fake one, so a simulator run would say nothing about key strength
  (`tests/native/management_module/CMakeLists.txt` at 8e3737d2 restricts its fixture to native_sim for that reason);
- the fetch and build of the Mbed group in a workflow, the picolibc `fnmatch` behaviour, and whether the route sources
  compile from this repository.

## What this change adds

- A row `S6` in `budgets/limits.json`, equal to the `S5` row: the placeholder of 25 percent free in every region,
  declared before any measurement. No workflow uses it yet.
- `app/src/management_policy.[ch]`: a strict dotted IPv4 text check for the bind address, the two roles
  (administrator with `access.manage`, `status.read` and `config.save`; read-only with `status.read`), the session
  limits (15 minutes idle, 8 hours absolute) and a check of the version text. The permission names were read in
  `crux/access.h`, `crux/management_status.h` and `crux/config_service.h` at 8e3737d2. The password rule is left to
  Crux's reference rule.
- `app/src/management_port.h`: the product-owned port, with ISO C only and no Crux, Zephyr or composition header.
- Host tests of the policy and the validator, and tooling tests that pin the facts of this note that can be checked
  as text.

It adds no CMake source, Kconfig symbol, configuration fragment, overlay or workflow, so no firmware image changes.
