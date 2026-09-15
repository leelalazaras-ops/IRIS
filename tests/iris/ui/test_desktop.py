"""
Tests for the IRIS desktop UI.
"""
import sys
import pytest
from PySide6.QtWidgets import QApplication, QTextEdit, QLineEdit, QPushButton, QLabel
from src.iris.ui.desktop.main_window import IrisMainWindow


@pytest.fixture
def app():
    """Create a QApplication instance for testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_main_window_creation(app):
    """Test that the main window can be created and has expected UI elements."""
    window = IrisMainWindow()
    assert window.windowTitle() == "IRIS - Intelligent Responsive Interactive System"
    assert window.isVisible() is False  # Not shown yet

    # Check that central widget exists
    central_widget = window.centralWidget()
    assert central_widget is not None

    # Find child widgets by type (corrected class arguments)
    text_edits = central_widget.findChildren(QTextEdit)
    line_edits = central_widget.findChildren(QLineEdit)
    push_buttons = central_widget.findChildren(QPushButton)
    labels = central_widget.findChildren(QLabel)

    # We expect at least one of each
    assert len(text_edits) >= 1
    assert len(line_edits) >= 1
    assert len(push_buttons) >= 1
    assert len(labels) >= 1

    # Check specific widget properties
    conversation_display = window.conversation_display
    assert conversation_display is not None
    assert conversation_display.isReadOnly() is True

    text_input = window.text_input
    assert text_input is not None
    assert text_input.placeholderText() == "Type a message and press Enter or click Send..."

    send_button = window.send_button
    assert send_button is not None
    assert send_button.text() == "Send"

    status_label = window.status_label
    assert status_label is not None
    assert status_label.text() == "READY"

    # Clean up
    window.close()


def test_voice_button_exists(app):
    """Test that the voice push-to-talk button exists and is checkable."""
    window = IrisMainWindow()
    # The voice button should be present in the input layout
    voice_button = window.findChild(QPushButton, "voiceButton")
    assert voice_button is not None
    assert voice_button.text() == "Mic"
    # Ensure it's enabled by default
    assert voice_button.isEnabled()
    window.close()