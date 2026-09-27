"""
DRAM Rowhammer (Kim et al. 2014) flip hunter.

Allocates physically-contiguous-ish buffers, picks same-bank row neighbours
(assumed via physical address stride when /proc/self/pagemap is readable,
otherwise linear 2*row_size guess), hammers, and sweeps victim rows for bit
flips. Requires: native extension, lots of RAM, and typically root for
reliable physical mapping; without root we fall back to linear guessing.

WARNING: research tool — run only on machines you own and are willing to
potentially destabilise. Rowhammer can cause machine-check exceptions.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from . import timing

DEFAULT_ROW_SIZE = 0x10000  # 64 KiB guess; DDR4 often 1<<14..1<<17 depending on DIMM


def read_pagemap(vaddr: int) -> Optional[int]:
    """Return physical frame for a userspace vaddr via /proc/self/pagemap (needs root)."""
    if not os.path.exists("/proc/self/pagemap"):
        return None
    try:
        with open("/proc/self/pagemap", "rb") as f:
            f.seek((vaddr // 4096) * 8)
            entry = struct.unpack("<Q", f.read(8))[0]
        if entry & (1 << 63):
            return (entry & ((1 << 55) - 1)) * 4096
    except PermissionError:
        return None
    return None


@dataclass
class Flip:
    offset_a: int
    offset_b: int
    victim_offset: int
    byte_index: int
    bit: int
    before: int
    after: int


@dataclass
class HammerResult:
    flips: List[Flip] = field(default_factory=list)
    hammers: int = 0
    rows_tested: int = 0
    note: str = ""

    @property
    def flipped_bits(self) -> int:
        return len(self.flips)


class RowHammer:
    def __init__(self, buffer_size: int = 512 * 1024 * 1024,
                 row_size: int = DEFAULT_ROW_SIZE):
        self.size = buffer_size
        self.row_size = row_size
        # uint64 buffer improves clflush granularity control
        self.buf = np.zeros(buffer_size // 8, dtype=np.uint64)

    def addr(self, byte_offset: int) -> int:
        return int(self.buf.ctypes.data + byte_offset)

    def fill(self, pattern: int = 0x00):
        self.buf.fill(pattern)

    def _same_bank_row_pairs(self):
        """Yield (rowA_off, rowB_off) aggressor candidates straddling victim rows."""
        rs = self.row_size
        n = self.size // rs
        for i in range(1, n - 1):
            yield i * rs, (i + 2) * rs  # A and B with one victim row between

    def hammer_pair(self, off_a: int, off_b: int, count: int):
        T = timing
        if not T.native_available():
            raise RuntimeError("rowhammer requires the native extension")
        a, b = self.addr(off_a), self.addr(off_b)
        T.mfence()
        for _ in range(count):
            T.touch(a, 1)
            T.touch(b, 1)
            T.clflush(a)
            T.clflush(b)
        T.mfence()

    def check_row(self, row_off: int) -> List[Flip]:
        flips = []
        view = self.buf[row_off // 8:(row_off + self.row_size) // 8]
        for i, v in enumerate(view):
            if v != 0:
                for bit in range(64):
                    if v & (1 << bit):
                        flips.append(Flip(-1, -1, row_off, i * 8 + bit // 8, bit, 0, 1))
        return flips

    def run(self, hammers_per_pair: int = 1_000_000,
            max_pairs: int = 64, verbose=False) -> HammerResult:
        res = HammerResult()
        res.note = ("linear row-guessing mode (no pagemap). "
                    "Run as root for physical/bank-aware placement.")
        self.fill(0x00)
        for pi, (oa, ob) in enumerate(self._same_bank_row_pairs()):
            if pi >= max_pairs:
                break
            victim = oa + self.row_size
            res.rows_tested += 1
            self.hammer_pair(oa, ob, hammers_per_pair)
            flips = self.check_row(victim)
            for f in flips:
                f.offset_a, f.offset_b = oa, ob
            res.flips.extend(flips)
            res.hammers += hammers_per_pair
            if verbose:
                print(f"[rowhammer] pair {pi}: victim@{victim:#x} flips={len(flips)}")
            self.fill(0x00)
        return res
