"""
Cache geometry discovery and eviction-set construction.

Backed by a numpy uint8 array laid out so consecutive "pages" (stride 4096)
map to candidate cache-set addresses. Uses the classic conflict-detection
method: a set of addresses forms an eviction set for target T if touching
every member evicts T (reload latency jumps above threshold).

All addresses are element indexes into the probe buffer; translate with
:func:`elem_address`.
"""
from __future__ import annotations

import ctypes
import math
from typing import List, Sequence, Tuple

import numpy as np

from . import timing

PAGE = 4096


def new_probe_buffer(n_pages: int, element_size: int = 8) -> np.ndarray:
    """
    Allocate a page-aligned probe buffer of n_pages * PAGE bytes.

    numpy's allocator does not guarantee 4096-byte alignment, so we
    over-allocate by one page and return a slice whose first element starts
    on a page boundary — every candidate page is then exactly 4096 apart.
    """
    dtype = np.uint64 if element_size == 8 else np.uint8
    step = PAGE // element_size
    total = n_pages * step + step
    raw = np.zeros(total, dtype=dtype)
    base = raw.ctypes.data
    off = ((PAGE - base % PAGE) % PAGE) // element_size
    return raw[off:off + n_pages * step]


def elem_address(buf: np.ndarray, idx: int) -> int:
    """Virtual address of buf.flat[idx]."""
    return int(buf.ctypes.data + idx * buf.itemsize)


def page_elems(buf: np.ndarray) -> int:
    """Elements per 4096-byte page for this buffer."""
    return PAGE // buf.itemsize


def candidate_pages(buf: np.ndarray, offset_elems: int = 0) -> List[int]:
    """Element index of the first element of each candidate page."""
    step = page_elems(buf)
    return [offset_elems + i * step for i in range(len(buf) // step)]


def conflict_test(buf: np.ndarray, target_idx: int, group: Sequence[int],
                  threshold: float, reps: int = 3) -> bool:
    """
    True if touching every page in `group` evicts `target_idx`
    (i.e. target's reload latency exceeds threshold).
    """
    from . import timing as T
    if not T.native_available():
        raise RuntimeError("conflict_test requires native rdtsc/clflush")
    taddr = elem_address(buf, target_idx)
    for _ in range(reps):
        T.touch(taddr, 8)                       # bring target into cache
        for gi in group:
            T.touch(elem_address(buf, gi), 1)   # touch potential conflicts
        if T.time_load(taddr) <= threshold:
            return False
    return True


def calibrate_threshold(buf: np.ndarray, samples: int = 2000) -> Tuple[float, float]:
    """
    Returns (cache_hit_max, cache_miss_min) style threshold via histogram:
    touch a line (hit) vs clflush it (miss), take midpoint of medians.
    """
    T = timing
    if not T.native_available():
        raise RuntimeError("requires native extension")
    idx = candidate_pages(buf)[0]
    addr = elem_address(buf, idx)
    hits, misses = [], []
    for _ in range(samples):
        T.touch(addr, 8)
        hits.append(T.time_load(addr))
        T.clflush(addr)
        misses.append(T.time_load(addr))
    hit_med = float(np.median(hits))
    miss_med = float(np.median(misses))
    return hit_med, miss_med


def build_eviction_set(buf: np.ndarray, target_idx: int,
                       threshold: float = None,
                       max_group: int = 32) -> List[int]:
    """
    Group-testing eviction set construction (Liu et al. 2015 style).

    Start with all candidate pages, iteratively reduce: if a sub-group still
    evicts the target, drop the complement. Result: minimal set of pages that
    maps to the same cache set as target_idx.
    """
    T = timing
    if threshold is None:
        _, miss_med = calibrate_threshold(buf)
        hit_med, _ = calibrate_threshold(buf, samples=200)
        threshold = (hit_med + miss_med) / 2.0
    candidates = [p for p in candidate_pages(buf) if p != target_idx]
    group: List[int] = list(candidates)
    # Prune: remove members that don't change eviction outcome
    for p in list(group):
        trial = [g for g in group if g != p]
        if len(trial) >= max_group - 1 and conflict_test(buf, target_idx, trial, threshold, reps=2):
            group = trial
        if len(group) <= 8:
            break
    return group


def probe_set(buf: np.ndarray, group: Sequence[int]) -> List[int]:
    """
    Touch each page in group, measuring per-page reload latency.
    Prime+Probe receiver: re-measure after a victim window; latency spikes
    mark sets the victim touched.
    """
    T = timing
    lat = []
    for gi in group:
        addr = elem_address(buf, gi)
        lat.append(T.time_load(addr))
    return lat


def prime_set(buf: np.ndarray, group: Sequence[int]) -> None:
    T = timing
    for gi in group:
        T.touch(elem_address(buf, gi), 1)
    T.mfence()
