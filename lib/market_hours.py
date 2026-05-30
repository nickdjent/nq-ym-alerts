"""Market hours helpers for CME E-mini futures (ET timezone)."""
from __future__ import annotations

from datetime import datetime, time, timedelta

import pytz

ET_TZ = pytz.timezone("US/Eastern")


def now_et() -> datetime:
    """Current ET time, timezone-aware."""
    return datetime.now(ET_TZ)


def is_market_open(now: datetime | None = None) -> bool:
    """
    CME E-mini futures session:
      - Open: Sunday 18:00 ET ~ Friday 17:00 ET
      - Daily break: 17:00 ~ 18:00 ET
      - Closed: Friday 17:00 ~ Sunday 18:00
    """
    if now is None:
        now = now_et()
    if now.tzinfo is None:
        now = ET_TZ.localize(now)
    else:
        now = now.astimezone(ET_TZ)

    weekday = now.weekday()  # Monday=0, Sunday=6
    t = now.time()

    # Saturday: fully closed
    if weekday == 5:
        return False
    # Sunday: open from 18:00
    if weekday == 6:
        return t >= time(18, 0)
    # Friday: open until 17:00
    if weekday == 4:
        return t < time(17, 0)
    # Mon-Thu: closed during 17:00-18:00 daily break
    if time(17, 0) <= t < time(18, 0):
        return False
    return True


def is_module_a_window(now: datetime | None = None) -> bool:
    """
    Module A push window:
      - Sunday ~ Thursday ET
      - 18:00 ~ 18:15 ET (cron jitter buffer)
    """
    if now is None:
        now = now_et()
    if now.tzinfo is None:
        now = ET_TZ.localize(now)
    else:
        now = now.astimezone(ET_TZ)

    weekday = now.weekday()  # Mon=0 ... Sun=6
    # Sunday (6) or Mon-Thu (0..3)
    if weekday not in (6, 0, 1, 2, 3):
        return False

    t = now.time()
    return time(18, 0) <= t <= time(18, 15)


def previous_session_open_datetime(now: datetime | None = None) -> datetime:
    """
    Returns the most recent Globex session open datetime (ET).
    Defined as today's 18:00 ET if now >= today 18:00, else yesterday 18:00 ET.
    Note: handles Saturday by stepping back to Friday's session boundary,
    but in practice the Sunday open is at 18:00 ET (no Saturday session).
    """
    if now is None:
        now = now_et()
    if now.tzinfo is None:
        now = ET_TZ.localize(now)
    else:
        now = now.astimezone(ET_TZ)

    today_18 = ET_TZ.localize(datetime.combine(now.date(), time(18, 0)))
    if now >= today_18:
        candidate = today_18
    else:
        prev_date = (now - timedelta(days=1)).date()
        candidate = ET_TZ.localize(datetime.combine(prev_date, time(18, 0)))

    # If candidate falls on Saturday (no session), step back to Friday 18:00
    # is not valid either — Friday session ends 17:00. The "previous session open"
    # would actually be Thursday 18:00. But Module A only runs Sun-Thu so this
    # path is defensive.
    while candidate.weekday() == 5:  # Saturday
        candidate -= timedelta(days=1)
    return candidate
