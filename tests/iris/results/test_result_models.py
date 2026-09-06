"""
Tests for ActionResult data model.
"""

import pytest
from datetime import datetime
from iris.results.models import ActionResult
from iris.planning.models import ActionStep
from iris.safety.classifier import SafetyLevel


class TestActionResult:
    """Tests for ActionResult class."""

    def test_action_result_creation_successful(self):
        """Test creating a successful ActionResult."""
        step = ActionStep(tool_name="test_tool", arguments={"arg": "value"})
        result = ActionResult(
            step=step,
            success=True,
            content="result content"
        )

        assert result.step == step
        assert result.success is True
        assert result.content == "result content"
        assert result.error is None
        assert result.safety_classification == SafetyLevel.SAFE
        assert isinstance(result.executed_at, datetime)
        assert result.metadata == {}

    def test_action_result_creation_failed(self):
        """Test creating a failed ActionResult."""
        step = ActionStep(tool_name="test_tool", arguments={"arg": "value"})
        result = ActionResult(
            step=step,
            success=False,
            error="something went wrong"
        )

        assert result.step == step
        assert result.success is False
        assert result.content is None
        assert result.error == "something went wrong"
        assert result.safety_classification == SafetyLevel.SAFE
        assert isinstance(result.executed_at, datetime)
        assert result.metadata == {}

    def test_action_result_creation_with_all_fields(self):
        """Test creating an ActionResult with all fields specified."""
        step = ActionStep(
            tool_name="test_tool",
            arguments={"arg": "value"},
            safety_classification=SafetyLevel.REQUIRES_CONFIRMATION,
            description="Test step"
        )
        timestamp = datetime(2023, 1, 1, 12, 0, 0)
        metadata = {"key": "value"}

        result = ActionResult(
            step=step,
            success=True,
            content="output",
            error=None,
            safety_classification=SafetyLevel.REQUIRES_CONFIRMATION,
            executed_at=timestamp,
            metadata=metadata
        )

        assert result.step == step
        assert result.success is True
        assert result.content == "output"
        assert result.error is None
        assert result.safety_classification == SafetyLevel.REQUIRES_CONFIRMATION
        assert result.executed_at == timestamp
        assert result.metadata == metadata

    def test_action_result_post_init_validation_success_without_error(self):
        """Test that successful result with None error is valid (no change)."""
        step = ActionStep(tool_name="test_tool")
        # This should not raise because success=True and error=None is allowed
        result = ActionResult(step=step, success=True, error=None)
        assert result.error is None

    def test_action_result_post_init_validation_failure_without_error(self):
        """Test that failed result without error gets default error message."""
        step = ActionStep(tool_name="test_tool")
        # When success=False and error is None, __post_init__ sets error to "Unknown error"
        result = ActionResult(step=step, success=False, error=None)
        assert result.error == "Unknown error"

    def test_action_result_step_validation(self):
        """Test that step must be an ActionStep instance."""
        with pytest.raises(ValueError, match="step must be an ActionStep instance"):
            ActionResult(
                step="not-a-step",
                success=True
            )

    def test_action_result_default_factories(self):
        """Test that default factories create new instances for metadata."""
        step = ActionStep(tool_name="test")
        result1 = ActionResult(step=step, success=True)
        result2 = ActionResult(step=step, success=True)

        # Metadata should be different instances
        assert result1.metadata is not result2.metadata
        # But both should be empty dicts
        assert result1.metadata == {}
        assert result2.metadata == {}

    def test_action_result_metadata_can_be_set(self):
        """Test that metadata can be set and modified."""
        step = ActionStep(tool_name="test")
        result = ActionResult(step=step, success=True)
        result.metadata["source"] = "test"
        assert result.metadata == {"source": "test"}

        result.metadata["another"] = 123
        assert result.metadata == {"source": "test", "another": 123}