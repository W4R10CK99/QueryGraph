import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.llm import parse_query
from app.query_builder import generate_sql
from app.dashboard_builder import build_dashboard


# ---------------------------------------------------
# Async Pipeline
# ---------------------------------------------------
async def run_pipeline(user_query: str):

    # MCP Client
    client = MultiServerMCPClient(
        {
            "fastquery": {
                "transport": "stdio",
                "command": "python",
                "args": ["mcp_server/server.py"]
            }
        }
    )

    # ------------------------------------------------
    # Load Tools
    # ------------------------------------------------
    tools = await client.get_tools()

    tool_map = {tool.name: tool for tool in tools}

    # ------------------------------------------------
    # Tool 1: Schema
    # ------------------------------------------------
    schema = await tool_map["get_schema"].ainvoke({})

    # (Later we pass schema into LangChain prompt directly)
    print("Loaded Schema:", schema)

    # ------------------------------------------------
    # Existing LLM
    # ------------------------------------------------
    intent = parse_query(user_query)

    # ------------------------------------------------
    # SQL Build
    # ------------------------------------------------
    sql = generate_sql(intent)

    # ------------------------------------------------
    # Tool 2: Run SQL
    # ------------------------------------------------
    data = await tool_map["run_sql"].ainvoke({
        "sql": sql
    })

    # ------------------------------------------------
    # Dashboard
    # ------------------------------------------------
    dashboard = build_dashboard(intent, data)

    return {
        "intent": intent,
        "sql": sql,
        "data": data,
        "dashboard": dashboard
    }