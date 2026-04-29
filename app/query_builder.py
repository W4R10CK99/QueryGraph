def generate_sql(intent):
    metric = intent["metric"]
    group_by = intent["group_by"]
    filters = intent["filters"]
    operation = intent["operation"]
    limit = intent["limit"]
    sort = intent["sort"]

    sql = "SELECT "

    if group_by:
        sql += ", ".join(group_by) + ", "

    sql += f"{operation.upper()}({metric}) as {metric} "

    sql += "FROM sales"

    conditions = []

    for key, value in filters.items():
        if isinstance(value, str):
            conditions.append(f"{key}='{value}'")
        else:
            conditions.append(f"{key}={value}")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    if group_by:
        sql += " GROUP BY " + ", ".join(group_by)

    if sort:
        sql += f" ORDER BY {sort}"

    if limit:
        sql += f" LIMIT {limit}"

    return sql