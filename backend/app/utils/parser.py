import json
import re


def strip_markdown_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_llm_json_array(content: str) -> list:
    content_str = content.strip()
    
    # Try parsing directly first
    try:
        data = json.loads(content_str)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # Try searching for a markdown json code block
    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", content_str)
    if match:
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # Try searching for any [...] pattern
    match = re.search(r"(\[[\s\S]*?\])", content_str)
    if match:
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # Fallback to the original method just in case
    cleaned = strip_markdown_fences(content_str)
    data = json.loads(cleaned)
    if not isinstance(data, list):
        raise ValueError("LLM response is not a JSON array")
    return data
