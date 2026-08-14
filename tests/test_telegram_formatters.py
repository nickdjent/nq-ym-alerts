"""Offline exact-output tests for Telegram alert text."""
from __future__ import annotations

from datetime import datetime
import unittest

import pytz

from modules.telegram_formatters import (
    format_60m_cross_alert,
    format_entry_signal_alert,
)


ET = pytz.timezone("US/Eastern")


class TelegramFormatterTests(unittest.TestCase):
    def test_nq_golden_cross_uses_60m_bar_close_time(self) -> None:
        text = format_60m_cross_alert(
            "NQ",
            "golden",
            ET.localize(datetime(2026, 8, 12, 21, 0)),
            29857.25,
            2,
        )

        self.assertEqual(
            text,
            "🔺 *NQ 60m 黃金交叉*\n\n"
            "收K時間: `2026-08-12 22:00 ET`\n"
            "收盤價: `29,857.25`",
        )
        self.assertNotIn("🕐", text)
        self.assertNotIn("EMA5", text)
        self.assertNotIn("EMA10", text)
        self.assertNotIn("K 棒時間", text)

    def test_nq_death_cross_uses_new_icon_and_60m_bar_close_time(self) -> None:
        text = format_60m_cross_alert(
            "NQ",
            "death",
            ET.localize(datetime(2026, 8, 12, 18, 0)),
            29797.75,
            2,
        )

        self.assertEqual(
            text,
            "🔻 *NQ 60m 死亡交叉*\n\n"
            "收K時間: `2026-08-12 19:00 ET`\n"
            "收盤價: `29,797.75`",
        )
        self.assertNotIn("🕐", text)
        self.assertNotIn("EMA5", text)
        self.assertNotIn("EMA10", text)

    def test_ym_entry_signal_preserves_5m_pullback_time(self) -> None:
        text = format_entry_signal_alert(
            "YM",
            "death",
            ET.localize(datetime(2026, 8, 13, 12, 30)),
        )

        self.assertEqual(
            text,
            "⭐️ *YM 進場訊號*\n\n"
            "60m 主趨勢: 下降\n"
            "回檔訊號於: `2026-08-13 12:30 ET`",
        )
        self.assertNotIn("🕐", text)
        self.assertNotIn("since", text)

    def test_existing_nq_and_ym_price_precision_is_preserved(self) -> None:
        nq_text = format_60m_cross_alert(
            "NQ",
            "golden",
            ET.localize(datetime(2026, 8, 12, 21, 0)),
            29857.2,
            2,
        )
        ym_text = format_60m_cross_alert(
            "YM",
            "golden",
            ET.localize(datetime(2026, 8, 12, 21, 0)),
            44123.6,
            0,
        )

        self.assertIn("收盤價: `29,857.20`", nq_text)
        self.assertIn("收盤價: `44,124`", ym_text)


if __name__ == "__main__":
    unittest.main()
