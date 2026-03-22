#!/bin/bash
# Zeabur backend startup script
# DB initialization and seeding are handled by FastAPI lifespan (api/main.py)

set -e

echo "=== Keeper League API - Startup ==="

# Load/refresh 2026 contract data (post-draft) into DB
echo "Loading 2026 post-draft contracts..."
python -m scripts.update_2026_post_draft || echo "WARNING: 2026 post-draft loading failed, continuing..."

# Load/refresh 2027 contract projections into DB
echo "Loading 2027 contract projections..."
python -m scripts.build_2027_contracts || echo "WARNING: 2027 contract loading failed, continuing..."

# Seed buyout records (idempotent - skips existing)
echo "Seeding buyout records..."
python -m scripts.seed_2026_buyouts || echo "WARNING: Buyout seeding failed, continuing..."

# Start uvicorn
PORT="${PORT:-8002}"
echo "Starting uvicorn on port $PORT..."
exec uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
