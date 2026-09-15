"""
Application entry point for the IRIS desktop UI.
"""

import sys
from PySide6.QtWidgets import QApplication
from .main_window import IrisMainWindow


def main():
    """Main entry point for the desktop UI."""
    app = QApplication(sys.argv)
    window = IrisMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()