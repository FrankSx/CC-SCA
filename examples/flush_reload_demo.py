#!/usr/bin/env python3
"""Flush+Reload demo: spy watches a shared line while a 'victim' touches it
with a chosen bit pattern. Run: python examples/flush_reload_demo.py"""
import sys, time
sys.path.insert(0, "..")
from sca_arsenal import flush_reload, timing

sp = flush_reload.SharedPage()
thr, hit, miss = flush_reload.calibrate_threshold(sp.mm)
print(f"[*] calibrated: threshold={thr:.0f} hit={hit:.0f} miss={miss:.0f}")

PATTERN = [1, 0, 1, 1, 0, 0, 1, 0]
spy = flush_reload.FlushReloadSpy(sp.mm, threshold=thr)

def victim(i):
    def _v():
        if PATTERN[i]:
            timing.touch(spy.addr, 8)
    return _v

recovered = spy.spy_window(len(PATTERN), victim=lambda: None)
print(f"[*] idle window: hit_ratio={recovered.hit_ratio:.2f} (expect ~0)")

bits = []
for i in range(len(PATTERN)):
    spy2 = flush_reload.FlushReloadSpy(sp.mm, threshold=thr)
    res = spy2.spy_window(1, victim=victim(i))
    bits.append(1 if res.hit_ratio > 0.5 else 0)
print(f"[+] pattern={PATTERN}")
print(f"[+] recovered={bits}")
print("[+] MATCH" if bits == PATTERN else "[-] mismatch")
