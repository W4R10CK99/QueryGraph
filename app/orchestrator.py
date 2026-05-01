import json
import asyncio
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.query_builder import generate_sql
from app.agents.planner_agent import plan_dashboard_async

logger = logging.getLogger(__name__)

_mcp_client: MultiServerMCPClient | None = None
_tool_map: dict = {}
_cached_schema: dict | list | None = None


async def init_mcp():
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

    raw_schema = await _tool_map["get_schema"].ainvoke({})
    _cached_schema = _unwrap_mcp_response(raw_schema)

    if not isinstance(_cached_schema, dict) or "error" in _cached_schema:
        raise RuntimeError(f"Schema load failed: {_cached_schema}")

    if not _cached_schema:
        raise RuntimeError("Schema load failed: empty schema returned from MCP server.")

    logger.info("Schema cached: %s", _cached_schema)


async def teardown_mcp():
    global _mcp_client
    if _mcp_client is not None:
        if hasattr(_mcp_client, "aclose"):
            await _mcp_client.aclose()
        _mcp_client = None
    logger.info("MCP client shut down.")


def _unwrap_mcp_response(result):
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


def _fallback_dashboard(schema: dict, user_query: str) -> dict:
    first_table = next(iter(schema.keys())) if isinstance(schema, dict) and schema else "sales"
    return {
        "title": f"Dashboard for {user_query}",
        "widgets": [
            {
                "id": "w1",
                "type": "kpi_card",
                "title": "Total Sales",
                "table": first_table,
                "metric": "sales",
                "operation": "sum",
                "group_by": [],
                "filters": {},
                "sort": None,
                "limit": None,
                "chart": "bar",
                "priority": 1,
            },
            {
                "id": "w2",
                "type": "table",
                "title": "Raw Data",
                "table": first_table,
                "metric": "sales",
                "operation": "sum",
                "group_by": [],
                "filters": {},
                "sort": None,
                "limit": 20,
                "chart": "bar",
                "priority": 99,
            },
        ],
    }


async def _execute_widget(widget: dict) -> dict:
    if widget.get("type") == "table":
        widget["data"] = []
        return widget

    if "metric" not in widget:
        widget["data"] = []
        return widget

    try:
        intent = {
            "table": widget.get("table", "sales"),
            "metric": widget["metric"],
            "group_by": widget.get("group_by", []),
            "filters": widget.get("filters", {}),
            "operation": widget.get("operation", "sum"),
            "limit": widget.get("limit"),
            "sort": widget.get("sort"),
        }

        sql = generate_sql(intent)
        widget["sql"] = sql

        raw_data = await _tool_map["run_sql"].ainvoke({"sql": sql})
        widget["data"] = _unwrap_mcp_response(raw_data)

        if isinstance(widget["data"], dict) and "error" in widget["data"]:
            widget["error"] = widget["data"]["error"]
            widget["data"] = []

    except Exception as e:
        logger.error(
            "Widget [%s] '%s' failed: %s",
            widget.get("id", "?"),
            widget.get("title", "?"),
            e,
            exc_info=True,
        )
        widget["data"] = []
        widget["error"] = str(e)

    return widget


async def run_pipeline(user_query: str) -> dict:
    if _cached_schema is None:
        raise RuntimeError("MCP not initialised. Ensure init_mcp() ran at startup.")

    logger.info("Pipeline start — query: %r", user_query)

    dashboard_plan = await plan_dashboard_async(user_query, _cached_schema)

    widgets = dashboard_plan.get("widgets", [])
    if not isinstance(widgets, list) or len(widgets) == 0:
        logger.warning("Planner returned no widgets; using fallback dashboard.")
        dashboard_plan = _fallback_dashboard(_cached_schema, user_query)

    logger.info(
        "Planner produced %d widgets for: %r",
        len(dashboard_plan.get("widgets", [])),
        user_query,
    )

    tasks = [_execute_widget(widget) for widget in dashboard_plan.get("widgets", [])]
    await asyncio.gather(*tasks)

    return {"dashboard": dashboard_plan}