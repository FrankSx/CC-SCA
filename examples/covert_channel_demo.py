#!/usr/bin/env python3
"""Full cache covert channel in one process (transmitter thread + receiver).
Slower slots are more reliable on noisy hosts: --slot-ns 500000 --rep 3"""
import sys, argparse
sys.path.insert(0, "..")
from sca_arsenal import covert_channel, flush_reload

ap = argparse.ArgumentParser()
ap.add_argument("--message", default="cross-cache hello")
ap.add_argument("--slot-ns", type=int, default=300_000)
ap.add_argument("--rep", type=int, default=1)
a = ap.parse_args()

sp = flush_reload.SharedPage()
got = covert_channel.transfer(sp.mm, a.message.encode(), slot_ns=a.slot_ns, rep=a.rep)
print("sent:", a.message)
print("recv:", got.decode() if got else "<protocol failure>")
