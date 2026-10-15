"""
Focused tests for Phase 11C.3: LLM intent classification integrated with
the deterministic rule-based detector.

These tests verify only the four behaviors called out by the Phase 11C.3
specification. They reuse the existing test infrastructure and mocks and do
not duplicate the larger integration suites.
"""

import pytest
from unittest.mock import AsyncMock

from iris.core.cli import IRISConversation
from iris.intent.models import Intent


def _make_llm_mock(action, confidence, arguments):
    """Return an AsyncMock that mimics classify_intent's dict return contract."""
    return AsyncMock(
        return_value={
            "action": action,
            "confidence": confidence,
            "arguments": arguments,
        }
    )


class TestPhase11C3IntentFallback:
    """LLM classification falls back to rule-based detection when the LLM
    does not identify an actionable intent or is below the 0.70 threshold."""

    def setup_method(self):
        self.conversation = IRISConversation()
        self.conversation.conversation_history = []
        self.conversation.tools_enabled = True
        self.conversation.dry_run_mode = False
        self.conversation.ai_service = AsyncMock()

    # 1. LLM "none" falls back to rule-based detection.

    @pytest.mark.asyncio
    async def test_llm_none_falls_back_to_rule_based(self, monkeypatch):
        monkeypatch.setattr(
            "iris.core.cli.classify_intent",
            _make_llm_mock("none", 0.0, {}),
        )

        intent = await self.conversation._create_intent_from_user_input("read file.txt")

        assert intent.source == "rule_based"
        assert intent.action == "read_file"
        assert intent.arguments == {"path": "file.txt"}
        assert intent.confidence == 0.8
        assert intent.original_request == "read file.txt"

    # 2. LLM low confidence falls back to rule-based detection.

    @pytest.mark.asyncio
    async def test_llm_low_confidence_falls_back_to_rule_based(self, monkeypatch):
        monkeypatch.setattr(
            "iris.core.cli.classify_intent",
            _make_llm_mock("read_file", 0.5, {"path": "doc.txt"}),
        )

        intent = await self.conversation._create_intent_from_user_input("show doc.txt")

        assert intent.source == "rule_based"
        assert intent.action == "read_file"
        assert intent.arguments == {"path": "doc.txt"}
        assert intent.confidence == 0.8
        assert intent.original_request == "show doc.txt"

    # 3. LLM high-confidence actionable intent remains source="llm".

    @pytest.mark.asyncio
    async def test_llm_high_confidence_actionable_remains_llm(self, monkeypatch):
        monkeypatch.setattr(
            "iris.core.cli.classify_intent",
            _make_llm_mock("list_directory", 0.9, {"path": "."}),
        )

        intent = await self.conversation._create_intent_from_user_input("show files")

        assert intent.source == "llm"
        assert intent.action == "list_directory"
        assert intent.arguments == {"path": "."}
        assert intent.confidence == 0.9
        assert intent.original_request == "show files"

    # 4. Fallback uses original user input rather than conversation context.

    @pytest.mark.asyncio
    async def test_fallback_uses_original_input_not_context(self, monkeypatch):
        # Spy on the rule-based fallback so we can confirm it receives the
        # ORIGINAL user input, not the context-enriched classifier prompt.
        # NOTE: _create_intent_from_user_input_rule_based is a synchronous
        # method in production (cli.py), so the spy must be synchronous too -
        # the control flow calls and awaits it inline, not as a coroutine.
        original_rule_based = self.conversation._create_intent_from_user_input_rule_based
        captured = {}

        def _spy_rule_based(user_input):
            captured["input"] = user_input
            return original_rule_based(user_input)

        self.conversation._create_intent_from_user_input_rule_based = _spy_rule_based

        # History contains a keyword ("read") that would falsely trigger the
        # rule-based detector if the context-enhanced input were used.
        self.conversation.memory_manager.add_user_message("Please read this file carefully")
        self.conversation.memory_manager.add_assistant_message("I've read the file")

        monkeypatch.setattr(
            "iris.core.cli.classify_intent",
            _make_llm_mock("none", 0.0, {}),
        )

        intent = await self.conversation._create_intent_from_user_input("hello there")

        # The LLM said "none" and the current input has no keyword, so the
        # rule-based detector must run on the ORIGINAL input ("hello there")
        # and produce a non-actionable intent - NOT a false "read_file"
        # match caused by the history.
        assert captured["input"] == "hello there"
        assert intent.source == "rule_based"
        assert intent.action == "none"
        assert intent.confidence == 0.0
        assert intent.original_request == "hello there"
        assert isinstance(intent, Intent)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])