"""
Business calendar utilities for BidChip.

Business clock definition:
  - Operating hours: Monday 06:00 – Friday 17:00 America/New_York
  - Weekends (Saturday, Sunday) are fully excluded
  - US business holidays stored in core.models.BusinessHoliday (is_active=True)
    are excluded

Public API:
  add_running_time(start, duration_minutes) -> datetime
    Returns the wall-clock datetime at which `duration_minutes` of running
    business-clock time has elapsed after `start`.
"""

from __future__ import annotations

import datetime
from typing import Optional

import pytz

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUSINESS_TZ = pytz.timezone("America/New_York")

# Business clock: Mon (0) – Fri (4), 06:00 – 17:00 ET
CLOCK_OPEN_HOUR = 6    # 06:00 ET
CLOCK_CLOSE_HOUR = 17  # 17:00 ET

# Weekday indices where the clock runs (Monday=0 … Friday=4)
BUSINESS_WEEKDAYS = frozenset(range(5))  # 0–4

# Minutes of running time available per business day
MINUTES_PER_DAY = (CLOCK_CLOSE_HOUR - CLOCK_OPEN_HOUR) * 60  # 660


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_holiday_dates() -> frozenset[datetime.date]:
    """
    Return the set of active business holiday dates from the database.
    Results are NOT cached here — callers that need caching should wrap this
    function themselves (e.g. with Django's cache framework).
    """
    try:
        from core.models import BusinessHoliday

        return frozenset(
            BusinessHoliday.objects.filter(is_active=True).values_list("date", flat=True)
        )
    except Exception:
        # If the DB is unavailable (e.g. during tests without migrations),
        # return an empty set so the clock still functions.
        return frozenset()


def _is_business_day(date: datetime.date, holidays: frozenset[datetime.date]) -> bool:
    """Return True if `date` is a weekday that is not a holiday."""
    return date.weekday() in BUSINESS_WEEKDAYS and date not in holidays


def _clock_open(date: datetime.date) -> datetime.datetime:
    """Return the clock-open datetime for a given date (naive ET)."""
    return datetime.datetime(date.year, date.month, date.day, CLOCK_OPEN_HOUR, 0, 0)


def _clock_close(date: datetime.date) -> datetime.datetime:
    """Return the clock-close datetime for a given date (naive ET)."""
    return datetime.datetime(date.year, date.month, date.day, CLOCK_CLOSE_HOUR, 0, 0)


def _to_et_naive(dt: datetime.datetime) -> datetime.datetime:
    """Convert an aware or naive datetime to a naive America/New_York datetime."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(BUSINESS_TZ)
        return dt.replace(tzinfo=None)
    # Assume already ET if naive
    return dt


def _to_utc_aware(dt_et_naive: datetime.datetime) -> datetime.datetime:
    """Localise a naive ET datetime and convert to UTC-aware."""
    et_aware = BUSINESS_TZ.localize(dt_et_naive, is_dst=None)
    return et_aware.astimezone(pytz.utc)


def _advance_to_next_open(
    dt: datetime.datetime,
    holidays: frozenset[datetime.date],
) -> datetime.datetime:
    """
    Given a naive ET datetime, advance it to the next clock-open moment if it
    currently falls outside business hours.

    Cases handled:
    - Before clock-open on a business day → advance to clock-open same day
    - After clock-close on a business day → advance to clock-open next business day
    - On a weekend or holiday → advance to clock-open next business day
    """
    candidate = dt
    while True:
        date = candidate.date()
        if not _is_business_day(date, holidays):
            # Move to 06:00 the following calendar day and re-check
            candidate = _clock_open(date + datetime.timedelta(days=1))
            continue

        # It's a business day — check the time window
        open_dt = _clock_open(date)
        close_dt = _clock_close(date)

        if candidate < open_dt:
            return open_dt
        if candidate >= close_dt:
            # After close — move to next calendar day
            candidate = _clock_open(date + datetime.timedelta(days=1))
            continue
        # Inside the window
        return candidate


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_running_time(
    start: datetime.datetime,
    duration_minutes: int,
) -> datetime.datetime:
    """
    Compute the datetime at which `duration_minutes` of business-clock running
    time has elapsed after `start`.

    Parameters
    ----------
    start : datetime.datetime
        The starting datetime. May be timezone-aware (any tz) or naive
        (assumed America/New_York).
    duration_minutes : int
        Number of business-clock minutes to add. Must be >= 0.

    Returns
    -------
    datetime.datetime
        The resulting datetime in the same timezone as `start` (or naive ET if
        `start` was naive).

    Notes
    -----
    - Business clock: Mon 06:00 – Fri 17:00 America/New_York
    - Weekends and active BusinessHoliday records are skipped
    - If `start` falls inside a pause (outside business hours), the clock
      starts ticking from the next clock-open moment
    """
    if duration_minutes < 0:
        raise ValueError("duration_minutes must be >= 0")

    original_tz = start.tzinfo  # may be None

    # Work entirely in naive ET throughout
    current = _to_et_naive(start)

    holidays = _get_holiday_dates()

    # Advance to the next open moment if start is outside business hours
    current = _advance_to_next_open(current, holidays)

    remaining = duration_minutes

    while remaining > 0:
        date = current.date()

        # Defensive: ensure we're on a business day (should be after the
        # _advance_to_next_open call above, but re-checked each iteration)
        if not _is_business_day(date, holidays):
            current = _advance_to_next_open(
                _clock_open(date + datetime.timedelta(days=1)), holidays
            )
            continue

        close_dt = _clock_close(date)

        # Minutes remaining in the current session
        minutes_left_today = int((close_dt - current).total_seconds() / 60)

        if remaining <= minutes_left_today:
            current = current + datetime.timedelta(minutes=remaining)
            remaining = 0
        else:
            # Consume the rest of today and move to tomorrow's open
            remaining -= minutes_left_today
            next_day = date + datetime.timedelta(days=1)
            current = _advance_to_next_open(_clock_open(next_day), holidays)

    # Convert result back to original timezone
    if original_tz is not None:
        result_utc = _to_utc_aware(current)
        return result_utc.astimezone(original_tz)
    return current


def is_business_hours(dt: Optional[datetime.datetime] = None) -> bool:
    """
    Return True if `dt` (defaults to now) falls within business hours.
    """
    if dt is None:
        dt = datetime.datetime.now(tz=pytz.utc)
    holidays = _get_holiday_dates()
    naive_et = _to_et_naive(dt)
    date = naive_et.date()
    if not _is_business_day(date, holidays):
        return False
    return _clock_open(date) <= naive_et < _clock_close(date)
