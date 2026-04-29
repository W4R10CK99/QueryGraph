from fastmcp import FastMCP
import sqlite3
import os

mcp = FastMCP("fastquery-tools")

DB_PATH = os.path.join("db", "sales.db")


# ---------------------------------------------------
# Tool 1: Health Check
# ---------------------------------------------------
@mcp.tool()
def health_check():
    return {
        "status": "ok",
        "server": "fastquery-tools"
    }


# ---------------------------------------------------
# Tool 2: Dynamic Schema
# ---------------------------------------------------
@mcp.tool()
def get_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        AND name NOT LIKE 'sqlite_%'
    """)

    tables = [row[0] for row in cursor.fetchall()]

    schema = {}

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = cursor.fetchall()

        schema[table] = [
            {
                "name": col[1],
                "type": col[2]
            }
            for col in cols
        ]

    conn.close()
    return schema


# ---------------------------------------------------
# Tool 3: Run SQL
# ---------------------------------------------------
@mcp.tool()
def run_sql(sql: str):
    if not sql.strip().lower().startswith("select"):
        return {"error": "Only SELECT queries allowed"}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute(sql)

    rows = cursor.fetchall()

    result = [dict(row) for row in rows]

    conn.close()

    return result


# ---------------------------------------------------
# Start Server
# ---------------------------------------------------
if __name__ == "__main__":
    mcp.run()