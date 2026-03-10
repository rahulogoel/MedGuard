"""
Gate 2 — Date Normalization.

Converts all date_of_visit values to ISO 8601 format.
Resolves relative dates using the reference date (March 9, 2026).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from dateutil import parser as dateutil_parser

from config import REFERENCE_DATE


def normalize(date_str: str | None) -> tuple[str | None, str | None]:
    """
    Normalize a date string to ISO 8601 (YYYY-MM-DD).

    Returns:
        (normalized_date_or_None, error_or_None)
    """
    if date_str is None:
        return None, "date_of_visit is null"

    cleaned = date_str.strip().lower()

    if not cleaned:
        return None, "date_of_visit is empty"

    # Relative date patterns
    result = _try_relative(cleaned)
    if result is not None:
        return result.isoformat(), None

    # Complex relative ("2 weeks before 2026-03-09")
    result = _try_complex_relative(date_str.strip())
    if result is not None:
        return result.isoformat(), None

    # Standard / non-standard format parsing
    try:
        parsed = dateutil_parser.parse(date_str, dayfirst=False)
        return parsed.date().isoformat(), None
    except (ValueError, OverflowError):
        pass

    return None, f"Unable to parse date: '{date_str}'"


# Relative date helpers

_DAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _try_relative(cleaned: str) -> Optional[date]:
    """Resolve simple relative dates against REFERENCE_DATE."""

    if cleaned == "today":
        return REFERENCE_DATE

    if cleaned == "yesterday":
        return REFERENCE_DATE - timedelta(days=1)

    # "N days ago" or "approx N days ago"
    m = re.match(r"(?:approx(?:imately)?\s+)?(\d+)\s+days?\s+ago", cleaned)
    if m:
        return REFERENCE_DATE - timedelta(days=int(m.group(1)))

    # "N weeks ago" or "approx N weeks ago"
    m = re.match(r"(?:approx(?:imately)?\s+)?(\d+)\s+weeks?\s+ago", cleaned)
    if m:
        return REFERENCE_DATE - timedelta(weeks=int(m.group(1)))

    # "last <dayname>"
    m = re.match(r"last\s+(\w+)", cleaned)
    if m:
        day_name = m.group(1).lower()
        if day_name in _DAY_NAMES:
            target_weekday = _DAY_NAMES[day_name]
            ref_weekday = REFERENCE_DATE.weekday()
            days_back = (ref_weekday - target_weekday) % 7
            if days_back == 0:
                days_back = 7          # "last Tuesday" when ref IS Tuesday
            return REFERENCE_DATE - timedelta(days=days_back)

    return None


def _try_complex_relative(raw: str) -> Optional[date]:
    """
    Handle phrases like "2 weeks before 2026-03-09".
    """
    m = re.match(
        r"(\d+)\s+(days?|weeks?|months?)\s+before\s+(.+)",
        raw, re.IGNORECASE,
    )
    if not m:
        return None

    amount = int(m.group(1))
    unit = m.group(2).lower().rstrip("s")   # "weeks" -> "week"
    anchor_str = m.group(3).strip()

    try:
        anchor = dateutil_parser.parse(anchor_str).date()
    except (ValueError, OverflowError):
        return None

    if unit == "day":
        return anchor - timedelta(days=amount)
    elif unit == "week":
        return anchor - timedelta(weeks=amount)
    elif unit == "month":
        # Approximate: 30 days per month
        return anchor - timedelta(days=amount * 30)

    return None
