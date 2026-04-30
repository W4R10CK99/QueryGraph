"""
app/db/factory.py

Single import point for database access across the entire application.

Usage everywhere (orchestrator, MCP server, health routes):

    from app.db.factory import get_adapter

    adapter = get_adapter()          # returns the singleton for configured DB
    await adapter.connect()          # call once at startup
    schema = await adapter.get_schema()
    rows   = await adapter.run_query("SELECT ...")

Adding a new database engine:
    1. Create app/db/your_adapter.py  (subclass BaseDBAdapter)
    2. Add an entry to DBType enum in config.py
    3. Add a branch in _build_adapter() below
    That's it — nothing else in the codebase needs to change.
"""

import logging
from functools import lru_cache

from app.config import settings, DBType
from app.db.base import BaseDBAdapter

logger = logging.getLogger(__name__)


def _build_adapter() -> BaseDBAdapter:
    """Instantiate the correct adapter based on settings.db_type."""

    db_type = settings.db_type
    logger.info("Building DB adapter for type: %s", db_type)

    if db_type == DBType.SQLITE:
        from app.db.sqlite_adapter import SQLiteAdapter
        return SQLiteAdapter()

    if db_type == DBType.POSTGRESQL:
        from app.db.postgresql_adapter import PostgreSQLAdapter
        return PostgreSQLAdapter()

    if db_type == DBType.MYSQL:
        from app.db.mysql_adapter import MySQLAdapter
        return MySQLAdapter()

    if db_type == DBType.MONGODB:
        from app.db.mongodb_adapter import MongoDBAdapter
        return MongoDBAdapter()

    raise ValueError(
        f"Unsupported DB_TYPE: {db_type!r}. "
        f"Valid options: {[e.value for e in DBType]}"
    )


@lru_cache(maxsize=1)
def get_adapter() -> BaseDBAdapter:
    """
    Returns the module-level singleton adapter.
    lru_cache ensures _build_adapter() is called exactly once regardless
    of how many times get_adapter() is called across the codebase.
    """
    return _build_adapter()