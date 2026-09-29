"""Posting-slot guards: a late scheduler must still produce a post.

GitHub's cron has fired 4-6h late repeatedly; a 2h staleness limit silently cancelled a
whole day's posts. Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import LATE_LIMIT_HOURS, slot_state  # noqa: E402
from src.approve_bot import IST  # noqa: E402

SLOT = datetime(2026, 9, 29, 10, 0, tzinfo=IST)


def at(hours: float) -> datetime:
    return SLOT + timedelta(hours=hours)


@pytest.mark.parametrize("hours,expected", [
    (-2, "ok"),        # ran early (normal)
    (0, "ok"),
    (0.4, "ok"),       # a few minutes late is normal
    (0.6, "late"),
    (4.3, "late"),     # the real 29 Sep run: used to be skipped, must now generate
    (6.5, "late"),     # worst observed GitHub cron lag
    (11.9, "late"),
    (12.1, "stale"),   # a manual re-run of yesterday's slot
    (48, "stale"),
])
def test_slot_state(hours, expected):
    assert slot_state(SLOT, at(hours), slot_taken=False) == expected


def test_taken_slot_wins_over_lateness():
    assert slot_state(SLOT, at(4.3), slot_taken=True) == "taken"
    assert slot_state(SLOT, at(0), slot_taken=True) == "taken"


def test_limit_covers_observed_cron_lag():
    """Both daily crons must survive the worst lag we have seen (~6.5h)."""
    assert LATE_LIMIT_HOURS >= 8
