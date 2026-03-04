# Fantasy Baseball Keeper League Automation System

5-Man Keep 盟自動化管理系統 - 專為 16 隊 Keeper League 設計的合約追蹤與決策輔助工具。

## 功能

### Phase 1 - 核心功能 (已完成)
- 合約計算引擎 (1+1+X 制度: A-B-O / A-B-N-O)
- Excel 名單匯入 (支援 2023 字串格式 + 2024+ 分欄格式)
- Keeper 決策報表產生器
- 買斷計算 (一般路徑 + FAAB 路徑)
- 交易合約跟隨邏輯
- 特別條款處理 (退休/禁賽)

### Phase 2 - API 整合 (準備中)
- Yahoo Fantasy API 連線
- 即時數據同步

### Phase 3 - 自動化通知 (規劃中)
- LINE Bot 指令
- Email 通知
- 排程器

### Phase 4 - AI 功能 (規劃中)
- Claude API 週報摘要
- 智慧 Keeper 建議

## 快速開始

```bash
# 安裝依賴
pip install -r requirements.txt

# 複製環境變數
cp .env.example .env
# 編輯 .env 填入 Yahoo API credentials

# 匯入 Excel 名單
python scripts/import_excel.py "path/to/5-Man Keep盟 新版球員名單.xlsx"

# 產生 Keeper 報表
python scripts/generate_reports.py "path/to/5-Man Keep盟 新版球員名單.xlsx" --year 2026

# 測試 Yahoo API 連線
python scripts/test_yahoo_api.py
```

## 專案結構

```
fantasy-keeper-league/
├── config/
│   └── settings.py          # 聯盟規則設定
├── src/
│   ├── contract/
│   │   ├── models.py         # 資料模型 (Player, Contract, Team)
│   │   └── engine.py         # 合約計算引擎
│   ├── parser/
│   │   └── normalizer.py     # 資料標準化 (雙格式解析)
│   ├── api/
│   │   └── yahoo_client.py   # Yahoo Fantasy API
│   ├── notification/         # Phase 3
│   └── ai/                   # Phase 4
├── scripts/
│   ├── import_excel.py       # Excel 匯入腳本
│   ├── generate_reports.py   # 報表產生器
│   └── test_yahoo_api.py     # API 測試
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

## 合約制度

| 合約 | 說明 | 薪資變化 |
|------|------|----------|
| A | 選秀/FAAB 取得第一年 | 原價 |
| B | A 約留用第二年 | 不變 |
| O | B 約留用一年 (最後一年) | 不變 |
| N(x)+O | B 約延長 x+1 年 | +$5*N |
| R | 新人約 (板凳, 不佔名額) | 原價 |
