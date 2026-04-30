"""
mcp_server/server.py

FastMCP server — fully database-agnostic.

Previously this file was hardcoded to SQLite via sqlite3.
Now it delegates entirely to the adapter chosen by DB_TYPE in .env.

Switching databases:
    Set DB_TYPE=postgresql (or mysql / mongodb / sqlite) in your .env.
    Nothing in this file needs to change.

Tools exposed to the orchestrator:
    health_check()          → liveness + which DB engine is active
    get_schema()            → tables/collections + columns
    run_sql(sql)            → execute a query (SQL string or Mongo JSON)
"""

import asyncio
import logging

from fastmcp import FastMCP

from app.config import settings
from app.db.factory import get_adapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("fastquery-tools")

# ---------------------------------------------------------------------------
# Adapter singleton
# ---------------------------------------------------------------------------
# get_adapter() is cached via lru_cache — always returns the same instance.
_adapter = get_adapter()


# ---------------------------------------------------------------------------
# Startup / teardown
#
# FastMCP doesn't have a native lifespan hook, so we connect synchronously
# in a module-level block using asyncio.run — this runs before mcp.run().
# ---------------------------------------------------------------------------
async def _startup():
    await _adapter.connect()
    logger.info(
        "MCP server ready. DB engine: %s | DSN: %s",
        settings.db_type.value,
        _redact_dsn(settings.dsn()),
    )

def _redact_dsn(dsn: str) -> str:
    """Hide password in DSN for safe logging."""
    import re
    return re.sub(r":[^:@]+@", ":***@", dsn)


# ---------------------------------------------------------------------------
# Tool 1: Health check
# ---------------------------------------------------------------------------
@mcp.tool()
async def health_check() -> dict:
    """
    Returns server liveness status and which database engine is active.
    Also performs a lightweight DB ping so the orchestrator can detect
    connectivity issues before running real queries.
    """
    db_alive = await _adapter.health_check()
    return {
        "status":    "ok" if db_alive else "degraded",
        "server":    "fastquery-tools",
        "db_engine": settings.db_type.value,
        "db_alive":  db_alive,
    }


# ---------------------------------------------------------------------------
# Tool 2: Schema introspection
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_schema() -> dict:
    """
    Returns the schema of all tables (SQL) or collections (MongoDB).

    Return format:
        {
            "table_name": {
                "columns": [
                    {"name": "col", "type": "TEXT"},
                    ...
                ]
            },
            ...
        }

    The planner agent uses this to know which tables/columns exist so it
    can generate valid widget intent objects.
    """
    try:
        schema = await _adapter.get_schema()
        return schema
    except Exception as e:
        logger.error("get_schema failed: %s", e, exc_info=True)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool 3: Run query
# ---------------------------------------------------------------------------
@mcp.tool()
async def run_sql(sql: str) -> list | dict:
    """
    Executes a query against the configured database.

    For SQL databases  (SQLite / PostgreSQL / MySQL):
        `sql` is a plain SELECT string.

    For MongoDB:
        `sql` is a JSON string:
        {
            "collection": "orders",
            "pipeline":   [ { "$group": ... }, ... ]
        }

    Safety guardrails for SQL:
        - Only SELECT statements are accepted (enforced by query_builder.py,
          but double-checked here as a defence-in-depth measure).
        - Non-SELECT SQL is rejected with an error dict (not an exception)
          so the orchestrator can surface it gracefully.

    Returns:
        A list of row dicts on success.
        {"error": "<message>"} on failure — never raises, so one bad widget
        doesn't crash the whole dashboard pipeline.
    """
    import json as _json

    # ----- MongoDB: no SQL restriction needed ----------------------------
    if settings.db_type.value == "mongodb":
        try:
            _json.loads(sql)   # validate it parses as JSON
        except _json.JSONDecodeError:
            return {"error": "MongoDB adapter expects a JSON pipeline string, not raw SQL."}

        try:
            return await _adapter.run_query(sql)
        except Exception as e:
            logger.error("run_sql (mongo) failed: %s", e, exc_info=True)
            return {"error": str(e)}

    # ----- SQL databases: enforce SELECT-only ----------------------------
    if not sql.strip().lower().startswith("select"):
        logger.warning("Non-SELECT query rejected: %s", sql[:100])
        return {"error": "Only SELECT queries are permitted."}

    try:
        return await _adapter.run_query(sql)
    except Exception as e:
        logger.error("run_sql failed: %s | Query: %s", e, sql, exc_info=True)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(_startup())
    mcp.run()