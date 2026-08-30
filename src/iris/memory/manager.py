"""
Memory manager for IRIS conversation context.
"""

from typing import List, Dict, Any, Optional
from .models import MemoryContext


class MemoryManager:
    """Manages conversation memory and context for IRIS."""

    def __init__(self, max_turns: int = 20, summary_threshold: int = 30):
        """
        Initialize the memory manager.

        Args:
            max_turns: Maximum number of turns to keep in detail
            summary_threshold: Number of turns after which to start summarizing
        """
        self.context = MemoryContext(
            max_turns=max_turns,
            summary_threshold=summary_threshold
        )
        self._summary: Optional[str] = None

    def add_user_message(self, content: str) -> None:
        """Add a user message to memory."""
        self.context.add_user_message(content)

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to memory."""
        self.context.add_assistant_message(content)

    def remove_last_turn(self) -> bool:
        """Remove the last conversation turn if exists.

        Returns:
            True if a turn was removed, False otherwise.
        """
        if not self.context.turns:
            return False
        self.context.turns.pop()
        # Clear summary as it may no longer be valid
        self._summary = None
        return True

    def get_messages_for_ai(self) -> List[Dict[str, Any]]:
        """
        Get conversation messages formatted for AI service.

        Returns:
            List of message dictionaries with role and content
        """
        # Update summary if needed
        if self.context.should_summarize() and self._summary is None:
            self._summary = self.context.create_summary()

        # Temporarily set summary in context for get_messages_for_ai
        original_summary = self.context.summary
        self.context.summary = self._summary
        messages = self.context.get_messages_for_ai()
        self.context.summary = original_summary

        return messages

    def clear(self) -> None:
        """Clear all conversation memory."""
        self.context = MemoryContext(
            max_turns=self.context.max_turns,
            summary_threshold=self.context.summary_threshold
        )
        self._summary = None

    def get_turn_count(self) -> int:
        """Get the number of conversation turns."""
        return len(self.context.turns)

    def get_recent_turns(self, count: int) -> List[Dict[str, Any]]:
        """Get recent conversation turns."""
        return self.context.get_recent_turns(count)