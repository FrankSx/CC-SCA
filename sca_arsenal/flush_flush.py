"""
Flush+Flush (Gruss, Maurice, Wagner, Mangard 2016).

Instead of timing a reload, time the clflush instruction itself — it is
faster when the line is present. Lower noise than Flush+Reload, works
without accessing the data (read-only shared libs become viable).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List

from . import flush_reload, timing


@dataclass
class FFResult:
    cached_ratio: float
    threshold_cycles: float
    samples: int


def _time_flush(addr: int) -> int:
    T = timing
    t0 = T.rdtsc()
    T.clflush(addr)
    t1 = T.rdtsc()
    return t1 - t0


def calibrate_threshold_ff(mm, offset: int = 0, samples: int = 3000):
    T = timing
    if not T.native_available():
        raise RuntimeError("requires native extension")
    addr = flush_reload.ctypes_address(mm) + offset
    cached, flushed = [], []
    for _ in range(samples):
        T.touch(addr, 8)
        cached.append(_time_flush(addr))
        flushed.append(_time_flush(addr))  # now uncached
    c = statistics.median(cached)
    f = statistics.median(flushed)
    return (c + f) / 2.0, c, f


class FlushFlushSpy:
    def __init__(self, mm, offset: int = 0, threshold: float = None):
        self.mm = mm
        self.addr = flush_reload.ctypes_address(mm) + offset
        self.threshold = threshold if threshold is not None else calibrate_threshold_ff(mm, offset)[0]

    def classify(self) -> bool:
        """True if the line was cached (victim touched it)."""
        return _time_flush(self.addr) <= self.threshold

    def spy_window(self, iterations: int, victim=None) -> FFResult:
        hits = 0
        for _ in range(iterations):
            if victim is not None:
                victim()
            if self.classify():
                hits += 1
        return FFResult(hits / iterations, self.threshold, iterations)
