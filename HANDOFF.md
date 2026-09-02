# HANDOFF — Fantasy Baseball 5-Man Keepers

> 工程快照，只留最新狀態＋下一步。完整 session 敘事在 Obsidian，規則在 `CLAUDE.md`。
> 最後更新：2026-09-02（Session 2；同日深夜由 ObsidianVault 盤點 session 補註：OpenAI 已閉合、postgres 密碼項以關 port＋刪專案取代）

---

## 一句話總結

Zeabur 環境變數洩漏後啟動整廠搬遷：DB 已搬 Supabase（18 表逐列驗證）、後端已上 Fly.io 東京單機且排程活著、Zeabur postgres 公網 port 已關閉（實測拒連）、secrets 大部分輪替完成；**卡在 Yahoo Fantasy API 全面 403（app 層級，連 Zeabur 也早就壞了），待 Master 撤銷舊授權重走同意畫面**。

---

## 完成到哪

### A. 止血（洩漏處理）
- git 歷史稽查乾淨：`oauth2.json`／`.env` 從未入庫；`.gitignore` 補上 `*.db`（含 wal/shm）。
- 已輪替：LINE channel secret＋access token（Master 重發）、JWT（Fly 上是全新 64 字元值，與 Zeabur 不同）。
- **Zeabur postgres 公網 port 已關**（網路分頁的連線埠轉送）：外部連 `43.133.9.186:31826` 已 Connection refused，Zeabur 後端走內網不受影響（API 200 實測）。「洩漏密碼＋公網門」的組合洞已補。
- **OpenAI：已閉合**——08/29 已在 platform.openai.com 刪除所有舊 key（事件台帳），Zeabur 上那把已失效，免再 revoke。要續用 AI 週報摘要，需發一把新 key 設進 Fly secrets（Master 手動）。
- **postgres 密碼**：Jikka HANDOFF 曾列「Five-man postgres 密碼未輪替（需 ALTER USER）」；本專案以「關公網 port（實測拒連）＋切換日刪除整個 Zeabur 專案」取代，不做 ALTER USER，Jikka 側已同步改註。

### B. DB 搬遷（Zeabur postgres 18 → Supabase postgres 17）
- Supabase 專案：`keeper-league`（id `gbgruifhwvdzybqgngcv`，ap-northeast-1）。
- 本機無 pg 工具 → WSL Ubuntu-22.04 裝 postgresql-client-18（pgdg repo）完成 dump（3.4MB）。
- 唯一相容修正：刪 `SET transaction_timeout`（PG18 專有）。
- **逐表驗收全過**（18 表，基準檔在本次 session scratchpad）：users 16、teams 16、keeper_selections 499、keeper_submissions 16、buyouts 3、statcast_daily 15837、player_rankings 2362、mlb_pitching_daily 4706⋯
- 連線一律走 **session pooler**（直連 host 是 IPv6-only）：`aws-0-ap-northeast-1.pooler.supabase.com:5432`，user `postgres.gbgruifhwvdzybqgngcv`。

### C. 後端上 Fly.io
- App `keeper-league-api`（nrt 東京、shared-cpu-1x 512MB）；`fly.toml` 已 commit（8e083f7）。
- **關鍵設定**：`auto_stop_machines="off"`＋`min_machines_running=1`（排程器不可睡）；部署一律 `--ha=false` 單機（雙機＝排程重複觸發＝LINE 重複推播）。
- 部署時 IP 沒自動配發（Fly 的 org_slug 錯誤）→ 已手動 `fly ips allocate-v4 --shared`＋`allocate-v6`。
- 驗證過：API 200、7 個排程 job 全註冊（next_run 正確）、20 個 migration 被識別不重跑、Statcast coverage 41 天、post-draft 快照重建 16 隊 258 keepers。
- Secrets 已設：DATABASE_URL（Supabase）、新 JWT、Yahoo 舊 app 憑證、LINE 全套（新 token）、`REPORT_CATCHUP_ENABLED=false`（**過渡期防重複推播，切換完成後要改回 true**）。
- LINE 驗證：bot/info 200（token 有效）、webhook 未簽名請求 403（驗簽生效）。

### D. Yahoo OAuth（卡住中）
- **新 app 這條路死了**：此帳號建新 app 的 API Permissions 只剩 OpenID Connect＋TW Auction，**沒有 Fantasy Sports 可選**。
- 改沿用舊 app `Fantasy Baseball Keeper Assistant`（App ID v8FKI1yy，有 Fantasy Sports - Read）；已代 Master 加上 redirect URI `https://keeper-league-api.fly.dev/api/auth/yahoo/callback`（原三條保留）。
- Master 走過一次 login（Yahoo 靜默放行，token 已寫進 Supabase）→ **聯盟 API、profile、連 openid userinfo 全部 403「This application is not authorized」**。
- 已排除：IP 封鎖（本機直打同樣 403）、scope 參數（程式要 `openid fspt-r`）。**結論：舊 grant 整個壞掉（app 層級），Zeabur 近期的 Yahoo 403（commit 16698ed 就在修這個）是同一件事，不是搬遷造成。**
- 下一招（已指示 Master，等執行）：Yahoo 帳號「連線的服務」撤銷該 app → 重走 login 強迫出完整同意畫面。若同意畫面沒列 Fantasy Sports 或授權後仍 403 ＝ Yahoo 伺服器端收掉權限，需另議對策。

