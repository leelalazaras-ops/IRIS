"""
Action planning data models for IRIS Phase 7.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional
from iris.intent.models import Intent
from iris.safety.classifier import SafetyLevel


@dataclass
class ActionStep:
    """
    Represents a single executable action in a plan.

    Attributes:
        tool_name: Name of the tool to execute
        arguments: Dictionary of arguments to pass to the tool
        safety_classification: Safety level of this action (SAFE, REQUIRES_CONFIRMATION, BLOCKED)
        description: Human-readable description of what this action does
        metadata: Additional metadata about this step
    """
    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    safety_classification: SafetyLevel = SafetyLevel.SAFE
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate action step parameters."""
        if not self.tool_name:
            raise ValueError("tool_name cannot be empty")
        if not isinstance(self.arguments, dict):
            raise ValueError("arguments must be a dictionary")


@dataclass
class ActionPlan:
    """
    Represents an executable plan composed of one or more action steps.

    Attributes:
        steps: List of ActionStep objects to execute in sequence
        intent: The original intent that this plan is based on
        created_at: Timestamp when the plan was created
        metadata: Additional metadata about the plan
    """
    steps: List[ActionStep] = field(default_factory=list)
    intent: Optional[Intent] = None
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate action plan parameters."""
        for step in self.steps:
            if not isinstance(step, ActionStep):
                raise ValueError("All steps must be ActionStep instances")