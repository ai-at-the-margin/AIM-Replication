"""Chat Completions offline and provider-hosted Responses search for Stage C."""

from __future__ import annotations

from typing import Any

from .base import NormalisedResponse, ProviderAdapter, TransportError, merge_extra
from .native_search import normalise_native_search, require_native_search


class ChatCompletionsAdapter(ProviderAdapter):
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key or ''}", "Content-Type": "application/json"}

    def build_request(self, prompt_text: str, model_id: str, search_enabled: bool,
                      params: dict[str, Any] | None = None) -> dict[str, Any]:
        if search_enabled:
            require_native_search(self.provider, model_id)
            settings = self.config.experiment["search_tools"][self.provider]["default"]
            request = {"model": model_id, "input": prompt_text, "stream": False,
                       "tools": [dict(settings["tool"])], "tool_choice": "auto",
                       "max_output_tokens": settings["max_output_tokens"]}
            if "reasoning_effort" in settings:
                request["reasoning"] = {"effort": settings["reasoning_effort"]}
            if "include" in settings:
                request["include"] = list(settings["include"])
            return request
        request = dict(self.config.experiment.get("request", {}).get(self.provider, {}))
        merge_extra(request, self.config.model(model_id).get("request_extra"))
        merge_extra(request, (params or {}).get("request_extra"))
        request.update(model=model_id, messages=[{"role": "user", "content": prompt_text}], stream=False)
        return request

    async def send(self, request: dict[str, Any]) -> dict[str, Any]:
        search_enabled = "input" in request
        endpoint = "/responses" if search_enabled else "/chat/completions"
        response = await self.transport.request("POST", self.base_url + endpoint, self.headers(), request)
        raw = {"provider": self.provider, "responses": [response.json], "http_status": response.status}
        if search_enabled:
            raw["native_search"] = True
        return raw

    def normalise(self, raw: dict[str, Any]) -> NormalisedResponse:
        if raw.get("native_search"):
            return normalise_native_search(raw, self.provider)
        body = raw["responses"][-1]
        usage = body.get("usage") or {}
        refusal = (body.get("error") or {}).get("type") == "content_filter"
        choice = {} if refusal else body["choices"][0]
        message = {} if refusal else choice["message"]
        stop_reason = "content_filter" if refusal else choice.get("finish_reason")
        return NormalisedResponse(
            final_text=(message.get("content") or message.get("refusal") or "").strip(),
            reasoning_text=(message.get("reasoning_content") or "").strip(),
            tool_events=[], search_count=0,
            input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
            reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            model_returned=body.get("model"), stop_reason=stop_reason,
            refusal_flag=bool(message.get("refusal")) or stop_reason == "content_filter",
        )


class DeepSeekAdapter(ChatCompletionsAdapter):
    provider = "deepseek"


class KimiAdapter(ChatCompletionsAdapter):
    provider = "kimi"

    async def send(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            return await super().send(request)
        except TransportError as exc:
            error = exc.body.get("error") if isinstance(exc.body, dict) else None
            error_type = error.get("type") if isinstance(error, dict) else None
            if exc.status == 400 and error_type == "content_filter":
                return {"provider": self.provider, "responses": [exc.body], "http_status": exc.status,
                        "native_search": "input" in request}
            if exc.status == 429 and error_type == "exceeded_current_quota_error":
                exc.retryable = False
            raise
