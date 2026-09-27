"""
Cycle-accurate timing abstraction.

Priority:
  1. sca_arsenal._native  (rdtsc + clflush, built from _native.c at install)
  2. perf_counter_ns fallback (coarse; only suitable for coarse contention
     measurements, never for single-line cache discrimination)

Use :func:`native_available` to branch in experiments.
"""
from __future__ import annotations

import time
from typing import Optional

try:
    from . import _native as _n
    _HAVE_NATIVE = True
    _native_error = None
except Exception as _e:  # not built, wrong arch, etc.
    _n = None
    _HAVE_NATIVE = False
    _native_error = _e

HAVE_CLFLUSH = _HAVE_NATIVE

# Approximate TSC calibration (for reporting ns when only cycles known)
_tsc_ghz: Optional[float] = None


def native_available() -> bool:
    return _HAVE_NATIVE


def native_error() -> Optional[Exception]:
    return _native_error


def rdtsc() -> int:
    """Serialised cycle counter. Raises RuntimeError without native module."""
    if not _HAVE_NATIVE:
        raise RuntimeError("rdtsc requires the _native extension: %s" % _native_error)
    return _n.rdtsc()


def now_ns() -> int:
    """Best-effort nanosecond timestamp (native serialised rdtsc scaled, or perf_counter)."""
    if _HAVE_NATIVE:
        return calibrate() and int(_n.rdtsc() / _tsc_ghz)
    return time.perf_counter_ns()


def calibrate(rounds: int = 200) -> Optional[float]:
    """Estimate TSC frequency in GHz by sleeping a known duration."""
    global _tsc_ghz
    if _tsc_ghz is not None:
        return _tsc_ghz
    if not _HAVE_NATIVE:
        return None
    t0 = time.perf_counter_ns()
    c0 = _n.rdtsc()
    time.sleep(max(0.05, rounds / 2000.0))
    c1 = _n.rdtsc()
    t1 = time.perf_counter_ns()
    _tsc_ghz = (c1 - c0) / max(1, t1 - t0)
    return _tsc_ghz


def clflush(addr: int) -> None:
    if not _HAVE_NATIVE:
        raise RuntimeError("clflush requires _native extension")
    _n.clflush(addr)


def mfence() -> None:
    if _HAVE_NATIVE:
        _n.mfence()


def lfence() -> None:
    if _HAVE_NATIVE:
        _n.lfence()


def time_load(addr: int) -> int:
    """Load latency in cycles for a virtual address (native only)."""
    if not _HAVE_NATIVE:
        raise RuntimeError("time_load requires _native extension")
    return _n.time_load(addr)


def touch(addr: int, count: int = 1) -> None:
    if _HAVE_NATIVE:
        _n.touch(addr, count)


def measure_loads(buf_view, indexes, samples: int = 1) -> "list[int]":
    """
    Measure load latency for each index into a writable buffer.

    Works with the numpy-backed buffers from :mod:`sca_arsenal.eviction`.
    Falls back to a python-level timing loop (coarse) if native is absent.
    """
    from . import eviction
    out = []
    if _HAVE_NATIVE:
        for idx in indexes:
            addr = eviction.elem_address(buf_view, idx)
            ts = [time_load(addr) for _ in range(samples)]
            out.append(min(ts))
    else:
        import numpy as _np
        for idx in indexes:
            best = None
            for _ in range(samples):
                t0 = time.perf_counter_ns()
                _ = buf_view[idx]
                t1 = time.perf_counter_ns()
                d = t1 - t0
                best = d if best is None else min(best, d)
            out.append(best)
    return out
