"""First-run database setup for the desktop app: the database and the least-privilege runtime role the row-level security relies on.

docker-compose does this through the Postgres image (POSTGRES_DB) and apps/api/postgres-init/01-runtime-role.sh; this is the same thing
for a Postgres that was started without Docker. Idempotent: running it again changes nothing but the role password, which is set to the
current one. The password comes from the environment, never the command line.
"""

import asyncio
import os
from urllib.parse import urlsplit, urlunsplit

import asyncpg


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


async def main() -> None:
    url = urlsplit(os.environ["NEXUS_SETUP_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    name = url.path.lstrip("/")
    admin = await asyncpg.connect(urlunsplit(url._replace(path="/postgres")))
    try:
        if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await admin.execute(f"CREATE DATABASE {quote_identifier(name)}")
        exists = await admin.fetchval("SELECT 1 FROM pg_roles WHERE rolname = 'nexus_runtime'")
        verb = "ALTER" if exists else "CREATE"
        await admin.execute(f"{verb} ROLE nexus_runtime LOGIN INHERIT NOBYPASSRLS PASSWORD {quote_literal(os.environ['NEXUS_RUNTIME_DB_PASSWORD'])}")
    finally:
        await admin.close()


asyncio.run(main())
