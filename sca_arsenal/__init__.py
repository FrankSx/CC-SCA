"""
sca_arsenal — Cross-Container Side-Channel Attack Research Toolkit

Modules
-------
timing        cycle-accurate clock abstraction (native rdtsc w/ fallback)
eviction      cache eviction set construction & probing primitives
flush_reload  Flush+Reload shared-memory attack
prime_probe   Prime+Probe LLC set monitoring
flush_flush   Flush+Flush low-noise variant
evict_time    Evict+Time
rowhammer     DRAM rowhammer flip hunting
ksm           KSM page-merge detection (memory dedup side channel)
gpu_snooper   GPU/CPU memory contention observation
coresidency   co-residency detection & container recon
covert_channel cache-based covert channel (framing + CRC + repetition)
stego         LSB steganographic payload embed/extract
polyglot      PNG carrier generation with custom WASM chunk
exfil         exfiltration encoders (DNS label chunking etc.)
report        audit trail / evidence JSON generation

Authorized security research only. See README.md.
"""

__version__ = "1.0.0"

from . import timing  # noqa: F401
from . import report  # noqa: F401
