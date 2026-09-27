# Defenses Mapped to Attacks

| Attack | Primary mitigations |
|---|---|
| Flush+Reload | Don't share pages across trust boundaries (no MAP_SHARED secrets, disable KSM cross-tenant, per-tenant shared-library copies). Cache partition (Intel CAT/AMD QoS) shrinks the shared resource to nothing. |
| Prime+Probe | CAT/MBA partitioning; cache-aware scheduler placement; hugepages reduce set aliasing; constant-time code for crypto. |
| Flush+Flush | As Flush+Reload; also `clflush` is privileged-ish on some ARM — x86: partition. |
| Evict+Time | Constant-time implementations; masking/blinding; jitter hurts signal but prefer real constant-time. |
| Rowhammer | DDR5 + TRR/target-row-refresh; ECC (single-error-detect at minimum); `vm.rowhammer_kmitigation`-style throttling; MADV_DONTNEED promptly; physical-memory quotas per tenant. |
| KSM channel | Disable KSM in multi-tenant hosts (`echo 0 > /sys/kernel/mm/ksm/run`); if required, `stable` pages and per-tenant KSM groups. |
| GPU contention | vGPU time-slicing, MIG (NVIDIA) partitions, memory-bandwidth allocation; treat device timing as untrusted. |
| Stego/polyglot carriers | Strip unknown chunks at ingress; re-encode images (lossy re-encode kills LSB stego); entropy analysis on LSB planes; block `waSM`-like ancillary types at the WAF/CDN. |
| Covert channels | The only robust fix is eliminating the shared resource — bandwidth caps + cache partitioning reduce but do not eliminate; egress filtering catches the exfil half. |

## Detection

- Perf counters: anomalous `clflush` rates (`cpu/event=0x0,umask=0x0` /
  architectural `CLFLUSH` events) from one tenant.
- LLC miss-rate spikes correlating across cgroups.
- DNS query entropy (label-pattern chunking in `exfil.py` produces very
  regular `xxxx-<base32>` labels).
