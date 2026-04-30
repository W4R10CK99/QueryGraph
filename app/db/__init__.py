"""
app/db/__init__.py

Public API for the database package.
Import from here rather than from individual adapter files.
"""

from app.db.base import BaseDBAdapter
from app.db.factory import get_adapter

__all__ = ["BaseDBAdapter", "get_adapter"]