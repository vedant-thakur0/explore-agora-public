"""Thin Anthropic SDK wrapper with retry, rate limiting, and JSON parsing."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import anthropic

from pipeline.config import (
    ANTHROPIC_MODEL_BULK,
    ANTHROPIC_MAX_RETRIES,
    ANTHROPIC_RATE_DELAY_SECONDS,
    ANTHROPIC_RETRY_BASE_DELAY,
)

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


def call_claude(
    system: str,
    user: str,
    *,
    model: str = ANTHROPIC_MODEL_BULK,
    max_tokens: int = 2048,
    temperature: float | None = None,
) -> tuple[str, int, int]:
    """Call Claude and return (response_text, prompt_tokens, completion_tokens).

    Retries on transient errors with exponential backoff.
    Sleeps ANTHROPIC_RATE_DELAY_SECONDS after each successful call.
    """
    client = _get_client()
    last_err: Exception | None = None

    for attempt in range(ANTHROPIC_MAX_RETRIES):
        try:
            kwargs: dict[str, Any] = dict(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if temperature is not None:
                kwargs["temperature"] = temperature
            response = client.messages.create(**kwargs)
            text = response.content[0].text
            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens
            time.sleep(ANTHROPIC_RATE_DELAY_SECONDS)
            return text, prompt_tokens, completion_tokens

        except (
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            anthropic.APIConnectionError,
        ) as exc:
            last_err = exc
            delay = ANTHROPIC_RETRY_BASE_DELAY * (2 ** attempt)
            log.warning(
                "Anthropic API error (attempt %d/%d): %s. Retrying in %ds.",
                attempt + 1,
                ANTHROPIC_MAX_RETRIES,
                exc,
                delay,
            )
            time.sleep(delay)

    raise RuntimeError(
        f"Anthropic API failed after {ANTHROPIC_MAX_RETRIES} retries: {last_err}"
    )


def call_claude_json(
    system: str,
    user: str,
    *,
    model: str = ANTHROPIC_MODEL_BULK,
    max_tokens: int = 2048,
    temperature: float | None = None,
) -> tuple[dict[str, Any] | None, int, int]:
    """Call Claude expecting JSON output. Returns (parsed_dict, prompt_tokens, completion_tokens).

    On JSON parse failure, retries once with a stricter prompt prefix.
    Returns (None, tokens, tokens) if both attempts produce invalid JSON.
    """
    text, pt, ct = call_claude(system, user, model=model, max_tokens=max_tokens, temperature=temperature)

    # Try parsing the raw response
    parsed = _try_parse_json(text)
    if parsed is not None:
        return parsed, pt, ct

    # Retry with strict prefix
    log.warning("JSON parse failed, retrying with strict prefix.")
    strict_user = (
        'IMPORTANT: Return ONLY valid JSON starting with `{`. '
        'No explanation, no markdown fences.\n\n' + user
    )
    text2, pt2, ct2 = call_claude(system, strict_user, model=model, max_tokens=max_tokens)
    parsed2 = _try_parse_json(text2)
    return parsed2, pt + pt2, ct + ct2


def _try_parse_json(text: str) -> dict[str, Any] | None:
    """Attempt to parse JSON from LLM output, handling common issues."""
    text = text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    return None
