"""CONSTRAINTS F4: no test may reach the real Anthropic API (AI_PIPELINE 10)."""

import anthropic
import pytest

from tests.conftest import RealNetworkBlocked


def test_a_real_sdk_call_is_blocked_and_recorded(real_http_attempts: list[str]) -> None:
    client = anthropic.Anthropic(api_key="test-key-not-real", max_retries=0)

    with pytest.raises(anthropic.APIConnectionError) as caught:
        client.messages.create(
            model="test-model",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )

    assert isinstance(caught.value.__cause__, RealNetworkBlocked)
    assert any("api.anthropic.com" in url for url in real_http_attempts)
    # This test tripped the guard on purpose; clear it so teardown passes.
    real_http_attempts.clear()
