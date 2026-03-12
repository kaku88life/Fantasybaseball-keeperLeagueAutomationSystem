# Fantasy Baseball Keeper League - Project CLAUDE.md

> 本文件為專案的核心規則參考，涵蓋所有聯盟規則、合約邏輯、驗證條件。
> 所有程式碼修改與新功能開發，必須以此文件為依據進行規劃與確認。

---

## 1. 聯盟基本資訊

| 項目 | 值 |
|------|-----|
| 聯盟名稱 | 5-Man Keep盟 |
| 隊伍數量 | 16 隊 |
| 賽制 | H2H (Head-to-Head) 7x7 |
| 打擊數據 | R, H, HR, RBI, SB, AVG, OPS |
| 投球數據 | W, SV, HLD, K, ERA, WHIP, QS |
| 每週最低投球局數 | 30 IP |
| Commissioner | Kaku (楊善合) |

---

## 2. 名冊結構 (Roster Positions)

| 類別 | 位置 | 數量 |
|------|------|------|
| Active (野手) | C, 1B, 2B, 3B, SS, IF, LF, CF, RF, OF, UT, UT | 12 |
| Pitchers (投手) | SP x4, RP x3, P x3 | 10 |
| Bench (板凳) | BN x5 | 5 |
| NA (未上大聯盟) | NA x2 | 2 |
| DL (傷兵) | DL x4 | 4 |

---

## 3. 薪資帽 (Salary Cap)

### 公式
```
salary_cap = $300 + (year - 2024 + 1) x $5
```

| 年度 | 薪資帽 |
|------|--------|
| 2023 | $300 |
| 2024 | $305 |
| 2025 | $310 |
| 2026 | $315 |
| 2027 | $320 |

### 排名獎金 (Ranking Bonus)
根據上一年季後賽名次，獲得薪資帽加成：

| 名次 | 獎金 |
|------|------|
| 1st | +$10 |
| 2nd | +$7 |
| 3rd | +$5 |
| 4th | +$3 |
| 5th | +$2 |
| 6th | +$1 |
| 7th+ | $0 |

### 可用薪資計算
```
available_salary = salary_cap + ranking_bonus + trade_compensation
                   - keeper_cost - buyout_salary_cost
```

---

## 4. FAAB (Free Agent Acquisition Budget)

| 項目 | 值 |
|------|-----|
| 年度預算 | $100 |
| 最低出價 | $1 ($0 出價無效，自動跳到下一順位) |
| 完封獎金 | +$10 (H2H 對戰完封對手時獲得) |

### FAAB 可用額度
```
available_faab = faab_budget - buyout_faab_cost
```

---

## 5. 合約系統 (Contract System)

### 合約類型

| 類型 | 說明 | 可留用 | 佔名額 |
|------|------|--------|--------|
| A | 第一年約 (選秀/FAAB 取得) | Yes | Yes (active) |
| B | 第二年約 (A 留用後) | Yes | Yes (active) |
| N(x) | 延長約 (B 延長後，x = 剩餘延長年數) | Yes | Yes (active) |
| O | 到期約 (最後一年，之後成為 FA) | No | Yes (active) |
| R | 農場新秀約 (不佔 active 名額) | Yes | No (farm) |
| FA | 自由球員 | N/A | N/A |

### 合約流程圖

```
選秀 (Draft) / FAAB 撿人
       |
       v
   A 約 (第一年)
       |
       +--[留用 keep]--> B 約 (第二年)
       |                    |
       |                    +--[留用 keep]--> O 約 (到期年) --> FA
       |                    |
       |                    +--[延長 extend N年]--> N(x) 約
       |                                              |
       |                                              +--[自動]--> N(x-1) --> ... --> N1 --> O --> FA
       |
       +--[不保留 release]--> FA
       |
       +--[指定新秀 rookie]--> R 約 (農場新秀)
                                  |
                                  +--[維持 keep]--> R (持續為農場新秀)
                                  +--[啟用 activate]--> A 約 (進入正規合約)
                                  +--[不保留 release]--> FA
```

### 合約演進規則

