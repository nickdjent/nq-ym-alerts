"""Module C — buy-the-dip entry signal.

In a 60m main trend, push exactly one alert per cycle when a 5m REVERSE
cross occurs within 3 hours of the 60m cross.
  60m golden + 5m death  → 進場訊號 / 建議方向: 做多 (buy the pullback)
  60m death  + 5m golden → 進場訊號 / 建議方向: 做空 (sell the bounce)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from lib.data import fetch_intraday_bars
from lib.indicators import detect_cross, ema
from lib.market_hours import ET_TZ, is_market_open, now_et
from lib.telegram import send_error_alert, send_message


def _force_run_enabled() -> bool:
    return os.environ.get("FORCE_RUN", "").strip().lower() in ("1", "true", "yes")

TICKERS = [
    ("NQ=F", "NQ"),
    ("YM=F", "YM"),
]

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
WINDOW = timedelta(hours=3)
MIN_BARS_60M = 50
MIN_BARS_5M = 30


def _ticker_to_state_path(ticker: str) -> Path:
    safe = ticker.split("=")[0].lower()  # "NQ=F" -> "nq"
    return STATE_DIR / f"{safe}_module_c.json"


def _empty_state() -> dict:
    return {
        "active_60m_cross": None,
        "alerted_entry": False,
    }


def load_state(ticker: str) -> dict:
    path = _ticker_to_state_path(ticker)
    if not path.exists():
        return _empty_state()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all keys present (forward compat)
        base = _empty_state()
        base.update(data)
        return base
    except (json.JSONDecodeError, OSError) as e:
        print(f"Module C: failed to read state {path}, resetting. err={e}")
        return _empty_state()


def save_state(ticker: str, state: dict) -> None:
    """Atomic write: write to .tmp then os.rename over target."""
    path = _ticker_to_state_path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _parse_iso_et(s: str) -> datetime:
    """Parse ISO 8601 string back to ET tz-aware datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = ET_TZ.localize(dt)
    else:
        dt = dt.astimezone(ET_TZ)
    return dt


def _dir_to_chinese(direction: str) -> str:
    return "上升" if direction == "golden" else "下降"


def process_ticker(ticker: str, name: str, send=send_message) -> dict:
    """Run the full state machine for one ticker; returns updated state."""
    state = load_state(ticker)

    df_60m = fetch_intraday_bars(ticker, "60m", "30d")
    df_5m = fetch_intraday_bars(ticker, "5m", "5d")

    if len(df_60m) < MIN_BARS_60M:
        print(
            f"Module C ({name}): 60m bars only {len(df_60m)}, "
            f"need >= {MIN_BARS_60M}, skip"
        )
        return state
    if len(df_5m) < MIN_BARS_5M:
        print(
            f"Module C ({name}): 5m bars only {len(df_5m)}, "
            f"need >= {MIN_BARS_5M}, skip"
        )
        return state

    # (c) Detect a new 60m cross
    df_60m = df_60m.copy()
    df_60m["ema5"] = ema(df_60m["Close"], 5)
    df_60m["ema10"] = ema(df_60m["Close"], 10)
    crosses_60m = detect_cross(df_60m["ema5"], df_60m["ema10"])

    if not crosses_60m.empty:
        last_60m_cross_ts: pd.Timestamp = crosses_60m.index[-1]
        last_60m_dir = crosses_60m.iloc[-1]["cross_type"]
        last_60m_dt = last_60m_cross_ts.to_pydatetime()

        prev_ts = None
        if state["active_60m_cross"] is not None:
            prev_ts = _parse_iso_et(state["active_60m_cross"]["timestamp"])

        if prev_ts is None or last_60m_dt > prev_ts:
            print(
                f"Module C ({name}): new 60m {last_60m_dir} cross at "
                f"{last_60m_dt.isoformat()}, resetting alert flag"
            )
            state["active_60m_cross"] = {
                "direction": last_60m_dir,
                "timestamp": last_60m_dt.isoformat(),
            }
            state["alerted_entry"] = False

    # (d) Skip if no active cross or window expired
    if state["active_60m_cross"] is None:
        print(f"Module C ({name}): no active 60m cross")
        return state

    active_dir = state["active_60m_cross"]["direction"]
    active_ts = _parse_iso_et(state["active_60m_cross"]["timestamp"])
    now = now_et()
    window_end = active_ts + WINDOW

    if now > window_end:
        print(
            f"Module C ({name}): 3h window expired "
            f"(active {active_ts.isoformat()}, now {now.isoformat()})"
        )
        return state

    # (e) Detect 5m cross within window, only if it happened on latest closed bar
    df_5m = df_5m.copy()
    df_5m["ema5"] = ema(df_5m["Close"], 5)
    df_5m["ema10"] = ema(df_5m["Close"], 10)
    crosses_5m = detect_cross(df_5m["ema5"], df_5m["ema10"])
    if crosses_5m.empty:
        print(f"Module C ({name}): no 5m crosses found")
        return state

    latest_5m_bar_ts: pd.Timestamp = df_5m.index[-1]
    latest_5m_cross_ts: pd.Timestamp = crosses_5m.index[-1]

    # Must equal the latest closed 5m bar
    if latest_5m_cross_ts != latest_5m_bar_ts:
        print(
            f"Module C ({name}): last 5m cross {latest_5m_cross_ts} != "
            f"latest 5m bar {latest_5m_bar_ts}, no fresh signal"
        )
        return state

    # Must be after the active 60m cross and within window
    cross_dt = latest_5m_cross_ts.to_pydatetime()
    if cross_dt <= active_ts:
        print(
            f"Module C ({name}): 5m cross {cross_dt} not after "
            f"active 60m cross {active_ts}"
        )
        return state
    if cross_dt > window_end:
        print(
            f"Module C ({name}): 5m cross {cross_dt} outside 3h window "
            f"(end {window_end})"
        )
        return state

    cross_5m_dir = crosses_5m.iloc[-1]["cross_type"]

    # Entry signal fires only on 5m REVERSE cross (buy-the-dip strategy)
    if cross_5m_dir == active_dir:
        print(
            f"Module C ({name}): 5m same-direction cross ignored "
            f"(only reverse triggers entry signal)"
        )
        return state

    if state["alerted_entry"]:
        print(
            f"Module C ({name}): entry signal already alerted for "
            f"this 60m cross, skip"
        )
        return state

    text = (
        f"⚠️ *{name} 進場訊號*\n"
        f"🕐 {now_et().strftime('%Y-%m-%d %H:%M ET')}\n\n"
        f"60m 主趨勢: {_dir_to_chinese(active_dir)} "
        f"(since {active_ts.strftime('%Y-%m-%d %H:%M ET')})\n"
        f"回檔訊號於: `{cross_dt.strftime('%Y-%m-%d %H:%M ET')}`"
    )
    send(text)
    state["alerted_entry"] = True
    print(f"Module C ({name}): entry signal alert sent")
    return state


def run(send=send_message, persist: bool = True) -> None:
    if not is_market_open():
        if _force_run_enabled():
            print(
                f"Module C: market closed ({now_et().isoformat()}) "
                f"but FORCE_RUN=true, proceeding"
            )
        else:
            print(f"Module C: market closed ({now_et().isoformat()}), exit 0")
            return

    for tkr, name in TICKERS:
        new_state = process_ticker(tkr, name, send=send)
        if persist:
            save_state(tkr, new_state)


def main() -> int:
    try:
        run()
    except Exception as e:  # noqa: BLE001
        send_error_alert("Module C", e)
        print(f"Module C failed: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
