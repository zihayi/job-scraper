from __future__ import annotations

from typing import Any

import mistune


_markdown = mistune.create_markdown(
    escape=True,
    plugins=["strikethrough", "table"],
)


def render_markdown(text: str) -> str:
    return _markdown(text or "")


def render_chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for message in messages:
        item = dict(message)
        if item.get("role") == "assistant":
            item["html"] = render_markdown(str(item.get("content") or ""))
            reasoning = str(item.get("reasoning") or "")
            if reasoning:
                item["reasoning_html"] = render_markdown(reasoning)
        rendered.append(item)
    return rendered
