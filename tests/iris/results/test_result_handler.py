"""
Tests for ResultHandler.
"""

import pytest
from unittest.mock import Mock
from iris.results.handler import ResultHandler
from iris.results.models import ActionResult
from iris.planning.models import ActionStep
from iris.safety.classifier import SafetyLevel
from iris.memory.manager import MemoryManager


class TestResultHandler:
    """Tests for ResultHandler class."""

    def test_result_handler_initialization(self):
        """Test that ResultHandler initializes correctly."""
        memory_manager = Mock(spec=MemoryManager)
        handler = ResultHandler(memory_manager)

        assert handler.memory_manager == memory_manager

    def test_handle_result_successful(self):
        """Test handling a successful result."""
        memory_manager = Mock(spec=MemoryManager)
        handler = ResultHandler(memory_manager)

        step = ActionStep(
            tool_name="test_tool",
            arguments={"arg": "value"},
            description="Test step"
        )
        result = ActionResult(
            step=step,
            success=True,
            content="success output"
        )

        # Call handle_result
        handler.handle_result(result)

        # Verify that _store_result_in_memory was called (via memory_manager)
        memory_manager.add_assistant_message.assert_called_once()
        call_args = memory_manager.add_assistant_message.call_args
        # The content should contain success message
        assert "successfully" in call_args[0][0]
        assert "test_tool" in call_args[0][0]

    def test_handle_result_failed(self):
        """Test handling a failed result."""
        memory_manager = Mock(spec=MemoryManager)
        handler = ResultHandler(memory_manager)

        step = ActionStep(
            tool_name="test_tool",
            arguments={"arg": "value"},
            description="Test step"
        )
        result = ActionResult(
            step=step,
            success=False,
            error="test error"
        )

        # Call handle_result
        handler.handle_result(result)

        # Verify that _store_result_in_memory was called
        memory_manager.add_assistant_message.assert_called_once()
        call_args = memory_manager.add_assistant_message.call_args
        # The content should contain failure message
        assert "failed" in call_args[0][0]
        assert "test error" in call_args[0][0]

    def test_handle_result_with_content_truncation(self):
        """Test that long content is truncated in memory storage."""
        memory_manager = Mock(spec=MemoryManager)
        handler = ResultHandler(memory_manager)

        step = ActionStep(
            tool_name="test_tool",
            arguments={"arg": "value"},
            description="Test step with long output"
        )
        long_content = "x" * 200  # Longer than 100 chars
        result = ActionResult(
            step=step,
            success=True,
            content=long_content
        )

        # Call handle_result
        handler.handle_result(result)

        memory_manager.add_assistant_message.assert_called_once()
        call_args = memory_manager.add_assistant_message.call_args
        content = call_args[0][0]
        # Should contain truncated content (first 100 chars + "...")
        assert long_content[:100] in content
        # Should not contain the full 200 chars in the summary (though it's in the actual content)
        # The summary truncates to 100 chars

    def test_handle_multiple_results(self):
        """Test handling multiple results."""
        memory_manager = Mock(spec=MemoryManager)
        handler = ResultHandler(memory_manager)

        step1 = ActionStep(tool_name="tool1", arguments={})
        step2 = ActionStep(tool_name="tool2", arguments={})
        result1 = ActionResult(step=step1, success=True, content="result1")
        result2 = ActionResult(step=step2, success=False, error="error2")

        results = [result1, result2]

        # Call handle_multiple_results
        handler.handle_multiple_results(results)

        # Should have called add_assistant_message twice
        assert memory_manager.add_assistant_message.call_count == 2

    def test_store_result_in_memory_successful(self):
        """Test the internal _store_result_in_memory method for successful result."""
        memory_manager = Mock(spec=MemoryManager)
        handler = ResultHandler(memory_manager)

        step = ActionStep(
            tool_name="read_file",
            arguments={"path": "/tmp/test.txt"},
            description="Read file: /tmp/test.txt"
        )
        result = ActionResult(
            step=step,
            success=True,
            content="file contents here"
        )

        # Call the private method
        handler._store_result_in_memory(result)

        # Verify add_assistant_message was called with expected content
        memory_manager.add_assistant_message.assert_called_once()
        call_args = memory_manager.add_assistant_message.call_args
        content = call_args[0][0]
        assert "Action 'read_file' executed successfully" in content
        assert "Read file: /tmp/test.txt" in content
        assert "file contents here" in content  # Content is included

    def test_store_result_in_memory_failed(self):
        """Test the internal _store_result_in_memory method for failed result."""
        memory_manager = Mock(spec=MemoryManager)
        handler = ResultHandler(memory_manager)

        step = ActionStep(
            tool_name="write_file",
            arguments={"path": "/tmp/test.txt", "content": "data"},
            description="Write file: /tmp/test.txt"
        )
        result = ActionResult(
            step=step,
            success=False,
            error="Permission denied"
        )

        # Call the private method
        handler._store_result_in_memory(result)

        # Verify add_assistant_message was called with expected content
        memory_manager.add_assistant_message.assert_called_once()
        call_args = memory_manager.add_assistant_message.call_args
        content = call_args[0][0]
        assert "Action 'write_file' failed:" in content
        assert "Permission denied" in content

    def test_store_result_in_memory_with_long_description(self):
        """Test storage when description is long."""
        memory_manager = Mock(spec=MemoryManager)
        handler = ResultHandler(memory_manager)

        step = ActionStep(
            tool_name="test_tool",
            arguments={},
            description="A" * 150  # Long description
        )
        result = ActionResult(
            step=step,
            success=True,
            content="short"
        )

        handler._store_result_in_memory(result)

        memory_manager.add_assistant_message.assert_called_once()
        call_args = memory_manager.add_assistant_message.call_args
        content = call_args[0][0]
        # Description should be included as-is (no truncation on description)
        assert "A" * 150 in content

    def test_store_result_in_memory_with_long_content(self):
        """Test storage when content is long (should be truncated to 100 chars)."""
        memory_manager = Mock(spec=MemoryManager)
        handler = ResultHandler(memory_manager)

        step = ActionStep(
            tool_name="test_tool",
            arguments={},
            description="Test"
        )
        long_content = "B" * 150
        result = ActionResult(
            step=step,
            success=True,
            content=long_content
        )

        handler._store_result_in_memory(result)

        memory_manager.add_assistant_message.assert_called_once()
        call_args = memory_manager.add_assistant_message.call_args
        content = call_args[0][0]
        # Content should be truncated to first 100 chars in the summary
        assert long_content[:100] in content
        assert "B" * 150 not in content  # Full content should not be in summary