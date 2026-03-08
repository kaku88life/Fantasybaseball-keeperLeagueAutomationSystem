#!/bin/bash
# Zeabur backend startup script
# DB initialization and seeding are handled by FastAPI lifespan (api/main.py)

set -e

echo "=== Keeper League API - Startup ==="

# Start uvicorn
PORT="${PORT:-8002}"
echo "Starting uvicorn on port $PORT..."
exec uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
