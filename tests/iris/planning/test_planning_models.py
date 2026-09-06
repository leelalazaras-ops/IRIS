"""
Tests for planning data models.
"""

import pytest
from datetime import datetime
from iris.planning.models import ActionStep, ActionPlan
from iris.intent.models import Intent
from iris.safety.classifier import SafetyLevel


class TestActionStep:
    """Tests for ActionStep class."""

    def test_action_step_creation_minimal(self):
        """Test creating an ActionStep with minimal required fields."""
        step = ActionStep(tool_name="test_tool")

        assert step.tool_name == "test_tool"
        assert step.arguments == {}
        assert step.safety_classification == SafetyLevel.SAFE
        assert step.description == ""
        assert step.metadata == {}

    def test_action_step_creation_full(self):
        """Test creating an ActionStep with all fields specified."""
        args = {"path": "/tmp/test"}
        metadata = {"intent": "read_file"}
        step = ActionStep(
            tool_name="test_tool",
            arguments=args,
            safety_classification=SafetyLevel.REQUIRES_CONFIRMATION,
            description="Test description",
            metadata=metadata
        )

        assert step.tool_name == "test_tool"
        assert step.arguments == args
        assert step.safety_classification == SafetyLevel.REQUIRES_CONFIRMATION
        assert step.description == "Test description"
        assert step.metadata == metadata

    def test_action_step_tool_name_validation_empty(self):
        """Test that empty tool_name raises ValueError."""
        with pytest.raises(ValueError, match="tool_name cannot be empty"):
            ActionStep(tool_name="")

    def test_action_step_arguments_validation(self):
        """Test that arguments must be a dictionary."""
        with pytest.raises(ValueError, match="arguments must be a dictionary"):
            ActionStep(tool_name="test", arguments="not-a-dict")

    def test_action_step_post_init_validation(self):
        """Test that __post_init__ validation works."""
        # Valid step
        step = ActionStep(tool_name="valid")
        assert step.tool_name == "valid"

        # Invalid tool_name
        with pytest.raises(ValueError):
            ActionStep(tool_name="")

        # Invalid arguments
        with pytest.raises(ValueError):
            ActionStep(tool_name="test", arguments=[])

    def test_action_step_default_factories(self):
        """Test that default factories create new instances."""
        step1 = ActionStep(tool_name="test1")
        step2 = ActionStep(tool_name="test2")

        # Arguments and metadata should be different instances
        assert step1.arguments is not step2.arguments
        assert step1.metadata is not step2.metadata

        # But both should be empty dicts
        assert step1.arguments == {}
        assert step2.arguments == {}
        assert step1.metadata == {}
        assert step2.metadata == {}

    def test_action_step_arguments_can_be_set(self):
        """Test that arguments can be set and modified."""
        step = ActionStep(tool_name="test")
        step.arguments["key"] = "value"
        assert step.arguments == {"key": "value"}

        step.arguments["another"] = 123
        assert step.arguments == {"key": "value", "another": 123}

    def test_action_step_metadata_can_be_set(self):
        """Test that metadata can be set and modified."""
        step = ActionStep(tool_name="test")
        step.metadata["source"] = "unit_test"
        assert step.metadata == {"source": "unit_test"}

        step.metadata["version"] = "1.0"
        assert step.metadata == {"source": "unit_test", "version": "1.0"}


class TestActionPlan:
    """Tests for ActionPlan class."""

    def test_action_plan_creation_empty(self):
        """Test creating an ActionPlan with no steps."""
        plan = ActionPlan()

        assert plan.steps == []
        assert plan.intent is None
        assert isinstance(plan.created_at, datetime)
        assert plan.metadata == {}

    def test_action_plan_creation_with_steps_and_intent(self):
        """Test creating an ActionPlan with steps and intent."""
        intent = Intent(action="test_action", arguments={"arg": "value"})
        step = ActionStep(tool_name="test_tool")
        plan = ActionPlan(
            steps=[step],
            intent=intent,
            metadata={"planner": "test"}
        )

        assert plan.steps == [step]
        assert plan.intent == intent
        assert plan.metadata == {"planner": "test"}
        assert isinstance(plan.created_at, datetime)

    def test_action_plan_steps_validation(self):
        """Test that all steps must be ActionStep instances."""
        with pytest.raises(ValueError, match="All steps must be ActionStep instances"):
            ActionPlan(steps=["not-a-step"])

        with pytest.raises(ValueError, match="All steps must be ActionStep instances"):
            ActionPlan(steps=[ActionStep(tool_name="valid"), "invalid"])

        # Valid steps should not raise
        step1 = ActionStep(tool_name="tool1")
        step2 = ActionStep(tool_name="tool2")
        plan = ActionPlan(steps=[step1, step2])
        assert len(plan.steps) == 2

    def test_action_plan_default_factories(self):
        """Test that default factories create new instances."""
        plan1 = ActionPlan()
        plan2 = ActionPlan()

        # Steps and metadata should be different instances
        assert plan1.steps is not plan2.steps
        assert plan1.metadata is not plan2.metadata

        # But both should be empty/default
        assert plan1.steps == []
        assert plan2.steps == []
        assert plan1.metadata == {}
        assert plan2.metadata == {}

    def test_action_plan_intent_can_be_set(self):
        """Test that intent can be set and changed."""
        plan = ActionPlan()
        intent = Intent(action="test")
        plan.intent = intent
        assert plan.intent == intent

        plan.intent = None
        assert plan.intent is None

    def test_action_plan_steps_can_be_modified(self):
        """Test that steps list can be modified."""
        plan = ActionPlan()
        step = ActionStep(tool_name="test")
        plan.steps.append(step)
        assert len(plan.steps) == 1
        assert plan.steps[0] == step

        plan.steps.clear()
        assert len(plan.steps) == 0