"""
Typed data models for IRIS system telemetry.

Every field produced from a real local measurement is tagged with a
provenance label so that the UI can display data origin unambiguously.

Provenance labels used across IRIS:
    LIVE        - measured directly from the host right now
    DERIVED     - computed from one or more LIVE measurements
    UNAVAILABLE - the measurement is not supported/collectible on this host
    SIMULATED   - clearly-marked demo content (never produced in this module)

Nothing in this module fabricates values: measurements that cannot be taken
are reported as UNAVAILABLE.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

PROVENANCE_LIVE = "LIVE"
PROVENANCE_DERIVED = "DERIVED"
PROVENANCE_UNAVAILABLE = "UNAVAILABLE"
PROVENANCE_SIMULATED = "SIMULATED"


def now_iso() -> str:
    """ISO-8601 UTC timestamp for telemetry records."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class CoreSpec:
    """A single measurement with provenance."""

    value: Any
    unit: str = ""
    provenance: str = PROVENANCE_LIVE
    detail: str = ""


@dataclass
class CpuSample:
    percent: float
    per_core: list[float]
    core_count: int
    freq_mhz: Optional[float]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "percent": self.percent,
            "per_core": self.per_core,
            "core_count": self.core_count,
            "freq_mhz": self.freq_mhz,
            "timestamp": self.timestamp,
        }


@dataclass
class MemorySample:
    percent: float
    used_bytes: int
    total_bytes: int
    available_bytes: int
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "percent": self.percent,
            "used_bytes": self.used_bytes,
            "total_bytes": self.total_bytes,
            "available_bytes": self.available_bytes,
            "timestamp": self.timestamp,
        }


@dataclass
class DiskSample:
    percent: float
    used_bytes: int
    total_bytes: int
    read_bytes_sec: Optional[float]
    write_bytes_sec: Optional[float]
    provenance: str = PROVENANCE_LIVE
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "percent": self.percent,
            "used_bytes": self.used_bytes,
            "total_bytes": self.total_bytes,
            "read_bytes_sec": self.read_bytes_sec,
            "write_bytes_sec": self.write_bytes_sec,
            "provenance": self.provenance,
            "timestamp": self.timestamp,
        }


@dataclass
class InterfaceInfo:
    name: str
    is_up: bool
    addresses: list[str]
    speed_mbps: str  # e.g. "1000" or "UNAVAILABLE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "is_up": self.is_up,
            "addresses": self.addresses,
            "speed_mbps": self.speed_mbps,
        }


@dataclass
class NetworkSample:
    up_bytes_sec: float
    down_bytes_sec: float
    interfaces: list[InterfaceInfo]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "up_bytes_sec": self.up_bytes_sec,
            "down_bytes_sec": self.down_bytes_sec,
            "interfaces": [i.to_dict() for i in self.interfaces],
            "timestamp": self.timestamp,
        }


@dataclass
class GpuReport:
    available: bool
    util_percent: str
    temperature_c: str
    vram_used_bytes: str
    vram_total_bytes: str
    provenance: str = PROVENANCE_UNAVAILABLE
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "util_percent": self.util_percent,
            "temperature_c": self.temperature_c,
            "vram_used_bytes": self.vram_used_bytes,
            "vram_total_bytes": self.vram_total_bytes,
            "provenance": self.provenance,
            "message": self.message,
        }


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
        }


@dataclass
class TelemetrySnapshot:
    """Full host telemetry reading with provenance attached."""

    timestamp: str
    cpu: CpuSample
    memory: MemorySample
    disk: DiskSample
    network: NetworkSample
    gpu: GpuReport
    top_processes: list[ProcessInfo] = field(default_factory=list)
    data_origin: str = PROVENANCE_LIVE
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "data_origin": self.data_origin,
            "cpu": self.cpu.to_dict(),
            "memory": self.memory.to_dict(),
            "disk": self.disk.to_dict(),
            "network": self.network.to_dict(),
            "gpu": self.gpu.to_dict(),
            "top_processes": [p.to_dict() for p in self.top_processes],
        }
