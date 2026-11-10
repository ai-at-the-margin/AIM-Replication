"""Provider adapters (BUILD_BRIEF §6.2)."""

from __future__ import annotations

from typing import Any

from ..settings import Config
from .anthropic_adapter import AnthropicAdapter
from .base import ProviderAdapter, Transport
from .chat_completions import DeepSeekAdapter, KimiAdapter
from .openai_adapter import OpenAIAdapter


def make_adapter(provider: str, config: Config, transport: Transport, api_key: str | None) -> ProviderAdapter:
    if provider == "openai":
        return OpenAIAdapter(config, transport, api_key)
    if provider == "anthropic":
        return AnthropicAdapter(config, transport, api_key)
    if provider == "deepseek":
        return DeepSeekAdapter(config, transport, api_key)
    if provider == "kimi":
        return KimiAdapter(config, transport, api_key)
    raise ValueError(f"unknown provider {provider!r}")


def api_key_for(provider: str, config: Config) -> str | None:
    import os

    spec: dict[str, Any] = config.provider(provider)
    key = os.environ.get(spec.get("env_key") or "", "") or None
    fallback = spec.get("env_key_fallback")
    if key is None and fallback:
        key = os.environ.get(fallback, "") or None
    return key


__all__ = ["ProviderAdapter", "Transport", "make_adapter", "api_key_for", "OpenAIAdapter", "AnthropicAdapter"]
