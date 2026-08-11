# HANDOFF — Fantasy Baseball 5-Man Keepers

> 工程快照，只留最新狀態＋下一步。完整 session 敘事在 Obsidian，規則在 `CLAUDE.md`。
> 最後更新：2026-08-11

---

## 一句話總結

修好了「週報／月報沒定時發出」與「球員數據抓成整季」兩個並存的問題，並在此基礎上加了一整套 Statcast 進階數據（雷達頁、球員 modal、表格 toggle、FIP），9 個 commit 已 push；**尚未在 production 實際驗證過一次週報發送**。

---

## 完成到哪

### A. 排程失效修復（原始需求）
- **根因一**：`start_scheduler()` 排在 lifespan 最後，前面是一連串同步 Yahoo 呼叫（2 秒節流、429 時 sleep 60-300 秒）。啟動逾時就再也不會註冊排程 → 已提前到 `init_db()` 之後，重活移到背景 thread。
- **根因二**：APScheduler 預設 `misfire_grace_time` 只有 **1 秒**，容器重啟橫跨觸發時間就永久漏掉 → 改 6 小時 ＋ `coalesce`。
- **misfire 不夠**：記憶體 jobstore 重啟後只往後算，容器當下沒開就是漏掉 → 另做 `run_startup_catchup()`，比對「最近應發時間 vs 最後成功紀錄」補發。含全新部署 baseline 防呆、48h/72h 過期不補。
- **可觀測性**：新增 `scheduler_job_runs` 表（migration 016）＋ `GET /api/commissioner/scheduler/status`。這是判斷「沒觸發」還是「送失敗」的唯一依據，先前完全沒有。
- single-flight 鎖：cron／補發／手動端點三入口不會重複推播。

### B. 戰報數據區間修復（原始需求）
- 根因：Yahoo players collection 的 `;out=stats` **只受 `sort_type` 影響排序，回傳一律球季累積**。同一路徑形狀在 `_daily_ar_rank_refresh_job` 就是當季數據存的。
- 改由 MLB Stats API 依區間聚合：週報取 Yahoo scoreboard 的 `week_start`/`week_end`，月報取曆月起訖。
- 抓不到時顯示「數據暫缺」，**不再靜默退回球季累積**。
- 月報 gate 從 `month > 10` 放寬到 `> 11`（10 月的月報以前永遠不會發）。

### C. 年度自動化
- `resolve_league_key()`：靜態設定 → DB 快取（migration 017）→ Yahoo 即時探索。
- `discover_league_keys()` 改讀 Yahoo 回傳的 `season` 欄位，不再依賴寫死 game key 對照表。
- 修掉 `YAHOO_GAME_KEYS[2027]="TBD"` 會組出 `"TBD.l.TBD"`（語法合法但 Yahoo 回 400，所有 job 靜默停擺）。

### D. Statcast 進階數據（新功能）
- `src/analytics/statcast.py`：逐球資料每日抓取 → per-player-per-day 聚合（migration 018/019）。
- **為何不用 leaderboard**：實測 Savant `leaderboard/custom` 完全忽略 `start_date`/`end_date`/`month`（三種查詢回傳相同 632 列），無法支援滾動區間。
- 指標：Barrel%、強擊率、EV、xwOBA、xBA、xSLG、Whiff%、**CSW%**、Swing%、**Chase%**、K%、BB%、GB/LD/FB、速球均速。
- **FIP** 另接 MLB 官方 `stats=byDateRange&group=pitching`（一次取回全聯盟約 450 位投手），因為逐球資料沒有局數欄位（migration 020）。局數一律存 outs（`"2.2"` 是 2⅔ 局）；FIP 常數由聯盟資料反推，不寫死。
- **刻意不做 xERA**：Savant 未公開的專有迴歸，自行近似會與官網對不上。
- UI：`/radar` 雷達頁、球員 modal 的 Statcast 面板、球員表格「進階數據」toggle（含買點 ★ 標記）。
- 指標說明集中在 `frontend/src/lib/statcastGlossary.ts`，三處共用同一份文字。

