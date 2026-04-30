"""
app/query_builder.py

Generates a query string from a widget intent dict.

For SQL databases  → returns a SQL SELECT string.
For MongoDB        → returns a JSON aggregation pipeline string.

The MCP server / orchestrator always calls generate_query(intent) and passes
the result verbatim to adapter.run_query() — it never needs to know which
database is active.
"""

import re
import json
import logging

from app.config import settings, DBType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identifier / value safety (SQL only)
# ---------------------------------------------------------------------------

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALLOWED_OPERATIONS = {"sum", "count", "avg", "min", "max"}
SORT_DIRECTION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]* (ASC|DESC)$", re.IGNORECASE)


def _safe_id(value: str, label: str) -> str:
    if not SAFE_IDENTIFIER.match(value):
        raise ValueError(f"Unsafe {label} identifier rejected: {value!r}")
    return value


def _safe_op(op: str) -> str:
    op = op.lower().strip()
    if op not in ALLOWED_OPERATIONS:
        raise ValueError(f"Disallowed operation: {op!r}")
    return op


def _quote(value) -> str:
    if isinstance(value, str):
        return f"'{value.replace(chr(39), chr(39)*2)}'"
    if isinstance(value, (int, float)):
        return str(value)
    raise ValueError(f"Unsupported filter value type: {type(value)}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_query(intent: dict) -> str:
    """
    Returns a query string appropriate for the configured database.
    The caller does not need to know which engine is active.
    """
    if settings.db_type == DBType.MONGODB:
        return _build_mongo_query(intent)
    return _build_sql_query(intent)


# Keep old name as an alias so existing orchestrator code doesn't break
generate_sql = generate_query


# ---------------------------------------------------------------------------
# SQL generator  (SQLite / PostgreSQL / MySQL)
# ---------------------------------------------------------------------------

def _build_sql_query(intent: dict) -> str:
    table     = _safe_id(intent.get("table", "sales"), "table")
    metric    = _safe_id(intent["metric"], "metric")
    operation = _safe_op(intent.get("operation", "sum"))
    group_by  = [_safe_id(c, "group_by") for c in intent.get("group_by", [])]
    filters   = intent.get("filters") or {}
    limit     = intent.get("limit")
    sort      = intent.get("sort")

    # SELECT
    parts = list(group_by) + [f"{operation.upper()}({metric}) AS {metric}"]
    sql = f"SELECT {', '.join(parts)} FROM {table}"

    # WHERE
    conditions = [f"{_safe_id(k, 'filter col')} = {_quote(v)}" for k, v in filters.items()]
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    # GROUP BY
    if group_by:
        sql += " GROUP BY " + ", ".join(group_by)

    # ORDER BY
    if sort:
        sort = sort.strip()
        if SORT_DIRECTION.match(sort):
            sql += f" ORDER BY {sort}"
        else:
            logger.warning("Unsafe sort value ignored: %r", sort)

    # LIMIT
    if limit is not None:
        try:
            sql += f" LIMIT {int(limit)}"
        except (TypeError, ValueError):
            logger.warning("Non-integer limit ignored: %r", limit)

    logger.debug("Generated SQL: %s", sql)
    return sql


# ---------------------------------------------------------------------------
# MongoDB aggregation pipeline generator
# ---------------------------------------------------------------------------

# Maps SQL-style operation names → MongoDB accumulator operators
_MONGO_ACCUMULATORS = {
    "sum":   "$sum",
    "count": "$sum",   # COUNT(*) ≈ $sum: 1
    "avg":   "$avg",
    "min":   "$min",
    "max":   "$max",
}


def _build_mongo_query(intent: dict) -> str:
    """
    Builds a MongoDB aggregation pipeline and returns it as a JSON string.

    Return shape:
        {
            "collection": "<table value from intent>",
            "pipeline":   [ <stage>, ... ]
        }
    """
    collection = intent.get("table", "sales")
    metric     = intent["metric"]
    operation  = intent.get("operation", "sum").lower()
    group_by   = intent.get("group_by", []) or []
    filters    = intent.get("filters") or {}
    limit      = intent.get("limit")
    sort_str   = intent.get("sort")   # e.g. "sales DESC"

    pipeline = []

    # Stage 1: $match  (WHERE equivalent)
    if filters:
        pipeline.append({"$match": filters})

    # Stage 2: $group  (GROUP BY + aggregate)
    accumulator = _MONGO_ACCUMULATORS.get(operation, "$sum")
    accum_value = 1 if operation == "count" else f"${metric}"

    if group_by:
        group_id = {field: f"${field}" for field in group_by}
    else:
        group_id = None   # single global aggregate

    group_stage = {
        "_id":  group_id,
        metric: {accumulator: accum_value},
    }
    # Carry group-by fields forward as top-level keys
    for field in group_by:
        group_stage[field] = {"$first": f"${field}"}

    pipeline.append({"$group": group_stage})

    # Stage 3: $sort   (ORDER BY equivalent)
    sort_doc = {}
    if sort_str:
        parts = sort_str.strip().split()
        if len(parts) == 2:
            col, direction = parts
            sort_doc[col] = -1 if direction.upper() == "DESC" else 1
    if not sort_doc and group_by:
        # Default: sort by metric descending
        sort_doc[metric] = -1
    if sort_doc:
        pipeline.append({"$sort": sort_doc})

    # Stage 4: $limit
    if limit is not None:
        try:
            pipeline.append({"$limit": int(limit)})
        except (TypeError, ValueError):
            logger.warning("Non-integer limit ignored: %r", limit)

    payload = {"collection": collection, "pipeline": pipeline}
    logger.debug("Generated Mongo pipeline: %s", payload)
    return json.dumps(payload)