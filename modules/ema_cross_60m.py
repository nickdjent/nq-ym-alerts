"""Module B — 60m EMA5/10 golden/death cross alerts (stateless)."""
from __future__ import annotations

import sys

from lib.data import fetch_intraday_bars
from lib.indicators import detect_cross, ema
from lib.market_hours import is_market_open, now_et
from lib.telegram import send_error_alert, send_message

TICKERS = [
    ("NQ=F", "NQ", 2),
    ("YM=F", "YM", 0),
]

MIN_BARS = 50


def _fmt(value: float, decimals: int) -> str:
    if decimals == 0:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


def check_ticker(ticker: str, name: str, decimals: int, send=send_message) -> bool:
    """Return True if an alert was sent."""
    df = fetch_intraday_bars(ticker, interval="60m", period="30d")
    if len(df) < MIN_BARS:
        print(
            f"Module B ({name}): only {len(df)} bars, need >= {MIN_BARS}, skip"
        )
        return False

    df = df.copy()
    df["ema5"] = ema(df["Close"], 5)
    df["ema10"] = ema(df["Close"], 10)
    crosses = detect_cross(df["ema5"], df["ema10"])

    if crosses.empty:
        print(f"Module B ({name}): no crosses detected")
        return False

    last_cross_ts = crosses.index[-1]
    latest_bar_ts = df.index[-1]
    if last_cross_ts != latest_bar_ts:
        print(
            f"Module B ({name}): last cross {last_cross_ts} != latest bar "
            f"{latest_bar_ts}, no fresh signal"
        )
        return False

    cross_type = crosses.iloc[-1]["cross_type"]
    close_val = float(df.loc[latest_bar_ts, "Close"])
    ema5_val = float(df.loc[latest_bar_ts, "ema5"])
    ema10_val = float(df.loc[latest_bar_ts, "ema10"])

    if cross_type == "golden":
        title = f"⭐️ *{name} 60m 黃金交叉*"
        arrow = "⬆"
    else:
        title = f"💀 *{name} 60m 死亡交叉*"
        arrow = "⬇"

    text = (
        f"{title}\n"
        f"🕐 {now_et().strftime('%Y-%m-%d %H:%M ET')}\n\n"
        f"K 棒時間: `{latest_bar_ts.strftime('%Y-%m-%d %H:%M ET')}`\n"
        f"收盤價: `{_fmt(close_val, decimals)}`\n"
        f"EMA5: `{_fmt(ema5_val, decimals)}` {arrow} "
        f"EMA10: `{_fmt(ema10_val, decimals)}`"
    )
    send(text)
    print(f"Module B ({name}): {cross_type} cross alert sent")
    return True


def run(send=send_message) -> None:
    if not is_market_open():
        print(f"Module B: market closed ({now_et().isoformat()}), exit 0")
        return
    for tkr, name, dec in TICKERS:
        check_ticker(tkr, name, dec, send=send)


def main() -> int:
    try:
        run()
    except Exception as e:  # noqa: BLE001
        send_error_alert("Module B", e)
        print(f"Module B failed: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
