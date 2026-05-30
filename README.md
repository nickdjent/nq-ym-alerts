# NQ/YM Alerts

跑在 GitHub Actions 上的 NQ/YM 期貨自動化推播系統。透過 Telegram Bot 推送三類訊息到 1 個 Telegram Group。

## 三個模組

| 模組 | 用途 | 頻率 |
|---|---|---|
| **Module A** | NQ/YM 每日操作區間（開盤 ± ADR） | 每日一次（美東 18:05） |
| **Module B** | NQ/YM 60m EMA5/10 黃金與死亡交叉警示 | 每小時 |
| **Module C** | 主趨勢「逢回進場」訊號（buy-the-dip / sell-the-bounce） | 每 5 分鐘 |

### Module A — 每日操作區間
- 美東 18:00 Globex 開盤後，於 18:05 推送
- 取 NQ=F / YM=F 各自當天 18:00 5m bar 的 Open 為「Session Open」
- ADR(10) = 過去 10 根已收盤日 K 的 (High - Low) 平均
- 推送四個點位：開盤 ± ADR、開盤 ± ADR/2
- NQ 顯示 2 位小數、YM 顯示整數

### Module B — 60m EMA 交叉
- 每小時跑一次（每小時第 2 分，給 yfinance 反映剛收盤的 K 棒）
- 計算 60m K 棒 EMA5、EMA10
- 「Golden cross」：前一根 EMA5 ≤ EMA10 且當根 EMA5 > EMA10
- 「Death cross」：前一根 EMA5 ≥ EMA10 且當根 EMA5 < EMA10
- **無狀態設計**：只在「最新已收盤 K 棒」剛發生交叉時推播。漏跑就漏訊（接受 trade-off）

### Module C — 逢回進場訊號（buy-the-dip / sell-the-bounce）
每 5 分鐘跑一次，使用 `state/{nq,ym}_module_c.json` 作為狀態存檔。

1. 偵測「60m 新交叉」→ 設定為當前主趨勢，並重置 entry 旗標
2. 在 60m 交叉發生後的 **3 小時內**，盯著 5m K 棒：
   - **60m 上升 (golden) + 5m 反向 (death)** = 「⚠️ 進場訊號 / 建議方向: 做多」
   - **60m 下降 (death) + 5m 反向 (golden)** = 「⚠️ 進場訊號 / 建議方向: 做空」
   - **5m 同向交叉** → 不推（策略只在「逢回」進場）
3. 每個主趨勢週期只推一次（dedup）
4. 3 小時窗過後不再推播，等下一個 60m 新交叉
5. 5m 訊號必須在「最新已收盤的 5m K 棒」剛發生才推（避免重複偵測舊訊號）

## 部署 SOP（從零到收到第一則訊息）

### Step 1 — 建立 GitHub Repo
- 必須是 **Public**（Module C 每 5 分鐘執行會超過 private repo 的 2,000 min/月額度）
- 把這份 codebase 整個 push 上去

