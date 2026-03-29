# Fantasy Baseball Keeper League Automation System

A full-stack web application for managing a 16-team fantasy baseball keeper league with complex contract tracking, salary cap management, and automated notifications.

Built for leagues using a **1+1+X contract system** (A-B-O / A-B-N-O) with salary caps, FAAB budgets, farm rookie slots, and buyout mechanics.

> This project was built entirely through **vibe coding** with [Claude Code](https://claude.ai/claude-code) - from initial design to deployment, every line of code was AI-pair-programmed.

---

## Table of Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Contract System](#contract-system)
- [League Rules](#league-rules)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Database](#database)
- [Deployment](#deployment)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## Features

### Keeper Selection & Management
- **Interactive keeper selection UI** - Drag-and-drop style interface for choosing which players to keep, extend, or release
- **Real-time validation** - Instant feedback on salary cap, roster limits, and contract rule violations
- **Auto-save** - Selections are automatically saved with 1.5s debounce
- **Submit & lock** - Final submissions are locked and require Commissioner approval to modify
- **Multi-contract support** - A (1st year), B (2nd year), N(x) (extension), O (expiring), R (farm rookie)

### Contract Engine
- **Full contract lifecycle tracking** - From draft/FAAB acquisition through extension, trade, buyout, or expiration
- **Historical contract reconstruction** - Rebuilds complete contract chains from Yahoo Fantasy API draft + transaction data
- **Extension calculator** - B-contract players can extend 1-10 years at $5/year premium
- **Buyout calculator** - Normal buyouts (salary cap) and FAAB buyouts (split payment)
- **Trade contract inheritance** - Traded players inherit the longer/higher contract

### Commissioner Dashboard
- **Submission management** - Review, approve, reject, or unlock team keeper submissions
- **User management** - Assign users to teams, manage LINE names, grant commissioner privileges
- **Buyout management** - Create, edit, and track buyout records across years
- **Team adjustments** - Set trade compensation and FAAB adjustments per team
- **Excel import** - Import historical roster data from Excel spreadsheets
- **LINE Bot reminders** - Send keeper deadline reminders to the league LINE group

### Player Database
- **Yahoo Fantasy integration** - Live OR (Overall Rank) and AR (Actual Rank) from Yahoo API
- **MLB Stats API proxy** - Player career stats (MLB + MiLB) via official MLB Stats API
- **Multi-season stats** - Current season, last week, last month, today, and previous season
- **Top 100 Prospects** - MLB Pipeline prospect rankings with team/position data
- **Contract overlay** - See current + next-year contract status for every player
- **Advanced filtering** - By position, owner, contract type, free agent status

### Analytics
- **Draft analysis** - Historical draft pick value, hit rates, and position preferences
- **FAAB spending patterns** - Bidding history and acquisition costs
- **Trade statistics** - Trade volume, values, and league-wide activity
- **Salary rankings** - Team-by-team salary distribution and cap space
- **Multi-year support** - Analytics spanning 2014-2026 (10 seasons of data)

### League Overview
- **Year-by-year snapshots** - Complete league state for each season
- **In-season roster view** - Current Yahoo rosters with MLB team distribution
- **Keeper results** - Published keeper lists with financial summaries
- **Season countdown** - Draft day, opening day, weekly, and playoff countdowns

### Notifications
- **LINE Bot integration** - Group notifications for keeper deadlines
- **Scheduled reminders** - Every 3 days during keeper selection window (configurable)
- **Rookie call-up monitor** - Detects R-contract player MLB debuts (planned)

### Security
- **Yahoo OAuth2** - League members authenticate via their Yahoo Fantasy accounts
- **JWT via HttpOnly Cookie** - Secure token storage (not localStorage)
- **Role-based access** - Public, authenticated, and commissioner-level endpoints
- **Security headers** - X-Frame-Options, HSTS, Referrer-Policy, etc.

---

## Screenshots

> TODO: Add screenshots of key pages

---

## Architecture

```
                          +-------------------+
                          |   Yahoo Fantasy   |
                          |      API          |
                          +--------+----------+
                                   |
                                   v
+------------------+     +-------------------+     +------------------+
|   Next.js 15     | <-> |   FastAPI Backend  | <-> |   PostgreSQL     |
|   React 19       |     |   Python 3.11     |     |   (production)   |
|   Tailwind v4    |     |   Contract Engine  |     |   SQLite (dev)   |
+------------------+     +-------------------+     +------------------+
        |                         |
        |                         v
        |                +-------------------+
        |                |   LINE Bot API    |
        |                |   MLB Stats API   |
        |                +-------------------+
        v
  Browser (SWR cache)
```

### Data Flow

```
Historical Excel Rosters + Yahoo API (draft/transactions/rosters)
    |
    v
Contract Reconstruction Engine (scripts/rebuild_with_correct_mapping.py)
    |
    v
Contract JSON (data/20XX_contracts_v2.json)
    |
    v
Database Loader (scripts/load_20XX_contracts.py)
    |
    v
PostgreSQL / SQLite Database
    |
    v
FastAPI Backend (api/)
    |
    v
Next.js Frontend (keeper selection, analytics, player database)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, TypeScript 5.7, Tailwind CSS v4, SWR |
| Backend | FastAPI, Python 3.11, Uvicorn |
| Database | PostgreSQL (production), SQLite (development) |
| Auth | Yahoo OAuth2 + JWT (HttpOnly Cookie) |
| Notifications | LINE Messaging API, APScheduler |
| External APIs | Yahoo Fantasy API, MLB Stats API |
| Deployment | Docker, Zeabur (Tokyo) |

---

## Contract System

The league uses a **1+1+X contract system** where players progress through contract types:

| Type | Description | Can Keep? | Occupies Active Slot? |
|------|------------|-----------|----------------------|
| **A** | 1st year (draft/FAAB acquisition) | Yes | Yes |
| **B** | 2nd year (kept from A) | Yes | Yes |
| **N(x)** | Extension (x years remaining) | Mandatory | Yes |
| **O** | Expiring (final year, then FA) | No | Yes |
| **R** | Farm rookie (minor league eligible) | Yes | No (farm slot) |
| **FA** | Free agent | N/A | N/A |

### Contract Flow

```
Draft / FAAB Pickup
      |
      v
  A contract (year 1)
      |
      +--[keep]--> B contract (year 2)
      |               |
      |               +--[keep]--> O contract (expiring) --> FA
      |               |
      |               +--[extend N years]--> N(x) contract
      |                                        |
      |                                        +--> N(x-1) --> ... --> N(1) --> O --> FA
      |
      +--[release]--> FA
      |
      +--[designate rookie]--> R contract (farm)
                                 |
                                 +--[keep]--> R (stays in farm)
                                 +--[activate]--> A contract
                                 +--[release]--> FA
```

### Extension Pricing

When extending a B-contract, the salary increases by **$5 per extension year**:

- B/$20 + extend 3 years = **N3/$35** (then N2/$35 -> N1/$35 -> O/$35 -> FA)
- Salary remains **fixed** throughout the extension period

### Buyout Rules

| Type | Salary Cap Cost | FAAB Cost | Duration |
|------|----------------|-----------|----------|
| Normal | Full salary/year | - | Remaining years |
| FAAB | floor(salary/2)/year | ceil(salary/2)/year | Remaining years |

---

## League Rules

### Salary Cap

```
salary_cap = $300 + (year - 2024 + 1) * $5
```

| Year | Base Cap | With Ranking Bonus (1st place) |
|------|----------|-------------------------------|
| 2025 | $310 | $320 |
| 2026 | $315 | $325 |
| 2027 | $320 | $330 |

### Ranking Bonus (from previous season playoffs)

| Place | Bonus |
|-------|-------|
| 1st | +$10 |
| 2nd | +$7 |
| 3rd | +$5 |
| 4th | +$3 |
| 5th | +$2 |
| 6th | +$1 |

### Roster Structure

| Category | Positions | Count |
|----------|----------|-------|
| Active (hitters) | C, 1B, 2B, 3B, SS, IF, LF, CF, RF, OF, UT, UT | 12 |
| Pitchers | SP x4, RP x3, P x3 | 10 |
| Bench | BN x5 | 5 |
| Minor League | NA x2 | 2 |
| Injured | DL x4 | 4 |

### Keeper Limits

| Type | Min | Max |
|------|-----|-----|
| Active Keepers (A/B/N) | 12 | 15 |
| Farm Rookies (R) | 0 | 2 |

### FAAB (Free Agent Acquisition Budget)

- Annual budget: **$100**
- Minimum bid: **$1** ($0 bids are invalid)
- Shutout bonus: **+$10** (H2H shutout)

### Rookie Eligibility (R Contract)

| Stat | Threshold |
|------|-----------|
| Innings Pitched (IP) | > 50 IP loses eligibility |
| Plate Appearances (PA) | > 130 PA loses eligibility |

### Scoring Format

**H2H 7x7**

| Hitting | Pitching |
|---------|----------|
| R, H, HR, RBI, SB, AVG, OPS | W, SV, HLD, K, ERA, WHIP, QS |

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+ (v24 recommended)
- PostgreSQL (production) or SQLite (development)
- Yahoo Fantasy API credentials ([Yahoo Developer Console](https://developer.yahoo.com/apps/))
- LINE Bot credentials (optional, for notifications)

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/fantasy-keeper-league.git
cd fantasy-keeper-league

# Backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
cd ..
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required variables:
- `YAHOO_CLIENT_ID` / `YAHOO_CLIENT_SECRET` - Yahoo OAuth2 app credentials
- `YAHOO_LEAGUE_ID` - Your Yahoo Fantasy league ID (e.g., `469.l.80910`)
- `JWT_SECRET_KEY` - Random 32+ character string for JWT signing
- `OAUTH_REDIRECT_URI` - OAuth callback URL
- `FRONTEND_URL` - Frontend URL for post-login redirect

### 3. Initialize Data

```bash
# Option A: Import from Excel roster file
python scripts/import_excel.py "path/to/roster.xlsx"

# Option B: Fetch from Yahoo API (requires OAuth setup)
python scripts/fetch_historical_yahoo.py

# Rebuild contracts from Yahoo data
python scripts/rebuild_with_correct_mapping.py

# Load contracts to database
python scripts/load_2026_contracts.py
```

### 4. Start Development Servers

```bash
# Terminal 1: Backend (port 8002)
python -m uvicorn api.main:app --port 8002

# Terminal 2: Frontend (port 3001)
cd frontend
npx next dev -p 3001
```

> **Note:** Do NOT use `--reload` flag with uvicorn - it causes worker process issues in certain environments.

### 5. Access the App

- Frontend: http://localhost:3001
- Backend API: http://localhost:8002/api
- API Docs: http://localhost:8002/docs

---

## Project Structure

```
fantasy-keeper-league/
+-- api/                          # FastAPI backend
|   +-- main.py                   # App entry + lifespan
|   +-- database.py               # DB init + migrations
|   +-- dependencies.py           # Auth middleware
|   +-- yahoo_service.py          # Yahoo API integration
|   +-- routers/
|       +-- auth.py               # Yahoo OAuth + JWT
|       +-- teams.py              # Roster & keeper management
|       +-- league.py             # League snapshots
|       +-- commissioner.py       # Admin operations
|       +-- players.py            # MLB Stats API proxy
|       +-- analytics.py          # League statistics
|       +-- public.py             # Public endpoints
+-- config/
|   +-- settings.py               # League rules & constants
+-- src/
|   +-- contract/
|   |   +-- engine.py             # Contract calculation logic
|   |   +-- models.py             # Data models
|   +-- notification/
|   |   +-- scheduler.py          # APScheduler jobs
|   |   +-- line_service.py       # LINE Bot integration
|   |   +-- reminder.py           # Reminder logic
|   +-- analytics/
|       +-- draft_stats.py        # Draft analysis
+-- frontend/                     # Next.js 15 app
|   +-- src/
|       +-- app/                  # App Router pages
|       |   +-- [year]/           # League overview
|       |   +-- [year]/[teamId]/  # Keeper selection
|       |   +-- commissioner/     # Admin dashboard
|       |   +-- players/          # Player database
|       |   +-- analytics/        # League analytics
|       |   +-- rules/            # Rules reference
|       +-- components/           # Reusable UI components
|       +-- lib/                  # Utilities & hooks
|       +-- types/                # TypeScript definitions
+-- scripts/                      # ETL & utility scripts (38+)
+-- data/                         # JSON data files
+-- Dockerfile                    # Container image
+-- start.sh                      # Container startup
+-- requirements.txt              # Python dependencies
+-- CLAUDE.md                     # League rules reference
```

---

## API Reference

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/auth/yahoo/login` | - | Redirect to Yahoo OAuth |
| GET | `/api/auth/yahoo/callback` | - | OAuth callback handler |
| GET | `/api/auth/me` | JWT | Current user info |
| POST | `/api/auth/logout` | - | Clear auth cookie |

### League

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/league/settings` | - | League configuration |
| GET | `/api/league/years` | - | Available years |
| GET | `/api/league/{year}` | JWT | Full league snapshot |
| GET | `/api/league/{year}/summary` | JWT | League summary |
| GET | `/api/league/{year}/keeper-results` | JWT | Keeper submission results |

### Teams

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/teams/` | - | List all teams |
| GET | `/api/teams/{id}/roster/{year}` | JWT | Team roster |
| GET | `/api/teams/{id}/keeper-options/{year}` | JWT | Keeper decision options |
| GET | `/api/teams/{id}/keeper-selections/{year}` | JWT | Saved selections |
| PUT | `/api/teams/{id}/keeper-selections/{year}` | JWT | Update selections (auto-save) |
| POST | `/api/teams/{id}/keeper-submit/{year}` | JWT | Submit & lock |

### Commissioner (requires commissioner role)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/commissioner/import-excel` | Upload Excel roster |
| GET | `/api/commissioner/submissions/{year}` | All submission statuses |
| POST | `/api/commissioner/approve/{year}/{team_id}` | Approve submission |
| POST | `/api/commissioner/unlock/{year}/{team_id}` | Unlock for resubmission |
| POST | `/api/commissioner/assign-team` | Assign user to team |
| GET/PUT | `/api/commissioner/team-adjustments/{team_id}` | Team adjustments |
| GET/POST | `/api/commissioner/buyouts/{year}` | Buyout management |
| POST | `/api/commissioner/reminders/{year}/send` | Send LINE reminders |

### Players

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/players/stats` | - | MLB Stats API proxy |

### Analytics

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/analytics/draft-stats` | - | Draft analysis |
| GET | `/api/analytics/faab-stats` | - | FAAB spending |
| GET | `/api/analytics/trade-stats` | - | Trade statistics |
| GET | `/api/analytics/salary-rankings` | - | Salary rankings |
| GET | `/api/analytics/contract-values` | JWT | Contract values |
| GET | `/api/analytics/league-summary` | JWT | League summary |

---

## Database

### Migration System

The project uses a lightweight, custom migration system (not Alembic):

- Migrations are defined in `api/database.py` as a `MIGRATIONS` dict
- Tracked via `schema_migrations` table (version + applied_at)
- Auto-applied on startup via `init_db()`
- Each SQL statement must be **idempotent** (use `IF NOT EXISTS`)

### Current Migrations

| Version | Description |
|---------|-------------|
| 001 | Add LINE name to users |
| 002 | Performance indexes (5) |
| 003 | Foreign key constraints (6) |
| 004 | Buyouts table |
| 005 | Yahoo OAuth tokens |
| 006 | Player rankings |
| 007 | AR rank column |
| 008 | AB/IP stat columns |
| 009-014 | Player status, owner/manager, weekly standings, synced rosters, etc. |

### Adding a New Migration

```python
# In api/database.py, add to MIGRATIONS dict:
MIGRATIONS = {
    # ... existing migrations ...
    "015_your_migration": [
        "ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...;",
    ],
}
```

---

## Deployment

### Docker

```bash
docker build -t keeper-league .
docker run -p 8002:8002 --env-file .env keeper-league
```

### Zeabur (Current Production)

- Push to `master` triggers automatic redeployment
- Backend: `fantasybaseball-keeperleague.zeabur.app`
- Frontend: `5man-keeperleague.zeabur.app`

### Startup Sequence

```
1. start.sh: Load contract JSON -> DB
2. lifespan: init_db() -> Create tables + run migrations
3. lifespan: seed_if_empty() -> Auto-seed on first deploy
4. lifespan: cleanup_old_notifications(365) -> Prune old records
5. lifespan: start_scheduler() -> Start APScheduler
6. uvicorn: Accept requests
```

---

## Development

### Key Commands

```bash
# Frontend
cd frontend && npm run dev          # Dev server (port 3001)
cd frontend && npm run build        # Production build check

# Backend
python -m uvicorn api.main:app --port 8002   # API server

# Data Scripts
python scripts/rebuild_with_correct_mapping.py  # Rebuild contracts
python scripts/load_2026_contracts.py           # Load to DB
python scripts/fetch_transactions.py            # Fetch Yahoo data
```

### Naming Conventions

- Farm rookies: `farm_rookie` (code) / "Farm Rookie" (UI)
- Contract display: `$salary/type` (e.g., `$20/A`, `$35/N3`, `$5/R`)
- UI language: Traditional Chinese with English terms (e.g., "Keep", "Extend")
- Code: English variables and comments

### Frontend Validation Constants

These must stay in sync with `config/settings.py`:

```typescript
// frontend/src/lib/validation.ts
const KEEPER_ACTIVE_MIN = 12;
const KEEPER_ACTIVE_MAX = 15;
const KEEPER_BENCH_MAX = 2;
const EXTENSION_COST_PER_YEAR = 5;
```

---

## Adapting for Your League

This system was built for a specific 16-team keeper league, but can be adapted:

1. **League rules** - Modify `config/settings.py` for your league's salary cap, roster structure, scoring, etc.
2. **Contract types** - The contract engine in `src/contract/engine.py` supports the A-B-N-O-R system; modify for your contract structure
3. **Yahoo integration** - Update `YAHOO_LEAGUE_ID` in `.env` for your Yahoo league
4. **Manager mapping** - Update the manager name mapping in `config/settings.py`
5. **UI text** - Frontend is in Traditional Chinese; modify component text for your language

---

## Claude Code Development Context

This project includes a comprehensive `CLAUDE.md` file (20 sections, 600+ lines) that serves as a complete rules reference and development guide. It enables AI-assisted development with full context about:

- All league rules and contract mechanics
- API endpoint specifications
- Database schema and migration system
- Deployment configuration
- Manager name mappings

The file is designed to be used with [Claude Code](https://claude.ai/claude-code) for ongoing development and maintenance.

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (conventional commit format preferred)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is open source. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- Built with [Claude Code](https://claude.ai/claude-code) by Anthropic
- Yahoo Fantasy API for live league data
- MLB Stats API for player statistics
- LINE Messaging API for group notifications
