"""
Polyglot PNG carrier with custom 'waSM' ancillary chunk.

Structure:
  PNG sig | IHDR | waSM (payload, e.g. WASM module) | IDAT(s) | IEND

Both decoders see a valid PNG; the waSM chunk is ignored by image viewers
but harvestable by a WASM loader. Also provides JPEG-comment and
generic-append carriers for formats lacking chunk extensibility.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Optional, Tuple

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def chunk(ctype: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + ctype + data
            + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF))


def make_polyglot_png(width: int, height: int, wasm: bytes,
                      draw_fn=None) -> bytes:
    """
    Build a valid PNG containing `wasm` in a waSM chunk.
    draw_fn: callable(img_bytearray, w, h) to paint the visual layer;
             default: diagonal pattern (keeps LSB entropy natural-ish).
    """
    # raw RGBA scanlines, filter byte 0 per row
    raw = bytearray()
    img = bytearray(width * height * 4)
    if draw_fn:
        draw_fn(img, width, height)
    else:
        for y in range(height):
            for x in range(width):
                i = (y * width + x) * 4
                v = (x * 255 // max(1, width - 1) + y * 128 // max(1, height - 1)) % 256
                img[i:i + 4] = bytes([v, (v * 3) % 256, (v * 7) % 256, 255])
    for y in range(height):
        raw.append(0)
        raw.extend(img[y * width * 4:(y + 1) * width * 4])

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 6)
    return (PNG_SIG
            + chunk(b"IHDR", ihdr)
            + chunk(b"waSM", wasm)
            + chunk(b"IDAT", idat)
            + chunk(b"IEND", b""))


def extract_wasm(png: bytes) -> Optional[bytes]:
    """Pull the waSM chunk out of a polyglot PNG."""
    if not png.startswith(PNG_SIG):
        raise ValueError("not a PNG")
    off = len(PNG_SIG)
    while off < len(png):
        (length,) = struct.unpack(">I", png[off:off + 4])
        ctype = png[off + 4:off + 8]
        data = png[off + 8:off + 8 + length]
        if ctype == b"waSM":
            return data
        off += 12 + length
    return None


def validate_png(png: bytes) -> bool:
    """Full structural validation of every chunk."""
    if not png.startswith(PNG_SIG):
        return False
    off = len(PNG_SIG)
    seen_iend = False
    while off + 12 <= len(png):
        (length,) = struct.unpack(">I", png[off:off + 4])
        ctype = png[off + 4:off + 8]
        data = png[off + 8:off + 8 + length]
        crc_stored = struct.unpack(">I", png[off + 8 + length:off + 12 + length])[0]
        if zlib.crc32(ctype + data) & 0xFFFFFFFF != crc_stored:
            return False
        if ctype == b"IEND":
            seen_iend = True
            break
        off += 12 + length
    return seen_iend


def jpeg_append_carrier(jpeg: bytes, payload: bytes, marker: bytes = b"SCAWASM") -> bytes:
    """Append payload after EOI with a marker; extractable, survives re-encode losslessly only."""
    return jpeg + b"\xFF\xD9"[-2:] if False else jpeg.rstrip(b"\xFF\xD9") + payload + marker


def detect_nonstandard_chunks(png: bytes) -> list:
    """Defender-side: list all chunk types; flag non-RFC ones."""
    standard = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"cHRM", b"gAMA", b"iCCP",
                b"sBIT", b"sRGB", b"bKGD", b"hIST", b"tRNS", b"pHYs", b"sPLT",
                b"tIME", b"iTXt", b"tEXt", b"zTXt", b"eXIf", b"acTL", b"fcTL", b"fdAT"}
    out = []
    off = len(PNG_SIG)
    while off + 8 <= len(png):
        (length,) = struct.unpack(">I", png[off:off + 4])
        ctype = png[off + 4:off + 8]
        out.append((ctype.decode("latin1"), ctype not in standard))
        off += 12 + length
        if ctype == b"IEND":
            break
    return out
