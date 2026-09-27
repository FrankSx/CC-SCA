# sca-arsenal

**Cross-Container Side-Channel Attack Research Toolkit** — a standalone,
installable Python package extending the SCA proof-of-concept from the
WorldVQA/SCA research repo into a full toolkit: native x86-64 cache timing
primitives, four cache attacks, Rowhammer, KSM and GPU contention channels,
a framed cache covert channel, and steganographic/polyglot carriers.

> ⚠️ **Authorized security research only.** Every module targets shared
> microarchitectural state. Run only on hardware you own or are explicitly
> authorized to test. Rowhammer in particular can destabilise a machine.

## Install

```bash
pip install .            # builds the native rdtsc/clflush extension
pip install .[image,gpu,dev]
```

Without a C compiler the package still installs (pure-Python fallbacks are
used), but single-cache-line discrimination needs the native module.

## Components

| Module | Attack / Capability |
|---|---|
| `sca_arsenal.timing` | Serialised `rdtsc`, `clflush`, timed loads (native + fallback) |
| `sca_arsenal.eviction` | Cache geometry, eviction-set construction, prime/probe primitives |
| `sca_arsenal.flush_reload` | Flush+Reload on shared pages (Yarom & Falkner 2014) |
| `sca_arsenal.prime_probe` | Prime+Probe LLC set monitoring (OST 2006 / Liu 2015) |
| `sca_arsenal.flush_flush` | Flush+Flush low-noise variant (Gruss 2016) |
| `sca_arsenal.evict_time` | Evict+Time (Tsunoo 2002 / Tromer 2010) |
| `sca_arsenal.rowhammer` | DRAM flip hunting (Kim 2014), root-aware via pagemap |
| `sca_arsenal.ksm` | KSM page-merge timing side channel |
| `sca_arsenal.gpu_snooper` | GPU→host memory contention observation (OpenCL optional) |
| `sca_arsenal.coresidency` | Co-residency detection + container runtime fingerprinting |
| `sca_arsenal.covert_channel` | Framed cache covert channel: SYNC/LEN/CRC16 + repetition coding |
| `sca_arsenal.stego` | 6-bit/pixel RGB-LSB payload embed/extract (`SCA1` header) |
| `sca_arsenal.polyglot` | PNG+`waSM`-chunk WASM carrier, defender chunk scanner |
| `sca_arsenal.exfil` | DNS-label chunking, timing-pattern encoding, framed streams |
| `sca_arsenal.report` | Engagement audit trail (JSON evidence) |

## Quick start

```bash
sca-arsenal info                 # native capabilities + container fingerprint
sca-arsenal fr-calibrate         # hit/miss threshold for your CPU
sca-arsenal fr-spy --iterations 2000
sca-arsenal pp --pages 8192      # watch LLC set activity live
sca-arsenal scan                 # co-residency probability
sca-arsenal covert --message "hello cache" --slot-ns 300000 --rep 3
sca-arsenal polyglot module.wasm out.png
sca-arsenal stego-embed carrier.png payload.json carrier_stego.png
sca-arsenal ksm --content "secret-page-content"
sca-arsenal hammer --mb 256 --hammers 500000   # destructive; lab only
```

## Programmatic use

```python
from sca_arsenal import flush_reload, covert_channel, report

sp = flush_reload.SharedPage()
thr, hit, miss = flush_reload.calibrate_threshold(sp.mm)
spy = flush_reload.FlushReloadSpy(sp.mm, threshold=thr)
res = spy.spy_window(1000, victim=lambda: target_function())
print(res.hit_ratio)

# covert channel demo (see examples/ for process-to-process via MAP_SHARED)
got = covert_channel.transfer(sp.mm, b"exfil me", slot_ns=300_000, rep=3)

log = report.AuditLog(engagement="lab-2026-q3")
log.record("flush_reload", {"iterations": 1000}, res.as_dict())
log.save("audit.json")
```

## Repository layout

```
sca-arsenal/
├── sca_arsenal/          # the package (14 modules + native C source)
├── examples/             # runnable demos for each attack family
├── tests/                # unit tests (stego, polyglot, covert codec, eviction)
├── docs/
│   ├── ATTACKS.md        # per-attack theory, parameters, expected output
│   ├── COVERT_CHANNELS.md# covert channel protocol + tuning guide
│   └── DEFENSES.md       # mitigations mapped to each attack
├── setup.py              # builds _native C extension
└── pyproject.toml
```

## Relationship to the SCA HTML audit platform

The HTML platform (`sca_cross_container_audit.html`) is the browser-side
story: polyglot PNG → canvas LSB decode → Pyodide micro-code. This package
is the host/native-side counterpart — it produces the carriers
(`polyglot`, `stego`) and executes the real cache/DRAM attacks that the
browser layer can only simulate. Same wire formats: `SCA1` stego header,
`waSM` chunk type, and the micro-code JSON schema.

## Defenses

See `docs/DEFENSES.md`. TL;DR: cache partitioning (Intel CAT/AMD QoS),
hugepages + row-limiting mitigations, KSM disabled or `stable` advisories,
and stego/chunk scanning at your CDN/WAF ingress.

## License

MIT — see LICENSE. Use responsibly.

## Development & CI

```bash
pip install -e .[dev]
python -m unittest discover tests
```

GitHub Actions builds the native extension on Linux/macOS across Python
3.9–3.13 and runs the unit suite on every push; tags trigger a cibuildwheel
run + PyPI/GitHub release (see `.github/workflows/`).

### Analyzing traces from other hosts

`tools/decode_trace.py` decodes a recorded JSON trace of per-window load
latencies into the framed payload — useful for validating captures taken
on targets where you can't run Python, or for teaching:

```bash
python tools/decode_trace.py capture.json --auto-threshold
```