1. **A -> B**: 薪資不變
2. **B -> O**: 薪資不變，到期年（最後一年）
3. **B -> N(x)+O**: 延長合約
   - 新薪資 = 原薪資 + x x $5
   - 例：$20/B 延長 3 年 -> $35/N3 -> $35/N2 -> $35/N1 -> $35/O -> FA
   - 薪資在延長期間**固定不變**，$5/年只在 B->N 轉換時一次性加上
4. **N(x) -> N(x-1)**: 自動演進，薪資不變 (is_mandatory = true)
5. **N1 -> O**: 自動演進，薪資不變 (is_mandatory = true)
6. **O -> FA**: 到期自動成為自由球員，無法留用 (is_mandatory = true)
7. **R -> R**: 維持農場新秀，薪資不變
8. **R -> A**: 啟用進入正規合約，薪資不變

### N 約特別說明
- N 約球員為**自動延續 (mandatory keeper)**，無法選擇不留用
- 唯一的「退出」方式：
  - 買斷 (release → buyout)
  - 法律問題 (legal_issue → 合約凍結)

---

## 6. 留用規則 (Keeper Rules)

### 留用人數限制

| 項目 | 最少 | 最多 |
|------|------|------|
| Active Keepers (A/B/N 約) | 12 | 15 |
| Farm Rookies (R 約) | 0 | 2 |

### 留用選項 (按合約類型)

| 合約類型 | 可選動作 |
|----------|----------|
| A | keep (-> B), release (-> FA) |
| B | keep (-> O), extend N年 (-> N(x)), release (-> FA) |
| N | 自動延續 (mandatory), release (-> buyout), legal_issue (-> 凍結) |
| O | 自動成為 FA (mandatory，無法留用) |
| R | keep (-> R), activate (-> A), release (-> FA) |

### FAAB 強制留用規則
- FAAB >= $10 的球員**必須留用** (mandatory keeper)
- 不留用需支付買斷費用
- 來源 (source) 為 `"faab"` 或 `"trade_faab"` 的球員適用此規則

### 驗證條件 (Validation)

**錯誤 (Errors) — 阻止提交**：
1. Active keepers < 12 人（全部選擇完成後）
2. Active keepers > 15 人
3. Farm rookies > 2 人
4. O 約球員被標記為留用
5. 薪資超標：keeper_cost + buyout_salary_cost > salary_cap + ranking_bonus + trade_compensation
6. FAAB 超標：buyout_faab_cost > faab_budget

**警告 (Warnings) — 允許提交但提醒**：
1. Active keepers < 12 人（尚未全部選擇時）
2. 剩餘薪資空間 < $20

---

## 7. 買斷規則 (Buyout Rules)

### 一般買斷 (Normal Buyout)
- 每年支付**全額薪資**從薪資帽扣除
- 支付年數 = 合約剩餘年數
- 例：$30/N3 買斷 → 每年 $30，共 4 年 (3 年 N + 1 年 O)

### FAAB 買斷 (FAAB Buyout)
- 每年薪資拆成兩半支付：
  - FAAB 支付 `ceil(salary / 2)` (較大的一半)
  - 薪資帽支付 `floor(salary / 2)` (較小的一半)
- 例：$11 薪資 → FAAB $6 + 薪資帽 $5
- 例：$30 薪資 → FAAB $15 + 薪資帽 $15

### 各合約買斷年數

| 合約 | 剩餘年數 |
|------|----------|
| A | 1 年（通常直接不留用即可，無需買斷） |
| B | 1 年（通常直接不留用即可，無需買斷） |
| N(x) | x + 1 年 (N 年數 + O 年) |
| O | 1 年 |
| R | 0 年 (無限期，不需買斷) |

### FAAB 未撿人罰款 (Penalty for Missed Pickups)
- 第 1 次: $5
- 第 2 次: $10
- 第 3 次: $15 (遞增)

---

## 8. 交易規則 (Trade Rules)

### 合約繼承
當球員被交易時，使用**較高薪資**和**較長合約**：
- 薪資 = max(原始薪資, 交易價格)
- 合約類型 = 剩餘年數較長者
- 優先級：N/O > B > A > R

### 交易補償
- 最多 5 年分期支付
- `trade_compensation` 加到可用薪資中

### FAAB 取得規則
- 被原隊 drop → 其他隊 FAAB 撿走：新 A 約，薪資 = max(FAAB_bid, $1)
- 被原隊 drop → 同隊撿回：保留原始合約類型，薪資 = max(原始, FAAB_bid)

