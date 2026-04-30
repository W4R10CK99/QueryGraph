"""
app/db/postgresql_adapter.py

PostgreSQL adapter — uses asyncpg for true async + connection pooling.

Install: pip install asyncpg
"""

import logging
import asyncpg

from app.db.base import BaseDBAdapter
from app.config import settings

logger = logging.getLogger(__name__)


class PostgreSQLAdapter(BaseDBAdapter):

    def __init__(self):
        self._pool: asyncpg.Pool | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        logger.info(
            "PostgreSQL connecting to %s:%s/%s",
            settings.db_host, settings.db_port, settings.db_name,
        )
        self._pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
            command_timeout=settings.db_query_timeout_seconds,
        )
        logger.info("PostgreSQL pool ready.")

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL pool closed.")

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def get_schema(self) -> dict:
        """
        Introspects information_schema for all user tables + their columns.
        Excludes system schemas (pg_*, information_schema).
        """
        self._require_pool()

        query = """
            SELECT
                c.table_name,
                c.column_name,
                c.data_type
            FROM information_schema.columns c
            JOIN information_schema.tables t
                ON c.table_name = t.table_name
                AND c.table_schema = t.table_schema
            WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
              AND t.table_type = 'BASE TABLE'
            ORDER BY c.table_name, c.ordinal_position
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query)

        schema: dict = {}
        for row in rows:
            table = row["table_name"]
            schema.setdefault(table, {"columns": []})
            schema[table]["columns"].append({
                "name": row["column_name"],
                "type": row["data_type"],
            })

        return schema

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def run_query(self, query: str) -> list[dict]:
        self._require_pool()
        logger.debug("PostgreSQL query: %s", query)
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error("PostgreSQL query error: %s | Query: %s", e, query)
            raise RuntimeError(f"PostgreSQL query failed: {e}") from e

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        try:
            self._require_pool()
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    def _health_query(self) -> str:
        return "SELECT 1"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_pool(self):
        if self._pool is None:
            raise RuntimeError("PostgreSQLAdapter: connect() has not been called.")