"""
IRIS telemetry: real host measurements with explicit provenance.

Exports the public telemetry API used by the IRIS desktop UI and bridge.
"""

from iris.telemetry.models import (
    PROVENANCE_DERIVED,
    PROVENANCE_LIVE,
    PROVENANCE_SIMULATED,
    PROVENANCE_UNAVAILABLE,
    TelemetrySnapshot,
    now_iso,
)
from iris.telemetry.service import TelemetryService

__all__ = [
    "PROVENANCE_DERIVED",
    "PROVENANCE_LIVE",
    "PROVENANCE_SIMULATED",
    "PROVENANCE_UNAVAILABLE",
    "TelemetryService",
    "TelemetrySnapshot",
    "now_iso",
]
