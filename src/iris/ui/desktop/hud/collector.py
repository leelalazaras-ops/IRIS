"""
Background telemetry + security collector for the HUD.

Collects real host measurements (psutil / NVML / the read-only
observatory) on a dedicated daemon thread so the Qt UI thread is never
blocked by synchronous process/enumeration work — the heaviest part of
the pipeline, and on typical Windows machines process enumeration
dominates the frame budget when executed on the GUI thread.

Pause/resume is tied to window visibility: when the window is hidden or
minimized no samples are taken at all (no psutil calls, no WebChannel
messages), and collection resumes with an immediate sample when the
window becomes visible again.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional


class HudCollector(threading.Thread):
    """One daemon thread driving both telemetry and security cadences."""

    def __init__(
        self,
        telemetry_service,
        observatory,
        on_telemetry: Callable[[object], None],
        on_security: Callable[[object], None],
        telemetry_ms: int = 2000,
        security_ms: int = 5000,
    ) -> None:
        super().__init__(name="iris-hud-collector", daemon=True)
        self._telemetry = telemetry_service
        self._observatory = observatory
        self._on_telemetry = on_telemetry
        self._on_security = on_security
        self._telemetry_ms = max(500, int(telemetry_ms))
        self._security_ms = max(500, int(security_ms))
        self._stop_evt = threading.Event()
        self._pause = threading.Event()  # set == paused (window not visible)
        self._interval_lock = threading.Lock()

    # ------------------------------------------------------------- control

    def stop(self) -> None:
        self._stop_evt.set()
        self._pause.clear()  # wake the sleeper

    def pause(self) -> None:
        """Stop sampling entirely (window hidden/minimized). Non-blocking."""
        self._pause.set()

    def resume(self) -> None:
        """Resume sampling immediately (a fresh sample is taken first)."""
        self._pause.clear()

    def set_intervals(self, telemetry_ms: int, security_ms: int) -> None:
        with self._interval_lock:
            self._telemetry_ms = max(500, int(telemetry_ms))
            self._security_ms = max(500, int(security_ms))

    @property
    def is_paused(self) -> bool:
        return self._pause.is_set()

    @property
    def intervals_ms(self) -> tuple[int, int]:
        telemetry_s, security_s = self._current_intervals()
        return int(telemetry_s * 1000), int(security_s * 1000)

    def _current_intervals(self) -> tuple[float, float]:
        with self._interval_lock:
            return self._telemetry_ms / 1000.0, self._security_ms / 1000.0

    # ----------------------------------------------------------------- run

    def run(self) -> None:
        telemetry_s, security_s = self._current_intervals()
        next_telemetry = 0.0   # due immediately on start
        next_security = 0.0

        while not self._stop_evt.is_set():
            if self._pause.is_set():
                # Idle: cheap conditional wait, wakes on resume()/stop().
                self._pause.wait(timeout=0.5)
                if self._pause.is_set():
                    continue
                # Just resumed: sample immediately, then re-arm cadences.
                telemetry_s, security_s = self._current_intervals()
                next_telemetry = 0.0
                next_security = 0.0
                continue

            now = time.monotonic()
            did_work = False
            if now >= next_telemetry:
                try:
                    self._on_telemetry(self._telemetry.snapshot())
                except Exception:
                    pass  # never let a bad sample kill the collector
                telemetry_s, _ = self._current_intervals()
                next_telemetry = time.monotonic() + telemetry_s
                did_work = True
            if now >= next_security:
                try:
                    self._on_security(self._observatory.poll())
                except Exception:
                    pass
                _, security_s = self._current_intervals()
                next_security = time.monotonic() + security_s
                did_work = True

            if not did_work:
                # Sleep only until the next due sample (bounded to 0.25 s
                # so stop()/set_intervals() stay responsive).
                wait_s = min(0.25, max(0.0, next_telemetry - time.monotonic()))
                self._stop_evt.wait(timeout=wait_s)
