def build_dashboard(intent, data):
    widgets = []

    group_by = intent.get("group_by", [])
    metric = intent.get("metric", "sales")
    chart = intent.get("chart", "bar")

    meta = intent.get("dashboard_meta", {})

    dashboard_title = meta.get("title", "Dashboard")
    chart_title = meta.get("chart_title", f"{metric.title()} Chart")
    table_title = meta.get("table_title", "Detailed Data")
    kpi_title = meta.get("kpi_title", f"Total {metric.title()}")

    # ------------------------------------------------
    # KPI ONLY
    # ------------------------------------------------
    if not group_by and len(data) == 1:
        first_row = data[0]
        value = list(first_row.values())[0]

        widgets.append({
            "type": "kpi_card",
            "title": kpi_title,
            "value": value
        })

        return {
            "title": dashboard_title,
            "widgets": widgets
        }

    # ------------------------------------------------
    # Grouped Chart
    # ------------------------------------------------
    if group_by:
        x = group_by[0]
        y = metric

        widget_type = "bar_chart"

        if chart == "line":
            widget_type = "line_chart"

        widgets.append({
            "type": widget_type,
            "title": chart_title,
            "x": x,
            "y": y,
            "data": data
        })

    # ------------------------------------------------
    # Table
    # ------------------------------------------------
    widgets.append({
        "type": "table",
        "title": table_title,
        "data": data
    })

    return {
        "title": dashboard_title,
        "widgets": widgets
    }