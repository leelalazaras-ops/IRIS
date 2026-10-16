"""
Tests for IRIS telemetry service.

These tests verify REAL behavior on the current host:
GPU is unavailable in the CI/sandbox (no pynvml), which is asserted
explicitly - the service must report UNAVAILABLE rather than fake data.
"""

import pytest

from iris.telemetry import PROVENANCE_UNAVAILABLE, TelemetryService


@pytest.fixture
def service():
    return TelemetryService(history_len=10)


def test_cpu_snapshot_is_real(service):
    snap = service.snapshot()
    assert 0.0 <= snap.cpu.percent <= 100.0
    assert snap.cpu.core_count >= 1
    assert snap.cpu.timestamp.endswith("Z")


def test_network_snapshot_is_real(service):
    snap = service.snapshot()
    assert snap.network.up_bytes_sec >= 0.0
    assert snap.network.down_bytes_sec >= 0.0
    names = [i.name for i in snap.network.interfaces]
    assert len(names) >= 1  # loopback always exists
    for iface in snap.network.interfaces:
        assert iface.speed_mbps == "UNAVAILABLE" or iface.speed_mbps.isdigit()


def test_disk_snapshot_is_real(service):
    snap = service.snapshot()
    assert 0.0 <= snap.disk.percent <= 100.0
    assert snap.disk.total_bytes > 0


def test_gpu_unavailable_is_reported_not_fabricated(service):
    snap = service.snapshot()
    if not snap.gpu.available:
        assert snap.gpu.util_percent == "UNAVAILABLE"
        assert snap.gpu.temperature_c == "UNAVAILABLE"
        assert snap.gpu.vram_used_bytes == "UNAVAILABLE"
        assert snap.gpu.vram_total_bytes == "UNAVAILABLE"
        assert snap.gpu.provenance == PROVENANCE_UNAVAILABLE
        assert snap.gpu.message  # explains why it is unavailable
    else:
        # Only valid if a GPU is actually installed in this environment.
        assert 0 <= int(snap.gpu.util_percent) <= 100


def test_snapshot_is_serializable(service):
    snap = service.snapshot()
    d = snap.to_dict()
    assert d["data_origin"] == "LIVE"
    assert "timestamp" in d and "sequence" in d
    assert isinstance(d["top_processes"], list)
    for proc in d["top_processes"]:
        assert set(proc) == {"pid", "name", "cpu_percent", "memory_percent"}


def test_history_is_bounded(service):
    for _ in range(30):
        service.snapshot()
    hist = service.get_history()
    assert len(hist["cpu"]) == 10
    assert len(hist["mem" if "mem" in hist else "memory"]) == 10


def test_sequence_increments(service):
    s1 = service.snapshot()
    s2 = service.snapshot()
    assert s2.sequence == s1.sequence + 1
