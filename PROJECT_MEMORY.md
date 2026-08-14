# Project Memory — NQ/YM Alerts

## 專案目標

以 GitHub Actions 排程執行 NQ/YM 期貨資料檢查，透過 Telegram 發送每日區間、60m EMA 交叉與逢回進場訊號。

## 架構與限制

- `modules/daily_range.py`：Module A 每日操作區間。
- `modules/ema_cross_60m.py`：Module B 60m EMA5/10 交叉；state、stale 判斷與 dedup 使用交叉 K 棒原始索引時間。
- `modules/exhaustion_signal.py`：Module C 以 60m 主趨勢與 5m 反向交叉產生每趨勢一次的進場訊號。
- `modules/telegram_formatters.py`：純函式訊息組裝，沒有資料抓取、目前時間或 Telegram 副作用，可離線測試。
- 不更動交易策略、交叉判定、state schema、dedup、排程或資料抓取行為。

## 目前訊息格式

- Module B 保留粗體標題、圖示、收 K 時間與收盤價；黃金交叉為 `🔺`，死亡交叉為 `🔻`。
- 60m 的資料索引為開 K 時間，顯示的收 K 時間定義為 `last_cross_ts + 60 分鐘`；只改顯示，所有既有狀態與比較仍使用 `last_cross_ts`。
- Module C 保留粗體 `⭐️` 標題、僅含上升/下降的 60m 主趨勢，並保留原始 5m 回檔訊號時間（不額外加 5 分鐘）。
- Module B 的 NQ 價格顯示兩位小數，YM 顯示整數。

## 目前狀態與下一步

- 已新增離線的 Telegram formatter 精確輸出測試，避免測試依賴 Yahoo Finance、目前時間或 Telegram。
- 後續若要改文案，優先修改 formatter 並同步調整其精確輸出測試；不要把顯示時間變更延伸到 state 或交易訊號判定。
