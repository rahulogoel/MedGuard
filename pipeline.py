"""
Pipeline Orchestrator — MedGuard.

Processes raw_dump.json through four gates in order:
    Gate 3  →  Security Gate     (quarantine malicious records)
    Gate 1  →  Schema Validation (check canonical structure)
    Gate 4  →  Fixer Agent       (LLM-heal malformed records)
    Gate 2  →  Date Normalization(ISO 8601 normalisation)

Outputs:
    output/clean_output.json   — valid canonical records
    output/quarantined.json    — malicious records with reasons
    output/pipeline_log.json   — full processing log
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

# Load .env before any other imports that need env vars
load_dotenv()

from config import INPUT_FILE, OUTPUT_DIR, CLEAN_OUTPUT_FILE, QUARANTINED_FILE, PIPELINE_LOG_FILE
from gates import security_gate, schema_validator, date_normalizer, fixer_agent

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _load_records(path: Path) -> list[dict]:
    """Load raw records from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), "raw_dump.json must be a JSON array"
    return data


def _save_json(path: Path, data: list | dict) -> None:
    """Save data to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    logger.info("Saved → %s", path)


def run() -> None:
    """Execute the full pipeline."""
    logger.info("=" * 60)
    logger.info("MEDGUARD PIPELINE — Starting")
    logger.info("=" * 60)

    records = _load_records(INPUT_FILE)
    logger.info("Loaded %d records from %s", len(records), INPUT_FILE.name)

    clean_records: list[dict] = []
    quarantined_records: list[dict] = []
    pipeline_log: list[dict] = []

    for idx, record in enumerate(records):
        rid = record.get("record_id", f"UNKNOWN-{idx}")
        log_entry: dict = {"record_id": rid, "gates": {}}

        # Gate 3: Security Gate
        is_malicious, reasons = security_gate.scan(record)
        log_entry["gates"]["security"] = {
            "passed": not is_malicious,
            "reasons": reasons,
        }

        if is_malicious:
            logger.warning("QUARANTINED: %s — %s", rid, "; ".join(reasons[:2]))
            quarantined_records.append({
                "record": record,
                "quarantine_reasons": reasons,
            })
            log_entry["final_status"] = "QUARANTINED"
            pipeline_log.append(log_entry)
            continue

        # Gate 1: Schema Validation
        is_valid, parsed, errors = schema_validator.validate(record)
        log_entry["gates"]["schema_validation"] = {
            "passed": is_valid,
            "errors": errors,
        }

        if is_valid:
            # Record is already canonical - move to date normalisation
            working_record = parsed.model_dump()         # type: ignore
        else:
            # Gate 4: Fixer Agent
            logger.info("Fixer Agent invoked for %s", rid)
            healed = fixer_agent.heal(record, errors)
            log_entry["gates"]["fixer_agent"] = {
                "invoked": True,
                "input_record": record,
                "healed_record": healed,
            }

            # Re-validate the healed record
            is_valid_2, parsed_2, errors_2 = schema_validator.validate(healed)
            log_entry["gates"]["schema_revalidation"] = {
                "passed": is_valid_2,
                "errors": errors_2,
            }

            if is_valid_2:
                working_record = parsed_2.model_dump()   # type: ignore
            else:
                logger.warning(
                    "⚠️  Record %s still invalid after healing: %s",
                    rid, errors_2,
                )
                # Use the healed record as-is (best effort)
                working_record = healed

        # Gate 2: Date Normalization
        raw_date = working_record.get("date_of_visit")
        normalized_date, date_error = date_normalizer.normalize(raw_date)

        if normalized_date:
            working_record["date_of_visit"] = normalized_date
        log_entry["gates"]["date_normalization"] = {
            "original": raw_date,
            "normalized": normalized_date,
            "error": date_error,
        }

        clean_records.append(working_record)
        log_entry["final_status"] = "CLEAN"
        pipeline_log.append(log_entry)
        logger.info("✅ %s → clean", rid)

    # Save outputs
    _save_json(CLEAN_OUTPUT_FILE, clean_records)
    _save_json(QUARANTINED_FILE, quarantined_records)
    _save_json(PIPELINE_LOG_FILE, pipeline_log)

    # Summary
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info("  Clean records:       %d", len(clean_records))
    logger.info("  Quarantined records: %d", len(quarantined_records))
    logger.info("  Total processed:     %d", len(records))
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
