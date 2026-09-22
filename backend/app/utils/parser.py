"""Extract a JSON array from an LLM response.

A regex like `\[[\s\S]*?\]` looks adequate until a finding's code snippet
contains `items[0]` or `List[str]` - the non-greedy match stops at that inner
bracket and the whole array is lost. So we scan with a depth counter that
understands string literals and escapes.
"""
import json


class LLMParseError(ValueError):
    """The response did not contain a usable JSON array."""


def _find_balanced_array(text: str, start: int) -> str | None:
    """Return the substring from `start` through its matching `]`, or None."""
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def _candidates(content: str):
    """Yield plausible JSON-array substrings, most likely first."""
    text = content.strip()
    yield text

    # Fenced block, with or without a language tag.
    fence = text.find("```")
    while fence != -1:
        body_start = text.find("\n", fence)
        if body_start == -1:
            break
        body_end = text.find("```", body_start)
        body = text[body_start:body_end] if body_end != -1 else text[body_start:]
        stripped = body.strip()
        if stripped:
            yield stripped
        fence = text.find("```", body_end + 3) if body_end != -1 else -1

    # First balanced array anywhere in the response (prose preamble, etc.).
    bracket = text.find("[")
    while bracket != -1:
        balanced = _find_balanced_array(text, bracket)
        if balanced:
            yield balanced
        bracket = text.find("[", bracket + 1)


def parse_llm_json_array(content: str) -> list:
    """Best-effort extraction of a JSON array. Raises LLMParseError on failure."""
    if not content or not content.strip():
        raise LLMParseError("LLM returned an empty response")

    for candidate in _candidates(content):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, list):
            return data
        # Some models wrap the array: {"issues": [...]}.
        if isinstance(data, dict):
            for key in ("issues", "findings", "results", "items", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    return value

    raise LLMParseError("LLM response did not contain a JSON array")


def strip_markdown_fences(text: str) -> str:
    """Remove a single surrounding code fence, if present."""
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    newline = cleaned.find("\n")
    if newline == -1:
        return cleaned.strip("`").strip()
    body = cleaned[newline + 1 :]
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()