---

## 9. 農場新秀 (R 約 / Farm Rookie)

### 新秀資格門檻
| 項目 | 門檻 |
|------|------|
| 投球局數 (IP) | > 50 局失去資格 |
| 打席數 (PA) | > 130 打席失去資格 |

### R 約規則
- 每隊最多 2 名 R 約球員
- R 約**不佔 active keeper 15 人名額**，獨立計算
- R 約不是預設狀態，而是留用選擇 (A 約球員可選擇 designate 為 R)
- 啟用 (activate) 後進入 A 約，開始正規合約流程

---

## 10. 特殊條款 (Special Clause)

### 適用情況
- `legal_issue`: 家暴、醜聞等法律問題
- `retired`: 球員退休
- `lifetime_ban`: 終身禁賽

### 效果
- **不需支付薪資**
- **不佔 15 人留用名額**
- 合約凍結，必須在隊伍名冊下方註記
- 球員復出時：原始合約恢復，或 GM 可選擇買斷

---

## 11. 傷兵名單 (DL / Injured Reserve)

- 如果同一支 MLB 球隊有 2+ 名球員進入 DL，只算 1 個 DL 名額
- 不能直接撿起同隊球員，必須經過 waiver 或交易

---

## 12. 讓渡規則 (Waiver Rules)

- $0 出價無效 → 聯盟自動延伸到下一順位
- 讓渡優先權：
  - 第 1 年 = 當前戰績排名 (末位優先)
  - 第 2 年起 = 上一季最終排名 (末位優先)

---

## 13. 季後賽 (Playoffs)

| 項目 | 值 |
|------|-----|
| 季後賽週數 | 第 23, 24, 25 週 |
| 參賽隊伍數 | 8 隊 |

---

## 14. 前端驗證常數 (Frontend Validation Constants)

以下常數必須與後端 `config/settings.py` 保持同步：

```typescript
// frontend/src/lib/validation.ts
const KEEPER_ACTIVE_MIN = 12;
const KEEPER_ACTIVE_MAX = 15;
const KEEPER_BENCH_MAX = 2;
const EXTENSION_COST_PER_YEAR = 5;
```

### 前端驗證分類邏輯
```
getKeeperCategory(contractType, action):
  - release / fa        -> "none" (不佔名額)
  - legal_issue          -> "none" (不佔名額)
  - O 約 (任何 action)   -> "none" (到期 FA)
  - R 約 + keep          -> "farm" (農場新秀)
  - R 約 + activate      -> "active" (正規留用)
  - 其他 (A/B/N + keep)  -> "active" (正規留用)
```

### 薪資計算邏輯
```
computeNextSalary(contractType, currentSalary, action, extensionYears):
  - release / fa / legal_issue -> 0
  - B 約 + extend              -> currentSalary + extensionYears x $5
  - 其他 keep                   -> currentSalary (不變)
```

---

## 15. API 端點清單

### 認證 (Auth)
- `POST /api/auth/yahoo/login` → 302 redirect to Yahoo OAuth
- `GET /api/auth/yahoo/callback` → exchange code, redirect with JWT
- `GET /api/auth/me` → 當前使用者資訊

### 聯盟 (League)
- `GET /api/league/settings` → 聯盟規則設定
- `GET /api/league/{year}` → 該年度聯盟快照
- `GET /api/league/{year}/summary` → 聯盟總覽
- `GET /api/league/years` → 可用年度

### 隊伍 (Teams)
- `GET /api/teams/` → 隊伍清單
- `GET /api/teams/{id}/roster/{year}` → 隊伍名冊
- `GET /api/teams/{id}/keeper-options/{year}` → 各球員留用選項
- `GET /api/teams/{id}/keeper-selections/{year}` → 取得留用選擇
- `PUT /api/teams/{id}/keeper-selections/{year}` → 儲存留用選擇 (auto-save)
- `POST /api/teams/{id}/keeper-submit/{year}` → 提交留用 (鎖定)

