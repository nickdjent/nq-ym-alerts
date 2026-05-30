"""
Local dry-run for each module. Does NOT push to Telegram.

Usage:
    python tests/test_local.py daily_range
    python tests/test_local.py ema_cross_60m
    python tests/test_local.py exhaustion_signal

For Module A/B, ignores window/market-hours gating so you always get output.
For Module C, also runs without persisting state (in-memory only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make project root importable when invoked as `python tests/test_local.py …`
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib import telegram as telegram_mod  # noqa: E402
from lib.data import fetch_daily_bars, fetch_intraday_bars  # noqa: E402
from lib.indicators import adr, detect_cross, ema  # noqa: E402
from lib.market_hours import now_et  # noqa: E402


def _captured_send(text: str, parse_mode: str = "Markdown") -> None:
    print("\n========== [DRY-RUN TELEGRAM] ==========")
    print(text)
    print("========== [END] ==========\n")


def _patch_telegram():
    telegram_mod.send_message = _captured_send  # type: ignore[assignment]
    # Make error alerts also just print
    def _captured_err(module_name, error):
        print(f"[DRY-RUN ERROR ALERT] {module_name}: {type(error).__name__}: {error}")
    telegram_mod.send_error_alert = _captured_err  # type: ignore[assignment]


def run_daily_range():
    _patch_telegram()
    from modules import daily_range

    # Bypass time-window gate
    daily_range.is_module_a_window = lambda *a, **kw: True  # type: ignore[assignment]

    print(f"== Module A dry-run @ {now_et().isoformat()} ==")
    for tkr, name, decimals in daily_range.TICKERS:
        print(f"\n--- {name} ({tkr}) ---")
        levels = daily_range.compute_levels(tkr)
        print(f"  open_time : {levels['open_time'].isoformat()}")
        print(f"  open_price: {levels['open_price']}")
        print(f"  ADR(10)   : {levels['adr_10']}")
        print(f"  upper_full: {levels['upper_full']}")
        print(f"  upper_half: {levels['upper_half']}")
        print(f"  lower_half: {levels['lower_half']}")
        print(f"  lower_full: {levels['lower_full']}")

    daily_range.run(send=_captured_send)


def run_ema_cross_60m():
    _patch_telegram()
    from modules import ema_cross_60m

    ema_cross_60m.is_market_open = lambda *a, **kw: True  # type: ignore[assignment]
    print(f"== Module B dry-run @ {now_et().isoformat()} ==")
    for tkr, name, dec in ema_cross_60m.TICKERS:
        print(f"\n--- {name} ({tkr}) ---")
        df = fetch_intraday_bars(tkr, "60m", "30d")
        print(f"  60m bars: {len(df)}")
        if not df.empty:
            print(f"  latest bar: {df.index[-1]}  close={df['Close'].iloc[-1]}")
            df = df.copy()
            df["ema5"] = ema(df["Close"], 5)
            df["ema10"] = ema(df["Close"], 10)
            crosses = detect_cross(df["ema5"], df["ema10"])
            print(f"  total crosses: {len(crosses)}")
            if not crosses.empty:
                print(f"  last cross: {crosses.index[-1]} -> {crosses.iloc[-1]['cross_type']}")
        ema_cross_60m.check_ticker(tkr, name, dec, send=_captured_send)


def run_exhaustion_signal():
    _patch_telegram()
    from modules import exhaustion_signal

    exhaustion_signal.is_market_open = lambda *a, **kw: True  # type: ignore[assignment]

    print(f"== Module C dry-run @ {now_et().isoformat()} ==")
    for tkr, name in exhaustion_signal.TICKERS:
        print(f"\n--- {name} ({tkr}) ---")
        # Show inputs
        df60 = fetch_intraday_bars(tkr, "60m", "30d")
        df5 = fetch_intraday_bars(tkr, "5m", "5d")
        print(f"  60m bars: {len(df60)}  5m bars: {len(df5)}")
        if not df60.empty:
            df60 = df60.copy()
            df60["ema5"] = ema(df60["Close"], 5)
            df60["ema10"] = ema(df60["Close"], 10)
            c60 = detect_cross(df60["ema5"], df60["ema10"])
            print(f"  60m crosses: {len(c60)}")
            if not c60.empty:
                print(f"    last 60m cross: {c60.index[-1]} {c60.iloc[-1]['cross_type']}")
        if not df5.empty:
            tmp = df5.copy()
            tmp["ema5"] = ema(tmp["Close"], 5)
            tmp["ema10"] = ema(tmp["Close"], 10)
            c5 = detect_cross(tmp["ema5"], tmp["ema10"])
            print(f"  5m crosses : {len(c5)}")
            if not c5.empty:
                print(f"    last 5m cross : {c5.index[-1]} {c5.iloc[-1]['cross_type']}")
            print(f"  latest 5m bar : {df5.index[-1]}")

        new_state = exhaustion_signal.process_ticker(tkr, name, send=_captured_send)
        print("  resulting state:")
        print(json.dumps(new_state, indent=2, ensure_ascii=False))


COMMANDS = {
    "daily_range": run_daily_range,
    "ema_cross_60m": run_ema_cross_60m,
    "exhaustion_signal": run_exhaustion_signal,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"Available: {', '.join(COMMANDS)}")
        return 2
    COMMANDS[sys.argv[1]]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
