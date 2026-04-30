"""
app/db/mysql_adapter.py

MySQL adapter — uses aiomysql for async + connection pooling.

Install: pip install aiomysql
"""

import logging
import aiomysql

from app.db.base import BaseDBAdapter
from app.config import settings

logger = logging.getLogger(__name__)


class MySQLAdapter(BaseDBAdapter):

    def __init__(self):
        self._pool: aiomysql.Pool | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        logger.info(
            "MySQL connecting to %s:%s/%s",
            settings.db_host, settings.db_port, settings.db_name,
        )
        self._pool = await aiomysql.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            db=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            minsize=settings.db_pool_min,
            maxsize=settings.db_pool_max,
            connect_timeout=settings.db_query_timeout_seconds,
            autocommit=True,
            cursorclass=aiomysql.DictCursor,   # rows come back as dicts
        )
        logger.info("MySQL pool ready.")

    async def disconnect(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            logger.info("MySQL pool closed.")

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def get_schema(self) -> dict:
        """
        Uses information_schema to list tables and columns for the
        configured database.
        """
        self._require_pool()

        query = """
            SELECT
                c.TABLE_NAME  AS table_name,
                c.COLUMN_NAME AS column_name,
                c.DATA_TYPE   AS data_type
            FROM information_schema.COLUMNS c
            WHERE c.TABLE_SCHEMA = %s
            ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
        """

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, (settings.db_name,))
                rows = await cursor.fetchall()

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
        logger.debug("MySQL query: %s", query)
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query)
                    rows = await cursor.fetchall()
                    return list(rows)   # already dicts via DictCursor
        except Exception as e:
            logger.error("MySQL query error: %s | Query: %s", e, query)
            raise RuntimeError(f"MySQL query failed: {e}") from e

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        try:
            self._require_pool()
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
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
            raise RuntimeError("MySQLAdapter: connect() has not been called.")