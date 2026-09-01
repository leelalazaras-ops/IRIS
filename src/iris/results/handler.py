"""
Result handler for IRIS Phase 7.
"""

from typing import Dict, Any, List
from iris.results.models import ActionResult
from iris.memory.manager import MemoryManager


class ResultHandler:
    """
    Handles the results of action execution.
    """

    def __init__(self, memory_manager: MemoryManager):
        """
        Initialize the result handler.

        Args:
            memory_manager: The memory manager to store results in
        """
        self.memory_manager = memory_manager

    def handle_result(self, result: ActionResult) -> None:
        """
        Handle an action result by storing it in memory and potentially taking other actions.

        Args:
            result: The ActionResult to handle
        """
        # Store the result in memory
        self._store_result_in_memory(result)

        # Additional handling based on result outcome could go here
        # For example, triggering replanning on failure, etc.

    def _store_result_in_memory(self, result: ActionResult) -> None:
        """
        Store an action result in the conversation memory.

        Args:
            result: The ActionResult to store
        """
        # Create a summary of the result for storage
        if result.success:
            content_summary = f"Action '{result.step.tool_name}' executed successfully"
            if result.step.description:
                content_summary += f": {result.step.description}"
            if result.content is not None:
                content_summary += f" with result: {str(result.content)[:100]}"
        else:
            content_summary = f"Action '{result.step.tool_name}' failed: {result.error}"

        # Add as a system message to memory
        self.memory_manager.add_assistant_message(content_summary)

    def handle_multiple_results(self, results: List[ActionResult]) -> None:
        """
        Handle multiple action results.

        Args:
            results: List of ActionResult objects to handle
        """
        for result in results:
            self.handle_result(result)