### Step 2 — 建 Telegram Bot
1. Telegram 內找 [@BotFather](https://t.me/BotFather)
2. `/newbot` → 取個名稱、取個 username（必須以 `bot` 結尾）
3. 拿到 **HTTP API Token**（格式：`123456:ABC-DEF...`）→ 這就是 `TELEGRAM_BOT_TOKEN`

### Step 3 — 建 Telegram Group、加 Bot、取 chat_id
1. 建立一個 Telegram Group
2. 把剛建好的 Bot 拉進 Group
3. **重要**：在群組裡發任一訊息（讓 Bot 「看到」群組）
4. 開瀏覽器：`https://api.telegram.org/bot<TOKEN>/getUpdates`
5. 找到 `"chat":{"id":-100xxxxxxxxxx,...}` — 那個負數就是 `TELEGRAM_CHAT_ID`
   - Group/Supergroup 的 chat_id 一定是負數，且通常 `-100` 開頭
6. 建議在 Group → Bot 設定中允許 Bot 看訊息、給 admin 權限（避免之後被踢出）

### Step 4 — 設定 GitHub Secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**：

| Secret 名稱 | 內容 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Step 2 拿到的 token |
| `TELEGRAM_CHAT_ID` | Step 3 拿到的負數 chat_id（例：`-1001234567890`） |

### Step 5 — 手動觸發驗證
Repo → **Actions** tab → 對每個 workflow 點 **Run workflow**（`workflow_dispatch`）：
1. `Module A - Daily Range`：應收到 NQ/YM 每日區間訊息（如果你在 ET 18:00–18:15 之外手動跑，程式會 exit 0，這是正常的 — 若要強制看訊息，用本地 `test_local.py`）
2. `Module B - 60m EMA Cross`：市場開盤時跑會看到 log；若最新 K 棒剛好交叉才會推播
3. `Module C - Exhaustion Signal`：市場開盤時跑會看到 state 變化的 log
4. `Monthly Heartbeat`：手動跑一次驗證可以 commit/push

### Step 6 — 確認 Cron 已啟用
- GitHub 對長期沒活動的 repo 會自動停用 cron（60 天）
- 為避免這個問題，已內建 `heartbeat.yml`，每月 1 號自動 commit 一次
- 在 Actions tab 確認四個 workflow 的 schedule 已顯示為 `Active`

## 本地開發

```bash
# 1. 建 venv 並裝套件
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 設定 .env
cp .env.example .env
# 編輯 .env 填入 BOT_TOKEN 與 CHAT_ID

# 3. 推一則 Telegram 測試訊息（會真的推）
python tests/test_telegram.py

# 4. 跑各 module 的 dry-run（不會推播）
python tests/test_local.py daily_range
python tests/test_local.py ema_cross_60m
python tests/test_local.py exhaustion_signal
```

`test_local.py` 會繞過時間窗 / 市場開盤判斷，所以隨時都能看到輸出。

## 疑難排解

### Cron 沒觸發
- 確認 repo 是 Public（private repo 有額度限制）
- 確認 Actions tab 顯示 schedule 為 Active
- GitHub Actions cron **不保證準時**，常會延遲 5–15 分鐘
- 60 天沒任何活動的 repo 會自動停用 cron → heartbeat.yml 解決這個

### Telegram 收不到
- 用 `python tests/test_telegram.py` 確認 Token / chat_id 正確
- 確認 Bot 已加入 Group 且不是「Restricted」
- chat_id 必須是負數（Group/Supergroup）
- 訊息含 Markdown 特殊字元 (`_`、`*` 等) 可能被解析錯誤；目前已用 backticks 包價格

### yfinance 抓不到資料
- 已內建 3 次重試
- 偶爾 Yahoo Finance API 會短暫掛掉 → 接受偶發漏訊
- 確認 ticker 寫法為 `NQ=F`、`YM=F`（大寫，等號 F）

### Module C 沒推播
- 5m 訊號必須在 60m 交叉後的 3 小時內才會觸發
- 5m 訊號必須在「最新已收盤 5m K 棒」剛發生才會推
- 5m **同向**交叉不會推（策略只認逢回反向訊號）
- 每個主趨勢週期只推一次「進場訊號」（dedup）
- 看 Action log 裡的 print 訊息可以理解為何沒推

## 維護注意事項

- **每月 heartbeat**：`heartbeat.yml` 每月 1 號自動 commit 一次，避免 GitHub 自動停用 cron
- **State 檔不要手改**：`state/*_module_c.json` 由程式自動管理；要重置就刪掉檔案，下次跑會自動建立
- **yfinance 套件**：定期 `pip install -U yfinance` 更新（Yahoo 偶爾改 schema）
- **時區**：所有時間處理已使用 `pytz` US/Eastern；不要混入 naive datetime
- **`[skip ci]`**：Module C / Heartbeat 的 state commit 訊息已含 `[skip ci]` 避免無限迴圈