### E. 順帶修正
- `MANAGER_NAME_MAPPING` 的「楊善合 → Ｋａｋｕ」**兩邊都錯**：Ｋａｋｕ 的 Excel 名是「郭子睿(Rangers)」，「楊善合」是暱稱「哈寶好」的另一位經理。此表被 `auth.py::_match_by_nickname` 用於首次登入指派隊伍，**對錯會把使用者指派到別人的隊伍**。已修正並加測試釘住，同時標記為 legacy（Excel 已非資料來源）。
- CLAUDE.md：補齊 migration 001-020（原本只列到 003）、新增 API 端點、新增 18-1 排程可靠性／18-2 Statcast／18-3 年度自動化三節。

**測試**：66 項通過（`tests/` 從 0 個檔案長到 4 個）。`npm run build` 通過。

---

## 下一步從這開始

### 1.（最優先）部署後驗證 — 尚未做
```bash
# 排程是否真的活過來
curl -H "Authorization: Bearer <token>" \
  "https://5man-keeperleague.zeabur.app/api/commissioner/scheduler/status"
# 看 war_report 的 next_run_time 是否為下週一 21:00、misfire_grace_seconds 是否 21600

# Statcast 自動回補進度（啟動後背景跑 20 天，約 2-3 分鐘）
curl -H "Authorization: Bearer <token>" \
  "https://5man-keeperleague.zeabur.app/api/analytics/statcast-coverage"
```

### 2. 發一次週報（Master 要求，AI 不代發）
Commissioner 頁面「手動觸發排程作業」區已有按鈕。建議順序：
**戰報→Dry-run（只看文字）→ 戰報→Target（發給自己看 LINE 排版）→ 戰報→群組**。
這是修好後的第一則週報，格式已變（球員數據為該週區間、標題帶日期範圍、抓不到顯示「數據暫缺」）。
Dry-run 回傳的 `stats_debug.window.resolved` 會顯示 10 位球員中有幾位成功抓到區間數據。

### 3. LINE Bot 互動工具（構想已定，未動工）
Master 想把現有 LINE bot 加圖文選單，直接在 LINE 裡測試戰報。**關鍵事實：reply message 不計 LINE 額度，只有 push 計**，所以互動測試幾乎零成本（目前每測一次 Target 推送就吃 1 則 / 200 則月配額）。

現況：bot 是**純推播**，`line_service.py` 明寫 "No webhook handler needed"，這是全新功能。需要：
- Webhook endpoint ＋ `X-Line-Signature` 簽章驗證
- 新環境變數 `LINE_CHANNEL_SECRET`（目前只有 ACCESS_TOKEN）
- LINE Developers Console 設定 webhook URL、關閉「自動回覆訊息」
- **白名單**：webhook 是公開端點，任何人加 bot 好友都能傳訊息。能觸發「發群組」的指令必須驗證發送者 LINE user id。

建議分兩階段：先做文字指令版（`戰報` / `雷達` / `排程`）驗證流程，再包圖文選單（需要 2500×1686 px 圖片）。

**⛔ 阻塞中**：Master 上一則訊息說「LINE user id 是」但**值沒有貼上來**，白名單無法設定。需要補。

---

## 已知問題與假資料待補

| 項目 | 說明 |
|---|---|
| **未 commit** | `AGENTS.md` 有 Master 自己的未提交改動（session 開始前就在），本輪未觸碰、未提交 |
| **雷達 ownership 未實證** | 本機無 PostgreSQL，預覽時所有球員顯示 FA 並帶 ⚠ 提示。真實環境會排除 16 隊已持有者，但**這條路徑沒被實際跑過** |
| **既有使用者隊伍指派** | Manager 對照表修正**不會**回溯修正已存在的指派。若曾有人靠 nickname fallback 綁定，可能已綁錯隊 → 部署後查 `/api/commissioner/users` 對一下，有錯用 `POST /api/commissioner/assign-team` 改 |
| **進階數據欄位不支援排序** | 球員表格排序是 server-side，Statcast 是前端 join。要排序得把 `statcast_daily` join 進 SQL，未做。已在 UI 圖例標明「需要排名請用雷達頁」 |
| **非官方端點** | Baseball Savant 的 `statcast_search/csv` 無官方 API 合約，改版會無預警壞掉。已做顯性降級（顯示「數據暫缺」），但需留意 |
| 無假資料殘留 | 預覽用的 mock backend 只在 scratchpad，未進 repo |

---

## 驗證命令

