"""Anthropic Messages API adapter (BUILD_BRIEF §1.3, §6.2).

* Pinned ``anthropic-version``; no sampling parameters, no system prompt.
* Search tool from experiment.yaml (default ``web_search_20260318`` with dynamic
  filtering; robustness arm ``web_search_20250305``).
* Queries come from ``server_tool_use`` blocks, including nested blocks that carry a
  ``caller`` field (dynamic filtering). Results/errors come from
  ``web_search_tool_result`` blocks.
* ``stop_reason: "pause_turn"`` is continued by resending the partial assistant turn;
  ``stop_reason: "refusal"`` sets the refusal flag.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from .base import NormalisedResponse, ProviderAdapter, ToolEvent, merge_extra


class AnthropicAdapter(ProviderAdapter):
    provider = "anthropic"

    def headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": str(self.spec.get("api_version", "2023-06-01")),
            "content-type": "application/json",
        }

    def build_request(self, prompt_text: str, model_id: str, search_enabled: bool,
                      params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        settings = self.config.experiment.get("request", {}).get("anthropic", {})
        request: dict[str, Any] = {
            "model": model_id,
            "max_tokens": int(settings.get("max_tokens", 32000)),
            "messages": [{"role": "user", "content": prompt_text}],
        }
        if search_enabled:
            variant = params.get("search_variant", "default")
            tools_cfg = self.config.experiment.get("search_tools", {}).get("anthropic", {})
            tool = tools_cfg.get(variant, tools_cfg.get("default", {})).get("tool")
            request["tools"] = [copy.deepcopy(tool)]
        try:
            extra = self.config.model(model_id).get("request_extra") or {}
        except KeyError:
            extra = {}
        merge_extra(request, extra)
        merge_extra(request, params.get("request_extra"))
        return request

    async def send(self, request: dict[str, Any]) -> dict[str, Any]:
        settings = self.config.experiment.get("request", {}).get("anthropic", {})
        max_continuations = int(settings.get("pause_turn_max", 6))
        responses: list[Any] = []
        current = copy.deepcopy(request)
        prompt_message = request["messages"][0]
        assistant_blocks: list[Any] = []
        for _i in range(max_continuations + 1):
            response = await self.transport.request("POST", self.base_url + "/messages", self.headers(), current)
            body = response.json or {}
            responses.append(body)
            if body.get("stop_reason") != "pause_turn":
                break
            content = body.get("content") or []
            for j in range(len(content)):
                assistant_blocks.append(content[j])
            current = copy.deepcopy(request)
            current["messages"] = [prompt_message, {"role": "assistant", "content": copy.deepcopy(assistant_blocks)}]
        return {"provider": "anthropic", "responses": responses, "http_status": 200,
                "continuations": len(responses) - 1}

    def normalise(self, raw: dict[str, Any]) -> NormalisedResponse:
        responses = raw.get("responses") or []
        final_parts: list[str] = []
        reasoning_parts: list[str] = []
        events: list[ToolEvent] = []
        by_tool_id: dict[str, ToolEvent] = {}
        notes: list[str] = []
        input_tokens = 0
        output_tokens = 0
        usage_search = 0
        have_usage = False
        model_returned = None
        stop_reason = None
        for r in range(len(responses)):
            body = responses[r]
            if not isinstance(body, dict):
                continue
            model_returned = body.get("model") or model_returned
            stop_reason = body.get("stop_reason") or stop_reason
            usage = body.get("usage") or {}
            if usage:
                have_usage = True
                input_tokens += int(usage.get("input_tokens") or 0)
                input_tokens += int(usage.get("cache_creation_input_tokens") or 0)
                input_tokens += int(usage.get("cache_read_input_tokens") or 0)
                output_tokens += int(usage.get("output_tokens") or 0)
                server = usage.get("server_tool_use") or {}
                usage_search += int(server.get("web_search_requests") or 0)
            self._walk(body.get("content") or [], final_parts, reasoning_parts, events, by_tool_id, notes, None)
        executed = 0
        for i in range(len(events)):
            if events[i].executed and events[i].provider_event_type == "server_tool_use":
                executed += 1
        search_count = max(executed, usage_search)
        if len(responses) > 1:
            notes.append(f"pause_turn continuations: {len(responses) - 1}")
        return NormalisedResponse(
            final_text="".join(final_parts).strip(),
            reasoning_text="\n\n".join(reasoning_parts).strip(),
            tool_events=events,
            search_count=search_count,
            input_tokens=input_tokens if have_usage else None,
            output_tokens=output_tokens if have_usage else None,
            reasoning_tokens=None,
            model_returned=model_returned,
            stop_reason=stop_reason,
            refusal_flag=stop_reason == "refusal",
            reasoning_effort=None,
            notes=notes,
        )

    def _walk(self, blocks: list[Any], final_parts: list[str], reasoning_parts: list[str],
              events: list[ToolEvent], by_tool_id: dict[str, ToolEvent], notes: list[str],
              parent_caller: str | None) -> None:
        """Walk content blocks recursively so nested (dynamic-filtering) calls are found."""
        for i in range(len(blocks)):
            block = blocks[i]
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text":
                if block.get("text") is not None and parent_caller is None:
                    final_parts.append(str(block["text"]))
            elif kind == "thinking":
                if block.get("thinking"):
                    reasoning_parts.append(str(block["thinking"]))
            elif kind == "redacted_thinking":
                notes.append("redacted_thinking block present")
            elif kind == "server_tool_use":
                caller_value = block.get("caller")
                caller = None
                if caller_value is not None:
                    caller = caller_value if isinstance(caller_value, str) else json.dumps(caller_value, sort_keys=True)
                elif parent_caller is not None:
                    caller = parent_caller
                tool_input = block.get("input") or {}
                query = tool_input.get("query") if isinstance(tool_input, dict) else None
                name = block.get("name")
                if name in ("web_search", None) or query is not None:
                    event = ToolEvent(
                        event_idx=len(events), provider_event_type="server_tool_use",
                        query_text=query, query_visible=query is not None, caller=caller,
                        action_type=str(name) if name else "web_search", tool_use_id=block.get("id"),
                    )
                    events.append(event)
                    if block.get("id"):
                        by_tool_id[str(block["id"])] = event
                else:
                    notes.append(f"server_tool_use {name} (not a search)")
            elif kind == "web_search_tool_result":
                event = by_tool_id.get(str(block.get("tool_use_id")))
                content = block.get("content")
                if isinstance(content, dict) and "error_code" in content:
                    if event is not None:
                        event.error_code = str(content.get("error_code"))
                        event.executed = False
                    else:
                        notes.append(f"orphan search error {content.get('error_code')}")
                elif isinstance(content, list) and event is not None:
                    for j in range(len(content)):
                        if isinstance(content[j], dict) and content[j].get("url"):
                            event.result_urls.append(str(content[j]["url"]))
            # Recurse into any nested content (code-execution results that wrap searches).
            nested = block.get("content")
            if kind not in ("web_search_tool_result", "text", "thinking") and isinstance(nested, list):
                caller_here = parent_caller
                if block.get("caller") is not None and kind != "server_tool_use":
                    caller_here = json.dumps(block["caller"], sort_keys=True) if not isinstance(block["caller"], str) else block["caller"]
                self._walk(nested, final_parts, reasoning_parts, events, by_tool_id, notes,
                           caller_here if caller_here is not None else (kind if kind != "server_tool_use" else None))
