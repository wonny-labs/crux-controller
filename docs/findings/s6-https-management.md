# Finding: step S6, management over HTTPS

Status: step S6 is wired and builds in CI. **Nothing in this note is a CI result.** Zephyr builds and Twister runs
happen in CI only, no Zephyr build ran while the step was written, and the first CI run of the change that adds it is
the first build of this chain from outside `crux-pilot`. Nothing has run on a board. Every result that only CI can give
is marked Open below, with the job that gives it.

The groundwork that came before is in [s6-https-management-gaps.md](s6-https-management-gaps.md), which stays as
recorded. It lists three gaps found by reading: the locks of the PSA core, the first account and the route sources. This
note records what the step did about each.

Every statement carries one of three labels:

- **Verified**: read in a named file at a named revision, or checked by a command that ran while the step was
  written, which the row names. The tooling tests, the host tests, `clang-format`, `clang-tidy` and the boundary
  check ran locally. A syntax-only compile of the new composition source and of `composition.c` ran against the public
  Crux headers at the pin, with a stub of one Zephyr header; that is not a Zephyr build.
- **Inferred**: a reading of the sources, or a plan, that no file states and nothing has run.
- **Open**: a result that only a CI run can give. The job is named.

The revisions are `crux-pilot` at `8e3737d25d048b14a00c01da00494f58a62958c6`, the commit that `west.yml` pins ("8e3737d2"
in the rows), and Zephyr as read in a v4.4.0 checkout while the pin is v4.4.2.

## What the step is

HTTPS management on the network of S2, with the Mbed TLS profile of Crux: login and sessions of Crux Access, the status
service, the configuration service and one packaged page, served on `192.168.77.2` port 443. The certificate is
self-signed and made on the device at its first start. The medium is a RAM disk, so nothing persists across a reset. The
image has no account, so nobody can log in until a first-account console exists, which is a later change. The save route
of the configuration service exists and ends as not supported. There is no reboot, network or file route, no SSH and no
command line.

## Results that only CI can give

| Question | State | Job that answers it |
|---|---|---|
| Do the route sources of Crux compile from this repository, under `-Werror`, with no include path of ours? | **Open** | `S6 build`, the cross-build step, and `Budget S6` |
| Does `crux_web_routes()` accept the product's `app` target and the reviewed list? | **Open** | `S6 build`, the cross-build step |
| Does the in-process TLS 1.3 handshake complete with peer verification required, and does the server answer a request? | **Open** | `S6 build`, the Twister step (cases 1 to 3) |
| Is a self-signed leaf accepted as its own trust anchor, with the hostname `crux-controller` and no usable clock? | **Open** | `S6 build`, the Twister step |
| Is a client with only a TLS 1.2 suite refused (case 4)? | **Open**; if it cannot be built the case is dropped and the gap is recorded, never weakened | `S6 build`, the Twister step |
| Does picolibc satisfy the `fnmatch()` check at `crux_web_start()`, or does the scenario need the minimal libc? | **Open** | `S6 build`, the Twister step |
| Are the assets served compressed or as text (case 6)? | **Open** | `S6 build`, the Twister step |
| Does the board image resolve as the job asserts (the options on and off, the alias, the RAM disk, the TRNG as entropy source)? | **Open** | `S6 build`, the resolved-configuration step |
| Does `west update` with the group on fetch the Mbed pair and nothing else, and does the Twister report have the keys the job reads? | **Open** | `S6 build`, the fetch and report steps |
| Static size of the image against the declared limits | **Open**; if a margin is exceeded the limit is not changed in the same change | `Budget S6` |

## What the product had to write

| Item | Label | Source |
|---|---|---|
| The start sequence is one file in the composition zone, `app/compose/management_start.c`, which implements `app/src/management_port.h` in its documented order. It copies the product's policy into the Crux type member by member and refuses to start when the product's copy of a permission name differs from the Crux macro | **Verified** | the sources of this change, and `tests/tooling/test_s6.py` (`S6Sources`) |
| The order is the one of Crux's module fixture and its web start header, with the TLS certificate start after the configuration service, the status service and the event start | **Verified** | `tests/native/management_module/src/main.c` and `components/web/ports/zephyr/include/crux/web_zephyr.h` at 8e3737d2 |
| The route sources, the packaged page and the entropy rules are in `app/management/`, included by `app/CMakeLists.txt`, because Crux's route function sets properties on the sources of `app` | **Verified** | `cmake/CruxWebRoutes.cmake` at 8e3737d2, and the build files of this change |
| `crux_web_routes()` hands the private include directories of Crux's own route sources to each of them as a property of that source, so the product adds no include directory | **Verified** (that it does so); that it compiles from here is **Open** | `cmake/CruxWebRoutes.cmake` at 8e3737d2 |
| Crux System on this board needs the alias `crux-watchdog0`, an enabled `wdog0` and three native facilities, because the status service reads System | **Verified** | `components/system/ports/zephyr/CMakeLists.txt` and `system_binding.c` at 8e3737d2 (read for the plan), copied into `app/boards/s6.overlay` |
| The credential store needs two roots and a File provider. The RAM disk provider needs the SD card driver off, which Zephyr turns on when the board's devicetree has the card | **Verified** | `zephyr/Kconfig` and `zephyr/CMakeLists.txt` at 8e3737d2 |
| The status service takes the reset cause once, from the owner of the boot diagnostic, and never clears it. S4 clears it, so S6 and S4 are excluded from each other in Kconfig | **Verified** | `components/mgmt_status/include/crux/management_status.h` at 8e3737d2, and `app/Kconfig` |
| The members of an initialiser are not evaluated in a fixed order, so the reset cause is read before the initialiser that holds it. Crux's own sample reads it in the initialiser | **Inferred** (a reading of the C rule and of the sample) | `samples/management_rt1060_mbed/src/composition.c` at 8e3737d2 |
| The Mbed profile, the PSA algorithms and the sizes are a product-owned copy of Crux's sample for this board, plus the two lines that only that sample has | **Verified** | `samples/management_rt1060_mbed/prj.conf` at 8e3737d2, and `app/conf/s6.conf` |
| The page is three files, no framework, no external URL, no inline script or style; the packager checks only names, types, size and secrets, so the rest is checked by `S6Page` | **Verified** | `components/web/tools/web_assets.py` at 8e3737d2, and `tests/tooling/test_s6.py` |

