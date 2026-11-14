# Finding: the management features have no public product composition

Status: recorded after Stage 1 step S3. Filing it in `crux-pilot` needs the owner's approval and has not happened. No issue tracks it yet.

## Finding

Crux has code for HTTPS web management, a command line over serial, the command line over SSH, SFTP, accounts and sessions (Access), the credential store and the management services. At `crux-pilot` revision `a72032b2f29c8c4579de8de07a43b40f19bb9516` it has no public product composition for them. A product that keeps to public headers and public targets, which is what this repository's boundary check enforces, cannot compose them. Nothing described here has run on a board.

## Evidence

All read in `wonny-labs/crux-pilot` at `a72032b2f29c8c4579de8de07a43b40f19bb9516`. The pinned commit of this repository, `37c92b18`, is 61 commits earlier and was not re-read for this finding.

- **The module builds two of them.** Of the management components, `zephyr/CMakeLists.txt` adds `components/cli/ports/zephyr` under `CONFIG_CRUX_CLI` and `components/web/ports/zephyr` under `CONFIG_CRUX_WEB`. It adds nothing for Access, the credential store, the services or SSH. `docs/component-readiness.md` says the CLI directory is compile evidence that links none of its code into an image.
- **Start functions are in private headers.** `crux_web_start` is declared in `components/web/adapter/crux_web_adapter.h`, and `crux_tls_certificate_start` in `components/tls_certificate/adapter/crux_tls_certificate_adapter.h`. Neither is under `include/crux/`. The web adapter's include directory is offered only through the INTERFACE target `crux_web_adapter`, which has no `crux::` alias and is marked in the source "only for a composition".
- **SSH is private.** `components/ssh/CMakeLists.txt` begins "Private to Crux: no public header and no `crux::` target", and `zephyr/CMakeLists.txt` only checks the SSH settings at configuration and builds nothing for it.
- **Access has ports a composition must list.** `docs/architecture.md` says `crux::access` links no port provider, "so an image links only through a composition. No product composition exists". `docs/component-readiness.md` says Access has no Kconfig symbol and no composition under `zephyr/`.
- **The complete composition is a test.** `tests/native/management_composition/composition/composition.cmake` stops with an error unless the board is `native_sim`, because its entropy is test-only and its certificate and key are public. `composition/ssh.cmake` does the same for the SSH host key. The RT1060-EVKB image of the integrated stack, `tests/zephyr/management_rt1060_compile`, is a compile vehicle: its `main.c` states that it refuses to start, and `docs/rt1060-management-image-feasibility.md` says it is not a product.
- **Crux says what a product has to write.** `docs/management-in-a-product.md` ("What you get, and what is not built") lists the start order, the host key holding, the first account, user key registration, certificate registration with the listener, interface binding, a persistence provider and a network apply port as the product's work or as open decisions.

## Licence split

This is an engineering reading of what the `crux-pilot` documents state (`docs/upstream-reuse.md`, `patches/zephyr/README.md`, `docs/product-composition.md`). It is not legal advice.

| Feature | What it needs | Position here |
|---|---|---|
| HTTPS on the Mbed TLS profile | Mbed TLS and TF-PSA-Crypto, stated as Apache-2.0 OR GPL-2.0-or-later | Clear for an Apache-2.0 repository under the Apache-2.0 option. In the Crux manifest these two projects sit in the `crux-secure-management` group with the wolf projects, so fetching the group fetches GPL source. Crux's own workflow narrows it with a west project filter (`.github/workflows/psa-crypto.yml`). Whether this repository's import can do the same has not been tried. |
| SSH, CLI over SSH, SFTP | wolfSSH, wolfSSL and wolfPSA (the Wolf profile; the module refuses SSH on the Mbed profile) | GPL-3.0-or-later or a commercial licence (wolfPSA: GPL-3.0-or-later in its source, commercial terms unconfirmed). A binary that links them is subject to those terms when distributed. They stay off in default CI and in releases. |
| HTTPS on the Wolf profile | The same stacks, plus a Zephyr patch for the wolfSSL TLS socket backend | The patch comes from `wolfSSL/osp` revision `8c32b060ac6017b1291a6da0875a48637bfb682d`. Its terms are unconfirmed, so this repository does not store it and does not publish a fork that carries it. |
| Serial CLI, Access, credential store, events, services | Crux code, Apache-2.0 | Clear, but they share the composition gap above. |

## Consequence for this repository

The boundary check keeps no exception. This repository will not widen it to private adapter headers, Crux `ports/` paths or copies of Crux code. A rule that allows them would hide this finding. No management feature is built in this repository, and none is claimed.

## What would reopen it

A public composition in `crux-pilot`, for example composition interfaces under `include/crux/` with `crux::` targets, or one Crux-owned composition that Kconfig selects, following its composition interface rules. This repository would then answer as it did for File: a reviewed, narrow zone in the boundary check with an exact allow-list. The owner decides whether and how the platform request is filed. This repository will not file it without approval.

## What a later stage could cover, and what is decided

Not decided and not scheduled: whether and when any of this is built here.

- **Could be considered once a public composition exists and the owner approves it:** HTTPS on the Mbed profile, the serial command line, Access and the services around them, each as its own step with its own resource row and tests first on `native_sim`.
- **Not before the licence question is decided:** SSH, CLI over SSH and SFTP. The recorded position is that they stay off in default CI and in releases. Whether a manual, non-publishing job may build them is open.
- **Not possible in this repository today:** the Wolf profile for HTTPS, because of the patch terms.
- **Out of scope:** GPIO, I2C and SPI (frozen as Experimental), direct use of Crux Thread, Sync, Queue and Serial, Reliance Edge, any firmware image in public form.
- **Open before any listener is built:** security decisions such as certificate handling, host key holding, the first account, key registration, the interface a listener binds, and what management load may do to the control cycle. `crux-pilot` issue 197 lists control jitter with and without management load as an acceptance item, and no measurement of it was read for this finding.

## Not run

No build of any management feature was attempted here. No code was written for this finding. The licence reading was not checked by a lawyer. Nothing here claims that Crux cannot compose these features, only that a product cannot reach that composition through public targets.
