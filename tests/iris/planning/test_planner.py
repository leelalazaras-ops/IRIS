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


class TestPlannerMultistep:
    """Tests for Planner multi-step functionality (Phase 7.3)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.registry = Mock(spec=ToolRegistry)
        self.safety_classifier = Mock(spec=SafetyClassifier)
        self.safety_classifier.classify_action.return_value = SafetyLevel.SAFE
        self.planner = Planner(self.registry, self.safety_classifier)

    # --- Single-step behavior preservation tests ---

    def test_single_step_create_directory(self):
        """Test that single create_directory intent produces single step."""
        intent = Intent(action="create_directory", arguments={"path": "projects"})
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "create_directory"
        assert plan.steps[0].arguments == {"path": "projects"}

    def test_single_step_read_file(self):
        """Test that single read_file intent produces single step."""
        intent = Intent(action="read_file", arguments={"path": "test.txt"})
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "read_file"
        assert plan.steps[0].arguments == {"path": "test.txt"}

    def test_single_step_calculate(self):
        """Test that single calculate intent produces single step."""
        intent = Intent(action="calculate", arguments={"expression": "7 * 5"})
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "calculate"
        assert plan.steps[0].arguments == {"expression": "7 * 5"}

    def test_single_step_write_file(self):
        """Test that single write_file intent (without multi-step hints) produces single step."""
        intent = Intent(action="write_file", arguments={"path": "test.txt", "content": "hello"},
                       original_request="just write this file")
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "write_file"

    # --- Multi-step create_directory + write_file tests ---

    def test_multistep_create_dir_write_file(self):
        """Test create_directory + write_file multi-step pattern."""
        intent = Intent(
            action="write_file",
            arguments={"path": "notes.txt", "content": "hello"},
            original_request="create directory projects and write a file notes.txt containing hello"
        )
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "create_directory"
        assert plan.steps[0].arguments == {"path": "projects"}
        assert plan.steps[1].tool_name == "write_file"
        assert plan.steps[1].arguments["path"] == "notes.txt"
        assert plan.steps[1].arguments["content"] == "hello"

    def test_multistep_create_dir_write_file_with_to(self):
        """Test create_directory + write_file with 'save to' pattern."""
        intent = Intent(
            action="write_file",
            arguments={"path": "test.txt", "content": "content"},
            original_request="create directory data and save my content to test.txt"
        )
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "create_directory"
        assert plan.steps[0].arguments == {"path": "data"}
        assert plan.steps[1].tool_name == "write_file"

    def test_multistep_create_dir_write_file_with_then(self):
        """Test create_directory + write_file with 'then' pattern."""
        intent = Intent(
            action="write_file",
            arguments={"path": "test.txt", "content": "content"},
            original_request="create directory output then write a file test.txt with some data"
        )
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "create_directory"
        assert plan.steps[1].tool_name == "write_file"

    # --- Multi-step read_file + calculate tests ---

    def test_multistep_read_file_calculate(self):
        """Test read_file + calculate multi-step pattern."""
        intent = Intent(
            action="calculate",
            arguments={"expression": "2+2"},
            original_request="read file test.txt and calculate 2+2"
        )
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "read_file"
        assert plan.steps[0].arguments == {"path": "test.txt"}
        assert plan.steps[1].tool_name == "calculate"
        assert plan.steps[1].arguments == {"expression": "2+2"}

    def test_multistep_read_file_calculate_with_then(self):
        """Test read_file + calculate with 'then' pattern."""
        intent = Intent(
            action="calculate",
            arguments={"expression": "7 * 5"},
            original_request="read numbers.txt then calculate 7 * 5"
        )
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "read_file"
        assert plan.steps[1].tool_name == "calculate"

    def test_multistep_calculate_from_file(self):
        """Test calculate from file pattern."""
        intent = Intent(
            action="calculate",
            arguments={"expression": "sum"},
            original_request="calculate sum from file data.txt"
        )
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "read_file"
        assert plan.steps[0].arguments == {"path": "data.txt"}
        assert plan.steps[1].tool_name == "calculate"

    # --- Unsupported combination tests ---

    def test_unsupported_combination_remains_single_step(self):
        """Test that unsupported combinations remain single-step."""
        # Intent that looks like it could be multi-step but isn't supported
        intent = Intent(
            action="write_file",
            arguments={"path": "test.txt", "content": "hello"},
            original_request="write file to disk and list directory"
        )
        plan = self.planner.plan(intent)

        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "write_file"

    def test_multistep_metadata_flag(self):
        """Test that multi-step plans have multistep flag in metadata."""
        intent = Intent(
            action="write_file",
            arguments={"path": "test.txt", "content": "hello"},
            original_request="create directory data and write a file test.txt with content"
        )
        plan = self.planner.plan(intent)

        assert plan.metadata.get("multistep") is True

    def test_single_step_metadata_no_multistep_flag(self):
        """Test that single-step plans don't have multistep flag."""
        intent = Intent(action="read_file", arguments={"path": "test.txt"})
        plan = self.planner.plan(intent)

        assert plan.metadata.get("multistep") is None

    def test_multistep_step_order_preserved(self):
        """Test that multi-step plans preserve the requested order."""
        intent = Intent(
            action="write_file",
            arguments={"path": "test.txt", "content": "hello"},
            original_request="create directory projects and write a file test.txt containing hello"
        )
        plan = self.planner.plan(intent)

        # Verify order: create_directory should come before write_file
        assert plan.steps[0].tool_name == "create_directory"
        assert plan.steps[1].tool_name == "write_file"

        # Verify metadata indicates order
        assert plan.steps[0].metadata["intent_action"] == "create_directory"
        assert plan.steps[1].metadata["intent_action"] == "write_file"