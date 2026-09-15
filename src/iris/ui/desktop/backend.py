"""
Backend integration for IRIS desktop UI.
Wraps the existing IRISConversation to run in a background thread.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional, Dict

from PySide6.QtCore import QObject, Signal, QTimer

from iris.core.cli import IRISConversation

try:
    from iris.voice.voice_io import listen_for_speech
except ImportError:  # pragma: no cover - voice optional
    listen_for_speech = None


class IrisWorker(QObject):
    """Worker that runs IRIS conversation logic in a separate thread."""

    # Signals to communicate with the UI
    response_received = Signal(str)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    telemetry_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self._conversation: Optional[IRISConversation] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._timer: Optional[QTimer] = None
        self._lock = threading.Lock()

    def start(self):
        """Start the worker thread and initialize the conversation."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_worker, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the worker thread."""
        self._stop_event.set()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run_worker(self):
        """Worker thread entry point: run asyncio event loop."""
        # Create a new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            # Initialize conversation
            with self._lock:
                self._conversation = IRISConversation()
            # Initialize AI service (this may block)
            init_success = self._loop.run_until_complete(self._conversation.initialize())
            if not init_success:
                self.error_occurred.emit("Failed to initialize AI service. Check configuration.")
                return

            self.status_changed.emit("READY")

            # Set up telemetry timer
            self._timer = QTimer()
            self._timer.timeout.connect(self._update_telemetry)
            self._timer.start(1000)  # update every second

            # Keep the loop running until stop event
            while not self._stop_event.is_set():
                # Sleep a bit to avoid busy waiting
                self._loop.run_until_complete(asyncio.sleep(0.1))
        except Exception as e:  # pylint: disable=broad-except
            self.error_occurred.emit(f"Backend error: {e}")
        finally:
            # Cleanup
            if self._timer:
                self._timer.stop()
                self._timer = None
            with self._lock:
                if self._conversation:
                    self._loop.run_until_complete(self._conversation.cleanup())
                self._conversation = None
            self._loop.close()

    def _update_telemetry(self):
        """Gather current telemetry and emit signal."""
        with self._lock:
            if not self._conversation:
                # Not initialized yet
                data = {
                    "system_status": "OFFLINE",
                    "ai_status": "UNAVAILABLE",
                    "voice": "N/A",
                    "security": "N/A",
                    "tools": "N/A",
                }
                self.telemetry_updated.emit(data)
                return

            # Determine system status: if loop is running we consider online
            system_status = "ONLINE" if self._loop and self._loop.is_running() else "OFFLINE"
            # AI status: if conversation initialized and AI service exists
            ai_status = "READY" if self._conversation.ai_service is not None else "UNAVAILABLE"
            # Voice status
            voice = "ON" if getattr(self._conversation, "voice_mode", False) else "OFF"
            # Tools status
            tools = "ENABLED" if getattr(self._conversation, "tools_enabled", False) else "DISABLED"
            # Security/safety status: we can check if safety classifier exists
            security = "ACTIVE" if getattr(self._conversation, "safety_classifier", None) is not None else "PASSIVE"

        data = {
            "system_status": system_status,
            "ai_status": ai_status,
            "voice": voice,
            "security": security,
            "tools": tools,
        }
        self.telemetry_updated.emit(data)

    def toggle_voice(self):
        """Toggle the voice mode on the conversation."""
        with self._lock:
            if self._conversation:
                self._conversation.voice_mode = not self._conversation.voice_mode
                # Emit telemetry update to reflect the change immediately
                self._update_telemetry()

    def push_to_talk(self):
        """Trigger a push-to-talk voice recognition cycle."""
        if not self._conversation or not self._loop or not self._loop.is_running():
            self.error_occurred.emit("Backend not ready")
            return
        # Schedule the async handling on the worker's loop
        asyncio.run_coroutine_threadsafe(
            self._async_push_to_talk(), self._loop
        )

    async def _async_push_to_talk(self):
        """Handle push-to-talk: run blocking STT in a thread, then process."""
        with self._lock:
            if not self._conversation or not self._conversation.voice_mode:
                return
            if listen_for_speech is None:
                self.error_occurred.emit("Voice functionality not available")
                return
        # Run the blocking speech recognition in a thread to avoid blocking the event loop
        try:
            # Note: listen_for_speech may block until speech is recognized or timeout
            user_input = await asyncio.to_thread(listen_for_speech)
        except Exception as e:  # pragma: no cover - depends on microphone
            self.error_occurred.emit(f"Speech recognition error: {e}")
            return
        if user_input:
            # Process the recognized text through the normal pipeline
            await self._conversation.handle_user_input(user_input)
            # After processing, we need to get the response and emit it.
            # We can reuse the same logic as in _handle_input: get the last turn.
            last_turn = self._conversation.memory_manager.context.turns[-1]
            if isinstance(last_turn, dict) and last_turn.get("role") == "assistant":
                response = last_turn.get("content", "")
                if response:
                    self.response_received.emit(response)

    def process_user_input(self, user_input: str):
        """
        Process a user input string through the IRIS backend.
        This method is thread-safe and schedules the coroutine on the worker's loop.
        """
        if not self._conversation or not self._loop or not self._loop.is_running():
            self.error_occurred.emit("Backend not ready")
            return

        # Schedule the coroutine on the worker's loop
        asyncio.run_coroutine_threadsafe(
            self._handle_input(user_input), self._loop
        )

    async def _handle_input(self, user_input: str):
        """Handle user input and emit results."""
        try:
            self.status_changed.emit("PROCESSING")
            # Process input; returns False if should exit (we ignore for UI)
            await self._conversation.handle_user_input(user_input)
            # After processing, the response is already added to memory and spoken.
            # We need to get the latest assistant message from memory.
            # For simplicity, we can get the last turn from memory manager.
            # However, IRISConversation already prints the response; we can capture it.
            # Instead, we'll retrieve the last assistant message from memory.
            last_turn = self._conversation.memory_manager.context.turns[-1]
            # Assuming the last turn is the assistant message (role: assistant)
            if isinstance(last_turn, dict) and last_turn.get("role") == "assistant":
                response = last_turn.get("content", "")
                if response:
                    self.response_received.emit(response)
            self.status_changed.emit("READY")
        except Exception as e:  # pylint: disable=broad-except
            self.error_occurred.emit(f"Error processing input: {e}")
            self.status_changed.emit("ERROR")