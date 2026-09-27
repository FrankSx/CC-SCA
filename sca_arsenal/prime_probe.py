"""
Prime+Probe (Liu et al. 2015; Osvik-Shamir-Tromer 2006).

Monitor LLC sets via an eviction buffer. Unlike Flush+Reload this needs no
shared memory — only co-residency on the same physical core / LLC.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Sequence

import numpy as np

from . import eviction, timing


@dataclass
class SetActivity:
    set_id: int
    mean_latency: float
    p95_latency: float
    active: bool


class PrimeProbe:
    def __init__(self, n_pages: int = 4096):
        self.buf = eviction.new_probe_buffer(n_pages)
        self.threshold = None
        self.baseline: Dict[int, float] = {}

    def calibrate(self):
        hit, miss = eviction.calibrate_threshold(self.buf)
        self.threshold = (hit + miss) / 2.0
        return hit, miss, self.threshold

    def monitored_pages(self) -> List[int]:
        return eviction.candidate_pages(self.buf)

    def prime_all(self):
        eviction.prime_set(self.buf, self.monitored_pages())

    def probe_all(self) -> List[int]:
        return eviction.probe_set(self.buf, self.monitored_pages())

    def snapshot_baseline(self, rounds: int = 20):
        """Baseline per-page latency when the system is (hopefully) idle."""
        if self.threshold is None:
            self.calibrate()
        pages = self.monitored_pages()
        agg = {p: [] for p in pages}
        for _ in range(rounds):
            eviction.prime_set(self.buf, pages)
            for p, lat in zip(pages, eviction.probe_set(self.buf, pages)):
                agg[p].append(lat)
        self.baseline = {p: statistics.median(v) for p, v in agg.items()}

    def monitor_window(self, victim=None, rounds: int = 1) -> List[SetActivity]:
        """
        Prime -> (optional victim window) -> Probe. Returns per-set activity.
        Pages whose reload latency exceeds baseline+threshold are 'active'.
        """
        if not self.baseline:
            self.snapshot_baseline()
        pages = self.monitored_pages()
        acts = []
        deltas = []
        for _ in range(rounds):
            eviction.prime_set(self.buf, pages)
            if victim is not None:
                victim()
            lat = eviction.probe_set(self.buf, pages)
            deltas.append([l - self.baseline[p] for p, l in zip(pages, lat)])
        med_delta = [statistics.median([d[i] for d in deltas]) for i in range(len(pages))]
        for p, md in zip(pages, med_delta):
            acts.append(SetActivity(p, self.baseline[p] + md, 0, md > self.threshold))
        return acts

    def trace(self, samples: int, interval_ns: int = 0, victim=None) -> List[List[int]]:
        """
        Time-series of active-set bitmaps (one list of set-ids per sample).
        """
        out = []
        for _ in range(samples):
            acts = self.monitor_window(victim)
            out.append([a.set_id for a in acts if a.active])
            if interval_ns:
                t0 = timing.now_ns()
                while timing.now_ns() - t0 < interval_ns:
                    pass
        return out