---

## 下一步從這開始

1. **[需 Master] Yahoo 撤銷＋重授權**（上面 D 的下一招）→ 成功後跑 `POST /api/commissioner/yahoo-token/test` 驗證。
2. **[需 Master，僅若要續用 AI 週報摘要] 發新 OpenAI key 設進 Fly**（舊 key 08/29 已全數刪除，revoke 步驟免做）。
3. **LINE console 兩個設定**（Master 按或授權代按）：Webhook URL 設 `https://keeper-league-api.fly.dev/api/line/webhook`＋開 Use webhook；**Auto-reply messages 關閉**（目前 Enabled）。設完傳「排程」給 bot 實測。
4. **前端搬 Cloudflare**（OpenNext/Workers）→ 改 Fly 的 `FRONTEND_URL`／`ALLOWED_ORIGINS`。
5. **切換日 runbook**：開 Zeabur postgres 公網 port 5 分鐘 → 最終 re-dump→restore（流程同 B，先 `TRUNCATE`／drop schema 再灌）→ 關 port → `REPORT_CATCHUP_ENABLED=true` → 驗證隔日 00:15 `transaction_fetch` 寫入 `scheduler_job_runs` → **刪除整個 Zeabur 專案**（洩漏的 secrets 隨之消滅）。

## 已知問題與假資料待補

- Yahoo API 全面 403（見 D）——**這是現網既有故障**，週報／名冊同步等 Yahoo 相關功能兩邊都停擺中。
- 過渡期雙棧並行：Zeabur（現網，聯盟成員在用）寫 Zeabur DB；Fly 寫 Supabase。**資料在漂移，切換日必須 re-dump**。
- Fly 上 `FRONTEND_URL` 暫指 Zeabur 前端；登入後跳轉的頁面會 404（`/auth/callback` 帶著 Fly 簽的 JWT 去 Zeabur 前端），過渡期已知現象。
- `fly deploy` 需要 `FLY_API_TOKEN`（Master 在 fly.io/tokens 建的，值在 Master 手上；本 session 未存檔）。

## 驗證命令

```bash
# Fly 後端活著＋資料來自 Supabase
curl -s https://keeper-league-api.fly.dev/api/league/years   # 期望 [2026]
# Yahoo 連線（需 commissioner JWT）
curl -s -X POST https://keeper-league-api.fly.dev/api/commissioner/yahoo-token/test -H "Authorization: Bearer <JWT>"
# Zeabur postgres 公網門仍關著（期望 Connection refused）
wsl -d Ubuntu-22.04 -e /usr/lib/postgresql/18/bin/psql "postgresql://root:x@43.133.9.186:31826/zeabur" -c "SELECT 1"
# 排程執行紀錄（Supabase MCP 或 psql）
SELECT job_id, status, started_at FROM scheduler_job_runs ORDER BY started_at DESC LIMIT 10;
```

## 信心最低的產出與原因

- **Yahoo 403 的根因判斷**：「舊 grant 壞掉／Yahoo 收權限」是由排除法推出（非 IP、非 scope 參數、userinfo 也 403），尚未有 Yahoo 端的直接證據；撤銷重授權是驗證這個假說的實驗，失敗的話假說要修。
- **切換日 re-dump 的 TRUNCATE 順序**未演練過（外鍵約束下的匯入順序），到時建議直接 drop schema public cascade 再整份灌回。

## 本次模型與 effort

Claude Fable 5（claude-fable-5）。Effort 設定待 Master 到 usage 儀表板確認。

## 偏好提醒

- 回覆開頭稱呼「Master」；繁中回覆；不用 emoji；秘密值不寫進文件（本檔只寫存放位置）。
- 動帳號設定（Yahoo/LINE/OpenAI console）前先問；Master 已多次選「你來」代操作瀏覽器。

## 在哪開新 session（環境）

Windows 原生（純本機專案）。dump/restore 用 `wsl -d Ubuntu-22.04`（已裝 postgresql-client-18）。flyctl 在 `~\.fly\bin\flyctl.exe`（登入用 `FLY_API_TOKEN` 環境變數，token 向 Master 要）。

## Kickoff Prompt

```
接續 Fantasybaseball keeper 專案 Session 2（Zeabur→Fly/Supabase 搬遷）。
讀 HANDOFF.md。現況：後端已在 https://keeper-league-api.fly.dev（Fly nrt 單機）跑著、
資料在 Supabase（keeper-league），Zeabur 是現網但 postgres 公網 port 已關。
卡點：Yahoo Fantasy API 全面 403（app 層級、Zeabur 也一樣壞）。
先問 Master：(1) Yahoo 撤銷舊授權＋重授權做了沒？結果？(2) 要不要續用 AI 週報摘要（要就發新 OpenAI key 進 Fly；舊 key 08/29 已全刪）？
然後照 HANDOFF「下一步」1→5 推進；切換日照 runbook，完成後刪 Zeabur 專案。
```
