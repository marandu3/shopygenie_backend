#!/bin/sh
set -e

echo "Waiting for the database to accept connections..."
python <<'PYEOF'
import asyncio
import os
import sys

import asyncpg


async def wait_for_db() -> None:
    dsn = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    for attempt in range(1, 31):
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            print("Database is ready.")
            return
        except Exception as exc:  # noqa: BLE001 - genuinely want to retry on anything here
            print(f"[{attempt}/30] Database not ready yet ({exc}); retrying in 2s...")
            await asyncio.sleep(2)
    print("Database did not become ready in time.", file=sys.stderr)
    sys.exit(1)


asyncio.run(wait_for_db())
PYEOF

echo "Applying database migrations..."
alembic upgrade head

echo "Seeding platform owner / permissions (idempotent)..."
python -m scripts.seed || echo "Seed step failed or was already applied — continuing."

echo "Starting application: $*"
exec "$@"
