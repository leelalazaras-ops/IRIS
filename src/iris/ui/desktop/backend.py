
"""
Backend integration for IRIS desktop UI.
Runs the existing IRISConversation in a background thread.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from iris.core.cli import IRISConversation

try:
    from iris.voice.voice_io import listen_for_speech
except ImportError:  # pragma: no cover - voice optional
    listen_for_speech = None


class IrisWorker(QObject):
    """Worker that runs IRIS conversation logic in a separate thread."""

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
        self._lock = threading.Lock()
        self._action_state = "IDLE"

    def start(self):
        """Start the worker thread and initialize IRIS."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_worker,
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Stop the worker thread."""
        self._stop_event.set()

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join(timeout=5.0)

    def _run_worker(self):
        """Initialize IRIS and run its asyncio loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            conversation = IRISConversation()
            with self._lock:
                self._conversation = conversation

            init_success = self._loop.run_until_complete(
                conversation.initialize()
            )

            if not init_success:
                self.error_occurred.emit(
                    "Failed to initialize AI service. Check configuration."
                )
                self._update_telemetry()
                return

            self.status_changed.emit("READY")
            self._update_telemetry()

            while not self._stop_event.is_set():
                self._loop.run_until_complete(asyncio.sleep(0.1))

        except Exception as exc:  # pylint: disable=broad-except
            self.error_occurred.emit(f"Backend error: {exc}")
            self.status_changed.emit("ERROR")
            self._update_telemetry()

        finally:
            conversation = self._conversation

            if conversation and self._loop and not self._loop.is_closed():
                try:
                    if self._loop.is_running():
                        self._loop.call_soon_threadsafe(self._loop.stop)

                    self._loop.run_until_complete(conversation.cleanup())
                except (RuntimeError, Exception):
                    pass

            with self._lock:
                self._conversation = None
                self._action_state = "OFFLINE"

            if self._loop and not self._loop.is_closed():
                self._loop.close()

            self._update_telemetry()

    def _update_telemetry(self):
        """Emit a snapshot of actual IRIS runtime state."""
        with self._lock:
            conversation = self._conversation
            action_state = self._action_state
            loop = self._loop

            if conversation is None:
                data = {
                    "system_status": "OFFLINE",
                    "ai_status": "UNAVAILABLE",
                    "ai_engine": "N/A",
                    "voice": "N/A",
                    "security": "N/A",
                    "tools": "N/A",
                    "tool_count": "N/A",
                    "action_state": "OFFLINE",
                    "dry_run": "OFF",
                }
            else:
                ai_service = conversation.ai_service
                config = getattr(ai_service, "config", None)

                if config:
                    ai_engine = f"{config.provider} / {config.model}"
                else:
                    ai_engine = "N/A"

                pending = conversation.pending_plan is not None

                if pending:
                    action_state = "AWAITING CONFIRMATION"

                tool_registry = getattr(
                    conversation, "tool_registry", None
                )
                get_tool_names = getattr(
                    tool_registry, "get_tool_names", None
                )

                try:
                    tool_count = (
                        str(len(get_tool_names()))
                        if callable(get_tool_names)
                        else "N/A"
                    )
                except Exception:
                    tool_count = "N/A"

                data = {
                    "system_status": (
                        "ONLINE"
                        if loop and loop.is_running()
                        else "OFFLINE"
                    ),
                    "ai_status": (
                        "READY" if ai_service is not None else "UNAVAILABLE"
                    ),
                    "ai_engine": ai_engine,
                    "voice": (
                        "ON" if conversation.voice_mode else "OFF"
                    ),
                    "security": (
                        "ACTIVE"
                        if conversation.safety_classifier is not None
                        else "PASSIVE"
                    ),
                    "tools": (
                        "ENABLED"
                        if conversation.tools_enabled
                        else "DISABLED"
                    ),
                    "tool_count": tool_count,
                    "action_state": action_state,
                    "dry_run": (
                        "ON" if conversation.dry_run_mode else "OFF"
                    ),
                }

        # Emit outside the lock to avoid re-entrant deadlocks.
        self.telemetry_updated.emit(data)

    def toggle_voice(self):
        """Toggle voice mode and immediately refresh telemetry."""
        with self._lock:
            conversation = self._conversation
            if conversation is None:
                return

            conversation.voice_mode = not conversation.voice_mode

        self._update_telemetry()

    def push_to_talk(self):
        """Schedule a voice recognition cycle on the worker loop."""
        if (
            not self._conversation
            or not self._loop
            or not self._loop.is_running()
        ):
            self.error_occurred.emit("Backend not ready")
            return

        asyncio.run_coroutine_threadsafe(
            self._async_push_to_talk(), self._loop
        )

    async def _async_push_to_talk(self):
        """Recognize speech and process it through IRIS."""
        with self._lock:
            conversation = self._conversation

            if conversation is None or not conversation.voice_mode:
                return

            if listen_for_speech is None:
                self.error_occurred.emit(
                    "Voice functionality not available"
                )
                return

            self._action_state = "LISTENING"

        self._update_telemetry()

        try:
            user_input = await asyncio.to_thread(listen_for_speech)

            if not user_input:
                with self._lock:
                    self._action_state = "IDLE"
                self._update_telemetry()
                return

            with self._lock:
                self._action_state = "PROCESSING"

            self.status_changed.emit("PROCESSING")
            self._update_telemetry()

            await conversation.handle_user_input(user_input)
            self._emit_latest_response(conversation)

            with self._lock:
                self._action_state = (
                    "AWAITING CONFIRMATION"
                    if conversation.pending_plan is not None
                    else "IDLE"
                )

            self.status_changed.emit("READY")

        except Exception as exc:  # pragma: no cover - device dependent
            with self._lock:
                self._action_state = "ERROR"

            self.error_occurred.emit(
                f"Speech processing error: {exc}"
            )
            self.status_changed.emit("ERROR")

        finally:
            self._update_telemetry()

    def process_user_input(self, user_input: str):
        """Schedule user input on the worker's asyncio loop."""
        if (
            not self._conversation
            or not self._loop
            or not self._loop.is_running()
        ):
            self.error_occurred.emit("Backend not ready")
            return

        asyncio.run_coroutine_threadsafe(
            self._handle_input(user_input), self._loop
        )

    async def _handle_input(self, user_input: str):
        """Handle text input and publish the resulting state."""
        with self._lock:
            conversation = self._conversation
            self._action_state = "PROCESSING"

        if conversation is None:
            self.error_occurred.emit("Backend not ready")
            return

        self.status_changed.emit("PROCESSING")
        self._update_telemetry()

        try:
            await conversation.handle_user_input(user_input)
            self._emit_latest_response(conversation)

            with self._lock:
                self._action_state = (
                    "AWAITING CONFIRMATION"
                    if conversation.pending_plan is not None
                    else "IDLE"
                )

            self.status_changed.emit("READY")

        except Exception as exc:  # pylint: disable=broad-except
            with self._lock:
                self._action_state = "ERROR"

            self.error_occurred.emit(
                f"Error processing input: {exc}"
            )
            self.status_changed.emit("ERROR")

        finally:
            self._update_telemetry()

    def _emit_latest_response(self, conversation: IRISConversation):
        """Emit the latest assistant message, if available."""
        turns = conversation.memory_manager.context.turns

        if not turns:
            return

        last_turn = turns[-1]

        if (
            isinstance(last_turn, dict)
            and last_turn.get("role") == "assistant"
        ):
            response = last_turn.get("content", "")
            if response:
                self.response_received.emit(response)
