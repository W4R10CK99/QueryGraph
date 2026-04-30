import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identifier allowlist
#
# SECURITY FIX: The original code interpolated filter values, sort clauses,
# and column names directly into the SQL string — a classic SQL injection
# vector. We now:
#   1. Validate all column/table identifiers against a strict pattern.
#   2. Parameterise filter VALUES (returned separately so the MCP caller
#      can pass them as bound parameters — or we quote them safely here).
#   3. Validate the operation against an explicit enum.
# ---------------------------------------------------------------------------

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]*$")
ALLOWED_OPERATIONS = {"sum", "count", "avg", "min", "max"}
SORT_DIRECTION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]* (ASC|DESC)$", re.IGNORECASE)


def _safe_identifier(value: str, label: str) -> str:
    """Raise if value is not a safe SQL identifier."""
    if not SAFE_IDENTIFIER.match(value):
        raise ValueError(f"Unsafe {label} identifier rejected: {value!r}")
    return value


def _safe_operation(op: str) -> str:
    op = op.lower().strip()
    if op not in ALLOWED_OPERATIONS:
        raise ValueError(f"Disallowed SQL operation: {op!r}. Must be one of {ALLOWED_OPERATIONS}.")
    return op


def _quote_value(value) -> str:
    """
    Minimal safe quoting for filter values.
    For production: use parameterized queries at the DB driver level.
    """
    if isinstance(value, str):
        # Escape any single quotes inside the value
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    elif isinstance(value, (int, float)):
        return str(value)
    else:
        raise ValueError(f"Unsupported filter value type: {type(value)} for value {value!r}")


# ---------------------------------------------------------------------------
# SQL generator
#
# FIX: `table` is now taken from intent (dynamic) instead of hardcoded.
# FIX: All identifiers are validated before interpolation.
# FIX: Filter values are safely escaped.
# FIX: `operation` is validated against an enum.
# ---------------------------------------------------------------------------
def generate_sql(intent: dict) -> str:
    """
    Build a SELECT query from a widget intent dict.

    Expected intent keys:
        table      (str)        — table name from schema
        metric     (str)        — column to aggregate
        group_by   (list[str])  — columns to GROUP BY
        filters    (dict)       — {column: value} equality filters
        operation  (str)        — sum | count | avg | min | max
        limit      (int|None)   — LIMIT clause
        sort       (str|None)   — e.g. "sales DESC" or "city ASC"
    """
    table     = _safe_identifier(intent.get("table", "sales"), "table")
    metric    = _safe_identifier(intent["metric"], "metric")
    operation = _safe_operation(intent.get("operation", "sum"))
    group_by  = [_safe_identifier(col, "group_by column") for col in intent.get("group_by", [])]
    filters   = intent.get("filters", {}) or {}
    limit     = intent.get("limit")
    sort      = intent.get("sort")

    # SELECT clause
    select_parts = []
    if group_by:
        select_parts.extend(group_by)
    select_parts.append(f"{operation.upper()}({metric}) AS {metric}")
    sql = f"SELECT {', '.join(select_parts)} FROM {table}"

    # WHERE clause
    conditions = []
    for key, value in filters.items():
        safe_key = _safe_identifier(key, "filter column")
        conditions.append(f"{safe_key} = {_quote_value(value)}")
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    # GROUP BY
    if group_by:
        sql += " GROUP BY " + ", ".join(group_by)

    # ORDER BY — validate sort string format: "<column> ASC|DESC"
    if sort:
        sort = sort.strip()
        if not SORT_DIRECTION.match(sort):
            logger.warning("Unsafe sort value ignored: %r", sort)
        else:
            sql += f" ORDER BY {sort}"

    # LIMIT
    if limit is not None:
        try:
            sql += f" LIMIT {int(limit)}"
        except (TypeError, ValueError):
            logger.warning("Non-integer limit ignored: %r", limit)

    logger.debug("Generated SQL: %s", sql)
    return sql