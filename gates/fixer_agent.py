"""
Gate 4 — The "Fixer" Agent.

Uses OpenAI (GPT-5.2) to heal fragmented or malformed records by inferring
missing fields from available context and reconstructing a valid canonical
record.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI

from config import OPENAI_MODEL

logger = logging.getLogger(__name__)

# Load the system prompt once
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "fixer_prompt.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


def _build_client() -> OpenAI:
    """Build OpenAI client — expects OPENAI_API_KEY in env."""
    return OpenAI()       # reads OPENAI_API_KEY from environment automatically


def heal(record: dict[str, Any], validation_errors: list[str]) -> dict[str, Any]:
    """
    Send a malformed record to the LLM for repair.

    Args:
        record:            The raw JSON record.
        validation_errors: Errors from schema validation (for context).

    Returns:
        A repaired record dict (best-effort).
    """
    client = _build_client()

    user_message = (
        f"### Raw Record\n```json\n{json.dumps(record, indent=2)}\n```\n\n"
        f"### Validation Errors\n"
        + ("\n".join(f"- {e}" for e in validation_errors) if validation_errors else "- None (record fields are non-standard)")
    )

    logger.info("Fixer Agent: healing record %s", record.get("record_id", "?"))

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.0,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
    )

    raw_reply = response.choices[0].message.content or ""

    # Strip markdown fences if the model wraps in ```json ... ```
    raw_reply = raw_reply.strip()
    if raw_reply.startswith("```"):
        lines = raw_reply.splitlines()
        # Remove first and last line (``` markers)
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_reply = "\n".join(lines)

    try:
        repaired = json.loads(raw_reply)
        logger.info("Fixer Agent: successfully healed record %s", record.get("record_id", "?"))
        return repaired
    except json.JSONDecodeError:
        logger.warning(
            "Fixer Agent: could not parse LLM reply for record %s. Raw: %s",
            record.get("record_id", "?"),
            raw_reply[:200],
        )
        # Return the original record so the pipeline can still report it
        return record
