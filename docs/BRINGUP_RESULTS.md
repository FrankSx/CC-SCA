# Bring-up Results — Live Validation Log

Every result below was produced by actually executing the tool on the
bring-up host (Kata Containers pod on Alibaba Cloud ACK, 2 vCPUs,
1.5-CPU cgroup quota, Linux x86-64). Numbers are host-specific; always
re-calibrate (`fr-calibrate`) on your target.

## Timing environment

| Metric | Value |
|---|---|
| Flush+Reload hit (L1) | 46–90 cycles |
| Flush+Reload miss (DRAM) | ~248–300 cycles |
| Decision threshold | 147–183 cycles (per-run calibrated) |
| Cross-vCPU load | 250–300 cycles **regardless of touch** (no shared L3 domain) |
| vCPU steal effect | multi-ms scheduling gaps; kills fixed-phase protocols |

## Validated demos

| Demo | Command | Result |
|---|---|---|
| Flush+Reload bit recovery | `examples/flush_reload_demo.py` | pattern `[1,0,1,1,0,0,1,0]` recovered exactly |
| Idle spy | `sca-arsenal fr-spy` | 0/2000 hits — correctly reports no victim |
| Covert channel (rep=1) | `sca-arsenal covert --message "cache hello" --slot-ns 1000000 --pin` | `"cache hello"` received, CRC ok |
| Covert channel (rep=2) | `sca-arsenal covert --message "sca-arsenal v1.0" --rep 2 --pin` | `"sca-arsenal v1.0"` received, CRC ok |
| Prime+Probe monitor | `sca-arsenal pp --pages 4096` | 4/4096 sets active; latency spikes to 5834c on steal |
| Evict+Time | `sca-arsenal evict-time` | evicted +66.5µs vs cached (100 runs) |
| Co-residency scan | `sca-arsenal scan` | runtime=kubernetes (kubepods cgroup), quota 150000/100000, co-residency **low** |
| Polyglot carrier | `sca-arsenal polyglot m.wasm out.png` | valid PNG, wasm round-trip ok, `waSM` flagged non-standard |
| Stego carrier | `stego.embed_file`/`extract_file` | 993-byte payload round-trip exact |
| KSM probe | `sca-arsenal ksm` | no measurable merge in container (KSM not enabled — honest null result) |
| Unit tests | `python3 -m unittest discover tests` | 15/15 OK |

## Key bring-up facts

1. **The covert channel passes end-to-end on a steal-prone virtualised
   host** — but only with the full robustness stack: sustained-carrier TX,
   flush-per-sample RX, hunt-anchored phase lock, absolute-grid scheduling
   on both sides, and CRC-gated retries. See COVERT_CHANNELS.md's
   troubleshooting table for the nine failure modes that each component
   addresses.
2. **Unpinned operation is impossible on this class of VM**: cross-vCPU
   loads never hit, so there is no threshold that separates touched from
   untouched. `--pin` collapses both peers onto one L1 domain.
3. **Rowhammer was NOT executed** on the bring-up host (shared cloud
   infrastructure — would be both ineffective through the hypervisor and
   irresponsible). The module is code-reviewed and unit-tested but its
   flip-hunt is unverified; run it only on owned bare metal.
