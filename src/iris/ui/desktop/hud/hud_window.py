"""
HUD command-center window for IRIS.

Hosts the local HTML/CSS/JS control surface inside Qt WebEngine and wires
the Qt backend worker to a typed QWebChannel bridge. Falls back cleanly
(never crashing the app) if WebEngine is unavailable.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Slot, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebChannel import QWebChannel

    WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None
    QWebChannel = None
    WEBENGINE_AVAILABLE = False

from iris.ui.desktop.backend import IrisWorker
from iris.ui.desktop.hud.bridge import IrisBridge

ASSETS_DIR = Path(__file__).parent / "assets"


class IrisHudWindow(QMainWindow):
    """
    Command-center window:

      - loads the fully-local HUD page (no CDN, no network),
      - bridges real IRIS backend signals to the page,
      - samples real system telemetry and security state on timers,
      - stops all timers/workers on close.
    """

    def __init__(self, worker: IrisWorker | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IRIS Command Center")
        self.resize(1440, 860)
        self.setMinimumSize(1280, 720)

        self._worker = worker or IrisWorker()
        self._webgl_detail = "UNKNOWN"

        self._bridge = IrisBridge(self._worker, self)
        self._connect_worker_signals()

        self._channel = QWebChannel(self)
        self._channel.registerObject("iris", self._bridge)

        self._view = QWebEngineView(self)
        self._view.page().setWebChannel(self._channel)
        self.setCentralWidget(self._view)

        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.setInterval(self._bridge._telemetry_interval_ms)
        self._telemetry_timer.timeout.connect(self._poll_telemetry)

        self._security_timer = QTimer(self)
        self._security_timer.setInterval(self._bridge._security_interval_ms)
        self._security_timer.timeout.connect(self._poll_security)

        self._history_timer = QTimer(self)
        self._history_timer.setInterval(15000)
        self._history_timer.timeout.connect(self._push_history)

        self._build_menus()
        self._load_page()

        self._telemetry_timer.start()
        self._security_timer.start()
        self._history_timer.start()

    # ---------------------------------------------------------------- setup

    def _load_page(self) -> None:
        index = ASSETS_DIR / "index.html"
        if not index.exists():  # defensive: assets must ship with the app
            raise RuntimeError(f"HUD assets missing: {index}")
        self._view.load(QUrl.fromLocalFile(str(index)))

    def _build_menus(self) -> None:
        menu = self.menuBar().addMenu("&Command")
        export_act = QAction("Export Security Report…", self)
        export_act.setShortcut(QKeySequence("Ctrl+E"))
        export_act.triggered.connect(self._export_report)
        menu.addAction(export_act)
        diag_act = QAction("Diagnostics", self)
        diag_act.setShortcut(QKeySequence("Ctrl+D"))
        diag_act.triggered.connect(self._push_diagnostics)
        menu.addAction(diag_act)

    def _connect_worker_signals(self) -> None:
        self._worker.telemetry_updated.connect(self._bridge.emit_telemetry)
        self._worker.status_changed.connect(self._bridge.emit_status)
        self._worker.error_occurred.connect(self._bridge.emit_error)
        self._worker.response_received.connect(self._bridge.emit_response)
        self._worker.voice_event.connect(self._bridge.emit_voice_event)

    # ------------------------------------------------------------- polling

    @Slot()
    def _poll_telemetry(self) -> None:
        snapshot = self._bridge._telemetry.snapshot()
        self._bridge.emit_telemetry(snapshot.to_dict())

    @Slot()
    def _poll_security(self) -> None:
        snapshot = self._bridge._observatory.poll()
        self._bridge._last_security = snapshot
        self._bridge.emit_security(snapshot)

    @Slot()
    def _push_history(self) -> None:
        turns = self._worker.get_recent_turns(limit=50)
        self._bridge.pushHistory.emit(
            __import__("json").dumps({"ok": True, "turns": turns})
        )

    @Slot()
    def _push_diagnostics(self) -> None:
        self._bridge.pushDiagnostics.emit(
            __import__("json").dumps(
                {"ok": True, "diagnostics": self._bridge.build_diagnostics()}
            )
        )

    def _export_report(self) -> None:
        import json as _json
        import time as _t

        default = f"iris-security-report-{_t.strftime('%Y%m%d-%H%M%S')}.md"
        path = self._bridge._cmd_request_export_path({"format": "md"})
        if not path.get("path"):
            return  # user cancelled
        result = self._bridge.invoke(
            "export_report",
            _json.dumps({"path": path["path"], "format": "md"}),
        )
        payload = _json.loads(result)
        if payload.get("ok"):
            self._bridge.emit_export_ready(path["path"], "md")

    # ---------------------------------------------------------- preferences

    @Slot(int, int)
    def apply_preferences(self, telemetry_ms: int, security_ms: int) -> None:
        self._telemetry_timer.setInterval(max(500, telemetry_ms))
        self._security_timer.setInterval(max(500, security_ms))

    # --------------------------------------------------------------- close

    @property
    def webgl_detail(self) -> str:
        return self._bridge._webgl_detail

    def closeEvent(self, event):
        """Stop every timer and the backend worker; nothing outlives the UI."""
        for timer in (
            self._telemetry_timer,
            self._security_timer,
            self._history_timer,
        ):
            timer.stop()
        try:
            self._view.page().setWebChannel(None)
        except Exception:
            pass
        self._worker.stop()
        super().closeEvent(event)
