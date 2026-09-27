# Cache Covert Channel

`covert_channel.py` implements a complete, framed channel over a shared
cache line.

## Wire format

```
frame = SYNC(0xA5) | LEN(1B) | PAYLOAD(LEN) | CRC16-CCITT(payload)
bit   = '1' → transmitter touches line during slot
        '0' → transmitter idles during slot
```

Repetition coding: each bit sent `rep` times, majority vote at receiver.

## Between processes

Use `mmap.mmap(fileno, size, flags=mmap.MAP_SHARED)` on a `shm_open` fd
(or any shared file). Both processes map the **same physical page** ⇒ the
line is genuinely shared; Flush+Reload applies directly. In containers,
share via a shared volume bind-mounted file, or rely on KSM merging
identical pages (then `ksm.py` tells you merging happened first).

Cross *host* boundaries need a different medium (see `exfil.py` for DNS
label chunking and timing-pattern encoders).

## Tuning

| Symptom | Fix |
|---|---|
| CRC failures | increase `--slot-ns` (200 µs → 500 µs), increase `--rep` to 3 |
| Sync never found | verify shared mapping (`os.getpid()` maps, same file), slower slots |
| Everything '1' | threshold miscalibrated — re-run `fr-calibrate` on the quiet host |
| Everything '0' | victim line not actually shared, or slot too short for touch to stick |

## Capacity

With 200 µs slots and rep=1: ~5 kb/s raw, ~2.5 kb/s effective after framing
and CRC overhead — plenty for keys, tokens, and env dumps.

## Troubleshooting — nine failure modes found during bring-up

Each entry: symptom → root cause → fix (all implemented in `covert_channel.py`).

| # | Symptom | Root cause | Fix |
|---|---------|-----------|-----|
| 1 | Eviction sets never conflict | numpy arrays aren't page-aligned; candidates weren't 4096B apart | Over-allocate one page, slice to aligned base (`eviction.new_probe_buffer`) |
| 2 | RX reads all zeros, TX "sent" everything | TX burst ran during RX threshold calibration; RX's own `clflush` wiped the line before sampling | `threading.Event` handshake: RX fully armed before TX starts |
| 3 | Every bit shifted by one | Sampling at slot start reads the *previous* bit's touch (pipeline delay) | Sample at end of slot / mid-interval on absolute grid |
| 4 | Whole frame bursts into one instant | Busy-wait with bare `pass` holds the GIL; TX runs all bits in one scheduler slice | `time.sleep(0)` yields inside every wait loop |
| 5 | TX touch intervals 507µs…2054µs at 200µs slots | `time.sleep` timer slack (~100µs+) and vCPU steal smear wall-clock slots | Busy-wait on shared `now_ns()` clock, never `time.sleep` for pacing |
| 6 | Every window votes '1' even for '0' bits | "Read-only" sub-sampling self-fills: a load that *misses* also *fills* the line, so later sub-samples always hit | Flush **before every** sub-sample |
| 7 | Late frame bits all read '0', header fine | Loop-relative TX pacing: '1' slots do more work, TX lags one window per mark, cumulative | Absolute schedule: `win_end = t0 + (idx+1)*slot` from frame start |
| 8 | '0' bits with 3–4 hits mid-frame | Loop-relative RX waits can only run long; sub-samples spilled into the next bit's carrier | Absolute sub-sample deadlines on the anchor grid |
| 9 | `--rep 2` decodes garbage | TX stretches bit period to `slot_ns*rep` but RX sampled at `slot_ns` — grid mismatch | RX uses `slot_ns * rep` |

Cross-cutting environmental notes (this toolkit was brought up on a Kata/
Alibaba Cloud ACK pod, 2 vCPUs at 1.5-CPU quota):

- **Cross-vCPU loads never hit** (~250–300c regardless of touch — vCPUs
  don't share a discriminable L3). Unpinned demos are hopeless on VMs;
  `--pin` binds both threads to one vCPU so they share L1. Real
  cross-process attacks must target a genuinely shared LLC.
- **vCPU steal breaks fixed-phase sampling**; the hunt-anchored receiver +
  CRC retries (5 attempts) absorb it. On bare metal, attempt 1 passes at
  100–200µs slots; on virtualised hosts use ≥1ms slots.
- **Calibration is per-host**: 46c hit / 248c miss on the bring-up box.
  Never hardcode thresholds; always run `fr-calibrate` first.