### Commissioner
- `POST /api/commissioner/import-excel` → 上傳 Excel
- `GET /api/commissioner/submissions/{year}` → 所有提交狀態
- `GET /api/commissioner/submissions/{year}/{team_id}` → 單隊提交詳情
- `POST /api/commissioner/approve/{year}/{team_id}` → 審核
- `POST /api/commissioner/unlock/{year}/{team_id}` → 解鎖重新提交
- `POST /api/commissioner/assign-team` → 指派使用者到隊伍
- `GET /api/commissioner/users` → 所有使用者
- `POST /api/commissioner/set-commissioner/{user_id}` → 授權 Commissioner
- `GET /api/commissioner/all-team-adjustments` → 所有隊伍調整
- `PUT /api/commissioner/team-adjustments/{team_id}` → 更新隊伍調整

### 球員 (Players)
- `GET /api/players/stats?name={name}&position={position}` → MLB Stats API 代理

---

## 16. 技術架構

| 組件 | 技術 |
|------|------|
| 後端 | FastAPI (Python) |
| 前端 | Next.js 15 + React 19 + Tailwind CSS v4 |
| 認證 | Yahoo OAuth2 + JWT |
| 資料庫 | PostgreSQL (部署) / SQLite WAL (本地可選) |
| 部署 | Zeabur (Tokyo) |

### 開發伺服器
- Frontend: port 3001 (`node next dev -p 3001`)
- Backend: port 8002 (`python -m uvicorn api.main:app --port 8002`)
- Backend 不可使用 `--reload` flag（會導致 worker process 掛住）

### 資料流
```
Excel (歷史名冊)
  + Yahoo API (當年名冊/選秀/交易)
       |
       v
  scripts/rebuild_with_correct_mapping.py (合約追溯)
       |
       v
  data/2026_contracts_v2.json (合約清單)
       |
       v
  scripts/load_2026_contracts.py (載入 DB)
       |
       v
  SQLite/PostgreSQL DB
       |
       v
  FastAPI Backend (api/)
       |
       v
  Next.js Frontend (留用選擇介面)
```

---

## 17. Manager 名稱對照

| Excel 名稱 | Yahoo 暱稱 |
|------------|-----------|
| 楊善合 | Kaku |
| 林剛 | Hyper |
| Yu-Che Chang | 小喆 |
| Issac | rawstuff |
| Tony林芳民 | Tony |
| Billy WU | Billy |
| Eddie Chen | EDDIE |
| James Chen | 魚魚 |
| ywchiou | YWC |
| Chih-Wei | wei |
| Ponpon | Ponpon |
| Hank | 叫我寬哥 |
| TIMMY LIU | TIMMY LIU |
| Javier | 謙謙 |
| Leo | Leo |

---

## 18. 開發注意事項

### 前後端常數同步
以下常數在 `config/settings.py` 和 `frontend/src/lib/validation.ts` 中必須保持一致：
- `KEEPER_ACTIVE_MIN` / `KEEPER_ACTIVE_MAX`
- `KEEPER_BENCH_MAX`
- `EXTENSION_COST_PER_YEAR`

### 命名慣例
- 農場新秀統一使用 `farm_rookie` (英文) / `農場新秀` (中文)
- 不使用 `bench_keeper` / `板凳新秀` 等舊稱
- 程式碼變數/註解使用英文
- UI 顯示使用繁體中文，搭配英文術語 (例：「留用 Keep」、「延長 Extend」)

### 合約顯示格式
- 格式: `$薪資/合約類型`
- 例: `$20/A`, `$20/B`, `$35/N3`, `$20/O`, `$5/R`
- N 約顯示延長年數: `$35/N3` 表示還有 3 年 N + 1 年 O

### 前端 Auto-save
- 使用 1.5 秒 debounce
- 目標端點: `PUT /api/teams/{id}/keeper-selections/{year}`
- 提交 (submit) 後鎖定，需 Commissioner 解鎖才能修改

---

## 19. 資料庫遷移系統

### 概述
專案使用自製的輕量版本化遷移系統（非 Alembic），透過 `schema_migrations` 表追蹤已套用的遷移。

### 遷移追蹤表
```sql
schema_migrations (
    version TEXT PRIMARY KEY,     -- 遷移版本號，如 "001_add_line_name"
    applied_at TIMESTAMPTZ        -- 套用時間
)
```

### 現有遷移版本
| 版本 | 說明 |
|------|------|
| `001_add_line_name` | users 表新增 line_name 欄位 |
| `002_add_indexes` | 5 個效能索引（selections/submissions/notifications） |
| `003_add_foreign_keys` | 6 個外鍵約束（資料一致性保護） |

