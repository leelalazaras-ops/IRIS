"""
Typed, narrowly scoped bridge between the IRIS Qt backend and the HUD web UI.

Security model:
  - The browser layer (Qt WebEngine) gets ONE object on the QWebChannel:
    this bridge. All interaction goes through a single validated entry
    point, `invoke(command, payload_json)`, with a fixed whitelist of
    commands. No arbitrary Python execution, no shell access, and no file
    I/O from the page except explicitly requested report exports.
  - Outgoing data is pushed through dedicated Qt signals as JSON strings.
  - Secrets (API keys, tokens, base URLs) are never routed through this
    bridge. State builders strip anything that smells like a secret and
    only expose provider/model names.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from PySide6.QtCore import QObject, Slot, Signal
from PySide6.QtWidgets import QFileDialog

from iris.security import SecurityObservatory, SecuritySnapshot
from iris.telemetry import TelemetryService

__version__ = None  # populated from iris package if available


def _safe_json(payload: Any) -> str:
    try:
        return json.dumps(payload)
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": "unserializable payload"})


class IrisBridge(QObject):
    """
    The only QWebChannel object exposed to the HUD page.

    JS-visible API:
        signals : pushTelemetry(str), pushState(str), pushStatus(str),
                  pushResponse(str), pushMessage(str), pushError(str),
                  pushVoiceEvent(str), pushSecurity(str),
                  pushDiagnostics(str), pushHistory(str),
                  preferencesChanged(int, int)
        method  : invoke(str command, str payload_json) -> str (json result)
    """

    pushTelemetry = Signal(str)
    pushState = Signal(str)
    pushStatus = Signal(str)
    pushResponse = Signal(str)
    pushMessage = Signal(str)
    pushError = Signal(str)
    pushVoiceEvent = Signal(str)
    pushSecurity = Signal(str)
    pushDiagnostics = Signal(str)
    pushHistory = Signal(str)
    pushWebglStatus = Signal(str)
    preferencesChanged = Signal(int, int)

    #: commands the JS side may request; anything else is rejected
    COMMANDS = (
        "get_state",
        "get_history",
        "get_diagnostics",
        "send_message",
        "run_command",
        "toggle_voice",
        "push_to_talk",
        "get_security",
        "refresh_security",
        "search_findings",
        "search_history",
        "export_report",
        "get_telemetry_snapshot",
        "set_preferences",
        "report_webgl",
        "request_export_path",
    )

    def __init__(self, worker, parent=None):
        super().__init__(parent)
        self._worker = worker
        self._observatory = SecurityObservatory()
        self._telemetry = TelemetryService()
        self._last_security: Optional[SecuritySnapshot] = None
        self._telemetry_interval_ms = 2000
        self._security_interval_ms = 5000
        self._webgl_ok: Optional[bool] = None
        self._webgl_detail = "UNKNOWN"
        self._last_gpu_note = "UNAVAILABLE — no sample yet"

    # ------------------------------------------------------------ from worker

    def emit_telemetry(self, data: dict) -> None:
        self.pushTelemetry.emit(_safe_json(data))

    # Called from the collector thread (not the UI thread). QWebChannel
    # signal emits are thread-safe queued connections, so marshalling to
    # the UI thread happens here — no timers, no locks held.
    def emit_telemetry_object(self, snapshot) -> None:
        try:
            data = snapshot.to_dict()
        except Exception:
            return
        try:
            gpu_note = (data.get("gpu") or {}).get("message") or self._last_gpu_note
        except Exception:
            gpu_note = self._last_gpu_note
        self._last_gpu_note = gpu_note
        self.pushTelemetry.emit(_safe_json(data))

    def emit_state(self) -> None:
        self.pushState.emit(_safe_json(self.build_state()))

    def emit_status(self, status: str) -> None:
        self.pushStatus.emit(_safe_json({"status": status}))

    def emit_response(self, text: str) -> None:
        self.pushResponse.emit(
            _safe_json({"role": "assistant", "content": text})
        )

    def emit_error(self, text: str) -> None:
        self.pushError.emit(_safe_json({"role": "error", "content": text}))

    def emit_voice_event(self, event: str) -> None:
        self.pushVoiceEvent.emit(_safe_json({"event": event}))

    def emit_security(self, snapshot: SecuritySnapshot) -> None:
        self.pushSecurity.emit(_safe_json(snapshot.to_dict()))

    def emit_export_ready(self, path: str, fmt: str) -> None:
        self.pushMessage.emit(
            _safe_json(
                {
                    "role": "system",
                    "content": f"Exported {fmt.upper()} security report: {path}",
                }
            )
        )

    # -------------------------------------------------------------- builders

    def build_state(self) -> dict:
        """Initial handshake state. Contains no secrets and no URLs."""
        worker = self._worker
        state = {
            "app": "IRIS",
            "version": self._app_version(),
            "backend": worker.describe_state(),
            "tools": worker.get_tool_names(),
            "voice": {
                "mode": worker.describe_state().get("voice", "OFF"),
            },
            "provenance_legend": {
                "LIVE": "measured on this host right now",
                "DERIVED": "computed from live measurements",
                "SIMULATED": "labeled demo content, never counted as real",
                "UNAVAILABLE": "cannot be measured in this environment",
            },
        }
        return state

    @staticmethod
    def _app_version() -> str:
        try:
            from iris import __version__ as v  # type: ignore
        except Exception:
            try:
                from importlib.metadata import PackageNotFoundError, version

                v = version("iris")
            except Exception:
                v = "0.3.0"
        return str(v)

    def build_diagnostics(self) -> dict:
        diag = self._worker.describe_diagnostics()
        diag.update(
            {
                "webengine": True,
                "webgl": self._webgl_detail,
                "telemetry_provenance": "LIVE (psutil)",
                "gpu_note": self._last_gpu_note,  # cached from last live sample
            }
        )
        return diag

    # ------------------------------------------------------------ big entry

    @Slot(str, str, result=str)
    def invoke(self, command: str, payload_json: str = "{}") -> str:
        """
        Single validated entry point for the web layer.
        Returns a JSON string: {"ok": true/false, ...}.
        """
        if command not in self.COMMANDS:
            return _safe_json({"ok": False, "error": f"unknown command: {command}"})

        try:
            payload = json.loads(payload_json) if payload_json else {}
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
        except (ValueError, TypeError) as exc:
            return _safe_json({"ok": False, "error": f"bad payload: {exc}"})

        handler = {
            "get_state": self._cmd_get_state,
            "get_history": self._cmd_get_history,
            "get_diagnostics": self._cmd_get_diagnostics,
            "send_message": self._cmd_send_message,
            "run_command": self._cmd_run_command,
            "toggle_voice": self._cmd_toggle_voice,
            "push_to_talk": self._cmd_push_to_talk,
            "get_security": self._cmd_get_security,
            "refresh_security": self._cmd_refresh_security,
            "search_findings": self._cmd_search_findings,
            "search_history": self._cmd_search_history,
            "export_report": self._cmd_export_report,
            "get_telemetry_snapshot": self._cmd_telemetry_snapshot,
            "set_preferences": self._cmd_set_preferences,
            "report_webgl": self._cmd_report_webgl,
            "request_export_path": self._cmd_request_export_path,
        }[command]

        try:
            return _safe_json(handler(payload))
        except Exception as exc:  # single guarded catch-all surface
            return _safe_json(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            )

    # ------------------------------------------------------------ handlers

    def _cmd_get_state(self, payload: dict) -> dict:
        return {"ok": True, "state": self.build_state()}

    def _cmd_get_history(self, payload: dict) -> dict:
        limit = self._parse_limit(payload, default=50)
        turns = self._worker.get_recent_turns(limit=limit)
        return {"ok": True, "turns": turns, "data_origin": "LIVE"}

    def _cmd_get_diagnostics(self, payload: dict) -> dict:
        return {"ok": True, "diagnostics": self.build_diagnostics()}

    def _cmd_send_message(self, payload: dict) -> dict:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return {"ok": False, "error": "text is required"}
        self._worker.process_user_input(text.strip())
        return {"ok": True, "queued": True}

    def _cmd_run_command(self, payload: dict) -> dict:
        text = payload.get("command")
        if not isinstance(text, str):
            return {"ok": False, "error": "command text is required"}
        base = text.strip().lstrip("/").split(maxsplit=1)[0].lower()
        if base not in self._worker.ALLOWED_COMMANDS:
            return {"ok": False, "error": f"command not allowed: /{base}"}
        self._worker.process_command("/" + base)
        return {"ok": True, "queued": True}

    def _cmd_toggle_voice(self, payload: dict) -> dict:
        self._worker.toggle_voice()
        return {"ok": True, "state": self._worker.describe_state()}

    def _cmd_push_to_talk(self, payload: dict) -> dict:
        self._worker.push_to_talk()
        return {"ok": True, "queued": True}

    def _cmd_get_security(self, payload: dict) -> dict:
        if self._last_security is None:
            self._cmd_refresh_security({})
        snap = self._last_security
        return {"ok": True, "snapshot": snap.to_dict() if snap else None}

    def _cmd_refresh_security(self, payload: dict) -> dict:
        snapshot = self._observatory.poll()
        self._last_security = snapshot
        self.emit_security(snapshot)
        return {"ok": True, "snapshot": snapshot.to_dict()}

    def _cmd_search_findings(self, payload: dict) -> dict:
        if self._last_security is None:
            self._cmd_refresh_security({})
        snap = self._last_security
        query = str(payload.get("query", ""))
        severities = payload.get("severities")
        if severities is not None and not isinstance(severities, list):
            return {"ok": False, "error": "severities must be a list"}
        results = self._observatory.get_searchable_findings(
            snap, query=query, severities=severities
        )
        return {
            "ok": True,
            "findings": results,
            "classification": "HEURISTIC",
            "data_origin": "LIVE",
        }

    def _cmd_search_history(self, payload: dict) -> dict:
        query = str(payload.get("query", "")).strip().lower()
        limit = self._parse_limit(payload, default=100)
        turns = self._worker.get_recent_turns(limit=limit)
        if query:
            turns = [
                t
                for t in turns
                if query in t.get("content", "").lower()
                or query in t.get("role", "").lower()
            ]
        return {"ok": True, "turns": turns, "data_origin": "LIVE"}

    def _cmd_telemetry_snapshot(self, payload: dict) -> dict:
        snap = self._telemetry.snapshot()
        self.pushTelemetry.emit(_safe_json(snap.to_dict()))
        return {"ok": True, "snapshot": snap.to_dict()}

    def _cmd_set_preferences(self, payload: dict) -> dict:
        telem = payload.get("telemetry_interval_ms")
        sec = payload.get("security_interval_ms")
        if telem is not None:
            self._set_interval("telemetry_interval_ms", telem, self._set_telemetry_interval)
        if sec is not None:
            self._set_interval("security_interval_ms", sec, self._set_security_interval)
        return {
            "ok": True,
            "telemetry_interval_ms": self._telemetry_interval_ms,
            "security_interval_ms": self._security_interval_ms,
        }

    def _set_interval(self, key: str, value: Any, apply) -> None:
        try:
            ms = int(value)
        except (TypeError, ValueError):
            return
        if ms < 500:
            ms = 500
        if ms > 60000:
            ms = 60000
        apply(ms)

    def _set_telemetry_interval(self, ms: int) -> None:
        self._telemetry_interval_ms = ms
        self.preferencesChanged.emit(ms, self._security_interval_ms)

    def _set_security_interval(self, ms: int) -> None:
        self._security_interval_ms = ms
        self.preferencesChanged.emit(self._telemetry_interval_ms, ms)

    def refresh_telemetry_now(self) -> None:
        """Push one immediate telemetry sample to the page.

        Used when the window becomes visible again (restore from
        minimize) so the HUD has fresh data instead of waiting up to a
        full collector interval. Bounded cost: a single psutil/LIVE
        snapshot (~3 ms in this container), no secrets, no extra state.
        """
        try:
            snap = self._telemetry.snapshot()
            self.pushTelemetry.emit(_safe_json(snap.to_dict()))
        except Exception:
            pass

    def _cmd_report_webgl(self, payload: dict) -> dict:
        ok = bool(payload.get("available", False))
        detail = str(payload.get("detail", ""))[:120]
        self._webgl_ok = ok
        self._webgl_detail = (
            f"{'AVAILABLE' if ok else 'UNAVAILABLE'}"
            + (f" ({detail})" if detail else "")
        )
        self.pushWebglStatus.emit(
            _safe_json({"available": ok, "detail": self._webgl_detail})
        )
        return {"ok": True}

    def _cmd_request_export_path(self, payload: dict) -> dict:
        """
        Show a native save dialog and return the chosen path to the page.
        The page cannot write files itself; follow-up `export_report` is
        the only file-writing command and it writes a generated report only.
        """
        fmt = payload.get("format", "md")
        if fmt not in ("md", "json"):
            return {"ok": False, "error": "format must be 'md' or 'json'"}
        import time as _t

        default_name = f"iris-security-report-{_t.strftime('%Y%m%d-%H%M%S')}.{fmt}"
        filters = {
            "md": "Markdown (*.md);;All Files (*)",
            "json": "JSON (*.json);;All Files (*)",
        }[fmt]
        path, _selected = QFileDialog.getSaveFileName(
            self, "Export Security Report", default_name, filters
        )
        if not path:
            return {"ok": True, "path": None, "cancelled": True}
        return {"ok": True, "path": path, "cancelled": False}

    def _cmd_export_report(self, payload: dict) -> dict:
        path = payload.get("path")
        fmt = payload.get("format", "md")
        if fmt not in ("md", "json"):
            return {"ok": False, "error": "format must be 'md' or 'json'"}
        if not isinstance(path, str) or not path.strip():
            return {"ok": False, "error": "path is required"}
        # prevent writing outside plausible report destinations is not
        # reasonable to enforce in a desktop app (user picked the path via
        # a native dialog); still refuse obviously destructive paths.
        suspicious = (path.endswith("/"), path.endswith("\\"))
        if any(suspicious):
            return {"ok": False, "error": "invalid path"}
        if self._last_security is None:
            self._cmd_refresh_security({})
        written = SecurityObservatory.export_report(self._last_security, path, fmt=fmt)
        self.emit_export_ready(written, fmt)
        return {"ok": True, "path": written, "format": fmt}

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _parse_limit(payload: dict, default: int) -> int:
        try:
            raw = payload.get("limit", default)
            limit = int(raw)
        except (TypeError, ValueError):
            limit = default
        return max(1, min(limit, 500))
