"""
Tests for Intent data models.
"""

import pytest
from datetime import datetime
from iris.intent.models import Intent


class TestIntent:
    """Tests for Intent class."""

    def test_intent_creation_minimal(self):
        """Test creating an Intent with minimal required fields."""
        intent = Intent(action="test_action")

        assert intent.action == "test_action"
        assert intent.arguments == {}
        assert intent.confidence == 1.0
        assert intent.original_request == ""
        assert isinstance(intent.timestamp, datetime)
        assert intent.metadata == {}

    def test_intent_creation_full(self):
        """Test creating an Intent with all fields specified."""
        args = {"key": "value", "number": 42}
        metadata = {"source": "test"}
        timestamp = datetime(2023, 1, 1, 12, 0, 0)

        intent = Intent(
            action="test_action",
            arguments=args,
            confidence=0.5,
            original_request="test request",
            timestamp=timestamp,
            metadata=metadata
        )

        assert intent.action == "test_action"
        assert intent.arguments == args
        assert intent.confidence == 0.5
        assert intent.original_request == "test request"
        assert intent.timestamp == timestamp
        assert intent.metadata == metadata

    def test_intent_confidence_validation_valid(self):
        """Test that valid confidence values are accepted."""
        for confidence in [0.0, 0.1, 0.5, 0.9, 1.0]:
            intent = Intent(action="test", confidence=confidence)
            assert intent.confidence == confidence

    def test_intent_confidence_validation_invalid_too_low(self):
        """Test that confidence below 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            Intent(action="test", confidence=-0.1)

    def test_intent_confidence_validation_invalid_too_high(self):
        """Test that confidence above 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            Intent(action="test", confidence=1.1)

    def test_intent_action_validation_empty(self):
        """Test that empty action raises ValueError."""
        with pytest.raises(ValueError, match="action cannot be empty"):
            Intent(action="")

    def test_intent_action_validation_whitespace(self):
        """Test that whitespace-only action is allowed (only empty string is invalid)."""
        # Only empty string is invalid, whitespace is allowed
        intent = Intent(action="   ")
        assert intent.action == "   "

    def test_intent_action_validation_empty_only(self):
        """Test that only empty string action raises ValueError (whitespace is allowed)."""
        # Empty string should raise
        with pytest.raises(ValueError, match="action cannot be empty"):
            Intent(action="")

        # Whitespace-only strings should be allowed
        intent = Intent(action=" ")
        assert intent.action == " "

        intent = Intent(action="   ")
        assert intent.action == "   "

    def test_intent_post_init_validation(self):
        """Test that __post_init__ validation works."""
        # Test confidence validation
        with pytest.raises(ValueError):
            Intent(action="test", confidence=1.5)

        # Test action validation
        with pytest.raises(ValueError):
            Intent(action="")

        # Valid intent should not raise
        intent = Intent(action="valid", confidence=0.8)
        assert intent.action == "valid"
        assert intent.confidence == 0.8

    def test_intent_default_factories(self):
        """Test that default factories create new instances."""
        intent1 = Intent(action="test1")
        intent2 = Intent(action="test2")

        # Arguments and metadata should be different instances
        assert intent1.arguments is not intent2.arguments
        assert intent1.metadata is not intent2.metadata

        # But both should be empty dicts
        assert intent1.arguments == {}
        assert intent2.arguments == {}
        assert intent1.metadata == {}
        assert intent2.metadata == {}

    def test_intent_arguments_can_be_set(self):
        """Test that arguments can be set and modified."""
        intent = Intent(action="test")
        intent.arguments["key"] = "value"
        assert intent.arguments == {"key": "value"}

        intent.arguments["another"] = 123
        assert intent.arguments == {"key": "value", "another": 123}

    def test_intent_metadata_can_be_set(self):
        """Test that metadata can be set and modified."""
        intent = Intent(action="test")
        intent.metadata["source"] = "unit_test"
        assert intent.metadata == {"source": "unit_test"}

        intent.metadata["version"] = "1.0"
        assert intent.metadata == {"source": "unit_test", "version": "1.0"}