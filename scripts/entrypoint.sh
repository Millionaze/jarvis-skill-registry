#!/bin/sh
# Bring the stack up with zero manual steps: migrate, seed, serve.
set -e

echo "==> applying database migrations"
alembic upgrade head

echo "==> seeding fixture organizations and users"
python -m app.seed

echo "==> starting api on 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
