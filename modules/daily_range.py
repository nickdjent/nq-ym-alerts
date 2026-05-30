"""Module A — daily operating range (Open ± ADR) push."""
from __future__ import annotations

import os
import sys

from lib.data import fetch_daily_bars, get_globex_session_open
from lib.indicators import adr
from lib.market_hours import is_module_a_window, now_et
from lib.telegram import send_error_alert, send_message


def _force_run_enabled() -> bool:
    return os.environ.get("FORCE_RUN", "").strip().lower() in ("1", "true", "yes")

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
    daily_df = fetch_daily_bars(ticker, days=30)
    adr_10 = adr(daily_df, period=10)

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


def run(send=send_message) -> None:
    if not is_module_a_window():
        if _force_run_enabled():
            print(
                f"Module A: outside push window ({now_et().isoformat()}) "
                f"but FORCE_RUN=true, proceeding"
            )
        else:
            print(
                f"Module A: outside push window ({now_et().isoformat()}), exit 0"
            )
            return

    results = {}
    for tkr, _name, _dec in TICKERS:
        results[tkr] = compute_levels(tkr)

    text = format_message(results)
    send(text)
    print("Module A: message sent")


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
