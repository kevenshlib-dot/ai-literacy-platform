"""Tests for system LLM provider configuration."""
import pytest

from app.api.v1.endpoints import system_config as endpoint


def provider(api_key: str = "sk-test-secret-key") -> dict:
    return {
        "id": "provider-1",
        "name": "Test OpenAI",
        "provider_type": "openai",
        "api_key": api_key,
        "base_url": "https://api.example.com/v1",
        "model": "gpt-test",
        "enabled": True,
    }


def test_provider_out_masks_api_key():
    data = endpoint._provider_out(provider("sk-test-secret-key"))

    assert data["has_api_key"] is True
    assert data["api_key"] != "sk-test-secret-key"
    assert data["api_key"] == "sk-t********-key"


def test_provider_out_handles_empty_api_key():
    data = endpoint._provider_out(provider(""))

    assert data["has_api_key"] is False
    assert data["api_key"] == ""


def test_update_payload_preserves_existing_api_key_when_blank():
    payload = endpoint.ProviderIn(
        name="Renamed",
        provider_type="openai",
        api_key="",
        base_url="https://api.example.com/v1",
        model="gpt-test",
        enabled=True,
    )

    data = endpoint._provider_payload_with_existing_key(payload, provider("sk-original-key"))

    assert data["name"] == "Renamed"
    assert data["api_key"] == "sk-original-key"


def test_update_payload_preserves_existing_api_key_when_mask_echoed():
    existing = provider("sk-original-key")
    payload = endpoint.ProviderIn(
        name="Renamed",
        provider_type="openai",
        api_key=endpoint._mask_api_key(existing["api_key"]),
        base_url="https://api.example.com/v1",
        model="gpt-test",
        enabled=True,
    )

    data = endpoint._provider_payload_with_existing_key(payload, existing)

    assert data["api_key"] == "sk-original-key"


def test_update_payload_replaces_api_key_when_new_value_sent():
    payload = endpoint.ProviderIn(
        name="Renamed",
        provider_type="openai",
        api_key="sk-new-key",
        base_url="https://api.example.com/v1",
        model="gpt-test",
        enabled=True,
    )

    data = endpoint._provider_payload_with_existing_key(payload, provider("sk-original-key"))

    assert data["api_key"] == "sk-new-key"


def test_payload_for_provider_uses_stored_key_and_allows_overrides():
    payload = endpoint.TestPayload(api_key="", base_url="https://override.example.com/v1", model="gpt-override")

    data = endpoint._payload_for_provider(provider("sk-stored-key"), payload)

    assert data.api_key == "sk-stored-key"
    assert data.base_url == "https://override.example.com/v1"
    assert data.model == "gpt-override"


def test_payload_for_provider_accepts_empty_test_payload():
    data = endpoint._payload_for_provider(provider("sk-stored-key"), endpoint.TestPayload())

    assert data.api_key == "sk-stored-key"
    assert data.base_url == "https://api.example.com/v1"
    assert data.model == "gpt-test"


@pytest.mark.asyncio
async def test_saved_provider_test_endpoint_uses_stored_api_key(monkeypatch):
    seen = {}

    async def fake_get_provider_or_404(_db, provider_id):
        assert provider_id == "provider-1"
        return provider("sk-stored-key")

    async def fake_test(payload):
        seen.update(payload.model_dump())
        return {"success": True, "model": payload.model, "reply": "ok"}

    monkeypatch.setattr(endpoint, "_get_provider_or_404", fake_get_provider_or_404)
    monkeypatch.setattr(endpoint, "_test_provider_connection", fake_test)

    result = await endpoint.test_saved_provider(
        provider_id="provider-1",
        payload=endpoint.TestPayload(api_key="", base_url="", model=""),
        db=None,
        _=None,
    )

    assert result["success"] is True
    assert seen["api_key"] == "sk-stored-key"
    assert seen["base_url"] == "https://api.example.com/v1"
    assert seen["model"] == "gpt-test"
