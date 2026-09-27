#!/usr/bin/env python3
"""
Passive covert-channel trace decoder.

Feed it a JSON trace of per-window sub-sample latencies recorded on ANY
host (e.g. by a modified receiver, an external logic analyzer tapping a
shared page, or a perf capture) and it applies threshold voting, framing
and CRC to recover the payload — the "wireshark" for the sca-arsenal
covert protocol.

Trace format (list of windows, each a list of load latencies in cycles):
  [[312, 88, 90, 84, 91], [301, 295, 288, 290, 302], ...]

Usage:
  python tools/decode_trace.py trace.json --threshold 180
  python tools/decode_trace.py trace.json --auto-threshold   # Otsu split
"""
import argparse
import json
import sys

sys.path.insert(0, ".")
from sca_arsenal.covert_channel import bits_to_bytes, crc16, SYNC


def otsu_threshold(values):
    """Two-class split on the latency histogram (cached vs uncached)."""
    lo, hi = min(values), max(values)
    if lo == hi:
        return lo
    bins = [0] * 256
    for v in values:
        bins[int((v - lo) / (hi - lo) * 255)] += 1
    total = len(values)
    sum_all = sum(i * b for i, b in enumerate(bins))
    sum_b = w_b = 0.0
    best_t, best_var = 0, -1.0
    for t in range(256):
        w_b += bins[t]
        if w_b == 0 or w_b == total:
            continue
        sum_b += t * bins[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / (total - w_b)
        var = w_b * (total - w_b) * (m_b - m_f) ** 2
        if var > best_var:
            best_var, best_t = var, t
    return lo + (best_t / 255) * (hi - lo)


def vote_window(lats, threshold):
    hits = sum(1 for v in lats if v <= threshold)
    return 1 if hits > len(lats) // 2 else 0, hits, len(lats)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("trace")
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--auto-threshold", action="store_true")
    ap.add_argument("--max-payload", type=int, default=255)
    args = ap.parse_args()

    windows = json.load(open(args.trace))
    flat = [v for w in windows for v in w]
    if args.auto_threshold or args.threshold is None:
        thr = otsu_threshold(flat)
        print(f"[+] auto threshold: {thr:.1f} cycles "
              f"(min={min(flat)} max={max(flat)} windows={len(windows)})")
    else:
        thr = args.threshold

    bits = [vote_window(w, thr)[0] for w in windows]
    print(f"[+] voted {len(bits)} bits")

    # hunt for SYNC anywhere in the bitstream (handles pre-roll garbage)
    for off in range(len(bits) - 16):
        hdr = bits_to_bytes(bits[off:off + 16])
        if hdr and hdr[0] == SYNC and hdr[1] <= args.max_payload:
            length = hdr[1]
            need = 16 + (length + 2) * 8
            if off + need > len(bits):
                break
            body = bits_to_bytes(bits[off + 16:off + need])
            payload, got_crc = body[:length], int.from_bytes(body[length:length + 2], "big")
            ok = crc16(payload) == got_crc
            print(f"[+] frame @ bit {off}: len={length} crc={'OK' if ok else 'FAIL'}")
            print(f"    payload: {payload!r}")
            if ok:
                return 0
    print("[-] no valid frame found", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
