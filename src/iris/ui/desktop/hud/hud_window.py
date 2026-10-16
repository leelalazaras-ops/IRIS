"""
HUD command-center window for IRIS.

Hosts the local HTML/CSS/JS control surface inside Qt WebEngine and wires
the Qt backend worker to a typed QWebChannel bridge. Falls back cleanly
(never crashing the app) if WebEngine is unavailable.

Performance model:
  - psutil / NVML / observatory enumeration runs on a dedicated daemon
    collector thread, never on the Qt UI thread. Snapshots arrive on the
    UI thread as queued Qt signal deliveries.
  - When the window is minimized (or otherwise not visible) the collector
    is paused entirely — no psutil calls, no WebChannel messages — and on
    re-shown a fresh sample is pushed immediately.
  - On close, the collector is joined with a timeout and the worker is
    stopped; nothing outlives the UI.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, QUrl, Qt, Slot
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
from iris.ui.desktop.hud.collector import HudCollector

ASSETS_DIR = Path(__file__).parent / "assets"


class IrisHudWindow(QMainWindow):
    """
    Command-center window:

      - loads the fully-local HUD page (no CDN, no network),
      - bridges real IRIS backend signals to the page,
      - samples real system telemetry and security state on the
        dedicated collector thread (NOT the UI thread),
      - pauses sampling while hidden/minimized,
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

        self._history_timer = QTimer(self)
        self._history_timer.setInterval(15000)
        self._history_timer.timeout.connect(self._push_history)

        # Real psutil/NVML/observatory work happens on this dedicated
        # (daemon) thread — never on the Qt UI thread.
        self._collector = HudCollector(
            self._bridge._telemetry,
            self._bridge._observatory,
            self._bridge.emit_telemetry_object,
            self._bridge.emit_security,
            self._bridge._telemetry_interval_ms,
            self._bridge._security_interval_ms,
        )

        self._build_menus()
        self._load_page()

        self._history_timer.start()  # the only UI-thread polling timer
        self._collector.start()

        self.installEventFilter(self)  # visibility-based throttling

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

    # ------------------------------------------------ visibility throttling

    def eventFilter(self, obj, event) -> bool:
        """Pause/resume background work when the window state changes."""
        if obj is self and event.type() == QEvent.Type.WindowStateChange:
            minimized = bool(self.windowState() & Qt.WindowMinimized)
            if minimized:
                self._collector.pause()
            else:
                self._collector.resume()
                # Fresh data right away on restore instead of waiting up to
                # a full interval for the next collector tick.
                self._bridge.refresh_telemetry_now()
        return False

    def showEvent(self, event) -> None:
        self._collector.resume()
        self._bridge.refresh_telemetry_now()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._collector.pause()
        super().hideEvent(event)

    # ---------------------------------------------------------- preferences

    @Slot(int, int)
    def apply_preferences(self, telemetry_ms: int, security_ms: int) -> None:
        self._collector.set_intervals(telemetry_ms, security_ms)

    # --------------------------------------------------------------- close

    @property
    def webgl_detail(self) -> str:
        return self._bridge._webgl_detail

    def closeEvent(self, event):
        """Stop the collector, every timer, and the backend worker."""
        self._history_timer.stop()
        self._collector.stop()
        self._collector.join(timeout=3.0)
        try:
            self._view.page().setWebChannel(None)
        except Exception:
            pass
        self._worker.stop()
        super().closeEvent(event)
