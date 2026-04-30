import os
import json
import logging
import asyncio
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM — lazy init so missing API key fails at call time, not import time
# ---------------------------------------------------------------------------
_llm = None

def _get_llm():
    global _llm
    if _llm is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set in environment.")
        _llm = ChatGoogleGenerativeAI(
            # FIX: "gemini-3-flash-preview" does not exist.
            # Use "gemini-1.5-flash" (stable) or "gemini-2.0-flash" (latest preview).
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=api_key,
        )
    return _llm


# ---------------------------------------------------------------------------
# Safe JSON parser — logs the error instead of silently discarding it
# ---------------------------------------------------------------------------
def safe_json(text: str) -> dict:
    try:
        cleaned = text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("safe_json parse failure: %s\nRaw text:\n%s", e, text[:500])
        return {}


# ---------------------------------------------------------------------------
# Dashboard planner
#
# KEY FIX: The prompt now asks the LLM to return `table`, `operation`,
# `filters`, `limit`, and `sort` in each widget. Without these fields, the
# orchestrator was silently defaulting everything to "sum", "sales", empty
# filters, and no limit — making the SQL output identical for every widget.
# ---------------------------------------------------------------------------
def plan_dashboard(user_query: str, schema: dict) -> dict:
    """
    Returns a dashboard plan — a dict with `title` and `widgets` list.
    Each widget is fully self-describing so the orchestrator can build SQL
    without guessing defaults.
    """
    prompt = f"""
You are an expert BI dashboard planner. Given a user query and a database schema,
produce a JSON dashboard layout that tells the frontend exactly what to render
and tells the backend exactly how to fetch data for each tile.

USER QUERY:
{user_query}

DATABASE SCHEMA:
{json.dumps(schema, indent=2)}

Return ONLY a JSON object — no markdown fences, no explanation:

{{
  "title": "<descriptive dashboard title>",
  "widgets": [
    {{
      "id": "w1",
      "type": "kpi_card | bar_chart | line_chart | pie_chart | table",
      "title": "<human-readable widget title>",
      "table": "<table name from schema>",
      "metric": "<numeric column to aggregate>",
      "operation": "sum | count | avg | min | max",
      "group_by": ["<column>"],
      "filters": {{"<column>": "<value>"}},
      "sort": "<column> ASC | <column> DESC | null",
      "limit": <integer or null>,
      "chart": "bar | line | pie",
      "priority": <1=top-left, ascending>
    }}
  ]
}}

RULES — follow strictly:
- Use only table/column names that exist in the provided schema.
- "overview" or "summary" queries → start with 1-2 KPI cards, then charts.
- "compare <dimension>" → bar_chart grouped by that dimension.
- "trend over time / monthly" → line_chart grouped by the time column.
- "breakdown / split by category" → pie_chart.
- Always end with a table widget showing raw data (no group_by, reasonable limit).
- For KPI cards: no group_by, operation is usually sum or count.
- For pie_chart: group_by exactly one dimension, limit ≤ 10.
- `filters` must be an object, never null — use {{}} if no filters.
- `group_by` must be a list, never null — use [] if no grouping.
- `sort` for charts: sort by the metric DESC so top items show first.
- Assign sequential unique `id` values (w1, w2, …).
- Return only JSON. No markdown. No extra keys.
"""

    try:
        response = _get_llm().invoke(prompt)
        raw = response.content
        logger.debug("Planner raw response:\n%s", raw)

        plan = safe_json(raw)
        if not plan or "widgets" not in plan:
            raise ValueError("LLM returned empty or malformed plan.")

    except Exception as e:
        logger.error("plan_dashboard failed: %s", e)
        # Minimal fallback so the pipeline doesn't crash
        plan = {
            "title": "Dashboard",
            "widgets": [
                {
                    "id": "w1",
                    "type": "kpi_card",
                    "title": "Total Sales",
                    "table": _infer_first_table(schema),
                    "metric": "sales",
                    "operation": "sum",
                    "group_by": [],
                    "filters": {},
                    "sort": None,
                    "limit": None,
                    "chart": "bar",
                    "priority": 1,
                }
            ],
        }

    # Ensure required fields have safe defaults on every widget
    for i, w in enumerate(plan.get("widgets", [])):
        w.setdefault("id", f"w{i+1}")
        w.setdefault("operation", "sum")
        w.setdefault("filters", {})
        w.setdefault("group_by", [])
        w.setdefault("sort", None)
        w.setdefault("limit", None)
        w.setdefault("table", _infer_first_table(schema))

    plan["widgets"] = sorted(
        plan["widgets"], key=lambda x: x.get("priority", 999)
    )

    return plan


def _infer_first_table(schema: dict) -> str:
    """Best-effort: return the first table name from the schema dict."""
    if isinstance(schema, dict):
        tables = list(schema.keys())
        if tables:
            return tables[0]
    return "sales"


# ---------------------------------------------------------------------------
# Async wrapper — call this from the async orchestrator so it doesn't block
# the FastAPI event loop (plan_dashboard is a sync/blocking LLM call).
# ---------------------------------------------------------------------------
async def plan_dashboard_async(user_query: str, schema: dict) -> dict:
    return await asyncio.to_thread(plan_dashboard, user_query, schema)