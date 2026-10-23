"""
Tests for the IRIS HUD command-center window.

These run headless (offscreen platform). WebEngine availability is
detected at import time; tests skip cleanly when PySide6-WebEngine is
not installed so CI without the optional dependency stays green.
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Chromium refuses to run as root without these flags (containers/CI).
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage",
)

from iris.ui.desktop.backend import IrisWorker

pytest.importorskip("iris.ui.desktop.hud.hud_window", reason="HUD window import failed")

from iris.ui.desktop.hud.hud_window import ASSETS_DIR, WEBENGINE_AVAILABLE, IrisHudWindow  # noqa: E402

pytestmark = pytest.mark.skipif(
    not WEBENGINE_AVAILABLE, reason="PySide6 WebEngine is not installed"
)


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def worker():
    return IrisWorker()


def test_map_view_assets_and_attribution():
    """Map view ships as real markup; attribution is enforced by the module."""
    html = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    assert "view-map" in html
    assert "map-attrib" in html  # attribution slot exists (link injected by map.js)
    js = (ASSETS_DIR / "js" / "map.js").read_text(encoding="utf-8")
    assert "tile.openstreetmap.org" in js
    assert "openstreetmap.org/copyright" in js


def test_core_contract_mode_null_fallback_and_winding_guard():
    """Regression: core3d must never claim success without real WebGL.

    The late-breaking globe regression was caused by mode starting as the
    truthy string "none" so start() skipped _initGL entirely, then app.js
    reported any non-2d mode as AVAILABLE; plus back-face culling turned
    the sphere into an invisible shell. These checks pin the contract.
    """
    src = (ASSETS_DIR / "js" / "core3d.js").read_text(encoding="utf-8")
    # module-level init gate: mode starts falsy (null), never a truthy label
    assert 'this.mode = null;' in src
    assert 'this.mode = "none"' not in src
    # start() must attempt GL init before considering 2D fallback
    assert "_initGL())" in src.replace(" ", "") or "this._initGL()" in src
    # culling must not be enabled (culling hid the sphere when winding
    # was CW-outward); comment may mention it, so check the GL call form
    assert "gl.enable(gl.CULL_FACE)" not in src
    # app.js must gate AVAILABLE on the actual webgl mode strings
    app = (ASSETS_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert 'mode === "webgl2" || mode === "webgl1"' in app


def test_map_lazy_state_and_error_distinctness():
    """Map must fetch tiles only after create(), and expose distinct states."""
    msrc = (ASSETS_DIR / "js" / "map.js").read_text(encoding="utf-8")
    # distinct offline vs error status messages
    assert "OFFLINE" in msrc
    assert "TILE FETCH FAILED" in msrc
    # loading transmit state class exists in CSS
    css = (ASSETS_DIR / "css" / "style.css").read_text(encoding="utf-8")
    assert ".map-tile-loading" in css
    assert ".map-status.map-bad" in css


def test_core_geometry_upload_contract():
    """Regression: globe must upload real vertex data, never an empty buffer.

    _sphereGeometry returns { array, positionCount }. A past regression
    built the Float32Array from `sphere.length` (undefined on that
    object) — uploading a zero-length buffer while coreCount stayed
    correct, so every triangle collapsed to the origin and the globe
    pass drew nothing. The same bug existed for the rim shell buffer.
    """
    src = (ASSETS_DIR / "js" / "core3d.js").read_text(encoding="utf-8")
    assert "new Float32Array(sphere.array)" in src
    assert "new Float32Array(shell.array)" in src
    # the broken forms must not come back
    assert "new Float32Array(sphere.length)" not in src
    assert "new Float32Array(shell)" not in src


def test_hud_window_remote_tile_settings():
    """Regression: both file-URL permission attributes must be set.

    LocalContentCanAccessRemoteUrls defaults to false, which makes
    Chromium abort every remote tile fetch from the file:// HUD page
    with no network attempt at all (verified via net-log). Setting it
    also implicitly flips LocalContentCanAccessFileUrls to false in
    current QtWebEngine, so both must be asserted explicitly.
    """
    src = Path("src/iris/ui/desktop/hud/hud_window.py").read_text(encoding="utf-8")
    assert "LocalContentCanAccessRemoteUrls, True" in src
    assert "LocalContentCanAccessFileUrls, True" in src
    # ordering note: FileUrls must be re-asserted after the remote flag
    assert (src.find("LocalContentCanAccessRemoteUrls, True")
            < src.find("LocalContentCanAccessFileUrls, True"))


def test_local_assets_exist_and_reference_no_cdn():
    index = ASSETS_DIR / "index.html"
    assert index.exists()
    html = index.read_text(encoding="utf-8")
    # Essential assets must not depend on CDNs or the internet.
    assert "https://" not in html
    assert "http://" not in html
    for ref in ("js/qwebchannel.js", "js/core3d.js", "js/app.js", "js/map.js", "css/style.css"):
        assert ref in html
        assert (ASSETS_DIR / ref).exists(), ref


def test_construct_hud_window(qapp, worker):
    window = IrisHudWindow(worker)
    try:
        assert window.windowTitle() == "IRIS Command Center"
        assert window.centralWidget() is not None
        # collector thread drives snapshots; UI thread never blocks on psutil
        assert window._collector.is_alive()
        # manual refresh paths still work without touching the collector
        window._bridge.refresh_telemetry_now()
        window._bridge._cmd_refresh_security({})
        window._push_history()
        window._push_diagnostics()
        assert window.webgl_detail in ("UNKNOWN",) or window.webgl_detail
    finally:
        window.close()
    assert not window._collector.is_alive()


def test_close_stops_workers_and_timers(qapp, worker):
    window = IrisHudWindow(worker)
    for timer in window.findChildren(__import__("PySide6.QtCore", fromlist=["QTimer"]).QTimer):
        assert timer.isActive()
    window.close()
    assert worker._stop_event.is_set()
    for timer in window.findChildren(__import__("PySide6.QtCore", fromlist=["QTimer"]).QTimer):
        assert not timer.isActive()


def test_preferences_apply_to_collector(qapp, worker):
    window = IrisHudWindow(worker)
    try:
        window.apply_preferences(1000, 3000)
        telemetry_ms, security_ms = window._collector.intervals_ms
        assert telemetry_ms == 1000
        assert security_ms == 3000
    finally:
        window.close()


def test_bridge_is_registered_with_channel(qapp, worker):
    from PySide6.QtWebChannel import QWebChannel

    window = IrisHudWindow(worker)
    try:
        assert isinstance(window._channel, QWebChannel)
        assert window._bridge is not None
    finally:
        window.close()


def test_page_loads_from_local_file(qapp, worker):
    """Acceptance: the WebEngine UI loads the local HUD page (no CDN needed)."""
    from PySide6.QtCore import QEventLoop, QTimer, QUrl

    window = IrisHudWindow(worker)
    try:
        loop = QEventLoop()
        result = {}

        def on_load(ok: bool):
            result["ok"] = ok
            loop.quit()

        window._view.loadFinished.connect(on_load)
        # Re-issue the load so the signal listeners are already connected.
        window._view.load(QUrl.fromLocalFile(str(ASSETS_DIR / "index.html")))
        QTimer.singleShot(15000, loop.quit)  # hard cap: never hang the suite
        loop.exec()

        assert result.get("ok") is True, "HUD page failed to load"
        url = window._view.url().toString()
        assert url.startswith("file://"), url
    finally:
        window.close()
