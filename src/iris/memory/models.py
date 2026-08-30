"""
Memory data models for IRIS.
"""

from typing import List, Optional, Dict, Any


class MemoryContext:
    """Represents the current memory context for conversation."""

    def __init__(self, max_turns: int = 20, summary_threshold: int = 30):
        """
        Initialize memory context.

        Args:
            max_turns: Maximum number of turns to keep in detail
            summary_threshold: Number of turns after which to start summarizing
        """
        self.turns: List[Dict[str, Any]] = []
        self.summary: Optional[str] = None
        self.max_turns = max_turns
        self.summary_threshold = summary_threshold

    def add_message(self, message: Dict[str, Any]) -> None:
        """Add a message to memory."""
        self.turns.append(message)

    def add_user_message(self, content: str) -> None:
        """Add a user message to memory."""
        self.add_message({
            "role": "user",
            "content": content
        })

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to memory."""
        self.add_message({
            "role": "assistant",
            "content": content
        })

    def get_recent_turns(self, count: int) -> List[Dict[str, Any]]:
        """Get the most recent conversation turns."""
        if count <= 0:
            return []
        return self.turns[-count:] if self.turns else []

    def get_all_turns(self) -> List[Dict[str, Any]]:
        """Get all conversation turns."""
        return self.turns.copy()

    def get_messages_for_ai(self) -> List[Dict[str, Any]]:
        """Get messages formatted for AI service, with summarization if needed."""
        if len(self.turns) <= self.max_turns:
            # Return all turns as-is if under threshold
            return self.turns.copy()

        # If we have a summary, use it plus recent turns
        if self.summary:
            recent_turns = self.get_recent_turns(self.max_turns)
            return [{"role": "system", "content": f"Conversation summary: {self.summary}"}] + recent_turns

        # No summary yet, just return recent turns
        recent_turns = self.get_recent_turns(self.max_turns)
        return recent_turns.copy()

    def should_summarize(self) -> bool:
        """Check if memory should be summarized."""
        return len(self.turns) > self.summary_threshold

    def create_summary(self) -> str:
        """Create a summary of older conversation turns."""
        if len(self.turns) <= self.max_turns:
            return ""

        # Summarize turns that are older than recent ones
        turns_to_summarize = self.turns[:-self.max_turns] if len(self.turns) > self.max_turns else self.turns

        if not turns_to_summarize:
            return ""

        # Simple summarization: concatenate and truncate
        content_parts = []
        for turn in turns_to_summarize:
            role = turn.get('role', 'unknown')
            content = turn.get('content', '')
            content_parts.append(f"{role}: {content}")

        full_content = " ".join(content_parts)
        # Simple summary: first 200 chars + indicator if truncated
        if len(full_content) > 200:
            return full_content[:200] + "..."
        return full_content