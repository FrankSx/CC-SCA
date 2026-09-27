"""
LSB steganography for SCA payload carriers.

Embed/extract arbitrary payloads in the 2 LSBs of RGB channels (6 bits/pixel)
of PNG images — matching the wire format the HTML audit platform decodes.
Pure-Python/numpy; no Pillow required for raw access (Pillow used for IO).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass
class StegoHeader:
    magic: bytes = b"SCA1"
    length: int = 0


def embed(image: np.ndarray, payload: bytes) -> np.ndarray:
    """
    Embed payload into RGB LSBs (2 bits per channel, 6 bits per pixel).
    image: HxWx3 (or HxWx4; alpha preserved) uint8 array. Returns new array.
    Header: magic 'SCA1' (4B) + uint32 length = 8B = 64 bits = 11 pixels.
    """
    h = StegoHeader(length=len(payload))
    header = h.magic + len(payload).to_bytes(4, "big")
    stream = header + payload
    need_bits = len(stream) * 8
    pixels = image[:, :, :3].reshape(-1, 3)
    capacity = pixels.shape[0] * 6
    if need_bits > capacity:
        raise ValueError(f"payload too large: need {need_bits} bits, capacity {capacity}")
    bits = np.unpackbits(np.frombuffer(stream, dtype=np.uint8))
    # pad to multiple of 6
    pad = (-len(bits)) % 6
    bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    grp = bits.reshape(-1, 6)
    flat = pixels.copy()
    for ch in range(3):
        two = grp[:, ch * 2:ch * 2 + 2]            # 2 bits for this channel
        vals = (two[:, 0] << 1) | two[:, 1]
        flat[:len(vals), ch] = (flat[:len(vals), ch] & 0xFC) | vals
    out = image.copy()
    out[:, :, :3] = flat.reshape(image[:, :, :3].shape)
    return out


def extract(image: np.ndarray) -> bytes:
    """Extract payload embedded by :func:`embed`."""
    pixels = image[:, :, :3].reshape(-1, 3)
    vals = pixels & 0x03                            # 2 LSBs per channel
    bits = np.empty((pixels.shape[0], 6), dtype=np.uint8)
    for ch in range(3):
        bits[:, ch * 2] = (vals[:, ch] >> 1) & 1
        bits[:, ch * 2 + 1] = vals[:, ch] & 1
    flat_bits = bits.reshape(-1)
    nbytes = (len(flat_bits) // 8) * 8
    raw = np.packbits(flat_bits[:nbytes]).tobytes()
    if raw[:4] != b"SCA1":
        raise ValueError("no SCA1 magic — not a sca_arsenal stego image")
    length = int.from_bytes(raw[4:8], "big")
    return raw[8:8 + length]


def embed_file(src_png: str, dst_png: str, payload: bytes):
    from PIL import Image
    img = np.array(Image.open(src_png).convert("RGBA"))
    out = embed(img, payload)
    Image.fromarray(out).save(dst_png, "PNG")


def extract_file(src_png: str) -> bytes:
    from PIL import Image
    img = np.array(Image.open(src_png))
    return extract(img)


def payload_json(obj: dict) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()


def payload_microcode(operations: dict) -> bytes:
    """Serialize SCA micro-op descriptors (opcodes from _native / asm)."""
    return payload_json({"microcode": operations})
