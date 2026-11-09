# Finding: step S2 ran once on a board (9 November 2026)

Status: the S2 image ran **once** on one RT1060-EVKB Rev B, and the board was then restored to the
accepted normal image. This note says what that one run shows and what it does not show.

Every statement is labelled **Measured** (a tool of the run printed it, or it follows by counting in
the raw capture of the run, which is kept privately and is not published here) or **Not shown**.
Crux Controller is the official reference consumer firmware of Crux and is not a mandatory exit
criterion of any Crux milestone; this run is supporting evidence at most.

## What ran

| Item | Value |
|---|---|
| Image | S2 `zephyr.bin`, SHA-256 `e7c588c79c31d113ef3b0464731f17dfb4cc453874831b8bc20f9dd7da55b56c`, 103,180 bytes |
| Firmware identity | `8493243091295c6d9ec305b6e5b097df738ee226550394a5ab0fdac388f73164` |
| Source | `crux-controller` `d123620` (main after pull request 28), with `crux-pilot` pinned at `37c92b18` |
| Board | NXP RT1060-EVKB Rev B |
| Network | board static IPv4 `192.168.77.2/24`, no gateway; host peer `192.168.77.1:42420`; the board's locally administered MAC from the devicetree is `02:43:52:55:58:20` |
| Reviewed driver | the `crux-pilot` target test driver at `3b2dce56` (the merges of pull requests 352 and 353) with its S2 image profile: one start, a raw passive UART capture of 180 s |
| Restored afterwards | the accepted normal image, BIN SHA-256 `ad729684749181f0c26853828550187a2c3e60dbb28cf3ee2194a7984141e02f`, 107,872 bytes |

The S2 hash is the one that CI printed for this source and pin, and that the local rebuild
reproduced before the run (Measured by the preparation of the run; not re-measured here).

## Results

| What | Result | Label |
|---|---|---|
| Identify, before anything was written | status `IDENTIFIED`, matching the accepted normal image; the read-back said `Verify successful.` | Measured |
| Program | status `M5_PROGRAMMED_VERIFIED_STARTED`: the S2 image was loaded, verified and started | Measured |
| UART capture | 41,527 bytes, 484 lines, 0 non-ASCII bytes, 0 gaps in the host's polling (threshold 0.25 s), no reader failure, window of 180 s | Measured |
| Link | the host adapter's interface reported `status: active`, `100baseTX <full-duplex>`, and a host route to `192.168.77.2` on that interface | Measured |
| Ping | 5 packets sent, 5 received, 0.0 % loss; round trips 1.628, 0.858, 1.756, 1.273, 1.757 ms; min/avg/max/stddev 0.858 / 1.454 / 1.757 / 0.347 ms | Measured |
| ARP | `192.168.77.2` at `2:43:52:55:58:20` (the host prints the MAC without leading zeros) | Measured |
| One TCP exchange | the host peer, started once for one exchange, accepted a connection from `192.168.77.2` and recorded request and response `000000fa5a5a5aa0`, `echoed: true`; the board logged `net: exchange ok cycle=250` | Measured |
| `net: exchange failed ... result=-2` | 174 lines, from `cycle=10` (uptime 6.097 s) to `cycle=1750` (uptime 2:58.810), one for every message cycle in the window except cycle 250 | Measured |
| Restore | status `NORMAL_RESTORED_VERIFIED_STARTED`; the normal image was loaded and verified (`Verify successful.`), verified again by a read-only step, and started; the 15 s capture after the start shows `M3_BOOT source=ec94fbec22cd profile=integrated`, which is the boot identity line of the accepted normal image | Measured |
| Offline replay of the capture | the replay record says `status: PASS` for its default state. The files do not say what its oracle asserts for an S2 image, so this note builds nothing on it | Measured, not interpreted |

### The `result=-2` lines

The workload sends one message about every second (every tenth 100 ms cycle). Each message is one
TCP exchange: connect, send 8 bytes, expect the same 8 bytes back. `result=-2` is an immediate
connect failure. In the capture they appear before the peer existed, and they are the expected
outcome when nothing listens at `192.168.77.1:42420`. The peer was started once, about 29 s after the
board's boot, for exactly one exchange; the first message after that, at cycle 250 (uptime 28.812 s),
succeeded. The peer then stopped by design (`exchanges_done: 1`), and every later message failed
with `result=-2` again until the window ended. The 174 lines are therefore not a link fault; they
are what the board logs when no peer listens. The TCP exchange was **informational** and was not a
pass criterion of the run.

## Main finding

**The S2 image brought the Ethernet link up without the MDIO correction that the Crux sample applies, in
this run.** The image carries no such correction. The host saw the link active at 100 Mbit/s full
duplex, ping was answered 5 of 5 times at the static address, and the board answered ARP with the
MAC from its devicetree. One TCP exchange with the host peer was echoed.

This is **one boot of one board in one run**. It is not repeatability and it is not a statement
about the PHY, the board design or the correction in general.

## Friction

1. **The restore's first step ends with the accepted J-Link diagnostic.** In the load step the
   probe tool loaded and verified the normal image (`Verify successful.`, exit status 0) and then
   printed `****** Error: Could not start CPU core. (ErrorCode: -1)` as the last line. The run's
   rules accept exactly this diagnostic when the exit status is 0 and the read-back succeeded, as in
   an earlier platform stage; the run record keeps it as an accepted diagnostic, and the later
   read-only verify and the start step both completed.
2. **The capture opens before the load.** The raw capture was opened 9.2 s before the S2 image was
   started (the marks of the run: opened, window-start, stopped). Its first 10,435 bytes (134 lines)
   come from the previous image: they are `M3_` status lines and a thread-analysis block, with
   uptimes of the previous image (for example `monotonic_ms=369009`), and none of them has the
   Zephyr log timestamp format `[hh:mm:ss.mmm,uuu]` that every line of the S2 image has. The S2
   image's own lines start after that mark. Counts of the capture above include these lines.
3. **A shell word-splitting error on the host, once, before the first tool run.** The operator's
   command was rejected by the shell (`command too long`), the driver did not start and nothing ran;
   the same command was then run as a plain command line. It did not affect the board.

## Not shown

- Run-time values of S2: stack use, CPU use and timing beyond what the log lines literally print.
- Repeatability: the link, ping or exchange on a second boot, another board or another cable.
- Behaviour after the 180 s window.
- Whether the link comes up the same way after a cold power cycle; the run restarted the image by
  programming and reset.
- An exchange that is repeated, or an exchange when the peer is slow or restarts.
- Anything about the S3 image, microSD, or the release bundle: they did not run.

## Method

The owner approved one run of a written plan for this image, hashes and capture time. The plan was
reviewed independently before it was approved. An operator then ran only the reviewed driver in
four gated steps (identify, program, host checks, restore), each started only after the owner's
go-ahead and a host-side guard check, and the normal image was restored and verified at the end.
The evidence of the run (host command output, probe logs, the raw capture, the peer record) is
kept privately; this note quotes only what those files print and states the hashes above so that
the images can be recognised.

Sources that are public: `crux-controller` main at `d123620` (including pull request 28),
`crux-pilot` at `37c92b18` for the pinned build and `3b2dce56` for the driver (pull requests 352 and
353).
