"""
Tests for the Planner class.
"""

import pytest
from unittest.mock import Mock
from iris.planning.planner import Planner
from iris.planning.models import ActionPlan, ActionStep
from iris.intent.models import Intent
from iris.safety.classifier import SafetyClassifier, SafetyLevel
from iris.tools.registry import ToolRegistry


class TestPlanner:
    """Tests for Planner class."""

    def test_planner_initialization(self):
        """Test that Planner initializes correctly."""
        registry = Mock(spec=ToolRegistry)
        safety_classifier = Mock(spec=SafetyClassifier)
        planner = Planner(registry, safety_classifier)

        assert planner.registry == registry
        assert planner.safety_classifier == safety_classifier
        assert hasattr(planner, '_intent_to_tool_map')

    def test_planner_known_intent_mapped_correctly(self):
        """Test that known intents map to correct tools and arguments."""
        registry = Mock(spec=ToolRegistry)
        safety_classifier = Mock(spec=SafetyClassifier)
        # Configure safety classifier to return SAFE for all tests
        safety_classifier.classify_action.return_value = SafetyLevel.SAFE
        planner = Planner(registry, safety_classifier)

        # Test read_file intent
        intent = Intent(action="read_file", arguments={"path": "/tmp/test.txt"})
        plan = planner.plan(intent)

        assert len(plan.steps) == 1
        step = plan.steps[0]
        assert step.tool_name == "read_file"
        assert step.arguments == {"path": "/tmp/test.txt"}
        assert step.metadata["intent_action"] == "read_file"

    def test_planner_unknown_intent_returns_empty_plan(self):
        """Test that unknown intent results in plan with no steps."""
        registry = Mock(spec=ToolRegistry)
        safety_classifier = Mock(spec=SafetyClassifier)
        planner = Planner(registry, safety_classifier)

        intent = Intent(action="unknown_action", arguments={})
        plan = planner.plan(intent)

        assert len(plan.steps) == 0
        assert plan.intent == intent
        assert "error" in plan.metadata
        assert "No tool mapping found" in plan.metadata["error"]