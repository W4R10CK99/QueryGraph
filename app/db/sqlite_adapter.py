"""
app/db/sqlite_adapter.py

SQLite adapter — wraps aiosqlite for async access.

Install: pip install aiosqlite
"""

import logging
import aiosqlite

from app.db.base import BaseDBAdapter
from app.config import settings

logger = logging.getLogger(__name__)


class SQLiteAdapter(BaseDBAdapter):

    def __init__(self):
        self._conn: aiosqlite.Connection | None = None
        self._db_path = settings.db_path

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        logger.info("SQLite connecting to: %s", self._db_path)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row   # rows behave like dicts
        logger.info("SQLite connected.")

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("SQLite disconnected.")

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def get_schema(self) -> dict:
        """
        Introspects the SQLite file using sqlite_master + PRAGMA table_info.
        Returns the standard schema dict defined in BaseDBAdapter.
        """
        self._require_connection()
        schema = {}

        # List all user tables (exclude SQLite internal tables)
        async with self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ) as cursor:
            tables = [row[0] async for row in cursor]

        for table in tables:
            async with self._conn.execute(f"PRAGMA table_info({table})") as cursor:
                columns = [
                    {"name": row["name"], "type": row["type"]}
                    async for row in cursor
                ]
            schema[table] = {"columns": columns}

        return schema

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def run_query(self, query: str) -> list[dict]:
        self._require_connection()
        logger.debug("SQLite query: %s", query)
        try:
            async with self._conn.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error("SQLite query error: %s | Query: %s", e, query)
            raise RuntimeError(f"SQLite query failed: {e}") from e

    # ------------------------------------------------------------------
    # Health check override (cheaper than a full query)
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        try:
            self._require_connection()
            async with self._conn.execute("SELECT 1"):
                return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_connection(self):
        if self._conn is None:
            raise RuntimeError("SQLiteAdapter: connect() has not been called.")