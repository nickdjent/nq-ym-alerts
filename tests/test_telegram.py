"""
Manual Telegram smoke test. Reads .env from project root, pushes one message.

Usage:
    python tests/test_telegram.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def main():
    _load_dotenv(ROOT / ".env")

    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID"):
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID. Put them in .env "
              "or export them before running.")
        return 2

    from lib.market_hours import now_et
    from lib.telegram import send_message

    ts = now_et().strftime("%Y-%m-%d %H:%M:%S ET")
    send_message(f"📣 Telegram 連線測試 - {ts}")
    print(f"Sent test message at {ts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
