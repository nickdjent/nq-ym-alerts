"""Telegram Bot API wrappers."""
from __future__ import annotations

import os

import requests

from lib.market_hours import now_et

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def send_message(text: str, parse_mode: str = "Markdown") -> None:
    """Send a message to the configured Telegram group."""
    token = _env("TELEGRAM_BOT_TOKEN")
    chat_id = _env("TELEGRAM_CHAT_ID")

    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=15)
    if not resp.ok:
        print(f"Telegram send failed: status={resp.status_code} body={resp.text}")
        resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        msg = f"Telegram API returned not-ok: {data}"
        print(msg)
        raise RuntimeError(msg)


def send_error_alert(module_name: str, error: Exception) -> None:
    """Push a formatted error alert; safe to call from exception handlers."""
    err_type = type(error).__name__
    err_msg = str(error)
    if len(err_msg) > 200:
        err_msg = err_msg[:200] + "…"

    text = (
        f"⚠️ *{module_name} 執行異常*\n"
        f"🕐 {now_et().strftime('%Y-%m-%d %H:%M ET')}\n\n"
        f"`{err_type}`: {err_msg}"
    )
    try:
        send_message(text)
    except Exception as send_exc:  # noqa: BLE001
        # Last resort: print so it shows up in workflow logs
        print(f"Failed to send error alert: {send_exc}")
        print(f"Original error: {err_type}: {err_msg}")
