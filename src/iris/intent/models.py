"""
Intent data models for IRIS Phase 7.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional


@dataclass
class Intent:
    """
    Represents an interpreted user request as a structured intent.

    Attributes:
        action: The intent/action name (e.g., "read_file", "calculate")
        arguments: Dictionary of arguments for the action
        confidence: Confidence score (0.0-1.0) indicating certainty in interpretation
        original_request: The original user input string
        timestamp: When the intent was created
        metadata: Additional provider-specific or processing metadata
    """
    action: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    original_request: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate intent parameters."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence}")
        if not self.action:
            raise ValueError("action cannot be empty")