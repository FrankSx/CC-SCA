"""sca-arsenal command line interface."""
from __future__ import annotations

import argparse
import json
import sys


def _need_native():
    from . import timing
    if not timing.native_available():
        print("[!] native extension not available: %s" % timing.native_error(),
              file=sys.stderr)
        print("[!] cache-timing attacks will be coarse or unavailable. "
              "Rebuild with:  pip install .", file=sys.stderr)
        return False
    return True


def cmd_info(args):
    from . import timing, coresidency
    print(json.dumps({
        "native": timing.native_available(),
        "native_error": str(timing.native_error() or ""),
        "container": coresidency.container_info().__dict__,
    }, indent=2))


def cmd_fr_calibrate(args):
    from . import flush_reload
    if not _need_native():
        return 1
    sp = flush_reload.SharedPage()
    thr, hit, miss = flush_reload.calibrate_threshold(sp.mm)
    print(json.dumps({"threshold": thr, "hit_median": hit, "miss_median": miss}, indent=2))
    return 0


def cmd_fr_spy(args):
    from . import flush_reload
    if not _need_native():
        return 1
    sp = flush_reload.SharedPage()
    thr, _, _ = flush_reload.calibrate_threshold(sp.mm)
    spy = flush_reload.FlushReloadSpy(sp.mm, threshold=thr)
    res = spy.spy_window(args.iterations)
    print(json.dumps(res.as_dict(), indent=2))
    return 0


def cmd_pp(args):
    from . import prime_probe
    if not _need_native():
        return 1
    pp = prime_probe.PrimeProbe(n_pages=args.pages)
    hit, miss, thr = pp.calibrate()
    print(f"[+] calibrated hit={hit:.0f} miss={miss:.0f} threshold={thr:.0f}")
    pp.snapshot_baseline(rounds=10)
    acts = pp.monitor_window(rounds=args.rounds)
    active = [a for a in acts if a.active]
    print(f"[+] {len(active)}/{len(acts)} sets active")
    for a in active[:args.top]:
        print(f"    set@{a.set_id:#x} mean={a.mean_latency:.0f}c")
    return 0


def cmd_evict_time(args):
    from . import evict_time
    if not _need_native():
        return 1
    import numpy as np
    a = np.random.rand(256, 256)
    r = evict_time.evict_time(lambda: a @ a, runs=args.runs)
    print(json.dumps(r.__dict__, indent=2))
    return 0


def cmd_covert(args):
    from . import covert_channel, flush_reload
    if not _need_native():
        return 1
    import os
    sp = flush_reload.SharedPage()
    msg = args.message.encode()
    pin = args.pin_cpu
    if pin is None and args.pin:
        pin = sorted(os.sched_getaffinity(0))[0]
    got = covert_channel.transfer(sp.mm, msg, slot_ns=args.slot_ns, rep=args.rep,
                                  pin_cpu=pin)
    ok = got == msg
    print(json.dumps({"sent": msg.decode(), "recv": got.decode() if got else None,
                      "ok": ok}, indent=2))
    return 0 if ok else 1


def cmd_scan(args):
    from . import coresidency
    if not _need_native():
        return 1
    r = coresidency.detect_coresidency(rounds=args.rounds)
    print(json.dumps(r.as_dict(), indent=2, default=str))
    return 0


def cmd_stego_embed(args):
    from . import stego
    stego.embed_file(args.input, args.output, open(args.payload, "rb").read())
    print(f"[+] embedded {args.payload} -> {args.output}")
    return 0


def cmd_stego_extract(args):
    from . import stego
    data = stego.extract_file(args.input)
    sys.stdout.buffer.write(data)
    return 0


def cmd_polyglot(args):
    from . import polyglot
    wasm = open(args.wasm, "rb").read()
    png = polyglot.make_polyglot_png(args.width, args.height, wasm)
    with open(args.output, "wb") as f:
        f.write(png)
    print(json.dumps({
        "output": args.output,
        "bytes": len(png),
        "valid_png": polyglot.validate_png(png),
        "wasm_roundtrip": polyglot.extract_wasm(png) == wasm,
        "chunks": polyglot.detect_nonstandard_chunks(png),
    }, indent=2))
    return 0


