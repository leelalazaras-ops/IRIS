"""
IRIS HUD command-center package.

Local-only HTML/CSS/JS assets, Qt WebEngine hosting, and a typed
QWebChannel bridge between Python and the in-page control surface.
No network access is required at runtime.
"""

from iris.ui.desktop.hud.hud_window import (
    IrisHudWindow,
    WEBENGINE_AVAILABLE,
)

__all__ = ["IrisHudWindow", "WEBENGINE_AVAILABLE"]
