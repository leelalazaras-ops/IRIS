"""
Action result data models for IRIS Phase 7.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from iris.planning.models import ActionStep
from iris.safety.classifier import SafetyLevel


@dataclass
class ActionResult:
    """
    Represents the outcome of executing an action step.

    Attributes:
        step: The ActionStep that was executed
        success: Whether the action executed successfully
        content: The result content from the tool (if successful)
        error: Error message if execution failed
        safety_classification: The original safety classification of the action
        executed_at: Timestamp when the action was executed
        metadata: Additional metadata about the execution
    """
    step: ActionStep
    success: bool
    content: Any = None
    error: Optional[str] = None
    safety_classification: SafetyLevel = field(default_factory=lambda: SafetyLevel.SAFE)
    executed_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate action result parameters."""
        if not isinstance(self.step, ActionStep):
            raise ValueError("step must be an ActionStep instance")
        if not self.success and self.error is None:
            # If not successful, we should have an error message
            self.error = "Unknown error"