"""Module B — 60m EMA5/10 golden/death cross alerts.

Dedup is via per-ticker state: each ticker's latest-alerted cross
timestamp is persisted to state/{nq,ym}_module_b.json. A run pushes
only when the most recent cross has a strictly newer timestamp than
the stored one — so a single cross is alerted exactly once even when
cron lag causes multiple workflow fires close together.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from lib.data import fetch_intraday_bars
from lib.indicators import detect_cross, ema
from lib.market_hours import ET_TZ, is_market_open, now_et
from lib.telegram import send_error_alert, send_message

TICKERS = [
    ("NQ=F", "NQ", 2),
    ("YM=F", "YM", 0),
]

MIN_BARS = 50
# Don't push a cross older than this — defensive against backlog on first
# run / after state reset / extreme cron outages.
MAX_ALERT_AGE = timedelta(hours=2)

STATE_DIR = Path(__file__).resolve().parent.parent / "state"


def _force_run_enabled() -> bool:
    return os.environ.get("FORCE_RUN", "").strip().lower() in ("1", "true", "yes")


def _state_path(ticker: str) -> Path:
    safe = ticker.split("=")[0].lower()  # "NQ=F" -> "nq"
    return STATE_DIR / f"{safe}_module_b.json"


def _parse_iso_et(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = ET_TZ.localize(dt)
    else:
        dt = dt.astimezone(ET_TZ)
    return dt


def load_state(ticker: str) -> dict:
    path = _state_path(ticker)
    if not path.exists():
        return {"last_alerted_cross_ts": None}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        base = {"last_alerted_cross_ts": None}
        base.update(data)
        return base
    except (json.JSONDecodeError, OSError) as e:
        print(f"Module B ({ticker}): failed to read state, resetting. err={e}")
        return {"last_alerted_cross_ts": None}


def save_state(ticker: str, state: dict) -> None:
    """Atomic write."""
    path = _state_path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _fmt(value: float, decimals: int) -> str:
    if decimals == 0:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


def check_ticker(
    ticker: str,
    name: str,
    decimals: int,
    send=send_message,
    persist: bool = True,
) -> bool:
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
    last_cross_dt = last_cross_ts.to_pydatetime()
    cross_type = crosses.iloc[-1]["cross_type"]

    force = _force_run_enabled()
    state = load_state(ticker)
    prev_ts_str = state.get("last_alerted_cross_ts")
    prev_ts = _parse_iso_et(prev_ts_str) if prev_ts_str else None

    # Already alerted this cross?
    if prev_ts is not None and last_cross_dt <= prev_ts and not force:
        print(
            f"Module B ({name}): no new cross since last alert "
            f"({prev_ts.isoformat()})"
        )
        return False

    # Too stale to alert? Seed state so we don't backlog on next run.
    age = now_et() - last_cross_dt
    if age > MAX_ALERT_AGE and not force:
        print(
            f"Module B ({name}): latest cross {last_cross_dt.isoformat()} is "
            f"{age} old (> {MAX_ALERT_AGE}); skip and seed state."
        )
        state["last_alerted_cross_ts"] = last_cross_dt.isoformat()
        if persist:
            save_state(ticker, state)
        return False

    close_val = float(df.loc[last_cross_ts, "Close"])
    ema5_val = float(df.loc[last_cross_ts, "ema5"])
    ema10_val = float(df.loc[last_cross_ts, "ema10"])

    if cross_type == "golden":
        title = f"🔺 *{name} 60m 黃金交叉*"
        arrow = "⬆"
    else:
        title = f"⬇️ *{name} 60m 死亡交叉*"
        arrow = "⬇"

    text = (
        f"{title}\n"
        f"🕐 {now_et().strftime('%Y-%m-%d %H:%M ET')}\n\n"
        f"K 棒時間: `{last_cross_ts.strftime('%Y-%m-%d %H:%M ET')}`\n"
        f"收盤價: `{_fmt(close_val, decimals)}`\n"
        f"EMA5: `{_fmt(ema5_val, decimals)}` {arrow} "
        f"EMA10: `{_fmt(ema10_val, decimals)}`"
    )
    send(text)

    state["last_alerted_cross_ts"] = last_cross_dt.isoformat()
    if persist:
        save_state(ticker, state)
    print(
        f"Module B ({name}): {cross_type} cross alert sent "
        f"(bar={last_cross_dt.isoformat()})"
    )
    return True


def run(send=send_message, persist: bool = True) -> None:
    if not is_market_open():
        if _force_run_enabled():
            print(
                f"Module B: market closed ({now_et().isoformat()}) "
                f"but FORCE_RUN=true, proceeding"
            )
        else:
            print(f"Module B: market closed ({now_et().isoformat()}), exit 0")
            return
    for tkr, name, dec in TICKERS:
        check_ticker(tkr, name, dec, send=send, persist=persist)


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
