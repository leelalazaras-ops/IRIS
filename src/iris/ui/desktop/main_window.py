"""
Main window for the IRIS desktop UI.
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QFrame,
    QSplitter,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QIcon

from .backend import IrisWorker


class IrisMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IRIS - Intelligent Responsive Interactive System")
        self.setMinimumSize(900, 600)
        self._worker = IrisWorker()
        self._worker.response_received.connect(self._append_iris_response)
        self._worker.status_changed.connect(self._update_status)
        self._worker.error_occurred.connect(self._show_error)
        self._worker.telemetry_updated.connect(self._update_telemetry)
        # Store references to sidebar value labels for updates
        self._sidebar_labels = {}
        self.setup_ui()
        self.apply_dark_theme()
        # Start backend worker
        self._worker.start()

    def setup_ui(self):
        """Set up the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(8)

        # Sidebar title
        sidebar_title = QLabel("IRIS")
        sidebar_title.setObjectName("sidebarTitle")
        sidebar_title_font = QFont()
        sidebar_title_font.setPointSize(18)
        sidebar_title_font.setBold(True)
        sidebar_title.setFont(sidebar_title_font)
        sidebar_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(sidebar_title)

        # Sidebar status placeholders
        # We'll handle VOICE specially with a toggle button
        status_labels = [
           ("SYSTEM STATUS", "N/A"),
    ("AI STATUS", "N/A"),
    ("AI ENGINE", "N/A"),
    ("VOICE", None),
    ("SECURITY", "N/A"),
    ("ACTION STATE", "IDLE"),
    ("TOOLS", "N/A"),
    ("DRY RUN", "OFF"),
        ]
        for title, value in status_labels:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame_layout = QHBoxLayout(frame)
            frame_layout.setContentsMargins(8, 4, 8, 4)
            title_label = QLabel(title)
            title_label.setObjectName("sidebarTitleLabel")
            if value is None:
                # Special case for VOICE: create a toggle button
                self.voice_toggle = QPushButton("OFF")
                self.voice_toggle.setCheckable(True)
                self.voice_toggle.setObjectName("voiceToggle")
                self.voice_toggle.toggled.connect(self._on_voice_toggled)
                frame_layout.addWidget(title_label)
                frame_layout.addStretch()
                frame_layout.addWidget(self.voice_toggle)
            else:
                value_label = QLabel(value)
                value_label.setObjectName("sidebarValueLabel")
                frame_layout.addWidget(title_label)
                frame_layout.addStretch()
                frame_layout.addWidget(value_label)
                # Store reference to value label for later updates
                self._sidebar_labels[title] = value_label
            sidebar_layout.addWidget(frame)

        sidebar_layout.addStretch()
        main_layout.addWidget(sidebar)

        # Main chat area
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(12, 12, 12, 12)
        chat_layout.setSpacing(8)

        # Header
        header_label = QLabel("IRIS")
        header_label.setObjectName("headerLabel")
        header_font = QFont()
        header_font.setPointSize(24)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chat_layout.addWidget(header_label)

        # Conversation display area
        self.conversation_display = QTextEdit()
        self.conversation_display.setObjectName("conversationDisplay")
        self.conversation_display.setReadOnly(True)
        self.conversation_display.setPlaceholderText("Conversation will appear here...")
        chat_layout.addWidget(self.conversation_display, stretch=1)

        # Input area
        input_layout = QHBoxLayout()
        self.text_input = QLineEdit()
        self.text_input.setObjectName("textInput")
        self.text_input.setPlaceholderText("Type a message and press Enter or click Send...")
        self.text_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.text_input, stretch=1)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)

        self.voice_button = QPushButton("Mic")
        self.voice_button.setObjectName("voiceButton")
        self.voice_button.clicked.connect(self._on_voice_button_clicked)
        input_layout.addWidget(self.voice_button)

        chat_layout.addLayout(input_layout)

        # Status indicator
        self.status_label = QLabel("READY")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        chat_layout.addWidget(self.status_label)

        main_layout.addWidget(chat_container, stretch=1)

    def apply_dark_theme(self):
        """Apply a dark theme with cyan accents."""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #000000;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            #sidebar {
                background-color: #001a1a;
                border-right: 1px solid #003333;
            }
            #sidebarTitle {
                color: #00ffff;
                margin-bottom: 12px;
            }
            #sidebarTitleLabel {
                color: #00ffff;
                font-weight: bold;
            }
            #sidebarValueLabel {
                color: #00ff88;
                font-weight: bold;
            }
            #voiceToggle {
                background-color: #006666;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
                min-width: 30px;
            }
            #voiceToggle:checked {
                background-color: #009999;
            }
            #voiceToggle:hover:!checked {
                background-color: #005555;
            }
            QFrame[frameShape="5"] {  /* StyledPanel */
                background-color: #000f0f;
                border: 1px solid #003333;
                border-radius: 4px;
                margin-bottom: 4px;
            }
            #headerLabel {
                color: #00ffff;
                margin-bottom: 8px;
            }
            #conversationDisplay {
                background-color: #000f0f;
                color: #e0e0e0;
                border: 1px solid #003333;
                border-radius: 4px;
                padding: 8px;
                selection-background-color: #003333;
            }
            #textInput {
                background-color: #000f0f;
                color: #e0e0e0;
                border: 1px solid #003333;
                border-radius: 4px;
                padding: 8px;
            }
            #textInput:focus {
                border: 1px solid #00ffff;
            }
            #sendButton {
                background-color: #006666;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            #sendButton:hover {
                background-color: #009999;
            }
            #sendButton:pressed {
                background-color: #003333;
            }
            #statusLabel {
                color: #00ff88;
                font-weight: bold;
                margin-top: 8px;
            }
        """)

    @Slot()
    def send_message(self):
        """Handle sending a message."""
        text = self.text_input.text().strip()
        if not text:
            return

        # Display the user's message
        self.conversation_display.append(f"You: {text}")
        self.text_input.clear()
        # Disable input while processing to avoid flooding
        self.text_input.setEnabled(False)
        self.send_button.setEnabled(False)
        # Process via backend
        self._worker.process_user_input(text)

    @Slot()
    def _on_voice_button_clicked(self):
        """Handle push-to-talk voice button clicked."""
        # Only trigger if voice is enabled (optional, could also allow regardless)
        self._worker.push_to_talk()

    @Slot(bool)
    def _on_voice_toggled(self, checked):
        """Handle voice toggle button clicked."""
        self._worker.toggle_voice()
        # The telemetry update will handle updating the button state

    @Slot(str)
    def _append_iris_response(self, response: str):
        """Append IRIS response to conversation display."""
        self.conversation_display.append(f"IRIS: {response}")
        self.text_input.setEnabled(True)
        self.send_button.setEnabled(True)
        # Scroll to bottom
        self.conversation_display.verticalScrollBar().triggerAction(
            self.conversation_display.verticalScrollBar().SliderAction.SliderToMaximum
        )

    @Slot(str)
    def _update_status(self, status: str):
        """Update status label."""
        self.status_label.setText(status)

    @Slot(str)
    def _show_error(self, error_msg: str):
        """Show error in conversation display."""
        self.conversation_display.append(f"ERROR: {error_msg}")
        self.text_input.setEnabled(True)
        self.send_button.setEnabled(True)
        self._update_status("ERROR")

    @Slot(dict)
    def _update_telemetry(self, data: dict):
        """Update sidebar labels with telemetry data."""
        mapping = {
            "SYSTEM STATUS": data.get("system_status", "N/A"),
            "AI STATUS": data.get("ai_status", "N/A"),
            "VOICE": data.get("voice", "N/A"),
            "SECURITY": data.get("security", "N/A"),
            "TOOLS": data.get("tools", "N/A"),
        }
        for title, value in mapping.items():
            label = self._sidebar_labels.get(title)
            if label:
                label.setText(value)
        # Special handling for VOICE toggle button
        voice_state = data.get("voice", "N/A")
        if hasattr(self, 'voice_toggle'):
            if voice_state == "ON":
                self.voice_toggle.setChecked(True)
                self.voice_toggle.setText("ON")
            else:
                self.voice_toggle.setChecked(False)
                self.voice_toggle.setText("OFF")

    def closeEvent(self, event):
        """Handle window close event."""
        self._worker.stop()
        super().closeEvent(event)