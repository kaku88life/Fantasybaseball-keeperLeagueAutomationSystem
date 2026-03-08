#!/bin/bash
# Zeabur backend startup script
# 1. Initialize DB tables (idempotent)
# 2. Load contract data if DB is empty (first deploy)
# 3. Start uvicorn

set -e

echo "=== Keeper League API - Startup ==="

# Ensure DB directory exists
DB_PATH="${DATABASE_PATH:-data/keeper_league.db}"
DB_DIR=$(dirname "$DB_PATH")
mkdir -p "$DB_DIR"
echo "DB path: $DB_PATH"

# Initialize DB schema (idempotent - safe to run every time)
echo "Initializing database schema..."
python -c "from api.database import init_db; import asyncio; asyncio.run(init_db())"

# Check if league data already exists; if not, load 2026 contracts
HAS_DATA=$(python -c "
from api.database import get_db
conn = get_db()
try:
    row = conn.execute('SELECT COUNT(*) FROM league_snapshots').fetchone()
    print(row[0])
except:
    print(0)
finally:
    conn.close()
")

if [ "$HAS_DATA" = "0" ]; then
    echo "No league data found. Loading 2026 contracts..."
    python -m scripts.load_2026_contracts
    echo "Contract data loaded successfully."
else
    echo "League data already present ($HAS_DATA snapshots). Skipping load."
fi

# Start uvicorn
PORT="${PORT:-8002}"
echo "Starting uvicorn on port $PORT..."
exec uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
