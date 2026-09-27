"""
GPU memory/scheduler contention snooping.

Observes CPU-side timing artefacts while a GPU workload runs. Uses pyopencl
if available for native device timing; otherwise falls back to measuring
host-memory bandwidth/latency interference (useful for co-tenancy detection
in virtualised GPU environments).
"""
from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from . import timing


@dataclass
class GPUObservation:
    label: str
    idle_median_ns: float
    loaded_median_ns: float
    delta_ns: float
    samples: int


def host_memory_bench(iters: int = 2000) -> float:
    """Median ns of a strided host-memory walk (sensitive to memory bus contention)."""
    import numpy as np
    buf = np.zeros(16 * 1024 * 1024 // 8, dtype=np.uint64)
    idx = np.arange(0, len(buf), 4096 // 8)
    ts = []
    for _ in range(iters):
        t0 = timing.now_ns()
        s = int(buf[idx].sum())
        ts.append(timing.now_ns() - t0)
        _ = s
    return statistics.median(ts)


def opencl_available() -> bool:
    try:
        import pyopencl  # noqa: F401
        return True
    except Exception:
        return False


class GPUSnooper:
    """Compare host timing with idle GPU vs GPU under load."""

    def __init__(self):
        self.background_stop = threading.Event()
        self.background_thread: Optional[threading.Thread] = None

    def start_gpu_load(self, duration_s: float = 5.0):
        """Spin a busy OpenCL kernel if available, else a CPU matmul stand-in."""
        self.background_stop.clear()

        def _load():
            end = time.time() + duration_s
            try:
                import pyopencl as cl
                import numpy as np
                ctx = cl.create_some_context()
                q = cl.CommandQueue(ctx)
                a = np.random.rand(1024, 1024).astype(np.float32)
                b = np.random.rand(1024, 1024).astype(np.float32)
                mf = cl.mem_flags
                a_dev = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=a)
                b_dev = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=b)
                c_dev = cl.Buffer(ctx, mf.WRITE_ONLY, a.nbytes)
                prg = cl.Program(ctx, """
                    __kernel void mm(__global const float*A,__global const float*B,__global float*C){
                      int i=get_global_id(0),j=get_global_id(1),N=1024;float s=0;
                      for(int k=0;k<N;k++) s+=A[i*N+k]*B[k*N+j];
                      C[i*N+j]=s;
                    }""").build()
                while time.time() < end and not self.background_stop.is_set():
                    prg.mm(q, (1024, 1024), None, a_dev, b_dev, c_dev)
                    q.finish()
            except Exception:
                import numpy as np
                a = np.random.rand(1024, 1024)
                while time.time() < end and not self.background_stop.is_set():
                    _ = a @ a

        self.background_thread = threading.Thread(target=_load, daemon=True)
        self.background_thread.start()

    def stop_gpu_load(self):
        self.background_stop.set()
        if self.background_thread:
            self.background_thread.join(timeout=2)

    def observe(self, label: str = "host_bench", samples: int = 500) -> GPUObservation:
        idle = host_memory_bench(samples)
        self.start_gpu_load(duration_s=max(2.0, samples / 1000.0))
        time.sleep(0.2)  # let load ramp
        loaded = host_memory_bench(samples)
        self.stop_gpu_load()
        return GPUObservation(label, idle, loaded, loaded - idle, samples)
