"""Module A — daily operating range (Open ± ADR) push."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from lib.data import fetch_session_aggregates, get_globex_session_open
from lib.indicators import adr
from lib.market_hours import is_module_a_window, now_et
from lib.telegram import send_error_alert, send_message

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
STATE_PATH = STATE_DIR / "module_a.json"


def _force_run_enabled() -> bool:
    return os.environ.get("FORCE_RUN", "").strip().lower() in ("1", "true", "yes")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"last_push_date": None}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        base = {"last_push_date": None}
        base.update(data)
        return base
    except (json.JSONDecodeError, OSError) as e:
        print(f"Module A: failed to read state {STATE_PATH}, resetting. err={e}")
        return {"last_push_date": None}


def save_state(state: dict) -> None:
    """Atomic write to STATE_PATH."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)

TICKERS = [
    ("NQ=F", "NQ", 2),  # (yfinance ticker, display name, decimals)
    ("YM=F", "YM", 0),
]


def _fmt(value: float, decimals: int) -> str:
    if decimals == 0:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


def compute_levels(ticker: str):
    """Pure computation; returns dict of levels for one ticker."""
    open_time, open_price = get_globex_session_open(ticker)
    # ADR(10) is computed from 5m bars aggregated into Globex daily sessions
    # (Mon 18:00 ET → Tue 17:00 ET = "Tuesday's session", etc.). Sidesteps
    # yfinance daily-bar labelling quirks. Only fully-settled sessions are
    # returned, so the last 10 = the 10 most recent settled trading days.
    sessions = fetch_session_aggregates(ticker, days=30)
    adr_10 = adr(sessions, period=10)

    return {
        "open_time": open_time,
        "open_price": open_price,
        "adr_10": adr_10,
        "upper_full": open_price + adr_10,
        "lower_full": open_price - adr_10,
        "upper_half": open_price + adr_10 / 2,
        "lower_half": open_price - adr_10 / 2,
    }


def format_message(per_ticker: dict) -> str:
    header = (
        f"📊 *NQ/YM 每日操作區間*\n"
        f"🕐 {now_et().strftime('%Y-%m-%d %H:%M ET')}\n"
    )

    sections = []
    for tkr, name, decimals in TICKERS:
        d = per_ticker[tkr]
        open_time_str = d["open_time"].strftime("%Y-%m-%d %H:%M ET")
        sections.append(
            f"*{name} ({open_time_str})*\n"
            f"開盤: `{_fmt(d['open_price'], decimals)}`\n"
            f"ADR(10): `{_fmt(d['adr_10'], decimals)}`\n"
            f"上緣: `{_fmt(d['upper_full'], decimals)}` / "
            f"上半: `{_fmt(d['upper_half'], decimals)}`\n"
            f"下緣: `{_fmt(d['lower_full'], decimals)}` / "
            f"下半: `{_fmt(d['lower_half'], decimals)}`"
        )
    return header + "\n" + "\n\n".join(sections)


def run(send=send_message, persist: bool = True) -> None:
    force = _force_run_enabled()

    if not is_module_a_window():
        if force:
            print(
                f"Module A: outside push window ({now_et().isoformat()}) "
                f"but FORCE_RUN=true, proceeding"
            )
        else:
            print(
                f"Module A: outside push window ({now_et().isoformat()}), exit 0"
            )
            return

    # Per-day dedup — only one push per ET trading day
    state = load_state()
    today_et = now_et().strftime("%Y-%m-%d")
    if state.get("last_push_date") == today_et and not force:
        print(
            f"Module A: already pushed today ({today_et}), skip "
            f"(dedup via state/module_a.json)"
        )
        return

    results = {}
    for tkr, _name, _dec in TICKERS:
        results[tkr] = compute_levels(tkr)

    text = format_message(results)
    send(text)
    print("Module A: message sent")

    state["last_push_date"] = today_et
    if persist:
        save_state(state)


def main() -> int:
    try:
        run()
    except Exception as e:  # noqa: BLE001
        send_error_alert("Module A", e)
        print(f"Module A failed: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
