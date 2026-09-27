"""
Evict+Time (Tsunoo et al. 2002; Tromer et al. 2010).

Measure the *victim's* operation latency while we control cache occupancy.
No shared memory needed; coarser but more covert than Prime+Probe.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Callable, List

from . import eviction, timing


@dataclass
class ETResult:
    operation: str
    mean_evicted_ns: float
    mean_cached_ns: float
    delta_ns: float
    samples: int


def evict_buffer(buf, group):
    eviction.prime_set(buf, group)


def time_operation(operation: Callable[[], None], runs: int = 200) -> float:
    """Median wall latency (ns) of operation() over runs."""
    ts = []
    for _ in range(runs):
        t0 = timing.now_ns()
        operation()
        ts.append(timing.now_ns() - t0)
    return statistics.median(ts)


def evict_time(operation: Callable[[], None], buf=None, runs: int = 200) -> ETResult:
    """
    Compare operation latency when our probe buffer occupies the cache
    (evicted case) vs when it doesn't (cached case).
    """
    if buf is None:
        buf = eviction.new_probe_buffer(4096)
    pages = eviction.candidate_pages(buf)
    cached = []
    evicted = []
    for _ in range(runs):
        cached.append(time_operation(operation, runs=1))
        eviction.prime_set(buf, pages)
        evicted.append(time_operation(operation, runs=1))
    mc, me = statistics.median(cached), statistics.median(evicted)
    return ETResult(getattr(operation, "__name__", "op"), me, mc, me - mc, runs)
