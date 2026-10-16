"""
Application entry point for the IRIS desktop UI.

Launches the HUD command-center window by default. Falls back to the
classic Qt interface when Qt WebEngine is unavailable (or when the user
sets IRIS_UI_CLASSIC=1) — the classic window and all of its behavior are
unchanged.
"""

import os
import sys


def main():
    """Main entry point for the desktop UI."""
    app_module = None
    QApplication = None

    if os.environ.get("IRIS_UI_CLASSIC", "").strip() in ("1", "true", "yes"):
        want_hud = False
    else:
        want_hud = True

    window = None
    QApplication = None

    if want_hud:
        try:
            from PySide6.QtWidgets import QApplication as _QA
            from iris.ui.desktop.hud import IrisHudWindow, WEBENGINE_AVAILABLE

            if WEBENGINE_AVAILABLE:
                QApplication = _QA
                app_module = "hud"
        except ImportError:
            want_hud = False

    if app_module is None:
        from PySide6.QtWidgets import QApplication as _QA
        from iris.ui.desktop.main_window import IrisMainWindow

        QApplication = _QA
        app_module = "classic"

    app = QApplication(sys.argv)

    if app_module == "hud":
        from iris.ui.desktop.hud import IrisHudWindow

        window = IrisHudWindow()
        window.show()
    else:
        sys.stderr.write(
            "IRIS: Qt WebEngine is unavailable (or IRIS_UI_CLASSIC is set); "
            "starting the classic desktop interface.\n"
        )
        from iris.ui.desktop.main_window import IrisMainWindow

        window = IrisMainWindow()
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
