# Board bring-up for the RT1060-EVKB Rev B

**Outline. Not yet run for this controller.** This page sketches how a bring-up of this firmware on the
NXP RT1060-EVKB Rev B would go. It is not a procedure that someone has followed from this page. The only
board runs this repository records are the two S2 runs in
[docs/findings/s2-first-board-run.md](findings/s2-first-board-run.md), and those followed a gated procedure
that is not written out in this repository. Read the [roadmap](roadmap.md) for what has run, and the
[glossary](glossary.md) for the terms.

**Authorisation.** Physical programming, reset and any other operation on the board need the project
owner's explicit authorisation for each task (for example one run of one image), a verified target, probe and flash configuration, and a
safe setup. Nothing on this page grants that authorisation, and an earlier approval does not carry over to a
new task. If the authorisation is missing or unclear, stop before touching the board.

Where this page states a fact, it names the file it comes from. Where it proposes something, it says
"proposed". The commands that program the board are not in this repository and are not given here.

## What is needed

| Item | What the repository says |
|---|---|
| The board | NXP RT1060-EVKB Rev B. CI builds for `mimxrt1060_evk@B//qspi`. |
| Power | Not recorded in this repository. |
| Board settings (boot switches, jumpers) | Not recorded in this repository. Check the board documentation. Proposed: write the settings down in the run record before the first write. |
| USB debug connection | The S2 runs programmed and reset the board through a probe and read the log from a UART. The S1 base image writes the log to LPUART1 at 115200 baud (`app/boards/mimxrt1060_evk_mimxrt1062_qspi.overlay`). Which cable and adapter carry that UART is not recorded here. |
| Ethernet link | A cable from the board to the host peer. The S2 image has a static address and no DHCP client. |
| A host peer | A host with the address `192.168.77.1` on a `/24` network, able to listen on TCP port `42420` and echo what it receives. The board's address is `192.168.77.2` (`app/conf/s2.conf`, `app/Kconfig`, `docs/findings/s2-first-board-run.md`). |
| The programming and capture tools | Not in this repository. The S2 runs used the `crux-pilot` target test driver at revision `3b2dce56` (merged by wonny-labs/crux-pilot#352 and wonny-labs/crux-pilot#353), with a raw passive UART capture of 180 seconds. |
| The accepted normal image | The image that was on the board before and that is put back afterwards. The S2 note records its SHA-256 and size. Proposed: have it available before you start. |
| A written run record | The S2 note names what each run kept: host command output, probe logs, the raw capture and the peer record. They are kept privately, and the note says so. |

## The order of a bring-up

The order follows the S2 runs. Each step names what it should show, as far as the S2 note records it. A step
that does not show that is a reason to stop (see [Stop conditions](#stop-conditions)).

1. **Build the S2 image from CI's recipe.** The `S2 build` job of `.github/workflows/ci.yml` builds with the
   baseline gate required. Its command, run from the west workspace directory in CI:

   ```bash
   west build -p always -b 'mimxrt1060_evk@B//qspi' -d crux-controller/build/s2 \
     crux-controller/app -- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON \
     "-DEXTRA_CONF_FILE=conf/s1.conf;conf/s2.conf" \
     "-DEXTRA_DTC_OVERLAY_FILE=boards/s2.overlay"
   ```

   CI uploads no image, and a tooling test fails if a workflow uploads an artifact, so the image has to be
   built where the board is. [try-on-native-sim.md](try-on-native-sim.md) gives the CI commands for a local `native_sim` run
   and not for a board image; building that image locally is not covered here. For the S2 runs, the image was approved by its SHA-256 hash,
   a local rebuild gave that hash and two local builds were byte-identical (as the S2 note records). Proposed:
   do the same, and stop if the hash of the image to be programmed is not the approved one. Should show:
   `zephyr.bin` and `zephyr.meta` exist in `crux-controller/build/s2/zephyr` (the CI job checks both).

2. **Identify the board before anything is written.** Proposed: read the board's current image and compare
   it with the accepted normal image. The S2 note records status `IDENTIFIED`, matching the accepted normal
   image, and a read-back that said `Verify successful.`. Should show: the board is the expected board and
   holds the expected image.

3. **Program the S2 image and start it.** Proposed: with the project owner's explicit yes immediately before
   the board is overwritten, and a guard check before each probe step (the S2 note records both for its runs).
   Should show: the image is loaded, verified and started (status `M5_PROGRAMMED_VERIFIED_STARTED` in the S2
   note).

4. **Observe the log lines.** Capture the UART for a fixed window; the S2 runs used 180 seconds. Open the
   capture before the load only if you accept that its first lines belong to the previous image (the S2 note,
   friction 2). Should show, from the S2 note: lines of the S2 image with Zephyr's `[hh:mm:ss.mmm,uuu]`
   timestamps, `workload:` lines `cycle=10` to `cycle=1750` in steps of 10 (the first at about 4.8 seconds
   of uptime in run 2, which says this was as in run 1), and `net:` lines. With no peer listening, `net: exchange failed cycle=<n>
   result=-2` is the expected line, one per message; the S2 image logs no link line.

5. **Check the link and ping from the host.** Should show, from the S2 note: the host adapter's interface
   reports `status: active` and `100baseTX <full-duplex>`, there is a host route to `192.168.77.2`, and ping
   is answered 5 of 5 times. The board answers ARP with the MAC from its devicetree
   (`02:43:52:55:58:20`).

6. **One TCP exchange.** Start the host peer once, for one exchange, on `192.168.77.1:42420`. Should show:
   the peer records a connection from `192.168.77.2` and echoes the 8 bytes, and the board logs
   `net: exchange ok cycle=<n>`. The S2 note says this exchange was informational and not a pass criterion;
   proposed: keep it that way.

7. **Restore the accepted normal image.** Program it back, verify it, verify it again with a read-only step,
   start it, and capture its boot line for a short window (the S2 note used 15 seconds). Should show: the
   boot identity line of the accepted normal image. One accepted diagnostic is recorded: the probe tool
   printed `****** Error: Could not start CPU core. (ErrorCode: -1)` after a successful load and verify, and
   the run's rules accepted exactly that when the exit status was 0 and the read-back succeeded. Do not
   widen it to other errors. The board is not left in a bring-up state until this step succeeds.

8. **Record.** Write down the revision of this repository and of `crux-pilot`, the image hash, the board
   and bench, each step's result, every failure and every skipped step. Say that two boots on one bench are
   evidence collection and not qualification, as the S2 note does. Do not report anything that was not run as
   passing.

## Other images

Only the S2 image has a recorded board run. This outline does not cover the others.

- **S3** keeps a record in a file on a microSD card. It was never run on a board and no card was used. It
  needs a card with a directory named `files` (`app/Kconfig`).
- **S5** sets the Crux Time clock from an SNTP server, by default `192.168.77.1` (the S2 peer). It was never
  run on a board. A run would need a responder for SNTP (UDP port 123) on the host peer; this page does not
  describe one.
- **S6** serves HTTPS management on `192.168.77.2` port 443 with a certificate that the board makes for itself. It was
  never run on a board. The image has no account, so nobody could log in, and nothing persists across a reset because the
  medium is a RAM disk. This page does not describe a run of it.
- **S4** is described below.

### S4 needs supervision

S4 has never run on a board (`docs/findings/s4-system-composition.md`). It starts a hardware watchdog and
feeds it from the workload's producer thread. For the default 100 ms cycle the interval is 2000 ms. The
finding's friction 7 records the risk: the watchdog is armed before the workload starts, so if the workload
start fails, or the producer thread ends, nothing feeds it, the board resets, and because no reset cause
stops the product from arming it again, it would keep resetting. The finding marks this **Open**, because no
board has run it, and says: "Any future board run must be supervised and time-limited."

So an S4 board run, if it is ever authorised, must be supervised by a person who is present, with a time
limit and a way to stop it decided and written down before the board is programmed. Proposed: also write
down, beforehand, what a reset loop looks like in the capture (the boot lines repeat and the uptime restarts)
and what the operator does then. How to stop a reset loop on the bench is not recorded in this repository.

## Stop conditions

Stop and do not continue to the next step if any of these happens. The first column says where the item
comes from.

| Source | Stop when |
|---|---|
| Proposed | There is no explicit authorisation for the current task, or it does not cover the step. |
| Proposed | The target, probe or flash configuration is not what was verified, or you are unsure which board or probe is attached. |
| Proposed | The hash of the image to be programmed is not the approved one. |
| S2 note, identify step | The board's current image does not match the accepted normal image, or the read-back does not say `Verify successful.`. |
| S2 note, restore | A probe tool error other than the one accepted diagnostic above, or a non-zero exit status. |
| Proposed | The program step does not report the image as loaded, verified and started. |
| S4 note, friction 7 | The log shows boot lines repeating with the uptime restarting, or no log at all, after the image should have started. Treat it as a reset loop. |
| Proposed | The capture has gaps or non-ASCII bytes that the S2 runs did not have (they had none), so that the evidence cannot be trusted. |
| Proposed | The link does not come up, or ping is not answered, within the window. Record it as a finding; do not retry in a loop. |
| Proposed | Anything on the bench behaves unexpectedly: heat, smell, a probe that disconnects, or a power supply that drops. |
| S2 note, restore | The accepted normal image cannot be restored and verified. Leave the board as it is, record the state, and ask the project owner. |
| Proposed | The time limit of the run is reached. |

Stopping is not failing. A stopped run with an honest record is worth more than a completed run with a
doubtful one.

## What this page does not cover

- Anything that needs authorisation, including the programming, reset and power operations themselves.
- A qualification, a performance measurement, or the physical behaviour of the board beyond what the S2 note
  records.
- Any image other than S2 (S3, S4, S5 and S6 are mentioned above only to say they have not run).
- A cold power cycle. The S2 note lists it as not shown: its runs restarted the image by programming and
  reset.
