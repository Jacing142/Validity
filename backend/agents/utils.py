"""Shared utilities for LangGraph agent nodes."""

import json
import re


def strip_json_fences(content: str) -> str:
    """Strip markdown JSON code fences and trailing commas from an LLM response.

    Handles responses that look like:
        ```json
        { ... }
        ```
    or just plain JSON (returned as-is).
    Also removes trailing commas before } or ] which are invalid JSON but
    common in LLM output.
    """
    content = content.strip()
    if content.startswith("```"):
        # Split on ``` and take the second segment (the content between fences)
        parts = content.split("```")
        if len(parts) >= 2:
            inner = parts[1]
            # Strip optional leading "json" language tag
            if inner.startswith("json"):
                inner = inner[4:]
            content = inner.strip()
    # Remove trailing commas before closing braces/brackets (invalid JSON)
    content = re.sub(r',(\s*[}\]])', r'\1', content)
    return content


def parse_llm_json(content: str) -> dict:
    """Strip JSON fences and parse the result, raising a clear error on failure."""
    stripped = strip_json_fences(content)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse LLM response as JSON: {exc}\nContent was: {stripped[:200]!r}"
        ) from exc
