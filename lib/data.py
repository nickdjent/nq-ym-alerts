"""yfinance wrappers — return ET-localized pandas DataFrames."""
from __future__ import annotations

import time as _time
from datetime import datetime, time, timedelta

import pandas as pd
import pytz
import yfinance as yf

from lib.market_hours import ET_TZ, now_et, previous_session_open_datetime

_INTERVAL_TO_TIMEDELTA = {
    "1m": timedelta(minutes=1),
    "2m": timedelta(minutes=2),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "60m": timedelta(minutes=60),
    "90m": timedelta(minutes=90),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
}


def _normalize_ticker(ticker: str) -> str:
    """Normalize ticker casing (NQ=F / YM=F) — yfinance is case-sensitive on suffix."""
    return ticker.strip().upper()


def _retry(callable_, *, attempts: int = 3, delay: float = 5.0):
    """Run a no-arg callable with retries."""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return callable_()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if i < attempts - 1:
                _time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _to_et_index(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure DataFrame index is tz-aware in US/Eastern."""
    if df.empty:
        return df
    idx = df.index
    if idx.tz is None:
        df.index = idx.tz_localize("UTC").tz_convert(ET_TZ)
    else:
        df.index = idx.tz_convert(ET_TZ)
    return df


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance sometimes returns MultiIndex columns; collapse to single level."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def fetch_daily_bars(ticker: str, days: int = 30) -> pd.DataFrame:
    """
    Settled daily futures bars. Columns: Open, High, Low, Close, Volume.

    yfinance returns daily futures bars indexed by a naive midnight Timestamp
    whose date is the trading-day label in ET (e.g., `2026-05-29 00:00` is
    Friday May 29's full session, which settles Fri 17:00 ET). We tz-localize
    that to ET — NOT tz_convert from UTC, which would shift the date by one.

    The last bar is dropped only if its settle time (date + 17:00 ET) is
    still in the future, i.e. the session hasn't closed yet.
    """
    ticker = _normalize_ticker(ticker)
    period = f"{max(days + 5, 10)}d"

    def _do():
        df = yf.download(
            ticker,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            raise RuntimeError(f"yfinance returned empty daily bars for {ticker}")
        return df

    df = _retry(_do)
    df = _flatten_columns(df)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.dropna(inplace=True)

    if df.empty:
        return df

    # Localize (don't convert) — preserves the trading-day date label
    if df.index.tz is None:
        df.index = df.index.tz_localize(ET_TZ)
    else:
        df.index = df.index.tz_convert(ET_TZ)

    # Drop the last bar only if it hasn't settled yet (futures settle 17:00 ET)
    now = now_et()
    last_date = df.index[-1].date()
    settle_time = ET_TZ.localize(datetime.combine(last_date, time(17, 0)))
    if now < settle_time:
        df = df.iloc[:-1]

    return df.tail(days)


def fetch_intraday_bars(
    ticker: str, interval: str, period: str = "5d"
) -> pd.DataFrame:
    """
    Intraday bars with the last (not-yet-closed) bar dropped.
    Columns: Open, High, Low, Close, Volume. ET-tz index.
    """
    ticker = _normalize_ticker(ticker)
    if interval not in _INTERVAL_TO_TIMEDELTA:
        raise ValueError(f"Unsupported interval: {interval}")

    def _do():
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            raise RuntimeError(
                f"yfinance returned empty intraday bars for {ticker} {interval}"
            )
        return df

    df = _retry(_do)
    df = _flatten_columns(df)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.dropna(inplace=True)
    df = _to_et_index(df)

    if df.empty:
        return df

    # Drop the last bar if it hasn't closed yet:
    # close_time = bar timestamp + interval; if close_time > now → not closed
    delta = _INTERVAL_TO_TIMEDELTA[interval]
    now = now_et()
    last_close = df.index[-1].to_pydatetime() + delta
    if last_close > now:
        df = df.iloc[:-1]

    return df


def fetch_session_aggregates(
    ticker: str, days: int = 30, period: str = "60d"
) -> pd.DataFrame:
    """
    Aggregate 5m intraday bars into Globex daily sessions for futures.

    Each row = one trading day's session in the standard futures convention:
        session_start = (D-1 calendar day) 18:00 ET
        session_end   = D day 17:00 ET   (= settlement)

    For Mon D, this gives session_start = Sun 18:00 ET (Sunday Globex re-open).
    Saturdays have no session and are skipped. In-progress sessions (where
    `now < session_end`) are excluded — so only fully settled sessions appear.

    Returns DataFrame with columns Open, High, Low, Close, Volume, indexed by
    `session_end` timestamp (tz-aware ET, D at 17:00). Most recent `days` rows.

    This is the preferred input for Module A's ADR — it sidesteps yfinance's
    daily-bar labeling quirks (where the "Tue Jun 2" daily bar actually tracks
    the still-forming Wed session starting Tue 18:00 ET).
    """
    df5 = fetch_intraday_bars(ticker, interval="5m", period=period)
    if df5.empty:
        return df5

    now = now_et()
    all_dates = sorted({ts.date() for ts in df5.index})
    if not all_dates:
        return pd.DataFrame()

    earliest, latest = all_dates[0], all_dates[-1]

    rows = []
    d = earliest
    while d <= latest:
        if d.weekday() < 5:  # Mon-Fri (skip Sat/Sun as session-end dates)
            session_start = ET_TZ.localize(
                datetime.combine(d - timedelta(days=1), time(18, 0))
            )
            session_end = ET_TZ.localize(datetime.combine(d, time(17, 0)))

            if now >= session_end:  # only fully-settled sessions
                mask = (df5.index >= session_start) & (df5.index < session_end)
                sub = df5[mask]
                if not sub.empty:
                    vol = (
                        float(sub["Volume"].sum())
                        if "Volume" in sub.columns
                        else 0.0
                    )
                    rows.append(
                        {
                            "Date": session_end,
                            "Open": float(sub["Open"].iloc[0]),
                            "High": float(sub["High"].max()),
                            "Low": float(sub["Low"].min()),
                            "Close": float(sub["Close"].iloc[-1]),
                            "Volume": vol,
                        }
                    )
        d += timedelta(days=1)

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows).set_index("Date")
    return out.tail(days)


def get_globex_session_open(ticker: str) -> tuple[datetime, float]:
    """
    Most recent Globex session open: ET 18:00 5m bar's Open price.
    Returns (open_time_et, open_price).
    """
    ticker = _normalize_ticker(ticker)
    session_open_dt = previous_session_open_datetime()

    # Pull enough 5m data to be sure we include the session open bar.
    df = fetch_intraday_bars(ticker, interval="5m", period="5d")
    if df.empty:
        raise RuntimeError(f"No 5m data available for {ticker}")

    # Find the 5m bar whose timestamp == session_open_dt (ET 18:00)
    # tolerate small differences — yfinance bar timestamps align to interval boundary
    target = session_open_dt
    # Exact match first
    match = df.index[df.index == target]
    if len(match) == 0:
        # Fallback: find the bar with the same date and hour=18, minute=0
        mask = (
            (df.index.date == target.date())
            & (df.index.hour == 18)
            & (df.index.minute == 0)
        )
        match = df.index[mask]

    if len(match) == 0:
        # Last resort: take the latest bar at-or-before target
        before = df.index[df.index <= target]
        if len(before) == 0:
            raise RuntimeError(
                f"Could not locate Globex session open bar for {ticker} at {target}"
            )
        bar_ts = before[-1]
    else:
        bar_ts = match[-1]

    open_price = float(df.loc[bar_ts, "Open"])
    return bar_ts.to_pydatetime(), open_price
