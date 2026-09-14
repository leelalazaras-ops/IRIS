"""
LLM-based intent classifier for IRIS.

Uses the existing AIService to classify user utterances into supported actions.
"""
from typing import Dict, Any
from iris.ai.service import AIService

# List of supported actions
SUPPORTED_ACTIONS = [
    "read_file",
    "write_file",
    "list_directory",
    "create_directory",
    "get_current_time",
    "calculate",
    "get_system_info",
    "get_current_directory",
    "get_environment_info",
    "none",
]

async def classify_intent(user_input: str, ai_service: AIService) -> Dict[str, Any]:
    """
    Classify user intent using the AI service.

    Args:
        user_input: The user's utterance.
        ai_service: An instance of AIService to use for classification.

    Returns:
        A dictionary with keys: action (str), confidence (float), arguments (dict).
        On any error, returns a safe default: {"action": "none", "confidence": 0.0, "arguments": {}}.
    """
    # Prepare the prompt
    prompt = f"""You are an intent classification system for IRIS. Classify the user's request into one of the following actions:
read_file, write_file, list_directory, create_directory, get_current_time, calculate, get_system_info, get_current_directory, get_environment_info, none.
Return a JSON object with keys: action (string), confidence (float between 0.0 and 1.0), arguments (object).
If the request does not match any action, set action to 'none' and confidence to 0.0.
User request: \"\"\"{user_input}\"\""
JSON:"""

    try:
        # Generate classification from AI service (text-only generation)
        response = await ai_service.generate(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,  # We want deterministic output for classification
        )

        # Extract JSON from the response
        import json
        import re

        # Try to find a JSON object in the response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in AI response")

        json_str = json_match.group(0)
        data = json.loads(json_str)

        # Validate and extract fields
        action = data.get("action")
        confidence = data.get("confidence")
        arguments = data.get("arguments", {})

        # Validate action
        if action not in SUPPORTED_ACTIONS:
            raise ValueError(f"Unsupported action: {action}")

        # Validate confidence
        if not isinstance(confidence, (int, float)):
            raise ValueError("Confidence must be a number")
        confidence = float(confidence)
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("Confidence out of range [0.0, 1.0]")

        # Validate arguments is a dict-like
        if not isinstance(arguments, dict):
            # Try to convert if it's a JSON string? But we expect dict.
            raise ValueError("Arguments must be an object/dict")

        return {
            "action": action,
            "confidence": confidence,
            "arguments": arguments,
        }

    except Exception:
        # Fail safely: return a default that indicates no intent
        return {
            "action": "none",
            "confidence": 0.0,
            "arguments": {},
        }