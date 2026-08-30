"""
Tests for IRIS memory manager.
"""

import pytest
from typing import List, Dict, Any
from iris.memory.manager import MemoryManager
from iris.memory.models import MemoryContext


def test_memory_manager_initialization():
    """Test memory manager initialization with default values."""
    manager = MemoryManager()
    assert manager.context.max_turns == 20
    assert manager.context.summary_threshold == 30
    assert manager._summary is None
    assert len(manager.context.turns) == 0


def test_memory_manager_custom_initialization():
    """Test memory manager initialization with custom values."""
    manager = MemoryManager(max_turns=10, summary_threshold=25)
    assert manager.context.max_turns == 10
    assert manager.context.summary_threshold == 25


def test_add_user_message():
    """Test adding user messages to memory."""
    manager = MemoryManager()
    manager.add_user_message("Hello, IRIS!")

    assert manager.get_turn_count() == 1
    assert manager.context.turns[0]["role"] == "user"
    assert manager.context.turns[0]["content"] == "Hello, IRIS!"


def test_add_assistant_message():
    """Test adding assistant messages to memory."""
    manager = MemoryManager()
    manager.add_assistant_message("Hello, human!")

    assert manager.get_turn_count() == 1
    assert manager.context.turns[0]["role"] == "assistant"
    assert manager.context.turns[0]["content"] == "Hello, human!"


def test_remove_last_turn():
    """Test removing the last conversation turn."""
    manager = MemoryManager()
    manager.add_user_message("First message")
    manager.add_assistant_message("First response")

    assert manager.get_turn_count() == 2

    # Remove last turn
    result = manager.remove_last_turn()
    assert result is True
    assert manager.get_turn_count() == 1
    assert manager.context.turns[0]["content"] == "First message"

    # Remove another turn
    result = manager.remove_last_turn()
    assert result is True
    assert manager.get_turn_count() == 0

    # Try to remove from empty memory
    result = manager.remove_last_turn()
    assert result is False


def test_get_messages_for_ai_under_threshold():
    """Test getting messages when under summary threshold."""
    manager = MemoryManager(max_turns=20, summary_threshold=30)
    manager.add_user_message("Hello")
    manager.add_assistant_message("Hi there")
    manager.add_user_message("How are you?")

    messages = manager.get_messages_for_ai()
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Hi there"
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "How are you?"


def test_get_messages_for_ai_over_threshold_no_summary():
    """Test getting messages when over threshold but no summary yet."""
    manager = MemoryManager(max_turns=3, summary_threshold=5)
    # Add 4 messages (over max_turns but under summary_threshold)
    manager.add_user_message("Message 1")
    manager.add_assistant_message("Response 1")
    manager.add_user_message("Message 2")
    manager.add_assistant_message("Response 2")

    messages = manager.get_messages_for_ai()
    # Should return last 3 messages (max_turns)
    assert len(messages) == 3
    assert messages[0]["content"] == "Response 1"
    assert messages[1]["content"] == "Message 2"
    assert messages[2]["content"] == "Response 2"


def test_get_messages_for_ai_with_summary():
    """Test getting messages when summary exists."""
    manager = MemoryManager(max_turns=2, summary_threshold=3)
    # Add messages to trigger summary creation
    manager.add_user_message("First user message")
    manager.add_assistant_message("First assistant response")
    manager.add_user_message("Second user message")
    manager.add_assistant_message("Second assistant response")
    manager.add_user_message("Third user message")

    # Force summary creation
    manager._summary = "Summary of earlier conversation"

    messages = manager.get_messages_for_ai()
    # Should have summary + last 2 messages
    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert "Conversation summary:" in messages[0]["content"]
    assert messages[1]["content"] == "Second assistant response"
    assert messages[2]["content"] == "Third user message"


def test_clear_memory():
    """Test clearing all conversation memory."""
    manager = MemoryManager()
    manager.add_user_message("Test message")
    manager.add_assistant_message("Test response")
    manager._summary = "Test summary"

    assert manager.get_turn_count() == 2
    assert manager._summary is not None

    manager.clear()

    assert manager.get_turn_count() == 0
    assert manager._summary is None
    assert len(manager.context.turns) == 0


def test_get_recent_turns():
    """Test getting recent conversation turns."""
    manager = MemoryManager()
    manager.add_user_message("First")
    manager.add_assistant_message("Second")
    manager.add_user_message("Third")

    recent = manager.get_recent_turns(2)
    assert len(recent) == 2
    assert recent[0]["content"] == "Second"
    assert recent[1]["content"] == "Third"

    # Test getting more than available
    recent = manager.get_recent_turns(5)
    assert len(recent) == 3

    # Test getting zero
    recent = manager.get_recent_turns(0)
    assert len(recent) == 0


def test_should_summarize():
    """Test summarization threshold logic."""
    manager = MemoryManager(max_turns=5, summary_threshold=10)

    # Under threshold
    for i in range(10):
        manager.add_user_message(f"Message {i}")

    assert manager.context.should_summarize() is False

    # Over threshold
    manager.add_user_message("Message 11")

    assert manager.context.should_summarize() is True


def test_create_summary():
    """Test summary creation."""
    manager = MemoryManager(max_turns=2, summary_threshold=5)
    manager.add_user_message("Short")
    manager.add_assistant_message("Also short")
    manager.add_user_message("A bit longer message that should be summarized")
    manager.add_assistant_message("Another response")

    summary = manager.context.create_summary()
    assert len(summary) <= 200  # Should be truncated if needed
    # With max_turns=2, the first 2 messages should be summarized
    assert "Short" in summary
    assert "Also short" in summary
    # The last 2 messages should NOT be in the summary (they're kept as recent turns)
    assert "A bit longer message" not in summary
    assert "Another response" not in summary