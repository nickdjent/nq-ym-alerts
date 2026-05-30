"""Technical indicators."""
from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average using pandas ewm(adjust=False)."""
    return series.ewm(span=period, adjust=False).mean()


def detect_cross(short_ema: pd.Series, long_ema: pd.Series) -> pd.DataFrame:
    """
    Detect golden/death crosses between two EMAs.

    Returns DataFrame indexed by timestamp of the cross bar, with column
    `cross_type` in {"golden", "death"}.

    golden: prev short <= prev long AND curr short > curr long
    death:  prev short >= prev long AND curr short < curr long
    """
    if len(short_ema) < 2 or len(long_ema) < 2:
        return pd.DataFrame(columns=["cross_type"])

    aligned = pd.concat([short_ema, long_ema], axis=1).dropna()
    aligned.columns = ["short", "long"]
    if len(aligned) < 2:
        return pd.DataFrame(columns=["cross_type"])

    prev_short = aligned["short"].shift(1)
    prev_long = aligned["long"].shift(1)

    golden = (prev_short <= prev_long) & (aligned["short"] > aligned["long"])
    death = (prev_short >= prev_long) & (aligned["short"] < aligned["long"])

    rows = []
    for ts in aligned.index:
        if bool(golden.loc[ts]):
            rows.append((ts, "golden"))
        elif bool(death.loc[ts]):
            rows.append((ts, "death"))

    if not rows:
        return pd.DataFrame(columns=["cross_type"])

    out = pd.DataFrame(rows, columns=["timestamp", "cross_type"]).set_index(
        "timestamp"
    )
    return out


def adr(daily_df: pd.DataFrame, period: int = 10) -> float:
    """
    Average Daily Range = mean(High - Low) over the most recent `period`
    closed daily bars. Assumes daily_df has already dropped today's open bar.
    """
    if len(daily_df) < period:
        raise ValueError(
            f"Need at least {period} daily bars for ADR, got {len(daily_df)}"
        )
    window = daily_df.iloc[-period:]
    return float((window["High"] - window["Low"]).mean())
