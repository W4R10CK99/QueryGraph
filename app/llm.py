import os
import json
import logging
from dotenv import load_dotenv
from google import genai
from schema_tool import get_schema

# ---------------------------------------------------
# Logging
# ---------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------
# ENV + Gemini Client
# ---------------------------------------------------
load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

logger.info("Gemini client initialized.")


# ---------------------------------------------------
# Build Dynamic Schema Prompt
# ---------------------------------------------------
def build_schema_prompt():
    schema = get_schema()

    lines = []

    for table_name, columns in schema.items():
        lines.append(f"Table: {table_name}")

        for col in columns:
            lines.append(f"- {col['name']} ({col['type']})")

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------
# Normalize Intent
# ---------------------------------------------------
def normalize_intent(raw):
    logger.info(f"Raw Parsed JSON: {raw}")

    group_by = (
        raw.get("group_by")
        or raw.get("grouping")
        or raw.get("dimensions")
        or []
    )

    if isinstance(group_by, str):
        group_by = [group_by]

    metric = raw.get("metric", "sales")

    # synonym cleanup
    if metric.lower() in ["revenue", "income", "earnings", "earning"]:
        metric = "sales"

    operation = raw.get("operation", "sum").lower()

    if operation not in ["sum", "avg", "count", "max", "min"]:
        operation = "sum"

    limit = raw.get("limit")
    sort = raw.get("sort")

    if limit and not sort:
        sort = f"{metric} DESC"

    chart = (
        raw.get("chart")
        or raw.get("chart_type")
        or "bar"
    )

    dashboard_meta = raw.get("dashboard_meta", {})

    normalized = {
        "metric": metric,
        "group_by": group_by,
        "filters": raw.get("filters", {}),
        "operation": operation,
        "limit": limit,
        "sort": sort,
        "chart": chart,
        "dashboard_meta": {
            "title": dashboard_meta.get("title"),
            "subtitle": dashboard_meta.get("subtitle"),
            "chart_title": dashboard_meta.get("chart_title"),
            "table_title": dashboard_meta.get("table_title"),
            "kpi_title": dashboard_meta.get("kpi_title")
        }
    }

    logger.info(f"Normalized Intent: {normalized}")

    return normalized


# ---------------------------------------------------
# Parse Query
# ---------------------------------------------------
def parse_query(user_query):
    logger.info("=" * 60)
    logger.info(f"Incoming Query: {user_query}")

    schema_text = build_schema_prompt()

    prompt = f"""
You are an analytics query understanding engine.

Your task:
Convert the user analytics request into STRICT JSON.

LIVE DATABASE SCHEMA:
{schema_text}

Return this exact JSON structure:

{{
  "metric": "sales",
  "group_by": [],
  "filters": {{}},
  "operation": "sum",
  "limit": null,
  "sort": null,
  "chart": "bar",
  "dashboard_meta": {{
    "title": "",
    "subtitle": "",
    "chart_title": "",
    "table_title": "",
    "kpi_title": ""
  }}
}}

RULES:

1. Use ONLY columns available in schema.
2. revenue / income / earnings = sales
3. If query says top 5 products:
   group_by = ["product"]
   limit = 5
   sort = "sales DESC"

4. If query says compare sales by city:
   group_by = ["city"]

5. If query says monthly sales:
   group_by = ["month"]
   chart = "line"

6. If no grouping:
   chart = "kpi"

7. dashboard_meta titles must be human-friendly and based on user query.

Examples:

User: total revenue city wise
title: Total Revenue by City

User: top 5 products
title: Top 5 Products by Sales

User: monthly sales
title: Monthly Sales Trend

8. Return ONLY JSON
9. No markdown
10. No explanation

USER QUERY:
{user_query}
"""

    logger.info("Sending prompt to Gemini...")

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt
    )

    text = response.text.strip()

    logger.info(f"Raw Gemini Response: {text}")

    # remove fences if model adds them
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        raw = json.loads(text)
        logger.info("JSON parsing successful.")
    except Exception as e:
        logger.error(f"JSON parse failed: {str(e)}")

        raw = {
            "metric": "sales",
            "group_by": [],
            "filters": {},
            "operation": "sum",
            "limit": None,
            "sort": None,
            "chart": "bar",
            "dashboard_meta": {
                "title": "Analytics Dashboard",
                "subtitle": "",
                "chart_title": "Chart",
                "table_title": "Detailed Data",
                "kpi_title": "Total Sales"
            }
        }

    return normalize_intent(raw)