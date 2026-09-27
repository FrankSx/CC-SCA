"""
Flush+Reload (Yarom & Falkner 2014) on shared pages.

Requires a shared memory region (MAP_SHARED mmap) mapped into both the
spy and victim address spaces — same physical page, hence same cache lines.
"""
from __future__ import annotations

import mmap
import os
import statistics
from dataclasses import dataclass, field
from typing import List, Optional

from . import timing


@dataclass
class FRResult:
    accesses: int
    hits: int
    hit_ratio: float
    threshold_cycles: float
    latencies: List[float] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["latencies_summary"] = {
            "min": min(self.latencies) if self.latencies else None,
            "median": statistics.median(self.latencies) if self.latencies else None,
            "max": max(self.latencies) if self.latencies else None,
        }
        del d["latencies"]
        return d


class SharedPage:
    """MAP_SHARED anonymous mapping (Linux). Falls back to a memfd/tempfile."""

    def __init__(self, size: int = 4096):
        self.size = size
        if hasattr(mmap, "MAP_SHARED") and hasattr(mmap, "MAP_ANONYMOUS"):
            # anonymous shared mapping needs syscall; use memfd-backed file approach
            pass
        import tempfile
        self._tmp = tempfile.TemporaryFile()
        self._tmp.truncate(size)
        self.mm = mmap.mmap(self._tmp.fileno(), size, access=mmap.ACCESS_WRITE,
                            flags=getattr(mmap, "MAP_SHARED", mmap.MAP_SHARED))

    @property
    def address(self) -> int:
        return ctypes_address(self.mm)

    def close(self):
        try:
            self.mm.close()
        finally:
            self._tmp.close()


def ctypes_address(mm: mmap.mmap) -> int:
    import ctypes
    buf = (ctypes.c_char * len(mm)).from_buffer(mm)
    return ctypes.addressof(buf)


def calibrate_threshold(mm: mmap.mmap, offset: int = 0, samples: int = 3000):
    """Returns hit/miss midpoint cycle threshold for a line in the mapping."""
    T = timing
    if not T.native_available():
        raise RuntimeError("Flush+Reload requires the native rdtsc/clflush extension")
    addr = ctypes_address(mm) + offset
    hits, misses = [], []
    for _ in range(samples):
        T.touch(addr, 8)
        hits.append(T.time_load(addr))
        T.clflush(addr)
        misses.append(T.time_load(addr))
    hit = statistics.median(hits)
    miss = statistics.median(misses)
    return (hit + miss) / 2.0, hit, miss


class FlushReloadSpy:
    """Watches a shared line. classify() reports whether the victim touched it."""

    def __init__(self, mm: mmap.mmap, offset: int = 0, threshold: float = None):
        self.mm = mm
        self.offset = offset
        self.addr = ctypes_address(mm) + offset
        if threshold is None:
            threshold, _, _ = calibrate_threshold(mm, offset)
        self.threshold = threshold

    def classify(self) -> bool:
        """True if line is cached (victim accessed since our last flush)."""
        T = timing
        t = T.time_load(self.addr)
        T.clflush(self.addr)
        return t <= self.threshold

    def spy_window(self, iterations: int, victim=None) -> FRResult:
        """
        Run `iterations` flush/reload rounds; if victim callable provided it is
        invoked between flush and reload to simulate the victim's access window.
        """
        hits = 0
        lat = []
        T = timing
        for _ in range(iterations):
            T.clflush(self.addr)
            if victim is not None:
                victim()
            t = T.time_load(self.addr)
            lat.append(t)
            if t <= self.threshold:
                hits += 1
        return FRResult(iterations, hits, hits / iterations, self.threshold, lat)


def receive_bits(spy: FlushReloadSpy, bits: int, slot_ns: int = 0,
                 on_tick=None) -> List[int]:
    """
    Generic bit receiver: sample once per timeslot.
    `on_tick(i)` lets the caller pace the sender in demos.
    """
    out = []
    T = timing
    for i in range(bits):
        if on_tick:
            on_tick(i)
        out.append(1 if spy.classify() else 0)
        if slot_ns:
            t0 = T.now_ns()
            while T.now_ns() - t0 < slot_ns:
                pass
    return out
