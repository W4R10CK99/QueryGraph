import json
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.llm import parse_query
from app.query_builder import generate_sql
from app.dashboard_builder import build_dashboard


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

    tools = await client.get_tools()
    tool_map = {tool.name: tool for tool in tools}

    # --------------------------------------------
    # Tool: Schema
    # --------------------------------------------
    raw_schema = await tool_map["get_schema"].ainvoke({})
    schema = unwrap_mcp_response(raw_schema)

    print("Loaded Schema:", schema)

    # --------------------------------------------
    # LLM Intent
    # --------------------------------------------
    intent = parse_query(user_query)

    # --------------------------------------------
    # SQL
    # --------------------------------------------
    sql = generate_sql(intent)

    # --------------------------------------------
    # Tool: Run SQL
    # --------------------------------------------
    raw_data = await tool_map["run_sql"].ainvoke({"sql": sql})
    data = unwrap_mcp_response(raw_data)

    # --------------------------------------------
    # Dashboard
    # --------------------------------------------
    dashboard = build_dashboard(intent, data)

    return {
        "intent": intent,
        "sql": sql,
        "data": data,
        "dashboard": dashboard
    }