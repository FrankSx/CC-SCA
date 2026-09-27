"""
Cache covert channel with framing, CRC-16 and repetition coding.

Transmitter encodes bytes into cache-line touches on a shared mapping;
receiver samples Flush+Reload per timeslot. Works within a process (demo),
between processes on the same page (shm_open/mmap MAP_SHARED), or across
containers sharing a page (KSM-assisted or shared volume).

Protocol
--------
frame  = SYNC(0xA5) LEN(1B) PAYLOAD(LEN) CRC16(PAYLOAD)
on-wire bits are NRZI-ish: '1' = touch line in slot, '0' = idle slot.
Repetition: each bit sent `rep` times, majority vote at receiver.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import flush_reload, timing

SYNC = 0xA5


def crc16(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def bytes_to_bits(data: bytes) -> List[int]:
    bits = []
    for b in data:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
    return bits


def bits_to_bytes(bits: List[int]) -> bytes:
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        out.append(byte)
    return bytes(out)


def frame(payload: bytes) -> bytes:
    assert len(payload) <= 255
    return bytes([SYNC, len(payload)]) + payload + crc16(payload).to_bytes(2, "big")


class CacheTransmitter:
    """Touches the shared line to encode bits."""

    def __init__(self, mm, offset: int = 0):
        self.addr = flush_reload.ctypes_address(mm) + offset

    def send_bit(self, bit: int):
        T = timing
        if bit:
            T.touch(self.addr, 8)

    def send_bytes(self, data: bytes, slot_ns: int, rep: int = 1,
                   progress: Optional[Callable[[int, int], None]] = None,
                   start_event: "Optional[threading.Event]" = None):
        """
        A '1' bit is a *sustained* touch of the shared line for the whole
        slot (every touch_interval_ns); a '0' is silence. Sustained touching
        is required because the receiver must flush before every sub-sample
        (a load that misses also FILLS the line, so read-only sampling
        self-caches and destroys the signal). Single touches would register
        at most one hit per window after flush-per-sample.
        """
        bits = bytes_to_bits(data)
        sent = 0
        if start_event is not None:
            start_event.wait()
        t0 = timing.now_ns()          # absolute frame schedule anchor
        slot_eff = slot_ns * rep      # bit period
        touch_iv = max(10_000, slot_eff // 16)
        for idx, bit in enumerate(bits):
            win_end = t0 + (idx + 1) * slot_eff
            # Absolute scheduling: slot boundaries are computed from the
            # frame start, NOT loop-relative. Loop-relative pacing lets TX
            # lag accumulate (a '1' slot does more work than a '0' slot, so
            # TX falls one window further behind per mark) — that was the
            # systematic drift that killed late frame bits.
            while timing.now_ns() < win_end:
                if bit:
                    timing.touch(self.addr, 8)
                # Busy-wait on the shared clock; sleep(0) yields the core
                # to the receiver. Do NOT use time.sleep(): its timer slack
                # (100µs+ on VMs, ms under steal) smears slot framing.
                t_in = timing.now_ns()
                while timing.now_ns() - t_in < touch_iv:
                    time.sleep(0)
            sent += 1
            if progress:
                progress(sent, len(bits))


class CacheReceiver:
    def __init__(self, mm, offset: int = 0, threshold: float = None):
        self.spy = flush_reload.FlushReloadSpy(mm, offset, threshold)

    def recv_bits(self, n_bits: int, slot_ns: int, rep: int = 1,
                  oversample: int = 4,
                  progress: Optional[Callable[[int, int], None]] = None) -> List[int]:
        """
        Window-voting receiver.

        The transmitter's slot phase drifts under scheduler jitter / vCPU
        steal, so sampling at one instant per slot is unreliable. Instead,
        each bit window is sub-sampled `oversample + 2` times across the
        full slot. Critically, sub-samples do NOT flush: a touch must stay
        visible to every sub-sample in its window (flushing after the first
        sub-sample would erase the evidence). One clflush per window resets
        state for the next bit. A bit is '1' if touches were seen in a
        majority of sub-sample repetitions.
        """
        bits = []
        sub = max(1, slot_ns // oversample)
        n_sub = oversample + 2
        for i in range(n_bits):
            votes = []
            for _ in range(rep):
                for _ in range(n_sub):
                    t = timing.time_load(self.spy.addr)
                    votes.append(1 if t <= self.spy.threshold else 0)
                    t0 = timing.now_ns()
                    while timing.now_ns() - t0 < sub:
                        time.sleep(0)  # yield GIL so the TX thread keeps pace
                timing.clflush(self.spy.addr)  # one flush per window
            bits.append(1 if sum(votes) > len(votes) // 2 else 0)
            if progress:
                progress(i + 1, n_bits)
        return bits

    def recv_frame(self, max_payload: int = 255, slot_ns: int = 200_000,
                   rep: int = 1) -> Optional[bytes]:
        """Receive one SYNC-framed message (legacy fixed-phase sampling)."""
        hdr_bits = self.recv_bits(16, slot_ns, rep)          # SYNC + LEN
        hdr = bits_to_bytes(hdr_bits)
        if len(hdr) < 2 or hdr[0] != SYNC:
            return None
        length = hdr[1]
        if length > max_payload:
            return None
        body_bits = self.recv_bits((length + 2) * 8, slot_ns, rep)
        body = bits_to_bytes(body_bits)
        payload, got_crc = body[:length], int.from_bytes(body[length:length + 2], "big")
        if crc16(payload) != got_crc:
            return None
        return payload

    def recv_frame_auto(self, max_payload: int = 255, slot_ns: int = 1_000_000,
                        oversample: int = 5, hunt_timeout_s: float = 10.0) -> Optional[bytes]:
        """
        Self-anchoring frame receiver for noisy/steal-prone hosts.

        Phase is anchored on the leading '1' of the SYNC byte (0xA5 starts
        with a 1 bit), which is the first thing the transmitter touches.
        After that, each bit window is [anchor + i*slot, anchor + (i+1)*slot)
        and is sub-sampled `oversample` times WITHOUT flushing between
        sub-samples (a touch must stay visible to the whole window); one
        clflush per window resets state. Majority vote per window.
        """
        T = timing
        spy = self.spy
        # --- hunt: wait for the first touch, use it as the phase anchor ---
        anchor = None
        t_hunt = T.now_ns()
        while anchor is None:
            t = T.time_load(spy.addr)
            T.clflush(spy.addr)
            if t <= spy.threshold:
                anchor = T.now_ns()
            else:
                time.sleep(0)
            if T.now_ns() - t_hunt > hunt_timeout_s * 1e9:
                return None
        bits = [1]  # bit 0 of SYNC is known to be 1 (it IS the anchor)
        total = None
        i = 1
        sub = max(1, slot_ns // oversample)
        while total is None or i < total:
            # Sub-sample deadlines on the absolute grid anchored to the
            # first touch. Loop-relative waits can only run LONG (a
            # descheduled stretch inflates each interval), so oversample
            # intervals of slot/oversample spill into the next bit window
            # and vote on the wrong bit — absolute deadlines bound every
            # sample inside its own window. Sample at mid-interval.
            votes = 0
            for j in range(oversample):
                deadline = anchor + i * slot_ns + j * sub + sub // 2
                while T.now_ns() < deadline:
                    time.sleep(0)
                # Flush-before-every-sample is mandatory: a load that misses
                # also fills the line, so without this the later sub-samples
                # would always "hit" regardless of the signal.
                t = T.time_load(spy.addr)
                T.clflush(spy.addr)
                if t <= spy.threshold:
                    votes += 1
            bits.append(1 if votes > oversample // 2 else 0)
            if i == 15:  # header complete: SYNC + LEN
                hdr = bits_to_bytes(bits)
                if hdr[0] != SYNC:
                    return None
                if hdr[1] > max_payload:
                    return None
                total = 16 + (hdr[1] + 2) * 8
            i += 1
        body = bits_to_bytes(bits[16:])
        length = bits_to_bytes(bits)[1]
        payload, got_crc = body[:length], int.from_bytes(body[length:length + 2], "big")
        if crc16(payload) != got_crc:
            return None
        return payload


def transfer(mm, payload: bytes, slot_ns: int = 200_000, rep: int = 1,
             use_thread: bool = True, pin_cpu: "Optional[int]" = None,
             attempts: int = 5) -> bytes:
    """
    In-process full-duplex demo: transmitter thread + receiver main loop.
    Returns the received bytes (None on protocol failure).

    pin_cpu: bind BOTH threads to one logical CPU. On hosts where vCPUs
    don't share a discriminable L3 (most VMs), cross-vCPU loads never hit
    and the channel can't classify — pinning collapses both peers onto one
    L1/L2 domain so the demo works everywhere. Real cross-process attacks
    leave this None and rely on a genuinely shared LLC.

    attempts: the CRC-framed protocol fails gracefully under vCPU steal /
    scheduler jitter (accumulated phase drift corrupts late frame bits).
    Each attempt is a fresh TX run + re-anchored receive; drift is random
    per attempt, so a clean frame usually lands within a few tries.
    """
    import os
    tx = CacheTransmitter(mm)
    rx = CacheReceiver(mm)
    data = frame(payload)
    eff_slot = max(slot_ns, 1_000_000)

    # Handshake: the receiver must be fully armed (calibrated + line flushed)
    # BEFORE the transmitter starts, otherwise the TX burst lands during RX
    # calibration and the receiver's own clflush wipes it before sampling.
    armed = threading.Event()

    def _tx():
        if pin_cpu is not None:
            os.sched_setaffinity(0, {pin_cpu})
        tx.send_bytes(data, slot_ns, rep, start_event=armed)

    result = None
    for attempt in range(attempts):
        if use_thread:
            th = threading.Thread(target=_tx, daemon=True)
            th.start()
        if pin_cpu is not None:
            os.sched_setaffinity(0, {pin_cpu})
        if attempt == 0:
            # Arm: flush once so the first sample starts from a known state.
            timing.clflush(rx.spy.addr)
        armed.set()
        if not use_thread:
            _tx()
        # Self-anchoring receiver: tolerates vCPU steal / scheduler jitter
        # that makes fixed-phase sampling impossible on virtualised hosts.
        result = rx.recv_frame_auto(max_payload=255, slot_ns=eff_slot * rep)
        if use_thread:
            th.join(timeout=eff_slot / 1e9 * len(bytes_to_bits(data)) * rep + 2)
        if result is not None:
            break
        armed.clear()  # reset handshake for the next attempt
    return result
