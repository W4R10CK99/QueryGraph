"""
mcp_server/server.py

FastMCP server — database-agnostic.
"""

import asyncio
import json
import logging
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastmcp import FastMCP
from app.config import settings
from app.db.factory import get_adapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("fastquery-tools")

_adapter = get_adapter()
_connected = False
_connect_lock = asyncio.Lock()


async def _ensure_connected():
    global _connected
    if _connected:
        return

    async with _connect_lock:
        if _connected:
            return

        await _adapter.connect()
        _connected = True
        logger.info(
            "DB adapter connected. Engine: %s | DSN: %s",
            settings.db_type.value,
            _redact_dsn(settings.dsn()),
        )


def _redact_dsn(dsn: str) -> str:
    import re
    return re.sub(r":[^:@/]+@", ":***@", dsn)


@mcp.tool()
async def health_check() -> dict:
    try:
        await _ensure_connected()
        db_alive = await _adapter.health_check()
    except Exception as e:
        logger.error("health_check failed: %s", e, exc_info=True)
        db_alive = False

    return {
        "status": "ok" if db_alive else "degraded",
        "server": "fastquery-tools",
        "db_engine": settings.db_type.value,
        "db_alive": db_alive,
    }


@mcp.tool()
async def get_schema() -> dict:
    try:
        await _ensure_connected()
        schema = await _adapter.get_schema()
        return schema
    except Exception as e:
        logger.error("get_schema failed: %s", e, exc_info=True)
        return {"error": str(e)}


@mcp.tool()
async def run_sql(sql: str) -> list | dict:
    try:
        await _ensure_connected()

        if settings.db_type.value == "mongodb":
            try:
                json.loads(sql)
            except json.JSONDecodeError:
                return {"error": "MongoDB adapter expects a JSON pipeline string, not raw SQL."}
            return await _adapter.run_query(sql)

        if not sql.strip().lower().startswith("select"):
            logger.warning("Non-SELECT query rejected: %s", sql[:120])
            return {"error": "Only SELECT queries are permitted."}

        return await _adapter.run_query(sql)

    except Exception as e:
        logger.error("run_sql failed: %s | Query: %s", e, sql, exc_info=True)
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()