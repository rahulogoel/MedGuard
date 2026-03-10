"""
Pipeline configuration — reference date, schema, constants.
"""

from datetime import date
from pathlib import Path


# Paths
BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "raw_dump.json"
OUTPUT_DIR = BASE_DIR / "output"
CLEAN_OUTPUT_FILE = OUTPUT_DIR / "clean_output.json"
QUARANTINED_FILE = OUTPUT_DIR / "quarantined.json"
PIPELINE_LOG_FILE = OUTPUT_DIR / "pipeline_log.json"

# Reference Date
# "Use today's date (March 9, 2026) as the reference point for all relative
# date resolution."
REFERENCE_DATE = date(2026, 3, 9)

# OpenAI
OPENAI_MODEL = "gpt-5.2"
