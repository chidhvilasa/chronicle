"""Extracts prompt data from a run's `llm_call` events, for the Prompt Inspector.

Two tiers, mirroring `server/src/registry.py`'s snapshot summary/detail split:
`build_prompt_summaries` (cheap, no full message content - safe to call for a
run with hundreds of events) and `build_prompt_detail` (full content for one
event, fetched lazily by the app only when a specific prompt is opened).

Adapters don't agree on one prompt shape yet (see `KNOWN_ISSUES.md`), so
`_extract_messages` reads whichever of `data["messages"]` (list of role/content
dicts), `data["prompts"]`/`data["prompt"]` (LangGraph/PydanticAI's raw string
form), and `data["completion"]`/`data["response"]` is present, degrading to an
empty list rather than raising when none of them are.
"""

from __future__ import annotations

from typing import Any, TypedDict


class PromptSummary(TypedDict):
    event_id: str
    step_index: int
    agent_name: str | None
    timestamp: float
    total_chars: int
    total_tokens: int


class PromptDetail(TypedDict):
    event_id: str
    step_index: int
    agent_name: str | None
    timestamp: float
    system_prompt: str | None
    user_messages: list[dict[str, Any]]
    assistant_messages: list[dict[str, Any]]
    total_chars: int
    total_tokens: int


def _extract_messages(
    data: dict[str, Any],
) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    system_prompt = data.get("system_prompt")
    if not isinstance(system_prompt, str):
        system_prompt = None

    raw_messages = data.get("messages")
    user_messages: list[dict[str, Any]] = []
    assistant_messages: list[dict[str, Any]] = []

    if isinstance(raw_messages, list):
        for message in raw_messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = str(message.get("content", ""))
            if role in ("user", "human"):
                user_messages.append({"role": "user", "content": content})
            elif role in ("assistant", "ai"):
                assistant_messages.append({"role": "assistant", "content": content})
            elif role == "system" and system_prompt is None:
                system_prompt = content
    else:
        prompts = data.get("prompts")
        if isinstance(prompts, list):
            user_messages = [{"role": "user", "content": str(p)} for p in prompts]
        elif isinstance(data.get("prompt"), str):
            user_messages = [{"role": "user", "content": data["prompt"]}]

    if not assistant_messages:
        text = data.get("completion") if isinstance(data.get("completion"), str) else None
        text = text or (data.get("response") if isinstance(data.get("response"), str) else None)
        if text:
            assistant_messages = [{"role": "assistant", "content": text}]

    return system_prompt, user_messages, assistant_messages


def _total_chars(
    system_prompt: str | None, user_messages: list[dict[str, Any]], assistant_messages: list[dict[str, Any]]
) -> int:
    total = len(system_prompt) if system_prompt else 0
    total += sum(len(str(m.get("content", ""))) for m in user_messages)
    total += sum(len(str(m.get("content", ""))) for m in assistant_messages)
    return total


def _ordered_llm_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((e for e in events if e["event_type"] == "llm_call"), key=lambda e: e["timestamp"])


def build_prompt_summaries(events: list[dict[str, Any]]) -> list[PromptSummary]:
    """Cheap per-event summaries (no message content) for `GET /runs/{id}/prompts`."""
    summaries: list[PromptSummary] = []
    for index, event in enumerate(_ordered_llm_events(events)):
        data = event.get("data") or {}
        system_prompt, user_messages, assistant_messages = _extract_messages(data)
        summaries.append(
            {
                "event_id": event["event_id"],
                "step_index": index,
                "agent_name": event.get("agent_name"),
                "timestamp": event["timestamp"],
                "total_chars": _total_chars(system_prompt, user_messages, assistant_messages),
                "total_tokens": (event.get("input_tokens") or 0) + (event.get("output_tokens") or 0),
            }
        )
    return summaries


def build_prompt_detail(events: list[dict[str, Any]], event_id: str) -> PromptDetail | None:
    """Full prompt content for one `llm_call` event, for `GET /runs/{id}/prompts/{event_id}`."""
    for index, event in enumerate(_ordered_llm_events(events)):
        if event["event_id"] != event_id:
            continue
        data = event.get("data") or {}
        system_prompt, user_messages, assistant_messages = _extract_messages(data)
        return {
            "event_id": event["event_id"],
            "step_index": index,
            "agent_name": event.get("agent_name"),
            "timestamp": event["timestamp"],
            "system_prompt": system_prompt,
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "total_chars": _total_chars(system_prompt, user_messages, assistant_messages),
            "total_tokens": (event.get("input_tokens") or 0) + (event.get("output_tokens") or 0),
        }
    return None


def prompt_text(detail: PromptDetail) -> str:
    """Flattens a prompt detail into one string (system + user + assistant, in order) for diffing."""
    parts: list[str] = []
    if detail["system_prompt"]:
        parts.append(detail["system_prompt"])
    parts.extend(str(m.get("content", "")) for m in detail["user_messages"])
    parts.extend(str(m.get("content", "")) for m in detail["assistant_messages"])
    return "\n".join(parts)
