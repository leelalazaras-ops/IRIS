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

    def add_assistant_message(self, content: str, tool_calls: Optional[List[Any]] = None) -> None:
        """
        Add an assistant message to memory.

        Args:
            content: The assistant message content
            tool_calls: Optional tool calls attached to this assistant message
        """
        message: Dict[str, Any] = {
            "role": "assistant",
            "content": content
        }
        if tool_calls:
            # Serialize tool calls into the OpenAI format so the following
            # tool result messages are properly paired with this message.
            message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.tool_name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in tool_calls
            ]
        self.add_message(message)

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
            return self._strip_leading_orphaned_tool_messages(self.turns.copy())

        # If we have a summary, use it plus recent turns
        if self.summary:
            recent_turns = self.get_recent_turns(self.max_turns)
            recent_turns = self._strip_leading_orphaned_tool_messages(recent_turns)
            return [{"role": "system", "content": f"Conversation summary: {self.summary}"}] + recent_turns

        # No summary yet, just return recent turns
        recent_turns = self.get_recent_turns(self.max_turns)
        return self._strip_leading_orphaned_tool_messages(recent_turns.copy())

    @staticmethod
    def _strip_leading_orphaned_tool_messages(
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Remove leading tool messages that are not paired with a preceding
        assistant message containing tool_calls.

        An OpenAI-compatible history must never begin with a role="tool"
        message. This happens when the max_turns window cuts into the middle
        of an assistant(tool_calls) -> tool exchange. All leading tool
        messages are orphaned (their assistant tool_calls message was
        truncated away), so they are dropped and the window starts at the
        first non-tool message. Tool messages that remain in the window
        after that boundary are untouched, so valid exchanges stay intact.

        Args:
            messages: Candidate message list

        Returns:
            Message list that does not start with an orphaned tool message
        """
        if not messages:
            return messages

        first_valid_index = 0
        for message in messages:
            if message.get("role") == "tool":
                # Leading tool message: its paired assistant tool_calls
                # message is outside the window, so it is orphaned.
                first_valid_index += 1
            else:
                break

        if first_valid_index > 0:
            return messages[first_valid_index:]
        return messages

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