def cmd_ksm(args):
    from . import ksm
    r = ksm.probe_content(args.content.encode(), samples=args.samples)
    print(json.dumps(r.__dict__, indent=2))
    return 0


def cmd_hammer(args):
    from . import rowhammer
    if not _need_native():
        return 1
    rh = rowhammer.RowHammer(buffer_size=args.mb * 1024 * 1024)
    res = rh.run(hammers_per_pair=args.hammers, max_pairs=args.pairs, verbose=args.verbose)
    print(json.dumps({"flipped_bits": res.flipped_bits, "hammers": res.hammers,
                      "rows_tested": res.rows_tested, "note": res.note,
                      "flips": [f.__dict__ for f in res.flips[:20]]}, indent=2))
    return 0


def cmd_gpu(args):
    from . import gpu_snooper
    obs = gpu_snooper.GPUSnooper().observe(samples=args.samples)
    print(json.dumps(obs.__dict__, indent=2))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="sca-arsenal",
                                description="Cross-container side-channel attack research toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="environment & native capability report").set_defaults(fn=cmd_info)

    b = sub.add_parser("fr-calibrate", help="Flush+Reload threshold calibration"); b.set_defaults(fn=cmd_fr_calibrate)
    b = sub.add_parser("fr-spy", help="Flush+Reload spy window"); b.set_defaults(fn=cmd_fr_spy)
    b.add_argument("--iterations", type=int, default=1000)

    b = sub.add_parser("pp", help="Prime+Probe LLC monitor"); b.set_defaults(fn=cmd_pp)
    b.add_argument("--pages", type=int, default=4096)
    b.add_argument("--rounds", type=int, default=1)
    b.add_argument("--top", type=int, default=10)

    b = sub.add_parser("evict-time", help="Evict+Time on a matrix op"); b.set_defaults(fn=cmd_evict_time)
    b.add_argument("--runs", type=int, default=100)

    b = sub.add_parser("covert", help="in-process cache covert channel demo"); b.set_defaults(fn=cmd_covert)
    b.add_argument("--message", default="SCA-ARSENAL")
    b.add_argument("--slot-ns", type=int, default=500_000)
    b.add_argument("--rep", type=int, default=1)
    b.add_argument("--pin", action="store_true",
                   help="pin TX+RX to one shared CPU (needed on VMs without a shared L3)")
    b.add_argument("--pin-cpu", type=int, default=None, help="explicit CPU id for --pin")

    b = sub.add_parser("scan", help="co-residency detection"); b.set_defaults(fn=cmd_scan)
    b.add_argument("--rounds", type=int, default=300)

    b = sub.add_parser("stego-embed"); b.set_defaults(fn=cmd_stego_embed)
    b.add_argument("input"); b.add_argument("payload"); b.add_argument("output")

    b = sub.add_parser("stego-extract"); b.set_defaults(fn=cmd_stego_extract)
    b.add_argument("input")

    b = sub.add_parser("polyglot", help="PNG+WASM polyglot generator"); b.set_defaults(fn=cmd_polyglot)
    b.add_argument("wasm"); b.add_argument("output")
    b.add_argument("--width", type=int, default=400); b.add_argument("--height", type=int, default=300)

    b = sub.add_parser("ksm", help="KSM merge timing probe"); b.set_defaults(fn=cmd_ksm)
    b.add_argument("--content", default="A" * 64)
    b.add_argument("--samples", type=int, default=300)

    b = sub.add_parser("hammer", help="rowhammer flip hunt"); b.set_defaults(fn=cmd_hammer)
    b.add_argument("--mb", type=int, default=256)
    b.add_argument("--hammers", type=int, default=500_000)
    b.add_argument("--pairs", type=int, default=16)
    b.add_argument("--verbose", action="store_true")

    b = sub.add_parser("gpu", help="GPU contention observation"); b.set_defaults(fn=cmd_gpu)
    b.add_argument("--samples", type=int, default=500)

    args = p.parse_args(argv)
    try:
        rc = args.fn(args)
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
