"""Pure Telegram message formatters shared by alert modules."""
from __future__ import annotations

from datetime import datetime, timedelta


def _fmt_price(value: float, decimals: int) -> str:
    if decimals == 0:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


def format_60m_cross_alert(
    name: str,
    cross_type: str,
    last_cross_ts: datetime,
    close_value: float,
    decimals: int,
) -> str:
    """Format a 60m cross alert using the bar's actual closing time."""
    if cross_type == "golden":
        icon = "🔺"
        label = "黃金交叉"
    elif cross_type == "death":
        icon = "🔻"
        label = "死亡交叉"
    else:
        raise ValueError(f"Unsupported cross type: {cross_type}")

    close_time = last_cross_ts + timedelta(minutes=60)
    return (
        f"{icon} *{name} 60m {label}*\n\n"
        f"收K時間: `{close_time.strftime('%Y-%m-%d %H:%M ET')}`\n"
        f"收盤價: `{_fmt_price(close_value, decimals)}`"
    )


def format_entry_signal_alert(
    name: str,
    active_direction: str,
    pullback_signal_ts: datetime,
) -> str:
    """Format an entry signal without changing the 5m signal timestamp."""
    trend = "上升" if active_direction == "golden" else "下降"
    return (
        f"⭐️ *{name} 進場訊號*\n\n"
        f"60m 主趨勢: {trend}\n"
        f"回檔訊號於: `{pullback_signal_ts.strftime('%Y-%m-%d %H:%M ET')}`"
    )
