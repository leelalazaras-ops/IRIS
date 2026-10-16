"""
IRIS system telemetry service.

Collects genuine local host measurements with psutil and NVIDIA NVML (when
installed). Values that cannot be measured on the host are reported as
UNAVAILABLE - never fabricated.

The service is pure Python (no Qt) so it can be unit-tested without a GUI.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Deque, Optional

import psutil

from iris.telemetry.models import (
    PROVENANCE_DERIVED,
    PROVENANCE_LIVE,
    PROVENANCE_UNAVAILABLE,
    CpuSample,
    DiskSample,
    GpuReport,
    InterfaceInfo,
    MemorySample,
    NetworkSample,
    ProcessInfo,
    TelemetrySnapshot,
    now_iso,
)
from iris.telemetry import models as _models

_HIST_LEN = 120  # bounded history: ~4 minutes at 2s default interval


class TelemetryService:
    """
    Collects real host telemetry. Pure python; thread-safe; no mocking.

    Unsupported measurements surface as UNAVAILABLE (provenance string on
    the payload), gold-plated nowhere.
    """

    def __init__(self, history_len: int = _HIST_LEN) -> None:
        self._lock = threading.Lock()
        self._cpu_history: Deque[dict] = deque(maxlen=history_len)
        self._mem_history: Deque[dict] = deque(maxlen=history_len)
        self._net_history: Deque[dict] = deque(maxlen=history_len)
        self._sequence = 0
        self._last_net: Optional[tuple] = None
        self._last_disk: Optional[tuple] = None
        self._last_disk_ts = 0.0
        psutil.cpu_percent(interval=None)  # prime cumulative counters

    # ------------------------------------------------------------------ history

    def get_history(self) -> dict[str, list]:
        """Snapshot copy of bounded sample histories (charts)."""
        with self._lock:
            return {
                "cpu": list(self._cpu_history),
                "memory": list(self._mem_history),
                "network": list(self._net_history),
            }

    # ------------------------------------------------------------------ gpu

    @staticmethod
    def _gpu_report() -> GpuReport:
        """Real NVIDIA GPU metrics via NVML when the interface is present."""
        try:
            import pynvml  # type: ignore

            pynvml.nvmlInit()
            handles = pynvml.nvmlDeviceGetCount()
            if handles == 0:
                return GpuReport(
                    available=False,
                    util_percent="UNAVAILABLE",
                    temperature_c="UNAVAILABLE",
                    vram_used_bytes="UNAVAILABLE",
                    vram_total_bytes="UNAVAILABLE",
                    message="No NVIDIA devices detected",
                )
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return GpuReport(
                available=True,
                util_percent=f"{util.gpu}",
                temperature_c=f"{temp}",
                vram_used_bytes=str(mem.used),
                vram_total_bytes=str(mem.total),
                provenance=_models.PROVENANCE_LIVE,
                message="NVIDIA NVML",
            )
        except ImportError:
            return GpuReport(
                available=False,
                util_percent="UNAVAILABLE",
                temperature_c="UNAVAILABLE",
                vram_used_bytes="UNAVAILABLE",
                vram_total_bytes="UNAVAILABLE",
                message="pynvml not installed - install it to expose NVIDIA GPU metrics",
            )
        except Exception as exc:  # NVML init/driver errors
            return GpuReport(
                available=False,
                util_percent="UNAVAILABLE",
                temperature_c="UNAVAILABLE",
                vram_used_bytes="UNAVAILABLE",
                vram_total_bytes="UNAVAILABLE",
                message=f"UNAVAILABLE ({exc.__class__.__name__})",
            )

    # ------------------------------------------------------------------ pieces

    @staticmethod
    def _cpu() -> CpuSample:
        percent = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        count = psutil.cpu_count(logical=True) or 0
        freq = None
        try:
            sf = psutil.cpu_freq()
            if sf is not None:
                freq = sf.current
        except Exception:
            freq = None
        return CpuSample(
            percent=round(float(percent), 1),
            per_core=[round(float(p), 1) for p in per_core],
            core_count=count,
            freq_mhz=round(float(freq), 1) if freq else None,
            timestamp=now_iso(),
        )

    @staticmethod
    def _memory() -> MemorySample:
        vm = psutil.virtual_memory()
        return MemorySample(
            percent=round(float(vm.percent), 1),
            used_bytes=int(vm.used),
            total_bytes=int(vm.total),
            available_bytes=int(vm.available),
            timestamp=now_iso(),
        )

    def _disk(self) -> DiskSample:
        usage = psutil.disk_usage("/")
        read_sec = None
        write_sec = None
        try:
            counters = psutil.disk_io_counters()
            if counters is not None:
                ts = time.monotonic()
                if self._last_disk is not None and ts > self._last_disk_ts:
                    elapsed = ts - self._last_disk_ts
                    if elapsed > 0:
                        prev = self._last_disk
                        read_sec = max(
                            0.0, (counters.read_bytes - prev[0]) / elapsed
                        )
                        write_sec = max(
                            0.0, (counters.write_bytes - prev[1]) / elapsed
                        )
                self._last_disk = (
                    counters.read_bytes,
                    counters.write_bytes,
                )
                self._last_disk_ts = ts
                if read_sec is None or write_sec is None:
                    return DiskSample(
                        percent=round(float(usage.percent), 1),
                        used_bytes=int(usage.used),
                        total_bytes=int(usage.total),
                        read_bytes_sec=None,
                        write_bytes_sec=None,
                        provenance=PROVENANCE_LIVE,
                        timestamp=now_iso(),
                    )
        except Exception:
            read_sec = None
            write_sec = None
        return DiskSample(
            percent=round(float(usage.percent), 1),
            used_bytes=int(usage.used),
            total_bytes=int(usage.total),
            read_bytes_sec=None if read_sec is None else round(read_sec, 1),
            write_bytes_sec=None if write_sec is None else round(write_sec, 1),
            provenance=PROVENANCE_DERIVED if read_sec is not None else PROVENANCE_LIVE,
            timestamp=now_iso(),
        )

    def _network(self) -> NetworkSample:
        counters = psutil.net_io_counters()
        ts = time.monotonic()
        up_sec = 0.0
        down_sec = 0.0
        if self._last_net is not None and ts > self._last_net[2]:
            elapsed = ts - self._last_net[2]
            if elapsed > 0:
                prev = self._last_net
                up_sec = max(0.0, (counters.bytes_sent - prev[0]) / elapsed)
                down_sec = max(0.0, (counters.bytes_recv - prev[1]) / elapsed)
        self._last_net = (counters.bytes_sent, counters.bytes_recv, ts)

        interfaces: list[InterfaceInfo] = []
        addr_map = psutil.net_if_addrs()
        stats_map = psutil.net_if_stats()
        for name, addrs in addr_map.items():
            address_values = [a.address for a in addrs if a.address]
            is_up = bool(stats_map.get(name) and stats_map[name].isup)
            speed: str
            stat = stats_map.get(name)
            if stat is not None and getattr(stat, "speed", 0) and stat.speed > 0:
                speed = str(int(stat.speed))
            else:
                speed = "UNAVAILABLE"
            interfaces.append(
                InterfaceInfo(
                    name=name,
                    is_up=is_up,
                    addresses=address_values,
                    speed_mbps=speed,
                )
            )
        return NetworkSample(
            up_bytes_sec=round(up_sec, 1),
            down_bytes_sec=round(down_sec, 1),
            interfaces=interfaces,
            timestamp=now_iso(),
        )

    @staticmethod
    def _top_processes(limit: int = 8) -> list[ProcessInfo]:
        result: list[ProcessInfo] = []
        try:
            procs = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    procs.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            procs.sort(
                key=lambda p: (p.info.get("cpu_percent") or 0.0), reverse=True
            )
            for proc in procs[:limit]:
                info = proc.info
                name = info.get("name") or f"pid/{info.get('pid')}"
                result.append(
                    ProcessInfo(
                        pid=int(info.get("pid") or 0),
                        name=name,
                        cpu_percent=round(float(info.get("cpu_percent") or 0.0), 1),
                        memory_percent=round(float(info.get("memory_percent") or 0.0), 1),
                    )
                )
        except Exception:
            return []
        return result

    # ------------------------------------------------------------------ public

    def snapshot(self) -> TelemetrySnapshot:
        """
        Take a full telemetry snapshot of real host state and append
        bounded history entries.
        """
        cpu = self._cpu()
        memory = self._memory()
        disk = self._disk()
        network = self._network()
        gpu = self._gpu_report()
        top = self._top_processes()

        with self._lock:
            self._sequence += 1
            seq = self._sequence
            self._cpu_history.append(
                {
                    "t": cpu.timestamp,
                    "percent": cpu.percent,
                    "seq": seq,
                }
            )
            self._mem_history.append(
                {
                    "t": memory.timestamp,
                    "percent": memory.percent,
                    "seq": seq,
                }
            )
            self._net_history.append(
                {
                    "t": network.timestamp,
                    "up": network.up_bytes_sec,
                    "down": network.down_bytes_sec,
                    "seq": seq,
                }
            )

        return TelemetrySnapshot(
            timestamp=cpu.timestamp,
            sequence=seq,
            cpu=cpu,
            memory=memory,
            disk=disk,
            network=network,
            gpu=gpu,
            top_processes=top,
            data_origin=PROVENANCE_LIVE,
        )
