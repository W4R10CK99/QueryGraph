import json
import asyncio
import logging
from contextlib import asynccontextmanager

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.query_builder import generate_sql
from app.agents.planner_agent import plan_dashboard_async

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons
#
# FIX: The original code created a new MultiServerMCPClient (and therefore
# spawned a new subprocess) on every single request. This is expensive —
# each call paid the full process fork + startup cost of server.py.
#
# We now hold one client and one cached schema for the lifetime of the app.
# These are initialised by the FastAPI lifespan in main.py.
# ---------------------------------------------------------------------------
_mcp_client: MultiServerMCPClient | None = None
_tool_map: dict = {}
_cached_schema: dict | list | None = None


async def init_mcp():
    """
    Called once at application startup (via FastAPI lifespan).
    Initialises the MCP client, fetches tool list, and caches the schema.
    """
    global _mcp_client, _tool_map, _cached_schema

    logger.info("Initialising MCP client...")
    _mcp_client = MultiServerMCPClient(
        {
            "fastquery": {
                "transport": "stdio",
                "command": "python",
                "args": ["mcp_server/server.py"],
            }
        }
    )

    tools = await _mcp_client.get_tools()
    _tool_map = {tool.name: tool for tool in tools}
    logger.info("MCP tools available: %s", list(_tool_map.keys()))

    # Cache schema — it doesn't change between requests
    raw_schema = await _tool_map["get_schema"].ainvoke({})
    _cached_schema = _unwrap_mcp_response(raw_schema)
    logger.info("Schema cached: %s", _cached_schema)


async def teardown_mcp():
    """Called at application shutdown."""
    global _mcp_client
    if _mcp_client is not None:
        # Close underlying connections if the client supports it
        if hasattr(_mcp_client, "aclose"):
            await _mcp_client.aclose()
        _mcp_client = None
    logger.info("MCP client shut down.")


# ---------------------------------------------------------------------------
# MCP response unwrapper
#
# FIX: Added explicit exception type and logging so failures aren't silent.
# ---------------------------------------------------------------------------
def _unwrap_mcp_response(result):
    """
    Converts MCP tool output:
        [{"type": "text", "text": "...json..."}]
    into a native Python object.
    """
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict) and "text" in first:
            text = first["text"]
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.debug("MCP response is plain text (not JSON): %s", text[:200])
                return text

    return result


# ---------------------------------------------------------------------------
# Per-widget SQL execution with error isolation
#
# FIX: If one widget's SQL fails, it should not crash the entire pipeline.
# We catch exceptions per widget and mark those widgets with an error state.
# The frontend can then show a "failed to load" tile rather than a blank page.
# ---------------------------------------------------------------------------
async def _execute_widget(widget: dict) -> dict:
    """
    Builds SQL for a single widget, runs it via MCP, and attaches the result.
    Returns the widget dict (mutated in-place for convenience).
    """
    if "metric" not in widget:
        # Table widgets or widgets with no metric don't need SQL
        widget["data"] = []
        return widget

    try:
        intent = {
            # FIX: All fields now come from the planner — no hardcoded defaults
            # for operation or filters. The planner_agent prompt was updated to
            # return these fields explicitly.
            "table":     widget.get("table", "sales"),
            "metric":    widget["metric"],
            "group_by":  widget.get("group_by", []),
            "filters":   widget.get("filters", {}),
            "operation": widget.get("operation", "sum"),
            "limit":     widget.get("limit"),
            "sort":      widget.get("sort"),
        }

        sql = generate_sql(intent)
        widget["sql"] = sql

        raw_data = await _tool_map["run_sql"].ainvoke({"sql": sql})
        widget["data"] = _unwrap_mcp_response(raw_data)

    except Exception as e:
        logger.error(
            "Widget [%s] '%s' failed: %s",
            widget.get("id", "?"),
            widget.get("title", "?"),
            e,
            exc_info=True,
        )
        widget["data"] = []
        widget["error"] = str(e)  # Surface to frontend for graceful degradation

    return widget


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
async def run_pipeline(user_query: str) -> dict:
    if _cached_schema is None:
        raise RuntimeError("MCP not initialised. Ensure init_mcp() ran at startup.")

    logger.info("Pipeline start — query: %r", user_query)

    # Step 1: Planner (async wrapper so it doesn't block the event loop)
    dashboard_plan = await plan_dashboard_async(user_query, _cached_schema)
    logger.info(
        "Planner produced %d widgets for: %r",
        len(dashboard_plan.get("widgets", [])),
        user_query,
    )

    # Step 2: Execute all widget queries concurrently
    # FIX: asyncio.gather runs all SQL calls in parallel rather than sequentially.
    tasks = [_execute_widget(widget) for widget in dashboard_plan.get("widgets", [])]
    await asyncio.gather(*tasks)

    return {"dashboard": dashboard_plan}