```bash
# 後端測試（66 項）
python -m pytest tests -q

# 前端 build（⚠ 跑之前先確認 dev server 沒在跑，兩者共用 .next 會互相污染）
cd frontend && npm run build

# Statcast 聚合正確性（打者側與投手側總計必須對帳）
python -m pytest tests/test_statcast.py -q

# Manager 對照表（防止再度改錯把人指派到別人隊伍）
python -m pytest tests/test_manager_mapping.py -q
```

---

## 信心最低的產出與原因

1. **排程修復（最低）**——本機無法重現「容器在 21:00 當下沒開」的情境。catch-up 的決策邏輯有 6 個情境的單元測試，但**整條路徑沒在真實停機後跑過**。要等下週一 21:00 或一次實際部署才知道。
2. **雷達的 ownership 過濾**——同上，本機無 DB。程式碼路徑與 war report 共用（已在 production 運作過），但雷達這條沒實跑。
3. **FIP 常數在球季初**——用聯盟資料反推，樣本少時會偏。已設 300 outs 門檻，低於就回 `None` 不顯示，但門檻值是我估的，沒有實證。
4. **名字比對**——Statcast/MLB 用 MLB id，Yahoo 用名字。跨源比對靠正規化（去變音符號、去 Jr./III）。已把正規化收斂到後端單一實作，但**罕見名字仍可能對不上**，症狀是該球員靜靜地沒有進階數據。

---

## 本次模型與 effort

- 模型：**claude-opus-5**（系統環境可查）
- effort：**待 Master 到 usage 儀表板確認**（本 session 查不到實際值）

---

## 偏好提醒

- 回覆全程繁體中文；程式碼變數與註解用英文。
- **每次回覆開頭稱呼「Master」**（工作區母法的指令遵循度哨兵）。
- Commit message：conventional commit 標題 ＋ `## Summary` 中文 bullets ＋ `Co-Authored-By: Claude (實際模型名) <noreply@anthropic.com>`。
- **不要擅自 push**；Master 明確說了才 push。
- 前端沿用既有頁面風格與用語（`<select>` 篩選、「資料說明 Info Guide」藍色可展開區塊、中英並列如「打者 Batters」），不要每頁自創。
- Master 對「多做多錯」有明確顧慮 → 新指標**資料層可以一次加齊，UI 慢慢開**（因為之後加要重抓歷史資料）。

---

## 在哪開新 session（環境）

**Windows 原生**（純本機專案，依母法環境節）。PowerShell、路徑 `C:\...`。
- Frontend: port 3001 (`node next dev -p 3001`)
- Backend: port 8002 (`python -m uvicorn api.main:app --port 8002`，**不可加 `--reload`**)
- 本機無 PostgreSQL，後端與雷達頁需要 DB 才能跑；純看畫面可用 scratchpad 的 mock backend。

---

## Kickoff Prompt

```
接續 Fantasy Baseball 5-Man Keepers 專案（C:\vibe coding\games\Fantasybaseball-keeperLeagueAutomationSystem）。

上一輪（2026-08-11）修好了週報/月報排程失效與數據區間錯誤，並新增整套 Statcast
進階數據（雷達頁 /radar、球員 modal 面板、球員表格進階數據 toggle、FIP）。
9 個 commit 已 push 到 master，Zeabur 應已部署。

先做這三件事：
1. 確認部署後排程真的註冊了：GET /api/commissioner/scheduler/status，
   檢查 war_report 的 next_run_time 與 misfire_grace_seconds=21600。
2. 確認 Statcast 自動回補完成：GET /api/analytics/statcast-coverage。
3. 問 Master 上週週報發了沒、內容對不對（AI 不代發，Commissioner 頁面有按鈕）。

接著的主線是 LINE Bot 互動工具（詳見 HANDOFF.md「下一步」第 3 點）：
webhook + 簽章驗證 + 白名單，先做文字指令版再包圖文選單。
⛔ 動工前必須先跟 Master 要到他的 LINE user id（U... 開頭），
   那是白名單唯一允許者，上一輪他沒貼上來。
   LINE_CHANNEL_SECRET 請 Master 直接設到 Zeabur 環境變數，不要貼進對話。

規則看 CLAUDE.md（專案憲章單一真相），特別是 18-1 排程可靠性、18-2 Statcast、
18-3 年度自動化三節——那裡記的是「不寫下來下次一定重犯」的知識。
```
