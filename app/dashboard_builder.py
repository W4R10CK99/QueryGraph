"""
dashboard_builder.py

FIX: In the original codebase this file was completely unused — the orchestrator
bypassed it entirely and mutated planner output directly.

This module's job is to take a planner widget spec + raw SQL data and produce
a clean, frontend-ready widget object. By centralising this logic here, the
orchestrator stays thin and the frontend contract stays consistent.
"""

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Widget type normalisation
#
# The planner can return type="bar_chart" or type="kpi_card" etc.
# The chart field can be "bar", "line", "pie".
# This function resolves both into a single canonical `type` for the frontend.
# ---------------------------------------------------------------------------
_CHART_FIELD_TO_TYPE = {
    "bar":  "bar_chart",
    "line": "line_chart",
    "pie":  "pie_chart",
}

_ALLOWED_TYPES = {"kpi_card", "bar_chart", "line_chart", "pie_chart", "table"}


def _resolve_widget_type(widget: dict) -> str:
    """
    Determines the canonical widget type from the planner's output.
    Handles the case where `type` and `chart` fields are inconsistent.
    """
    declared_type = widget.get("type", "bar_chart")

    if declared_type in _ALLOWED_TYPES:
        return declared_type

    # Fall back to the `chart` field if `type` is unrecognised
    chart = widget.get("chart", "bar")
    resolved = _CHART_FIELD_TO_TYPE.get(chart, "bar_chart")
    logger.warning(
        "Widget [%s] had unrecognised type %r; resolved to %r via chart field %r.",
        widget.get("id", "?"), declared_type, resolved, chart,
    )
    return resolved


# ---------------------------------------------------------------------------
# KPI value extraction
#
# For kpi_card widgets, the SQL result is a single-row aggregate.
# We extract the numeric value robustly.
# ---------------------------------------------------------------------------
def _extract_kpi_value(data: list, metric: str):
    """
    Given a SQL result like [{"sales": 98234.5}], returns 98234.5.
    Falls back to the first value of the first row if the metric key is absent.
    """
    if not data or not isinstance(data, list):
        return None

    row = data[0]
    if metric in row:
        return row[metric]

    # Fallback: first value of the row
    values = list(row.values())
    if values:
        logger.warning("KPI metric key %r not in row %s; using first value.", metric, row)
        return values[0]

    return None


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------
def build_widget(widget: dict) -> dict:
    """
    Takes a planner widget spec (with `data` already populated by the orchestrator)
    and returns a clean, frontend-ready widget dict.

    This is the only function the orchestrator should call from this module.
    """
    widget_type = _resolve_widget_type(widget)
    metric      = widget.get("metric", "value")
    data        = widget.get("data", [])
    group_by    = widget.get("group_by", [])
    title       = widget.get("title", "Widget")
    widget_id   = widget.get("id", "w?")
    error       = widget.get("error")

    base = {
        "id":    widget_id,
        "type":  widget_type,
        "title": title,
    }

    if error:
        base["error"] = error
        base["data"]  = []
        return base

    if widget_type == "kpi_card":
        base["value"] = _extract_kpi_value(data, metric)
        return base

    if widget_type == "table":
        base["data"] = data
        return base

    # Chart widgets (bar, line, pie)
    x_key = group_by[0] if group_by else None
    base.update({
        "x":    x_key,
        "y":    metric,
        "data": data,
    })

    return base


def build_dashboard(plan: dict) -> dict:
    """
    Processes all widgets in a dashboard plan and returns a frontend-ready
    dashboard object. Call this after the orchestrator has populated `data`
    on each widget.
    """
    built_widgets = [build_widget(w) for w in plan.get("widgets", [])]

    return {
        "title":   plan.get("title", "Dashboard"),
        "widgets": built_widgets,
    }