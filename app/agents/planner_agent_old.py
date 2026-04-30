import os
import json
import logging
from dotenv import load_dotenv
from typing import Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

logger = logging.getLogger(__name__)


llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.getenv("GEMINI_API_KEY")
)


def safe_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except:
        return {}


def plan_dashboard(user_query, schema):
    prompt = f"""
You are an elite BI dashboard planner.

Create dashboard widget plan from user query.

QUERY:
{user_query}

SCHEMA:
{json.dumps(schema)}

Return JSON:

{{
  "title": "",
  "widgets": [
    {{
      "type": "kpi_card|bar_chart|line_chart|pie_chart|table",
      "title": "",
      "metric": "sales",
      "group_by": [],
      "chart": "bar",
      "priority": 1
    }}
  ]
}}

Rules:
- overview => KPI + charts
- compare city => bar chart
- monthly trend => line chart
- category split => pie chart
- always include table last
- only JSON
"""

    response = llm.invoke(prompt)
    raw = response.content

    logger.info(raw)

    plan = safe_json(raw)

    if not plan:
        return {
            "title": "Dashboard",
            "widgets": [
                {
                    "type": "kpi_card",
                    "title": "Total Sales",
                    "metric": "sales",
                    "group_by": [],
                    "priority": 1
                }
            ]
        }

    plan["widgets"] = sorted(
        plan["widgets"],
        key=lambda x: x.get("priority", 999)
    )

    return plan