"""OpenAI Responses API adapter (BUILD_BRIEF §1.3, §6.2).

* No sampling parameters, no system prompt, ``store: false``.
* Search: ``{"type": "web_search"}`` with ``tool_choice: "auto"``; sources are
  requested through ``include``.
* Queries come from ``web_search_call`` output items; refusals from ``refusal``
  content parts.
"""

from __future__ import annotations

import copy
from typing import Any

from .base import NormalisedResponse, ProviderAdapter, ToolEvent, merge_extra


class OpenAIAdapter(ProviderAdapter):
    provider = "openai"

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key or ''}", "Content-Type": "application/json"}

    def build_request(self, prompt_text: str, model_id: str, search_enabled: bool,
                      params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        settings = self.config.experiment.get("request", {}).get("openai", {})
        request: dict[str, Any] = {
            "model": model_id,
            "input": prompt_text,
            "store": bool(settings.get("store", False)),
        }
        summary = settings.get("reasoning_summary")
        if summary:
            request["reasoning"] = {"summary": summary}
        if search_enabled:
            tool_cfg = self.config.experiment.get("search_tools", {}).get("openai", {})
            request["tools"] = [copy.deepcopy(tool_cfg.get("default", {"type": "web_search"}))]
            request["tool_choice"] = tool_cfg.get("tool_choice", "auto")
            include = tool_cfg.get("include")
            if include:
                request["include"] = list(include)
        try:
            extra = self.config.model(model_id).get("request_extra") or {}
        except KeyError:
            extra = {}
        merge_extra(request, extra)
        merge_extra(request, params.get("request_extra"))
        return request

    async def send(self, request: dict[str, Any]) -> dict[str, Any]:
        response = await self.transport.request("POST", self.base_url + "/responses", self.headers(), request)
        return {"provider": "openai", "responses": [response.json], "http_status": response.status}

    @staticmethod
    def normalise(raw: dict[str, Any]) -> NormalisedResponse:
        responses = raw.get("responses") or []
        body = responses[-1] if len(responses) > 0 and isinstance(responses[-1], dict) else {}
        output = body.get("output") or []
        final_parts: list[str] = []
        reasoning_parts: list[str] = []
        events: list[ToolEvent] = []
        refusal = False
        notes: list[str] = []
        for i in range(len(output)):
            item = output[i]
            if not isinstance(item, dict):
                continue
            kind = item.get("type")
            if kind == "reasoning":
                summary = item.get("summary") or []
                for j in range(len(summary)):
                    if isinstance(summary[j], dict) and summary[j].get("text"):
                        reasoning_parts.append(str(summary[j]["text"]))
                content = item.get("content") or []
                for j in range(len(content)):
                    if isinstance(content[j], dict) and content[j].get("text"):
                        reasoning_parts.append(str(content[j]["text"]))
            elif kind == "web_search_call":
                action = item.get("action") or {}
                action_type = action.get("type") if isinstance(action, dict) else None
                query = None
                if isinstance(action, dict):
                    query = action.get("query")
                    if query is None and isinstance(action.get("queries"), list) and len(action["queries"]) > 0:
                        query = action["queries"][0]
                urls: list[str] = []
                sources = action.get("sources") if isinstance(action, dict) else None
                if isinstance(sources, list):
                    for j in range(len(sources)):
                        if isinstance(sources[j], dict) and sources[j].get("url"):
                            urls.append(str(sources[j]["url"]))
                if isinstance(action, dict) and action.get("url"):
                    urls.append(str(action["url"]))
                status = item.get("status")
                events.append(ToolEvent(
                    event_idx=len(events), provider_event_type="web_search_call",
                    query_text=query, query_visible=query is not None, result_urls=urls,
                    action_type=action_type, tool_use_id=item.get("id"),
                    executed=status not in ("failed", "incomplete"),
                    error_code=None if status not in ("failed",) else "failed",
                ))
            elif kind == "message":
                content = item.get("content") or []
                for j in range(len(content)):
                    part = content[j]
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "output_text" and part.get("text") is not None:
                        final_parts.append(str(part["text"]))
                    elif part.get("type") == "refusal":
                        refusal = True
                        if part.get("refusal"):
                            final_parts.append(str(part["refusal"]))
            else:
                notes.append(f"ignored output item type {kind}")
        usage = body.get("usage") or {}
        details = usage.get("output_tokens_details") or {}
        status = body.get("status")
        stop_reason = status
        incomplete = body.get("incomplete_details") or {}
        if status == "incomplete" and isinstance(incomplete, dict) and incomplete.get("reason"):
            stop_reason = f"incomplete:{incomplete['reason']}"
        if isinstance(incomplete, dict) and incomplete.get("reason") == "content_filter":
            refusal = True
        effort = None
        reasoning_cfg = body.get("reasoning")
        if isinstance(reasoning_cfg, dict):
            effort = reasoning_cfg.get("effort")
        search_count = 0
        for i in range(len(events)):
            if events[i].executed and events[i].action_type in (None, "search"):
                search_count += 1
        return NormalisedResponse(
            final_text="\n".join(final_parts).strip(),
            reasoning_text="\n\n".join(reasoning_parts).strip(),
            tool_events=events,
            search_count=search_count,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            reasoning_tokens=details.get("reasoning_tokens"),
            model_returned=body.get("model"),
            stop_reason=stop_reason,
            refusal_flag=refusal,
            reasoning_effort=effort,
            notes=notes,
        )
