import json
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.query_builder import generate_sql
from app.agents.planner_agent import plan_dashboard

import logging
logger = logging.getLogger(__name__)

print("######## ORCHESTRATOR LOADED ########")


# ---------------------------------------------------
# Convert MCP wrapped responses to plain JSON
# ---------------------------------------------------
def unwrap_mcp_response(result):
    """
    Converts MCP tool output like:
    [{"type":"text","text":"...json..."}]

    into native python objects.
    """

    if isinstance(result, list) and len(result) > 0:
        first = result[0]

        if isinstance(first, dict) and "text" in first:
            text = first["text"]

            try:
                return json.loads(text)
            except:
                return text

    return result


# ---------------------------------------------------
# Main Pipeline
# ---------------------------------------------------
async def run_pipeline(user_query: str):
    client = MultiServerMCPClient(
        {
            "fastquery": {
                "transport": "stdio",
                "command": "python",
                "args": ["mcp_server/server.py"]
            }
        }
    )
    print("######## RUN_PIPELINE EXECUTED ########")
    tools = await client.get_tools()
    tool_map = {tool.name: tool for tool in tools}

    # Load schema
    raw_schema = await tool_map["get_schema"].ainvoke({})
    schema = unwrap_mcp_response(raw_schema)

    print("Loaded Schema:", schema)

    print("######## CALLING PLANNER ########")

    # ONLY planner agent
    dashboard_plan = plan_dashboard(user_query, schema)

    # Run each widget query
    for widget in dashboard_plan["widgets"]:

        if "metric" not in widget:
            continue

        intent = {
            "metric": widget.get("metric", "sales"),
            "group_by": widget.get("group_by", []),
            "filters": {},
            "operation": "sum",
            "limit": widget.get("limit"),
            "sort": widget.get("sort"),
            "chart": widget.get("chart", "bar"),
            "dashboard_meta": {}
        }

        sql = generate_sql(intent)

        raw_data = await tool_map["run_sql"].ainvoke({"sql": sql})
        data = unwrap_mcp_response(raw_data)

        widget["data"] = data
        widget["sql"] = sql

    return {
        "dashboard": dashboard_plan
    }