import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from iris.ai.service import AIService, PERSONALITY_PROMPT
from iris.ai.config import AIConfig
from iris.ai.provider import AIResponse


@pytest_asyncio.fixture
async def service():
    svc = AIService(
        config=AIConfig(
            provider="mock",
            base_url=None,
            api_key=None,
            model="m",
            timeout=30.0,
        )
    )
    provider = AsyncMock()
    provider.generate.return_value = AIResponse(content="Test response", model="m")
    svc._get_provider = lambda: provider
    svc.test_provider = provider
    yield svc
    await svc.close()


def assert_prompt_in_provider_request(service):
    request = service.test_provider.generate.call_args.args[0]
    assert PERSONALITY_PROMPT in request.messages[0]["content"]


@pytest.mark.asyncio
async def test_generate_injects_prompt(service):
    msg = [{"role": "user", "content": "hello"}]

    await service.generate(msg)

    assert_prompt_in_provider_request(service)
    assert msg == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_generate_with_metadata_injects_prompt(service):
    msg = [{"role": "user", "content": "hi"}]

    await service.generate_with_metadata(msg)

    assert_prompt_in_provider_request(service)


@pytest.mark.asyncio
async def test_generate_with_tools_injects_prompt_and_forwards_tools(service):
    msg = [{"role": "user", "content": "use tool"}]
    tools = [{"name": "t"}]

    await service.generate_with_tools(msg, tools=tools)

    assert_prompt_in_provider_request(service)
    request = service.test_provider.generate.call_args.args[0]
    assert request.tools == tools


@pytest.mark.asyncio
async def test_existing_system_preserved(service):
    msg = [{"role": "system", "content": "Be nice."}]

    await service.generate(msg)

    request = service.test_provider.generate.call_args.args[0]
    assert request.messages[0]["content"].startswith(PERSONALITY_PROMPT)
    assert "Be nice." in request.messages[0]["content"]
    assert msg[0]["content"] == "Be nice."


@pytest.mark.asyncio
async def test_original_messages_unchanged(service):
    original = [
        {"role": "system", "content": "Follow these rules."},
        {"role": "user", "content": "hello"},
    ]
    snapshot = [message.copy() for message in original]

    await service.generate(original)

    assert original == snapshot


