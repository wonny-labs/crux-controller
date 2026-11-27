# The composition zone

This page is the reference for the include rules of the source trees: what each tree may include and why. "Composition"
has four meanings; see the [glossary](glossary.md#product-platform-and-composition). `file` (Crux File) uses the
composition zone: `framework/compose/storage_mount.c` implements the port `framework/src/storage_port.h`. The zone also admits the
headers that the HTTPS management interface (Mbed profile) needs, see [The web composition](#the-web-composition), and the
start of the serial command line, see [The serial command line](#the-serial-command-line).

## Running the check

CI runs two checks in the `Boundary check` job: this repository's `scripts/check_boundary.py`, with the headers
that the pinned Crux publishes, and the product include check, which comes from Crux. Run them from the
repository root; the west workspace holds `crux/` beside the clone:

```bash
python scripts/check_boundary.py --crux-root ../crux
python ../crux/templates/product/check_domain_includes.py --product .
```

The first command checks `app/src`, `app/compose`, `app/os`, `workload` and the trees of the framework module
(`include`, `framework/src`, `framework/compose`, `framework/os`) against the public `<crux/NAME.h>`
headers of the checkout. The second is the product include check, the script
`templates/product/check_domain_includes.py` of Crux (see [the glossary](glossary.md#boundary-and-zones)).
In product mode (`--product`) it reads every C and C++ source under the repository, the tests included, and fails on
an include of `<crux/thread.h>`, `<crux/sync.h>`, `<crux/serial.h>` or `<crux/queue.h>`. Its stricter rules apply only
to a directory named `domain/`, which this repository does not have.

CI downloads that script from a fixed commit of Crux and checks its SHA-256 before it runs it (the step
`Run the product include check` of the `Boundary check` job). A second step of the job runs the same
script through the wrapper `check-includes.sh` of Crux, downloaded and checked the same way. The pinned
Crux contains the same script with the same SHA-256, so a local run uses the pinned copy. Both commands print
nothing but a pass line on success.

Without `--crux-root`, `scripts/check_boundary.py` checks the same rules but cannot tell that a `<crux/NAME.h>` name
is not a public header. The check skips each absent tree as long as at least one of the eight exists. If none exists
under `--repo`, because it ran from the wrong directory, the script exits with status 2 and says so, and it does not
report a pass.

## Why a zone

Crux publishes the File root binding as a composition interface, `<crux/file_zephyr.h>` with the
CMake target `crux::file_zephyr` (`docs/file-composition-interface.md` in Crux). It names a provider on purpose and it is for the code that also mounts the file
system. Application code stays on `<crux/file.h>`. A boundary that lets `app/src` include the
interface would let the application name a provider, and a boundary without any way to include it
would leave File unusable. So the include is allowed in one directory and nowhere else. The Web
composition interface `<crux/web_zephyr.h>` and the console composition interface `<crux/cli_zephyr.h>` follow the
same rule.

The application declares the port header and calls it. The zone implements it. The link joins them;
no include does. The port header lives in `app/src`, so the rules of `app/src` scan it, and it cannot
carry a Zephyr or composition include back into the application.

## The rules

| Tree | ISO C | Sockets profile | Public `<crux/NAME.h>` | Composition interfaces (`<crux/file_zephyr.h>`, `<crux/web_zephyr.h>`, `<crux/cli_zephyr.h>`) | Zephyr headers | Own tree | Other trees |
|---|---|---|---|---|---|---|---|
| `app/src` | yes | yes | yes | no | none | yes | `workload/include` |
| `workload` | yes | no | no | no | none | yes | none |
| `app/compose` | yes | no | yes | exactly those three (`COMPOSITION_CRUX_HEADERS`) | the allow-list below, nothing else | yes | header files (`.h`) of `app/src` (the port header) |
| `app/os` (the adapter zone) | yes | no | yes | no | `zephyr/kernel.h` and `zephyr/net/sntp.h`, nothing else | yes | header files (`.h`) of `app/src` (the port header) |

The zone fails on a Crux private or port header (`file_native.h`, a nested `<crux/ports/...>` path),
on a Zephyr header that is not on the list, on any vendor or third-party header (`fsl_*.h`, `ff.h`,
`lfs.h`), on the Sockets profile and other POSIX headers, and on a quoted include that does not
resolve inside the zone, or to a `.h` file of `app/src`. The rules restrict what the zone writes. A header of `app/src` that the zone includes is scanned under the `app/src` rules, so a Sockets profile header or a `workload` header that it includes reaches the zone indirectly. The scan forms are the same as for `app/src`: every file
whatever its suffix, `#include`, `#include_next` and `#import`, continued lines, CRLF, digraph and
trigraph, comments removed, and a macro operand is a violation.

Without `--crux-root` any `<crux/NAME.h>` passes the shape test, as it does for `app/src`, and the
three composition interfaces are denied outside the zone by name (`COMPOSITION_CRUX_HEADERS`); with
it (CI always passes it), a `<crux/NAME.h>` that is not a header Crux publishes fails, including
`<crux/file_native.h>`. Against a Crux checkout, `<crux/file_zephyr.h>`,
`<crux/web_zephyr.h>` and `<crux/cli_zephyr.h>` must be headers that Crux publishes under
`components/*/ports/*/include/crux/`, and any header found there is a composition interface that
`app/src` and the workload cannot include, whether or not this file names it. Any other composition
interface that Crux publishes stays out of the zone until a reviewed change lists it. The other Web
headers (`<crux/web.h>`, `<crux/web_session.h>`, `<crux/web_management.h>`),
`<crux/tls_certificate.h>` and `<crux/tls_certificate_start.h>` are ordinary public headers (Crux
publishes them under `components/*/include/crux/`) and keep the rule of every public
`<crux/NAME.h>` header.

## The allow-list of Zephyr headers

`COMPOSITION_ZEPHYR_HEADERS` in `scripts/check_boundary.py` is the whole list. There are no
wildcards. A header is on it only if mounting and binding the file system, or the web composition (see
[below](#the-web-composition)), needs it.

| Header | Why the zone needs it |
|---|---|
| `zephyr/fs/fs.h` | The mount API: `struct fs_mount_t`, `fs_mount`, `fs_unmount`, `fs_mkfs`, `fs_mkdir`, and `FS_FSTAB_DECLARE_ENTRY` and `FS_FSTAB_ENTRY`, which take a mount described in the devicetree as a `zephyr,fstab,...` node. Crux does not mount a file system for a product. |
| `zephyr/devicetree.h` | `DT_NODELABEL` and the other node-identifier macros that name the fstab node and read its `mount-point` and `disk-name`. `zephyr/fs/fs.h` does not include it (at the pinned Zephyr, `fs.h` includes only `sys/types.h`, `zephyr/sys/dlist.h` and `zephyr/fs/fs_interface.h`), yet its `FS_FSTAB_*` macros expand `DT_*` macros. The zone must include this header itself. |
| `zephyr/net/tls_credentials.h` | The TLS credential store, for the HTTPS management composition (see below). The zone registers the server certificate and key under the security tag that the Web composition names, and the Crux Web interface does not do that for a product. |

Left off on purpose, and why:

| Header | Why it is not on the list |
|---|---|
| `zephyr/storage/disk_access.h` | `disk_access_init` only tells a missing card from a failed mount. `fs_mount` reports both, and a product that must tell them apart can ask for the header in a reviewed change. |
| `ff.h` | The FatFs library header. Every reference composition in Crux includes it to declare a `FATFS` object. A mount that the devicetree describes as `zephyr,fstab,fatfs` makes Zephyr declare that object, so the zone does not need the header. Whether that route works for the `file` composition is a question of `file`, which records its answer in its findings note. |
| `zephyr/kernel.h`, `zephyr/sys/printk.h`, `zephyr/logging/log.h` | The composition returns a result code. The application logs through Crux Logging and runs its threads through the adapter zone `app/os`. `zephyr/kernel.h` is allowed in the adapter zone `app/os` and stays off this list, see [The adapter zone](#the-adapter-zone). `zephyr/net/sntp.h` is also allowed only in the adapter zone `app/os` and stays off this list, see [The adapter zone](#the-adapter-zone). |
| `zephyr/fs/littlefs.h`, `zephyr/fs/fs_sys.h` | Provider and file system specifics that `file` does not select. |
| `zephyr/drivers/*`, other `zephyr/net/*` headers (`zephyr/net/socket.h`, `zephyr/net/http/*`, `zephyr/net/net_if.h` and the rest), vendor `fsl_*.h` | Not part of binding a file system or the web server. A driver or network detail in the zone would be a second product layer, not a composition. `zephyr/net/tls_credentials.h` is the one network header on the list. |

A change to the list is a change of `scripts/check_boundary.py`, of
`tests/tooling/test_boundary.py` (`test_the_allow_list_is_the_reviewed_set` pins the set) and of this
page, in one reviewed pull request.

## The web composition

The HTTPS management interface (Mbed profile) is composed in `framework/compose`, as File is, by
`management_start.c` (`management`). The reason is that Crux publishes its binding to the Zephyr HTTP server as a composition interface:
`<crux/web_zephyr.h>` with the CMake target `crux::web_zephyr`. It declares `crux_web_start()`,
which binds the web core to Zephyr's HTTP server, its sockets and the TLS security tag, so only the
platform composition of a product calls it. That is the same reason as for `<crux/file_zephyr.h>`,
and the same rule follows: the include is allowed in `framework/compose` and fails in `app/src`, `app/os`
and `workload`, with or without `--crux-root`.

The zone also needs `zephyr/net/tls_credentials.h`. Crux expects the product to register the TLS
material under the security tag before it calls `crux_web_start()`, and the credential store is
Zephyr's. The public Crux headers do not wrap it, so the zone includes the Zephyr header itself.

Nothing else widens. The zone still fails on every other Zephyr header, on the Sockets profile, on
Crux private or port headers and on any other composition interface. The portable Web headers
(`<crux/web.h>`, `<crux/web_session.h>`, `<crux/web_management.h>`), `<crux/tls_certificate.h>`
and `<crux/tls_certificate_start.h>` are ordinary public headers. `app/src`, `app/os` and `workload` fail on
`<crux/web_zephyr.h>` and on `zephyr/net/tls_credentials.h`.
`management` is the composition source that uses them: `framework/compose/management_start.c` includes the Zephyr and
composition headers named above, and no other entry is needed for it. The route sources, the packaged
page and the route table are not in the zone: they belong to the target `app` and are named by
`framework/management/management.cmake`, which Crux's route function equips with the private include directories of
Crux's own sources one source at a time, so no build file here adds an include path.

## The serial command line

The serial command line is composed in `framework/compose`, by `cli_start.c` (`base`). Crux publishes the start of
its console as a composition interface: `<crux/cli_zephyr.h>` with the CMake target `crux::cli_zephyr`
(built under `CONFIG_CRUX_CLI_CONSOLE`). It declares `crux_cli_serial_start()`, which binds the Crux console,
with its login and its first-account setup, to the UART that the devicetree alias `crux-serial0` names, so only the
platform composition of a product calls it. That is the same reason as for `<crux/file_zephyr.h>` and
`<crux/web_zephyr.h>`, and the same rule follows: the include is allowed in `framework/compose` (and `app/compose`,
which shares the list) and fails in `app/src`, `app/os`, `workload`, `include`, `framework/src` and `framework/os`,
with or without `--crux-root`.

The command tables go to `crux_cli_init()` of `<crux/cli.h>`, an ordinary public header. The zone needs no Zephyr
header for the console: the UART is chosen by the alias in the devicetree, and Crux opens it. The Zephyr allow-list
and the frozen headers do not change. `framework/compose/CMakeLists.txt` links `crux::cli_zephyr` to the zone's
library only, as it links `crux::file_zephyr` and `crux::web_zephyr`.

## The adapter zone

`app/os` is a second zone, for the OS facilities of the product: threads, queues and sleeping.
Crux offers threads and locks through `<crux/thread.h>` and `<crux/sync.h>`, but a product
adapter that needs them uses Zephyr directly, and that use has one place to live. The reason is
that OS facilities use Zephyr directly in product adapters, while product behaviour stays plain C in
`app/src`. The application declares a small product-owned port header in `app/src`, calls it, and
the adapter in `app/os` implements it with Zephyr kernel calls. The link joins them; no include does.

The adapter zone may include ISO C headers, public `<crux/NAME.h>` headers, its own tree, header
files (`.h`) of `app/src` and exactly two Zephyr headers, `zephyr/kernel.h` and `zephyr/net/sntp.h`
(`OS_ADAPTER_ZEPHYR_HEADERS` in `scripts/check_boundary.py`, no wildcard). It fails on the Sockets
profile and other POSIX headers, on `<crux/file_zephyr.h>` and any other composition interface, on
every other Zephyr header (`zephyr/sys/printk.h`, `zephyr/logging/log.h`, a driver header, any other
network header, `zephyr/net/socket.h` included), on a vendor or third-party header, and on a quoted include that does not resolve
inside the zone or to a `.h` file of `app/src`. The scan forms and the indirect reach through an
`app/src` header are the same as for the composition zone.

`app/src`, `app/compose`, `framework/compose`, `framework/src`, `include` and `workload` keep failing on `zephyr/kernel.h` and on `zephyr/net/sntp.h`,
and a quoted include of an `app/os` header fails in each of them, as a quoted include of a composition
zone header does.

The adapter zone's allow-list is the whole list, and each entry has a reason:

| Header | Why the zone needs it |
|---|---|
| `zephyr/kernel.h` | Threads, message queues and sleeping, the OS facilities the zone exists for. |
| `zephyr/net/sntp.h` | The Zephyr SNTP library, for a product time-source adapter. See below. |

Why `zephyr/net/sntp.h`: Crux provides no SNTP client and leaves the choice of a time source to the product,
because its Time contract designates the product as the owner of the Time Authority. The Zephyr SNTP library is a
maintained alternative to a product-written packet parser, and the public Crux interface offers no time-source
client. The adapter uses the library's string-based query (`sntp_simple()`), so it includes no socket type and no
socket header itself, and the rule keeps `allow_sockets` off for the zone. The check reads direct includes only; the
allow-list entry allows the include and nothing else. The one source that uses it is `framework/os/time_sync_zephyr.c`
(`sntp`).

Why `zephyr/kernel.h` is not on the composition zone's list: that zone exists to mount a file system
and bind it to Crux, and `COMPOSITION_ZEPHYR_HEADERS` names only what that and the web composition
need. The kernel header
is the entry point to every kernel facility. If the composition zone could include it, a mount
routine could grow thread and queue code that belongs in the adapter zone, and the composition zone
would stop being a narrow composition. The two zones stay separate, each with an exact list, and a
change to either list is a reviewed change of `scripts/check_boundary.py`, of
`tests/tooling/test_boundary.py` (`test_the_adapter_allow_list_is_the_reviewed_set` pins the adapter
set) and of this page, in one pull request.

The same limit applies as for the composition zone: the check reads includes only, so the adapter
zone adds no include path to the application target. The only source of the tree `app/os` is
`workload_os_zephyr.c` (every configuration), which its `CMakeLists.txt` adds to the application target; the zone is
not a library of its own. The adapter zone of the module, `framework/os`, holds `time_sync_zephyr.c`, which
`framework/configurations.cmake` adds to the application target of `sntp` and the module builds into its library
for the base image. `tests/tooling/test_os_adapter.py` checks that the zone
adds no include path and no library, and that the application target links neither a zone library nor Crux Thread nor
Crux Queue.

### The frozen Crux headers

`app/src` and `app/os` also fail on `<crux/thread.h>`, `<crux/sync.h>` and `<crux/serial.h>`
(`FROZEN_CRUX_HEADERS` in `scripts/check_boundary.py`), although they are public headers, so the
statements above about public `<crux/NAME.h>` headers hold for every other name. The product uses
Zephyr directly for threads and queues, and the rule keeps a later change from bringing the Crux
contracts back. The rule is a field of the `Rule` of each of the two trees. It does not apply to
`workload`, which has no Crux header at all, and it does not change `app/compose` or `framework/compose`. Adding or removing a
name is a reviewed change of the script, of `tests/tooling/test_boundary.py` and of this page.

The check refuses a `<crux/NAME.h>` that Crux does not publish: with `--crux-root`, which CI always passes, in
every tree, the composition zone included, and the product include check refuses `<crux/queue.h>` in every source of
the repository. `tests/tooling/test_boundary.py` (`RemovedCruxQueue`) checks the first. Without `--crux-root` the name
passes the shape test, as any unknown `<crux/NAME.h>` does (see [Running the check](#running-the-check)).

## The trees of the framework module

The controller framework is a Zephyr module of this repository (`zephyr/module.yml`). Its sources live in four
checked trees, each with a rule of its own in `RULES`:

| Tree | Holds | May include |
|---|---|---|
| `include` | The interface headers `<controller/framework.h>` and `<controller/version.h>`, which a product includes | ISO C, public `<crux/NAME.h>` headers except the frozen three, its own tree |
| `framework/src` | The portable core: the startup sequence and the start function, the time synchronisation glue and policy, the management policy and the port headers | ISO C, public `<crux/NAME.h>` headers except the frozen three, its own tree, `<controller/NAME.h>`; no Zephyr header and no Sockets profile |
| `framework/compose` | The composition zone of the module: the storage mount, the start of web management and the start of the serial command line | the rule of `app/compose`, with header files (`.h`) of `framework/src` in place of those of `app/src` |
| `framework/os` | The adapter zone of the module: the SNTP query and its thread, and the health supervision (supervisor thread, task watchdog, retained region, fatal error handler, reboot thread) | the rule of `app/os` with the supervision headers below, and header files (`.h`) of `framework/src` in place of those of `app/src` |

`<controller/NAME.h>` must name a file of `include/controller/`, one level deep. `app/src` may include it and the
headers of `framework/src`, because the base image's `main()` calls the start function and the configurations built
on the workload compose the framework services that live in the module. No zone of `app/` or of the module may
include it, and the two zones of the module reach neither `app/src` nor each other.

A C or C++ source or header under `app/`, `framework/`, `include/` or `zephyr/` that lies in none of the checked trees fails
the check (`MODULE_TREES` in `scripts/check_boundary.py`), so a source cannot escape the rules by its place. Build
files, the web assets of `framework/management/` and the data files of `app/conf/` and `app/boards/` are not
sources. The allow-lists of the zones are those above, and the module's adapter zone adds the headers of the next section.

### The supervision headers of `framework/os`

The health supervision of the framework uses Zephyr directly, as the ports-and-adapters split of the
framework puts every OS call in an adapter zone: the portable core in `framework/src` decides, and
`framework/os` carries the decision out. Crux System gives the one hardware watchdog activation, the
reset cause and the software reset; it has no task watchdog, no retained memory and no fatal error
hook, so the public interface is not enough for these. `FRAMEWORK_OS_ZEPHYR_HEADERS` in
`scripts/check_boundary.py` is the list of `app/os` plus five headers, each with a reason:

| Header | Why `framework/os` needs it |
|---|---|
| `zephyr/task_wdt/task_wdt.h` | One task watchdog channel per supervised framework thread, with no hardware fallback (`task_wdt_init(NULL)`); the supervisor feeds the Crux watchdog only while no channel has expired. Established mechanism: Zephyr's task watchdog. |
| `zephyr/retention/retention.h` | The retained region of the boot counter and the last-fault record, with Zephyr's prefix and checksum over a retained memory device. The framework uses the retention API and not the retained memory driver header. Established mechanism: Zephyr's retention subsystem. |
| `zephyr/fatal.h` | The framework's `k_sys_fatal_error_handler()`, which writes a minimal record and ends in a reset: Crux's `crux_system_reset()` where the handler runs in thread context, otherwise `k_fatal_halt()`, after which the armed, unfed hardware watchdog resets the device. Established mechanism: Zephyr documents the handler as the place of an application's fatal error policy (`include/zephyr/fatal.h`); the halt that leaves the reset to the watchdog is a project-specific workaround in place of `zephyr/sys/reboot.h`, which is not on the list. |
| `zephyr/device.h` | The device of the retained region, for the retention API. |
| `zephyr/devicetree.h` | The lookup of the retained region by its node label `controller_retained`, which the board overlay names. |

`app/os`, the composition zones, the core, `include` and the workload keep failing on each of the five, except
`zephyr/devicetree.h`, which the composition zones already have. `tests/tooling/test_boundary.py`
(`FrameworkAdapterSupervision`) pins the set and checks both sides.

## What the zones do not cover

- The CMake side. The check reads includes only and does not see include paths from CMake. The
  composition zone is built as its own library (`framework/compose/CMakeLists.txt`) that links `crux::file_zephyr`
  privately, so the application target gets no include path from it. `tests/tooling/test_boundary.py`
  keeps checking that `app/CMakeLists.txt` adds none, and `tests/tooling/test_file.py` checks that
  only the composition zone's library links the composition interface and that the zone adds no
  include path.
- Whether a mount works. The check does not run anything.
