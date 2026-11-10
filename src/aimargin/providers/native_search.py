"""Provider-hosted Responses web search for the Stage C extension."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .base import NormalisedResponse, ToolEvent
from .openai_adapter import OpenAIAdapter

SEARCH_MODELS = {
    "deepseek": {"deepseek-v4-pro"},
    "kimi": {"kimi-k3.1-pro", "kimi-k3"},
}


def require_native_search(provider: str, model: str) -> None:
    if model not in SEARCH_MODELS.get(provider, ()):
        raise ValueError(f"{provider} search is unavailable for this experiment: {model}")


def normalise_native_search(raw: dict[str, Any], provider: str) -> NormalisedResponse:
    # Reuse Responses text, reasoning, refusal and token parsing. The providers
    # expose different search metadata, so derive tool observations separately.
    result = OpenAIAdapter.normalise(raw)
    body = raw["responses"][-1]
    error = body.get("error") or {}
    if error.get("type") == "content_filter" or error.get("code") == "content_filter":
        result = replace(result, refusal_flag=True, stop_reason="content_filter")
    output = body.get("output")
    complete = body.get("status") == "completed" and isinstance(output, list)
    events: list[ToolEvent] = []
    kimi_count = 0
    kimi_count_known = complete
    for item in output or []:
        if not isinstance(item, dict) or item.get("type") != "web_search_call":
            continue
        action = item.get("action") or {}
        action_type = action.get("type")
        queries = []
        for query in [action.get("query")] + (action.get("queries") or []):
            if isinstance(query, str) and query.strip() and query not in queries:
                queries.append(query)
        sources = action.get("sources")
        urls = [] if isinstance(sources, list) else None
        if urls is not None:
            for source in sources:
                if isinstance(source, dict) and source.get("url"):
                    urls.append(source["url"])
        if action.get("url"):
            urls = list(dict.fromkeys((urls or []) + [action["url"]]))
        status = item.get("status")
        error = item.get("error") or action.get("error") or {}
        error_code = item.get("error_code") or action.get("error_code")
        if isinstance(error, dict):
            error_code = error_code or error.get("code") or error.get("type")
        if error_code is None and status in ("failed", "incomplete"):
            error_code = status
        executed = True if status == "completed" else False if status in ("failed", "incomplete") else None
        for query in queries or [None]:
            events.append(ToolEvent(
                event_idx=len(events), provider_event_type="web_search_call", query_text=query,
                query_visible=query is not None, result_urls=urls, error_code=error_code,
                action_type=action_type, tool_use_id=item.get("id"), executed=executed,
            ))
        if executed and action_type in (None, "search") and urls != []:
            kimi_count += 1
        if executed is None:
            kimi_count_known = False

    # DeepSeek explicitly omits server_tool_use when both billed counts are zero.
    # This convention only applies when the usage object itself is present.
    usage = body.get("usage")
    fetch_count = None
    if provider == "deepseek":
        if isinstance(usage, dict) and usage:
            server = usage.get("server_tool_use")
            search_count = server.get("tool_search") if isinstance(server, dict) else None
            fetch_count = server.get("tool_fetch") if isinstance(server, dict) else None
            if "server_tool_use" not in usage:
                search_count = fetch_count = 0
        else:
            search_count = None
    else:
        # Kimi documents per-search billing through the output item, not an
        # aggregate count. Count once per item, even if multiple queries are visible.
        search_count = kimi_count if kimi_count_known else None

    invoked = True if events or (search_count or 0) > 0 or (fetch_count or 0) > 0 else False if complete else None
    return replace(result, tool_events=events, search_count=search_count, fetch_count=fetch_count,
                   search_invoked=invoked)
