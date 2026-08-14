# Changelog

## 2026-08-14

### Changed

- 將 Module B 與 Module C 的 Telegram 文字組裝抽至純函式 formatter。
- Module B 移除發送時間與 EMA 行，並改為顯示真正的 60m 收 K 時間（交叉索引加 60 分鐘）；死亡交叉圖示改為 `🔻`。
- Module C 移除發送時間與主趨勢 `since`，只顯示上升/下降及原始 5m 回檔訊號時間。
- 保留既有 NQ 兩位小數、YM 整數的收盤價格式。

### Verified

- `python3 -m unittest tests.test_telegram_formatters`：4 個離線精確輸出測試通過。
- `python3 -m compileall -q modules tests`：語法檢查通過。
- `git diff --check`：未發現空白格式錯誤。
