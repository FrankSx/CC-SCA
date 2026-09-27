"""
Co-residency detection & container environment recon.

Establishes whether another tenant/container shares this physical CPU,
and fingerprints the container runtime. Combines:
  - Prime+Probe cache noise floor
  - /proc / /sys / cgroup introspection
  - TSC/core jitter statistics
"""
from __future__ import annotations

import os
import platform
import re
import statistics
from dataclasses import dataclass, field, asdict
from typing import Dict, List

from . import timing


@dataclass
class ContainerInfo:
    hostname: str
    cgroup_driver: str
    container_runtime: str
    cpu_quota: str
    cpu_count: int
    in_container: bool
    indicators: Dict[str, str] = field(default_factory=dict)


@dataclass
class CoresidencyResult:
    noise_floor_p95: float
    co_resident_probability: str  # low / medium / high
    foreign_activity_windows: int
    samples: int
    info: ContainerInfo

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


def container_info() -> ContainerInfo:
    info = ContainerInfo(
        hostname=platform.node(),
        cgroup_driver="unknown",
        container_runtime="unknown",
        cpu_quota="unlimited",
        cpu_count=os.cpu_count() or 1,
        in_container=False,
    )
    ind = {}
    if os.path.exists("/.dockerenv"):
        info.in_container = True
        info.container_runtime = "docker"
        ind["/.dockerenv"] = "present"
    cg = "/proc/1/cgroup"
    if os.path.exists(cg):
        data = open(cg, errors="ignore").read()
        if "docker" in data:
            info.container_runtime = "docker"; info.in_container = True
            ind["cgroup"] = "docker"
        elif "kubepods" in data or "k8s" in data:
            info.container_runtime = "kubernetes"; info.in_container = True
            ind["cgroup"] = "kubepods"
        elif "containerd" in data:
            info.container_runtime = "containerd"; info.in_container = True
            ind["cgroup"] = "containerd"
        elif "lxc" in data:
            info.container_runtime = "lxc"; info.in_container = True
            ind["cgroup"] = "lxc"
    if os.path.exists("/sys/fs/cgroup/cpu.max"):
        try:
            q = open("/sys/fs/cgroup/cpu.max").read().strip()
            info.cpu_quota = q
            ind["cpu.max"] = q
        except OSError:
            pass
    elif os.path.exists("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"):
        try:
            q = open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read().strip()
            p = open("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read().strip()
            info.cpu_quota = f"{q}/{p}"
            ind["cfs_quota"] = info.cpu_quota
        except OSError:
            pass
    m = re.search(r"^(.+?)\s+.*:\d+$", open("/proc/1/sched", errors="ignore").readline() if os.path.exists("/proc/1/sched") else "")
    info.indicators = ind
    return info


def prime_probe_noise(pages: int = 2048, rounds: int = 400) -> Dict[str, float]:
    """Measure background cache-set activity via Prime+Probe."""
    from . import eviction
    buf = eviction.new_probe_buffer(pages)
    hit, miss = eviction.calibrate_threshold(buf)
    threshold = (hit + miss) / 2.0
    cands = eviction.candidate_pages(buf)
    spikes = 0
    all_lat = []
    for _ in range(rounds):
        eviction.prime_set(buf, cands)
        lat = eviction.probe_set(buf, cands)
        all_lat.extend(lat)
        spikes += sum(1 for l in lat if l > threshold)
    p95 = sorted(all_lat)[int(0.95 * len(all_lat))]
    total = rounds * len(cands)
    return {
        "p95_latency": p95,
        "active_ratio": spikes / total,
        "hit_threshold": hit,
        "miss_threshold": miss,
        "rounds": rounds,
    }


def detect_coresidency(rounds: int = 400) -> CoresidencyResult:
    noise = prime_probe_noise(rounds=rounds)
    ar = noise["active_ratio"]
    if ar < 0.05:
        prob = "low"
    elif ar < 0.2:
        prob = "medium"
    else:
        prob = "high"
    return CoresidencyResult(
        noise_floor_p95=noise["p95_latency"],
        co_resident_probability=prob,
        foreign_activity_windows=int(ar * rounds * 64),
        samples=rounds,
        info=container_info(),
    )
