"""
app/db/base.py

Abstract base class that every database adapter must implement.

The contract is deliberately minimal — two async methods:
    get_schema()  → dict   (what tables/collections + columns exist)
    run_query()   → list   (execute a query, return rows as dicts)

For SQL databases, `run_query` accepts a SQL string.
For MongoDB,     `run_query` accepts a JSON aggregation pipeline string
                 (see mongo_adapter.py for the expected format).

This interface is what the MCP server talks to — it never touches a
specific database driver directly.
"""

from abc import ABC, abstractmethod


class BaseDBAdapter(ABC):

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect(self) -> None:
        """
        Open connection / acquire pool.
        Called once at application startup.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection / release pool.
        Called at application shutdown.
        """

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_schema(self) -> dict:
        """
        Return the schema of all accessible tables or collections.

        SQL return format:
            {
                "orders": {
                    "columns": [
                        {"name": "id",     "type": "INTEGER"},
                        {"name": "sales",  "type": "REAL"},
                        {"name": "region", "type": "TEXT"}
                    ]
                },
                "products": { ... }
            }

        MongoDB return format (same shape, using collection/field names):
            {
                "orders": {
                    "columns": [
                        {"name": "sales",  "type": "number"},
                        {"name": "region", "type": "string"}
                    ]
                }
            }
        """

    @abstractmethod
    async def run_query(self, query: str) -> list[dict]:
        """
        Execute a query and return results as a list of dicts.

        SQL adapters   : `query` is a SQL SELECT string.
        MongoDB adapter: `query` is a JSON string with the shape:
            {
                "collection": "orders",
                "pipeline": [ { "$group": { ... } }, ... ]
            }

        Returns rows/documents as [{"column": value, ...}, ...].
        Raises RuntimeError on query failure.
        """

    # ------------------------------------------------------------------
    # Optional helpers (adapters may override)
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """
        Returns True if the database is reachable.
        Default implementation runs a trivial query.
        Adapters may override for a cheaper check.
        """
        try:
            await self.run_query(self._health_query())
            return True
        except Exception:
            return False

    def _health_query(self) -> str:
        """Trivial query used by the default health_check."""
        return "SELECT 1"