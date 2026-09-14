"""
Focused tests for the LLM intent classifier.
"""
import unittest
from unittest.mock import AsyncMock, patch

from iris.intent.llm_classifier import classify_intent, SUPPORTED_ACTIONS
from iris.ai.service import AIService


class TestLLMClassifier(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a mock AIService
        self.ai_service = AsyncMock(spec=AIService)

    def _setup_mock_response(self, json_str):
        """Configure the mock to return a given string."""
        self.ai_service.generate = AsyncMock(return_value=json_str)

    async def test_valid_classification(self):
        """Valid classification with action and confidence."""
        self._setup_mock_response('{"action": "read_file", "confidence": 0.9, "arguments": {"path": "notes.txt"}}')
        result = await classify_intent("read notes.txt", self.ai_service)
        self.assertEqual(result["action"], "read_file")
        self.assertEqual(result["confidence"], 0.9)
        self.assertEqual(result["arguments"], {"path": "notes.txt"})

    async def test_valid_classification_with_arguments(self):
        """Classification with arguments."""
        self._setup_mock_response('{"action": "calculate", "confidence": 0.8, "arguments": {"expression": "25*4"}}')
        result = await classify_intent("calculate 25 times 4", self.ai_service)
        self.assertEqual(result["action"], "calculate")
        self.assertEqual(result["confidence"], 0.8)
        self.assertEqual(result["arguments"], {"expression": "25*4"})

    async def test_action_none(self):
        """When the AI returns action 'none'."""
        self._setup_mock_response('{"action": "none", "confidence": 0.0, "arguments": {}}')
        result = await classify_intent("hello", self.ai_service)
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["arguments"], {})

    async def test_unsupported_action(self):
        """Unsupported action should be rejected and default to none."""
        self._setup_mock_response('{"action": "unknown_action", "confidence": 0.7, "arguments": {}}')
        result = await classify_intent("do something", self.ai_service)
        # Should fall back to safe default
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["arguments"], {})

    async def test_malformed_json(self):
        """Malformed JSON should fail safely."""
        self._setup_mock_response('This is not JSON')
        result = await classify_intent("something", self.ai_service)
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["arguments"], {})

    async def test_invalid_confidence(self):
        """Invalid confidence (string) should fail safely."""
        self._setup_mock_response('{"action": "read_file", "confidence": "high", "arguments": {}}')
        result = await classify_intent("read file", self.ai_service)
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["arguments"], {})

    async def test_ai_service_exception(self):
        """If AIService.generate raises an exception, fail safely."""
        self.ai_service.generate = AsyncMock(side_effect=Exception("AI error"))
        result = await classify_intent("read file", self.ai_service)
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["arguments"], {})

    async def test_confidence_outside_range(self):
        """Confidence outside [0.0, 1.0] should be rejected."""
        self._setup_mock_response('{"action": "list_directory", "confidence": 1.5, "arguments": {}}')
        result = await classify_intent("list files", self.ai_service)
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["arguments"], {})

    async def test_confidence_zero(self):
        """Confidence 0.0 is valid."""
        self._setup_mock_response('{"action": "get_current_time", "confidence": 0.0, "arguments": {}}')
        result = await classify_intent("what time", self.ai_service)
        self.assertEqual(result["action"], "get_current_time")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["arguments"], {})

    async def test_confidence_one(self):
        """Confidence 1.0 is valid."""
        self._setup_mock_response('{"action": "write_file", "confidence": 1.0, "arguments": {"path": "test.txt", "content": "hello"}}')
        result = await classify_intent("write hello to test.txt", self.ai_service)
        self.assertEqual(result["action"], "write_file")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["arguments"], {"path": "test.txt", "content": "hello"})


if __name__ == '__main__':
    unittest.main()