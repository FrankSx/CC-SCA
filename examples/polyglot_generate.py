#!/usr/bin/env python3
"""Generate a PNG+WASM polyglot and validate round-trips."""
import sys
sys.path.insert(0, "..")
from sca_arsenal import polyglot, stego

# Minimal valid WASM module header (magic + version) as stand-in payload.
WASM = b"\x00asm\x01\x00\x00\x00" + b"\x00" * 60

png = polyglot.make_polyglot_png(320, 240, WASM)
open("polyglot_demo.png", "wb").write(png)

print("valid PNG:", polyglot.validate_png(png))
print("wasm roundtrip:", polyglot.extract_wasm(png) == WASM)
print("nonstandard chunks:", polyglot.detect_nonstandard_chunks(png))

# Also show stego carrier on top of the polyglot
import numpy as np
from PIL import Image
img = np.array(Image.open("polyglot_demo.png").convert("RGBA"))
payload = stego.payload_json({"attack": "flush_reload", "target": "shared_l3", "threshold": 100})
marked = stego.embed(img, payload)
Image.fromarray(marked).save("polyglot_demo_stego.png")
back = stego.extract(np.array(Image.open("polyglot_demo_stego.png")))
print("stego roundtrip:", back == payload)