## Decisions, and the test that pins each

| Decision | Test |
|---|---|
| S6 depends on S2 and excludes S3 and S4. S5 is allowed and is not built in CI | `S6Configuration.test_the_step_option_excludes_the_steps_it_cannot_share_an_image_with` |
| The fragment names no Thread, Sync or Queue symbol; the Crux services select them | `S6Configuration.test_the_fragment_names_no_thread_sync_or_queue_symbol_because_the_services_select_them` |
| No build file adds an include path, and the route sources are the only sources `management.cmake` adds | `S6BuildFiles` |
| The network, reboot and file service routes are not named, so they are not in the table | `S6BuildFiles.test_the_management_cmake_names_the_session_and_management_routes_and_no_other`, `S6Routes` |
| The board image refuses a test entropy source and applies Crux's fail-closed correction of the entropy glue; the scenario does not include that file | `S6BuildFiles.test_the_entropy_rules_are_in_their_own_file_that_only_the_image_includes` |
| Both `tls_credential_add()` results are checked before the listener starts, because a listener with no certificate does not listen and does not say so | `S6Sources.test_both_tls_credential_registrations_are_checked_before_the_listener_starts` |
| The key material is named in one helper only, and is neither copied, logged nor released | `S6Sources.test_the_key_material_is_neither_copied_nor_logged_nor_released` |
| The group is switched on in the S6 job and the S6 Budget row only, after the project-list check, and never in `west.yml` | `S6Workflows` |

## Gaps for `crux-pilot`

| Gap | Label | Source |
|---|---|---|
| Crux's sample for this board checks the first random read at boot with code from `tests/zephyr/entropy_boot`, a test path that a product cannot reach without a private include path or a copy. This image does not have that check. It applies the fail-closed correction of the entropy glue and asserts the TRNG driver, and says nothing about a boot self-check | **Verified** (that the sample does so); **Inferred** (that no public form exists) | `samples/management_rt1060_mbed/CMakeLists.txt` and `src/main.c` at 8e3737d2 |
| Crux's own guide says the cross-build of its sample for this board has not run, so this is the first build of the Mbed profile for the board by anyone outside the repository | **Verified** | `docs/management-in-a-product.md` at 8e3737d2, "A board" |
| The first account can only be made from the serial console, which a product cannot compose here until the boundary check allows `<crux/cli_zephyr.h>`. That is a separate reviewed change, and it is why the image has no account | **Verified** | `s6-https-management-gaps.md` |
| If the route sources do not compile from this repository, there is no private include workaround: the failure is a platform gap, recorded here, and the owner decides | **Verified** (the rule) | `s6-https-management-gaps.md` |

No request has been filed in `crux-pilot`. Filing needs the owner's approval.

## Thread and Sync, and the other wording that this step made false

`CONFIG_CRUX_ACCESS`, `CONFIG_CRUX_WEB_SESSION` and `CONFIG_CRUX_WEB_MANAGEMENT` select the Thread and Sync symbols of
Crux, so the S6 image has them on. Product code still includes none of their headers and names none of their symbols,
and the boundary check still fails on them in `app/src` and `app/os`. The help of the S1 option, the S1 fragment and
`docs/architecture.md` said that no step selects them, which is true of S1 to S5 only. They now say that product code
includes none and that the services of S6 select them for themselves. The S1 to S5 jobs still assert the absence of
those symbols in their own configurations, and the S6 job asserts their presence.

## The limit of one silent client

The limit that the groundwork note records applies to this image unchanged: with the web adapter on, the handshake
runs on the one server thread, so one silent client stops every other client for up to the handshake timeout, 2,000 ms
by Crux's declaration, and the same value bounds every outbound TLS connect of the image. S6 makes no outbound TLS
connection. Whether 2,000 ms suits the target is not known.

## What the scenario cannot show

The scenario runs in one `native_sim` image, with a TLS client of the test in the same process over Zephyr's loopback
interface. It cannot show a successful login, any 200 from an API route, roles, a password change, the first account, a
configuration save, handshake time, stack use, heap peaks (the heap there is 180,000 bytes and the product declares
120,000), the strength of any key (the entropy is the simulator's fake source), the libc of the target when the
scenario runs on another one, the page in a browser, Ethernet, the address `192.168.77.2`, or anything on a board.

## What is not verified

- Anything on a board: the link, the address, the listener, the handshake, the page in a browser, and whether a browser
  accepts the generated certificate.
- Login, sessions and request-forgery protection with an account, roles at run time, and the first account.
- Timing: the handshake, password hashing, the time that key generation and the format of the RAM disk take on the main
  thread before the workload starts, and the effect of management on the control workload.
- Stack use of the main thread, the HTTP server thread and the Crux workers (all sizes are starting values), the heap
  of the TLS stack, and the network buffers.
- Entropy: the strength of the hardware random source and whether `CONFIG_ENTROPY_MCUX_TRNG` resolves on for this
  board, which the job asserts.
- Every Open row of the first table.
