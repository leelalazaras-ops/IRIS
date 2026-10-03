import pytest
from datetime import datetime
from iris.intent.models import Intent


def test_llm_intent_high_confidence():
    intent = Intent(
        action='test_action',
        confidence=0.8,
        source='llm',
        original_request='test request',
        timestamp=datetime.now()
    )
    assert intent.source == 'llm'
    assert intent.confidence >= 0.70


def test_llm_intent_medium_confidence():
    intent = Intent(
        action='test_action',
        confidence=0.5,
        source='llm',
        original_request='test request',
        timestamp=datetime.now()
    )
    assert intent.source == 'llm'
    assert 0.40 <= intent.confidence < 0.70


def test_llm_intent_low_confidence():
    intent = Intent(
        action='test_action',
        confidence=0.3,
        source='llm',
        original_request='test request',
        timestamp=datetime.now()
    )
    assert intent.source == 'llm'
    assert intent.confidence < 0.40


def test_rule_based_intent_preserved():
    intent = Intent(
        action='test_action',
        confidence=0.3,
        source='rule_based',
        original_request='test request',
        timestamp=datetime.now()
    )
    assert intent.source == 'rule_based'
