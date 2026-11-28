# Application template

This page is for a product team that starts a product on the controller framework.
Copy this folder once, follow [Start a product](#start-a-product), and you have a product repository that builds and runs on `native_sim` and builds for the reference board.
The framework stays a Zephyr module that the copy imports with west at a pinned commit, so a framework fix reaches the product when it moves that pin.

## What the copy holds

| File | Purpose |
| --- | --- |
| `west.yml` | The west manifest of the product repository: the framework at a full commit SHA, with Crux and Zephyr through the framework's manifest |
| `app/src/main.c` | `main()`, which passes the product's descriptor with its four entries (`init`, `start`, `stop`, `safe_state`) to the start function of `<controller/framework.h>` |
| `app/prj.conf` | The configuration on every board: the framework's Kconfig symbol and the services |
| `app/boards/native_sim_native_64.conf`, `.overlay` | The values of `native_sim`, for development and CI only |
| `app/boards/mimxrt1060_evk_mimxrt1062_qspi.conf`, `.overlay` | The values of the reference board, the RT1060-EVKB (`mimxrt1060_evk@B/mimxrt1062/qspi`) |
| `app/testcase.yaml` | The first test, a starting point for the product's own: Twister runs the application on `native_sim` and checks that `init` and `start` ran |
| `.gitignore` | Keeps the build folders out of the repository |

## Start a product

You need a clone of `crux-controller` at the commit to start from, in a folder named `crux-controller`, and the tools of the framework's [Getting started](https://github.com/wonny-labs/crux-controller/blob/main/docs/getting-started.md) page.
Run these commands in the folder that holds the clone:

```sh
mkdir product-workspace
cp -R crux-controller/template product-workspace/product
python3 crux-controller/scripts/pin_framework.py --framework crux-controller product-workspace/product/west.yml
cd product-workspace
git -C product init
git -C product add .
git -C product commit -m "feat: start the product from the controller framework template"
west init -l product
west update
```

The third command writes the full commit SHA of your clone as the framework's revision in `product/west.yml`.
The first time, it also writes that SHA as `template-revision` under `self: userdata`, the record of the framework commit that the copy was made from.
`west update` then fetches the framework at that commit, and Crux, Zephyr and the modules at the commits that the framework's own `west.yml` pins.

Build and run, from `product-workspace`:

```sh
west build -b native_sim/native/64 -d product/build/native_sim product/app -t run
west build -b mimxrt1060_evk@B/mimxrt1062/qspi -d product/build/evkb product/app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON
west twister -T product/app -p native_sim/native/64
```

On `native_sim` the log shows `product: init` and `product: start` after the framework's start-up steps; stop the program with Ctrl+C.
`-DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON` stops the build when the workspace has another Zephyr than the one Crux verified.
To give the product folder another name, also change `self: path` in `west.yml`.

## Move the framework pin

Run the same script against a clone at the new commit, then `west update`:

```sh
python3 crux-controller/scripts/pin_framework.py --framework crux-controller product-workspace/product/west.yml
```

It moves the revision and keeps `template-revision`.
Read the framework's `CHANGELOG.md` between the two commits first: it states the compatibility changes and the upgrade steps.

## What reaches a copy

- The framework module reaches the copy when the product moves its pin.
- Later changes to this template folder never reach a copy. A copy has no Git link to `crux-controller`, as a repository made from a GitHub template repository has none to its template.
- The copy depends on the framework only through `<controller/framework.h>` and the other headers of `include/`, the start function, the Kconfig symbol `CONFIG_CRUX_CONTROLLER_FRAMEWORK` and the build options. Their changes follow the stability tiers of the specification, section 3.4.
- `template-revision` tells you which version of this folder to compare when you want to adopt a later template change by hand.

## Boards

The application is the same for every board: the board is the `-b` argument of `west build`.
Put what one board needs in `app/boards/<board>.conf` and `app/boards/<board>.overlay`, where `<board>` is the board target with `/` replaced by `_` and without the revision, for example `native_sim_native_64` for `native_sim/native/64` and `mimxrt1060_evk_mimxrt1062_qspi` for `mimxrt1060_evk@B/mimxrt1062/qspi`. Zephyr ignores a file under any other name, such as `native_sim.conf` (Zephyr `cmake/modules/extensions.cmake`, `zephyr_build_string()`). Keep `prj.conf` free of board values.
A new board needs the devicetree roles that the framework looks up: the aliases `crux-serial0` (console) and `crux-watchdog0` (watchdog), the `chosen` node `zephyr,log-uart` (logging) and the fstab node label `controller_storage` (storage).

## Make a product build

`app/prj.conf` is a development configuration: with `boards/native_sim_native_64.conf` it runs with the simulator's test entropy (`CONFIG_FAKE_ENTROPY_NATIVE_SIM`) and starts without a watchdog (`CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG`).
A product build, on the product's board, follows criteria 19 and 38 of the specification:

- It has none of `CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG`, `CONFIG_FAKE_ENTROPY_NATIVE_SIM`, `CONFIG_TEST_RANDOM_GENERATOR`, `CONFIG_CRUX_DEVELOPMENT_IMAGE`, `CONFIG_SHELL`, `CONFIG_CRUX_WEB_PLAIN_HTTP_FOR_TESTS` and the debug snippet.
- It keeps `CONFIG_TASK_WDT_HW_FALLBACK=n`, `CONFIG_STACK_CANARIES=y` and, where the SoC supports it, `CONFIG_HW_STACK_PROTECTION=y`, with a watchdog timeout inside the range of its watchdog.
- It stores its data on a persistent medium in place of the RAM disk, and sets its own MAC address, IP address and SNTP server.

The reference board files already meet the first two rules; the `native_sim` files never do.

## Why the template is shaped this way

| Choice | Basis |
| --- | --- |
| The product repository is the west manifest repository and names everything it builds with | *Standard*: west "Workspaces", topology T2; Zephyr "Application Development" recommends starting from the `example-application` workspace application |
| The framework is pinned by a full commit SHA | *Standard*: the west manifest documentation says that only a SHA gives a reproducible workspace |
| Crux comes through the framework's manifest import, not from a project of its own | Decision (specification section 7.5): the copy builds with the Crux that the framework verified, as the framework's product integration check does |
| The template follows `main` and the first step pins it | *Project-specific workaround*: a manifest cannot name the commit that holds it; Crux's `templates/product` does the same |
| The Mbed TLS group is switched on in the manifest | *Standard*: west `group-filter`; the framework's import blocks the wolf projects of that group by name |
| Board values live in `app/boards/<board>.conf` and `.overlay` | *Standard*: Zephyr "Application Development", board configuration files |
| The first test is a Twister console harness | *Standard*: Zephyr "Test Runner (Twister)", `harness: console` |
| The copy records `template-revision` under `self: userdata` | Decision; *documented but optional*: west manifest `userdata` |
| Template sources include only the framework's interface headers, ISO C and public Crux headers | Decision (specification sections 7.3 and 7.5, criterion 48) |

The rules behind these choices are in the framework's [specification](https://github.com/wonny-labs/crux-controller/blob/main/docs/design/controller-framework-spec.md), section 7.5, and its [overview](https://github.com/wonny-labs/crux-controller/blob/main/docs/design/controller-framework.md#how-a-product-joins).
