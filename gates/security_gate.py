"""
Gate 3 — Security Gate: 3-Layer Defense-in-Depth.

Layer 1: Regex / Heuristic  — fast, zero-cost, catches known patterns
Layer 2: ML Classifier      — DeBERTa model for semantic injection detection
Layer 3: LLM-as-a-Judge     — GPT-5.2 final review of borderline records

Records flagged by ANY layer are QUARANTINED and never processed downstream.
Sequential escalation: if Layer 1 catches it, Layers 2 & 3 are skipped.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 1 — Regex / Heuristic
# ═══════════════════════════════════════════════════════════════════════════

# Layer 1 only carries GENERIC, universal signatures — the kind every
# production WAF / input filter would have.  Domain-specific and semantic
# attacks are deliberately left for Layer 2 (DeBERTa) and Layer 3 (LLM Judge).

_PATTERNS: list[tuple[str, re.Pattern]] = [
    # SQL injection — classic, universal
    ("sql_injection", re.compile(
        r"(;|'|\")?\s*(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE)\s+TABLE",
        re.IGNORECASE)),

    # XSS / HTML injection — classic, universal
    ("xss_payload", re.compile(r"<\s*script[^>]*>", re.IGNORECASE)),

    # Template injection syntax (Jinja / Mustache / SSTI)
    ("template_injection", re.compile(r"\{\{.*?\}\}")),
]

def _collect_strings(record: dict[str, Any]) -> list[tuple[str, str]]:
    """Flatten all string values in a record into (field_name, value) pairs."""
    pairs = []
    for key, val in record.items():
        if isinstance(val, str):
            pairs.append((key, val))
    return pairs


def _layer1_regex(record: dict[str, Any]) -> list[str]:
    """Layer 1: regex / heuristic scan.  Returns list of reasons (empty = safe)."""
    reasons: list[str] = []
    strings = _collect_strings(record)

    for field_name, value in strings:
        for label, pattern in _PATTERNS:
            if pattern.search(value):
                reasons.append(
                    f"[L1-regex][{label}] in '{field_name}': "
                    f"matched /{pattern.pattern}/"
                )

    return reasons


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 2 — ML Classifier (DeBERTa prompt-injection detector)
# ═══════════════════════════════════════════════════════════════════════════

_ml_classifier = None          # lazy-loaded singleton
_ML_MODEL_NAME = "protectai/deberta-v3-base-prompt-injection-v2"
_ML_THRESHOLD = 0.995           # high threshold to avoid false positives on structured data


def _get_ml_classifier():
    """Lazy-load the DeBERTa model to avoid cost if not needed."""
    global _ml_classifier
    if _ml_classifier is None:
        logger.info("Loading ML classifier: %s …", _ML_MODEL_NAME)
        from transformers import pipeline as hf_pipeline
        _ml_classifier = hf_pipeline(
            "text-classification",
            model=_ML_MODEL_NAME,
            truncation=True,
            max_length=512,
        )
        logger.info("ML classifier loaded.")
    return _ml_classifier


def _layer2_ml(record: dict[str, Any]) -> list[str]:
    """Layer 2: DeBERTa-based semantic injection detector."""
    reasons: list[str] = []
    classifier = _get_ml_classifier()
    strings = _collect_strings(record)

    for field_name, value in strings:
        # Skip very short values (IDs, dates, codes) — not meaningful
        if len(value.strip()) < 15:
            continue

        result = classifier(value)[0]
        label = result["label"]           # "INJECTION" or "SAFE"
        score = result["score"]

        if label == "INJECTION" and score >= _ML_THRESHOLD:
            reasons.append(
                f"[L2-ml][{label}] in '{field_name}': "
                f"confidence={score:.3f}"
            )

    return reasons


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 3 — LLM-as-a-Judge (GPT-5.2)
# ═══════════════════════════════════════════════════════════════════════════

_JUDGE_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "judge_prompt.txt"
_JUDGE_SYSTEM_PROMPT = _JUDGE_PROMPT_PATH.read_text(encoding="utf-8")


def _layer3_llm_judge(record: dict[str, Any]) -> list[str]:
    """Layer 3: LLM-as-a-Judge for final review."""
    from openai import OpenAI
    from config import OPENAI_MODEL

    reasons: list[str] = []
    client = OpenAI()

    # Send the full record for inspection
    user_message = (
        "Analyze the following data record for any security threats.\n\n"
        f"```json\n{json.dumps(record, indent=2, ensure_ascii=False)}\n```"
    )

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
        )

        raw_reply = (response.choices[0].message.content or "").strip()

        # Strip markdown fences if present
        if raw_reply.startswith("```"):
            lines = raw_reply.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_reply = "\n".join(lines)

        verdict = json.loads(raw_reply)

        if verdict.get("is_malicious", False):
            confidence = verdict.get("confidence", 0.0)
            threat_type = verdict.get("threat_type", "unknown")
            reason = verdict.get("reason", "")
            reasons.append(
                f"[L3-llm-judge][{threat_type}] confidence={confidence:.2f}: {reason}"
            )

    except Exception as exc:
        logger.warning(
            "LLM Judge failed for record %s: %s (treating as safe — fail-open for judge layer)",
            record.get("record_id", "?"), exc,
        )

    return reasons


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API — Sequential escalation
# ═══════════════════════════════════════════════════════════════════════════

def scan(record: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Scan a record through all 3 security layers (sequential escalation).

    If Layer 1 catches it → quarantine immediately (skip L2/L3).
    If Layer 1 says safe  → escalate to Layer 2.
    If Layer 2 catches it → quarantine immediately (skip L3).
    If Layer 2 says safe  → escalate to Layer 3.

    Returns:
        (is_malicious, reasons)
    """
    rid = record.get("record_id", "?")

    # Layer 1: Regex
    reasons = _layer1_regex(record)
    if reasons:
        logger.info("L1 (regex) flagged %s", rid)
        return True, reasons

    # Layer 2: ML Classifier 
    reasons = _layer2_ml(record)
    if reasons:
        logger.info("L2 (ML) flagged %s", rid)
        return True, reasons

    # Layer 3: LLM-as-a-Judge
    reasons = _layer3_llm_judge(record)
    if reasons:
        logger.info("L3 (LLM judge) flagged %s", rid)
        return True, reasons

    logger.info("✅ All 3 layers cleared %s", rid)
    return False, []
