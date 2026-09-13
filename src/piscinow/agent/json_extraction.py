import json
import re


def parse_json_object(raw: str) -> dict:
    """Tolerant JSON-object extraction from LLM output: finds the first
    {...} blob in the text and parses it, returning {} on any failure."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
