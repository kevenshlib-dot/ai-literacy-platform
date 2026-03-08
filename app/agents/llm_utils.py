"""Shared utilities for LLM response processing.

Handles common patterns like stripping thinking chains (<think>...</think>)
and extracting JSON from LLM output.

Supports multiple thinking output formats:
- Full tags: <think>...</think>
- Missing opening tag (vLLM strips it): Thinking Process:...\n</think>
- Plain text thinking: Thinking Process:...\n\n[actual content]
"""
import re


def strip_thinking_tags(text: str) -> str:
    """Remove thinking/reasoning chains from LLM output.

    Handles three common patterns produced by Qwen3.5 and similar models:

    1. Full <think>...</think> tags (standard format)
    2. Missing opening <think> tag (vLLM may consume it), but </think> present
       e.g.: "Thinking Process:\\n...\\n</think>\\n[JSON]"
    3. Plain text "Thinking Process:" without any XML tags
       e.g.: "Thinking Process:\\n...\\n\\n[JSON]"

    Args:
        text: Raw LLM output that may contain thinking content.

    Returns:
        Text with thinking content removed, ready for JSON extraction.
    """
    if not text:
        return text

    # Pattern 1: Full <think>...</think> tags
    if "<think>" in text and "</think>" in text:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return text

    # Pattern 2: Only </think> closing tag present (opening consumed by vLLM)
    # Take everything after the last </think>
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
        return text

    # Pattern 3: Plain text "Thinking Process:" without XML tags
    # The actual content (JSON) usually starts after a double newline
    if text.startswith("Thinking Process:") or text.startswith("Thinking:"):
        # Try to find JSON content by looking for [ or { after thinking
        # Strategy: find the first [ or { that starts a valid JSON structure
        for marker in ("[", "{"):
            idx = text.find(marker)
            if idx > 0:
                candidate = text[idx:]
                # Verify it looks like JSON (has matching closing bracket)
                closing = "]" if marker == "[" else "}"
                if closing in candidate:
                    return candidate.strip()
        # Fallback: return everything after double newline
        parts = text.split("\n\n")
        if len(parts) > 1:
            # Return the last substantial part (likely the JSON)
            for part in reversed(parts):
                part = part.strip()
                if part.startswith("[") or part.startswith("{"):
                    return part
        return text

    return text


def extract_json_text(raw: str) -> str:
    """Extract JSON text from LLM response.

    Handles multiple output patterns in order:
    1. Thinking chains (all formats: <think> tags, plain text)
    2. ```json ... ``` markdown code blocks
    3. ``` ... ``` generic code blocks

    Args:
        raw: Raw LLM output string.

    Returns:
        Cleaned string ready for json.loads().
    """
    # Step 1: Strip thinking content
    raw = strip_thinking_tags(raw)

    # Step 2: Extract from markdown code blocks
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in raw:
        raw = raw.split("```", 1)[1].split("```", 1)[0].strip()

    return raw


def extract_json_text_regex(raw: str, pattern: str = "object") -> str:
    """Extract JSON text using regex, with thinking tag support.

    Used by agents that rely on regex-based JSON extraction
    (e.g., searching for ```json {...} ``` or ```json [...] ```).

    Args:
        raw: Raw LLM output string.
        pattern: "object" to extract {...}, "array" to extract [...].

    Returns:
        Cleaned string ready for json.loads().
    """
    # Step 1: Strip thinking content
    raw = strip_thinking_tags(raw)

    # Step 2: Regex-based extraction
    if pattern == "array":
        json_match = re.search(
            r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL
        )
    else:
        json_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL
        )

    if json_match:
        raw = json_match.group(1)

    return raw
