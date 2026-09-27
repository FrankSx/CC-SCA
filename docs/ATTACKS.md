# Attack Reference

All cycle numbers are indicative for a modern x86-64 server part
(~2.5–3.5 GHz TSC). **Calibrate on your target — never hardcode thresholds.**

## Flush+Reload (`flush_reload.py`)

**Prerequisite:** a shared physical page between spy and victim
(`mmap MAP_SHARED`, shared library, KSM-merged page).

1. Calibrate: `calibrate_threshold()` → median hit vs median miss, midpoint
   is your decision boundary. Typical split: hit ≈ 40–90 cyc, miss ≈ 200–350 cyc.
2. Spy loop: `clflush(addr)` → victim window → `time_load(addr)`.
   Load below threshold ⇒ victim touched the line.
3. Resolution: single cache line (64 B). Bandwidth: high; noise: low.

**Limits:** needs sharing; SMT siblings and frequency scaling skew timings;
`clflush` itself is observable (see Flush+Flush defense notes).

## Prime+Probe (`prime_probe.py`, `eviction.py`)

**Prerequisite:** co-residency only — no shared memory.

1. Build eviction sets per LLC set with group testing
   (`build_eviction_set`), or approximate with 4 KiB-strided pages.
2. Prime: touch every line of your eviction set.
3. Victim window.
4. Probe: reload each line; latency spike ⇒ victim used that set.
5. Resolution: one LLC set (associativity × 64 B, typically 12–20 lines).
   Use `snapshot_baseline()` + deltas to suppress background noise.

**Tuning:** more monitored pages ⇒ wider coverage, slower rounds. Track
deltas vs baseline, not absolute latency.

## Flush+Flush (`flush_flush.py`)

Like Flush+Reload but times the `clflush` itself — faster when the line is
cached. Works on **read-only** shared targets (e.g. victim's code pages in a
shared library). Lower bandwidth, much lower noise, no data access needed.

## Evict+Time (`evict_time.py`)

Measure the victim's *operation* while our buffer holds the cache vs not.
Coarse (whole-operation granularity) but needs no eviction sets and is very
stealthy. Useful for binary "did the victim branch/cache this" questions.

## Rowhammer (`rowhammer.py`)

Double-sided: hammer rows N and N+2, sweep row N+1 for flips.
- Row size: auto-detect from DIMM if possible; `0x10000` (64 KiB) is a sane
  DDR4 starting guess.
- Root + `/proc/self/pagemap` enables physical/bank-aware placement; without
  it we fall back to linear guessing (much lower flip rate).
- Expect zero flips on DDR5 with TRR and on most ECC systems — that's the
  point of running it: to *verify* mitigations.

**Safety:** run on lab machines only. Machine-check exceptions possible.

## KSM (`ksm.py`)

1. Create page with candidate content, `madvise(MADV_MERGEABLE)`.
2. Wait for `ksmd` scan.
3. Measure single-byte write latency (COW-break when merged ⇒ slower).
Compare vs a private page. Leaks: "this content exists in another
container" — powerful when content is a known library page or key schedule.

## GPU contention (`gpu_snooper.py`)

Host memory bench (strided walk) with GPU idle vs under OpenCL matmul load.
Delta ⇒ co-tenancy / memory-bus sharing. With `pyopencl` you can instead
time *device-side* allocations to spot neighbours on the same card.

## Co-residency scan (`coresidency.py`)

Prime+Probe noise floor (active-set ratio) + `/proc/1/cgroup`, `cpu.max`,
`/.dockerenv` fingerprinting. Output: `low/medium/high` probability plus the
container runtime guess.
