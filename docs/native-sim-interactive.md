# Run the base image on your PC

For a developer who wants to try the base image by hand without a board: this page builds the controller framework
with no application for `native_sim`, runs it in the Dev Container, and reaches the Crux serial command line from
a terminal and web management (HTTPS) from a browser on the same machine. One command builds and runs it.

The configuration is for development only. Its entropy is the simulator's test source, so its key and its
passwords protect nothing, and its build refuses every board except `native_sim`. It is not a product image and
not board evidence.

## Before you start

- The Dev Container, opened in VS Code ([Getting started](getting-started.md)). The browser step needs VS Code's
  port forwarding; see [Limits](#limits) for a terminal without VS Code.
- The Mbed TLS modules in the workspace, once. They are in the optional group `crux-secure-management`. Run the
  steps of [Run the `workload` to `sntp` scenarios](native-setup.md#run-the-workload-to-sntp-scenarios) up to
  `west update` in the container's terminal, from `/workspaces/ws`. Leave the group on while you use this page.

## Build and run

In a terminal of the container, from the clone:

```bash
bash scripts/run-native-sim.sh
```

It builds `tests/framework/interactive` for `native_sim/native/64` into `build/native-sim`, then runs it in the
foreground. The log of the image appears in this terminal. Stop it with Ctrl+C. `--no-build` runs the last build,
and `--reset` deletes the stored state first (see [State](#state)).

Wait for the line `startup done phases=4 failed=0`. Two lines before it matter:

- `certificate sha256=<fingerprint> source=generated`: the fingerprint of the self-signed certificate;
- `https management started on 127.0.0.1 port 8443`.

## Make the first account on the serial command line

The image has no account. The first one is made on the serial command line. Open a second terminal of the container
and connect to the console's pseudo-terminal:

```bash
python3 -m serial.tools.miniterm --raw --eol CR build/native-sim/console 115200
```

Press Enter for the `login:` prompt, then:

1. Type `!setup` and press Enter.
2. At `new user:`, type a user name.
3. At `password:` and `repeat:`, type a password of your choice. It is not echoed.
4. The console prints `account created` and `login:` again. Log in with the new account; `help` lists the
   commands and `logout` ends the session.

Ctrl+] leaves miniterm. The image keeps running.

## Open web management in the browser

1. In VS Code, open the **Ports** view. Port 8443 is usually forwarded on its own when the image starts listening.
   If it is not listed, choose **Forward a Port** and enter `8443`.
2. Open `https://127.0.0.1:8443` on your machine, or the local address that the Ports view shows for 8443.
3. The browser warns about the certificate, because it is self-signed. Compare its SHA-256 fingerprint with the
   `certificate sha256=` line of the log, then accept it.
4. Log in with the account that you made on the serial command line.

## State

The store of the image (accounts, settings, the TLS key and the certificate) is a FAT volume on the flash
simulator, kept in the host file `build/native-sim/flash.bin`. It outlives a restart: the next start logs
`source=stored` and the same fingerprint. `bash scripts/run-native-sim.sh --reset` deletes the file, and the next
start makes a new key and has no account. `west build -p always` or deleting `build/` deletes it too.

## How each part is reached

| Part | How | Label | Source read |
|---|---|---|---|
| Network | native_sim's offloaded sockets driver (`CONFIG_NET_NATIVE_OFFLOADED_SOCKETS`): the image uses the host's sockets, with Zephyr's TLS socket layer on top. The listener binds the host's `127.0.0.1` port 8443, which needs no privilege. | Standard | Zephyr v4.5.0 `boards/native/native_sim/doc/index.rst`, "Offloaded sockets driver"; Zephyr's own test `tests/net/socket/tls_configurations` uses TLS over it; Crux uses it for its management composition (`docs/native-management-composition.md` at the pinned Crux) |
| Log | Crux Logging on native_sim's console UART `uart0`, connected to standard output by `CONFIG_UART_NATIVE_PTY_0_ON_STDINOUT` | Standard | Zephyr v4.5.0 native_sim page, "PTY UART"; Crux `docs/logging-contract.md` at the pinned Crux names this composition and tests the option |
| Serial command line | The console stays on an emulated UART (`crux-serial0`). A thread of the image (`src/interactive.c`) copies bytes between it and `uart1`, a PTY UART on its own pseudo-terminal. The run command links that pseudo-terminal to `build/native-sim/console` with `--uart_1_attach_uart_cmd`. | Project-specific workaround | Crux Serial accepts only an emulated UART on `native_sim` (`components/serial/ports/zephyr/serial_binding.c` at the pinned Crux). The PTY UART and its options are standard (native_sim page, "PTY UART"). |
| State | A `zephyr,flash-disk` on the flash simulator, kept in a host file with `--flash` | Standard | native_sim page, "Flash simulator"; Crux's `CRUX_FILE_FATFS_SIMULATOR` accepts a file-backed flash disk |
| Entropy seed | The run command passes a new `--seed` from `/dev/urandom` each run, because the test source repeats for the same seed | Documented but optional | native_sim page, "Entropy device" |
| Browser | VS Code forwards the container's port to the host | Documented but optional | VS Code documentation, "Forwarding a port" in Developing inside a Container (not read for this page: not verified) |
| Production guard | The build refuses any board but `native_sim` with its test entropy, and any listener address but `127.0.0.1`. A board image of the framework includes `framework/management/entropy.cmake`, which refuses a test entropy source. | Project-specific | `tests/framework/interactive/CMakeLists.txt`, `zephyr/CMakeLists.txt` |

CI builds and runs the same configuration in the `base` job: the Twister scenario
`controller.framework.native_sim.interactive` answers on the web port with TLS 1.3, makes the first account through
the pseudo-terminal, restarts the image and logs in again with the stored account.

## Limits

- **Hosts.** The Dev Container is an x86_64 (amd64) Linux image, and CI runs this configuration on x86_64 Linux.
  On an arm64 host (Apple silicon, arm64 Linux) Docker runs the container under emulation; that was not tried, so
  it is not known to work there.
- **Without VS Code.** `bash scripts/dev-shell.sh bash scripts/run-native-sim.sh` builds and runs the image, and the
  serial command line needs a second shell in the same container (`docker exec`). The browser on the host cannot
  reach the listener: it binds `127.0.0.1` inside the container, which Docker's port publishing does not reach.
  This route was not tried.
- **A browser that closes TCP without a TLS `close_notify`** can keep a thread of the web server busy until the
  connection ends. Crux records this limit of Mbed TLS over the offloaded sockets
  (`docs/native-management-composition.md`, "Limits found", at the pinned Crux).
- **The clock is not synchronised.** The time server is `127.0.0.1`, where no SNTP server answers, so nothing leaves
  the host.
- **Port 8443 in use.** The listener cannot bind, so expect the web phase to fail in the log (not tried). Stop the
  other program, then start again.
- Stack use, timing and memory here come from the simulator and the host, not from a device.