### 如何新增遷移
在 `api/database.py` 的 `MIGRATIONS` dict 中新增項目：

```python
MIGRATIONS: dict[str, list[str]] = {
    # ... 既有遷移 ...
    "004_your_migration_name": [
        "SQL statement 1;",
        "SQL statement 2;",
    ],
}
```

**規則：**
- 版本號格式：`NNN_描述`，數字遞增（如 `004_xxx`、`005_xxx`）
- 每個 SQL 必須**冪等**（可重複執行不出錯），使用 `IF NOT EXISTS` / `DO $$` 保護
- 遷移在 `init_db()` 啟動時自動執行，只跑尚未套用的版本
- 失敗時自動 rollback 並印錯誤，不影響其他遷移

### 外鍵約束清單
| 約束名稱 | 關係 | 刪除行為 |
|----------|------|---------|
| `fk_users_team_id` | users.team_id → teams.id | SET NULL |
| `fk_keeper_selections_team_id` | keeper_selections.team_id → teams.id | CASCADE |
| `fk_keeper_submissions_team_id` | keeper_submissions.team_id → teams.id | CASCADE |
| `fk_keeper_submissions_submitted_by` | keeper_submissions.submitted_by → users.id | SET NULL |
| `fk_notification_log_team_id` | notification_log.team_id → teams.id | CASCADE |
| `fk_league_snapshots_imported_by` | league_snapshots.imported_by → users.id | SET NULL |

### 效能索引清單
| 索引名稱 | 欄位 |
|----------|------|
| `idx_users_team_id` | users(team_id) |
| `idx_keeper_selections_year_team` | keeper_selections(year, team_id) |
| `idx_keeper_submissions_year_team` | keeper_submissions(year, team_id) |
| `idx_notification_log_team_year` | notification_log(team_id, year, notification_type) |
| `idx_notification_log_sent_at` | notification_log(sent_at DESC) |

---

## 20. 部署與容器化

### Dockerfile
專案根目錄有 `Dockerfile`，基於 `python:3.11-slim`：
- 安裝 `libpq-dev`（PostgreSQL 驅動編譯需要）
- 複用 `start.sh` 啟動腳本
- 預設 port 8002，可由 `PORT` 環境變數覆蓋

### 啟動順序（start.sh + lifespan）
```
1. start.sh: 載入 2026 合約 JSON → DB
2. lifespan: init_db() → 建表 + 跑遷移
3. lifespan: seed_if_empty() → 首次部署自動種子化
4. lifespan: cleanup_old_notifications(365) → 清理超過 1 年的通知紀錄
5. lifespan: start_scheduler() → 啟動排程器
6. uvicorn: 開始接受請求
```

### 環境變數（完整清單見 .env.example）
| 變數 | 必要性 | 說明 |
|------|--------|------|
| `DATABASE_URL` | 生產必要 | PostgreSQL 連線字串 |
| `JWT_SECRET_KEY` | 生產必要 | JWT 簽章密鑰（32+ 字元） |
| `YAHOO_CLIENT_ID` | 必要 | Yahoo OAuth2 Client ID |
| `YAHOO_CLIENT_SECRET` | 必要 | Yahoo OAuth2 Client Secret |
| `YAHOO_LEAGUE_ID` | 必要 | Yahoo 聯盟 ID |
| `OAUTH_REDIRECT_URI` | 必要 | OAuth 回調 URL |
| `FRONTEND_URL` | 必要 | 前端 URL（登入後導向） |
| `ALLOWED_ORIGINS` | 建議 | 額外 CORS 允許來源 |

### JWT 安全機制
- 支援 `JWT_SECRET` 或 `JWT_SECRET_KEY` 兩個變數名稱
- 未設定時使用 dev default 並印出 WARNING
- 仍使用舊 placeholder 值時印出 WARNING
- 生產環境務必設定：`python -c "import secrets; print(secrets.token_hex(32))"`

### notification_log 清理
- 啟動時自動刪除超過 365 天的通知紀錄
- 由 `cleanup_old_notifications()` 處理，失敗不影響啟動
- 可調整保留天數：修改 `main.py` 中的 `retention_days` 參數
