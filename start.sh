#!/bin/sh
set -e

# asyncpg doesn't support ?sslmode=require in the query string.
# Strip it and pass ssl via connect_args in the app instead.
# For Alembic we export a clean URL.
export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's/?sslmode=require//' | sed 's/&sslmode=require//' | sed 's/?channel_binding=require//' | sed 's/&channel_binding=require//')

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting AgentAuth server..."
exec uvicorn agentauth.api.server:app \
    --host 0.0.0.0 \
    --port 8080 \
    --workers 1
