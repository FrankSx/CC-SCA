#!/usr/bin/env python3
"""Prime+Probe: baseline the LLC, then run a noisy victim workload and
report which sets lit up."""
import sys
sys.path.insert(0, "..")
import numpy as np
from sca_arsenal import prime_probe

pp = prime_probe.PrimeProbe(n_pages=4096)
hit, miss, thr = pp.calibrate()
print(f"[*] threshold={thr:.0f} cycles (hit={hit:.0f} miss={miss:.0f})")

pp.snapshot_baseline(rounds=20)

def victim():
    a = np.random.rand(512, 512)
    _ = a @ a            # hammers LLC sets

acts = pp.monitor_window(victim=victim, rounds=3)
active = [a for a in acts if a.active]
print(f"[+] victim activity detected on {len(active)}/{len(acts)} monitored pages")
for a in active[:12]:
    print(f"    page elem {a.set_id:#x}: +{a.mean_latency - pp.baseline[a.set_id]:.0f} cycles")
